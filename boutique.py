# -*- coding: utf-8 -*-
"""Commande -> paiement (Stripe) -> fabrication du livre -> relecture -> impression (Lulu) -> suivi.
Abonnements : mensuel (Stripe facture chaque mois, un livre à chaque facture payée) ou livres de fête (6 livres, chacun lancé
35 jours avant une fête choisie par la famille, anniversaire compris ; payés en 12 mensualités).
Aucun appel OpenAI avant le paiement. Aucune impression sans ton accord (sauf AUTO_IMPRESSION=1)."""
import os, re, json, time, uuid, shutil, secrets, threading, traceback
from pathlib import Path
from xml.sax.saxutils import escape
from flask import Blueprint, request, jsonify, send_file, abort, redirect, Response
import commandes as db, paiement, lulu
import budget, procede, fabrication
import calendrier, coloriage
EXTRAS = {"calendrier": calendrier, "coloriage": coloriage}      # produits qui ne sont pas des livres
NOMS_EXTRAS = {"calendrier": "le calendrier", "coloriage": "le cahier de coloriage"}


def produit_de(folder):
    """Module du produit fabriqué dans ce dossier (calendrier, coloriage), ou None pour un livre."""
    return next((m for k, m in EXTRAS.items() if (Path(folder) / f"{k}.json").exists()), None)


def pages_extra(formule, folder):
    return calendrier.PAGES if formule == "calendrier" else coloriage.pages_impression(folder)

bp = Blueprint("boutique", __name__)
A = None                      # module app (injecté par setup)
STORE = db.DATA / "commandes"; STORE.mkdir(exist_ok=True)
MOIS = 30 * 86400
THEMES = ["La peur du noir", "La rentrée à l'école", "Apprendre à partager", "Oser se faire des amis", "La confiance en soi",
          "Gérer la colère", "Une aventure pour rire", "La patience", "Prendre soin de la nature", "Dire la vérité",
          "Essayer quelque chose de nouveau", "Aider les autres"]
import univers as U
UNIVERS = U.NOMS                                  # univers hors fêtes (rotation de l'abonnement)
PAYS = {"FR", "BE", "LU", "CH", "MC"}
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}$", re.I)


def setup(app_module):
    global A
    A = app_module
    threading.Thread(target=_scheduler, daemon=True).start()
    threading.Thread(target=_resume, daemon=True).start()


def _resume():
    """Après un redémarrage du serveur (mise à jour en ligne), les livres payés dont la fabrication a été coupée repartent seuls."""
    time.sleep(10)
    for o in db.lister(500):
        if o["statut"] in ("payee", "generation") and not A.JOBS.get(o["job_id"] or ""):
            if (o.get("tentatives") or 0) >= 3:            # garde-fou : jamais de boucle de relances qui coûte
                db.update(o["id"], statut="erreur", erreur="Fabrication interrompue 3 fois : relance-la à la main depuis l'admin")
                continue
            folder = A.OUT / (o["job_id"] or o["id"])
            if folder.exists() and procede.verrou_libre(folder):
                n = budget.orphelines_vers_incertain(procede.livre_id(folder))
                if n:                                  # appel coupé en plein vol : jamais renvoyé à l'aveugle
                    db.update(o["id"], statut="erreur", erreur=f"{n} appel(s) API au résultat incertain après redémarrage : "
                              "vérifie l'usage OpenAI et règle-les dans l'admin avant de relancer")
                    continue
            log(f"commande {o['id']} : fabrication interrompue, relance")
            try:
                start_book(o["id"], auto=True, reprise=True)   # reprend là où elle s'était arrêtée (rien n'est payé deux fois)
            except Exception:
                traceback.print_exc()


def auto_print():
    return os.getenv("AUTO_IMPRESSION", "") == "1"


def base_url():
    return (os.getenv("PUBLIC_URL") or request.host_url).rstrip("/")


def log(msg):
    print(time.strftime("[%d/%m %H:%M] "), msg, flush=True)


# ------------------------------------------------------------------ commande
def parse_address(a):
    a = {k: str((a or {}).get(k, "")).strip()[:120] for k in ("nom", "adresse1", "adresse2", "code_postal", "ville", "pays", "telephone")}
    a["pays"] = (a["pays"] or "FR").upper()
    miss = [k for k in ("nom", "adresse1", "code_postal", "ville", "telephone") if not a[k]]
    if miss:
        return None, "Adresse de livraison incomplète : " + ", ".join(miss).replace("_", " ")
    if a["pays"] not in PAYS:
        return None, "Livraison possible en France, Belgique, Luxembourg, Suisse et Monaco."
    if len(re.sub(r"\D", "", a["telephone"])) < 9:
        return None, "Numéro de téléphone invalide (demandé par le transporteur)."
    return a, None


@bp.post("/api/commandes")
def order_create():
    data = request.get_json(force=True, silent=True) or {}
    form, err = A.parse_book(data)
    if err:
        return jsonify(erreur=err), 400
    form.pop("demo", None); form.pop("code", None)
    c = data.get("commande") or {}
    formule = c.get("formule")
    if formule not in paiement.FORMULES:
        return jsonify(erreur="Choisis une formule."), 400
    email = str(c.get("email", "")).strip()[:190]
    if not EMAIL.match(email):
        return jsonify(erreur="Adresse e-mail invalide."), 400
    addr, err = parse_address(c.get("adresse"))
    if err:
        return jsonify(erreur=err), 400
    if c.get("cgv") is not True:
        return jsonify(erreur="Merci d'accepter les conditions générales de vente."), 400
    fetes = [x for x in (form.get("fetes") or "").split(",") if x in U.PAR_CLE and U.PAR_CLE[x].get("fete")]
    form["fetes"] = ",".join(fetes)
    if formule == "fetes" and len(fetes) != 6:
        return jsonify(erreur="Choisissez 6 fêtes pour la formule « 6 livres de fête »."), 400
    k = c.get("cadeau") if isinstance(c.get("cadeau"), dict) else None   # livre offert : de la part de, petit mot
    form["formule"] = formule
    if k and k.get("actif"):
        clean = lambda v, n: re.sub(r"\s+", " ", str(v or "")).strip()[:n]
        form["cadeau_de"], form["cadeau_message"] = clean(k.get("de"), 40), clean(k.get("message"), 160)
    if "anniversaire" in fetes and not re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", form.get("anniversaire") or ""):
        if formule == "fetes":
            return jsonify(erreur="Indiquez la date d'anniversaire de l'enfant, ou choisissez une autre fête."), 400
        fetes.remove("anniversaire"); form["fetes"] = ",".join(fetes)         # date facultative : pas de livre d'anniversaire
    cal = c.get("calendrier") if isinstance(c.get("calendrier"), dict) else {}
    avec_cal = formule == "calendrier" or bool(cal.get("actif"))           # calendrier seul, ou ajouté aux livres
    if avec_cal:
        import datetime
        debut = str(cal.get("debut") or calendrier.debut_par_defaut())
        if debut not in calendrier.debuts_possibles():
            return jsonify(erreur="Choisissez le premier mois du calendrier."), 400
        form["calendrier"] = {"debut": debut, "dates": calendrier.nettoyer_dates(cal.get("dates")), "pays": addr["pays"],
                              "commande_le": datetime.date.today().isoformat()}
    colo = c.get("coloriage") if isinstance(c.get("coloriage"), dict) else {}
    avec_colo = formule == "coloriage" or bool(colo.get("actif"))          # cahier de coloriage seul, ou ajouté
    if avec_colo:
        pages = [x for x in (colo.get("pages") or []) if isinstance(x, str)]
        if formule == "coloriage" and len([x for x in dict.fromkeys(pages) if x in coloriage.PAR_CLE]) < coloriage.NB_PAGES:
            return jsonify(erreur=f"Choisissez les {coloriage.NB_PAGES} pages du cahier de coloriage (ou complétez au hasard)."), 400
        form["coloriage"] = {"pages": coloriage.choisir(pages)}

    oid = uuid.uuid4().hex[:12]
    folder = STORE / oid; folder.mkdir(parents=True)
    guides = A.save_avatar_pngs(data.get("avatar_png") or {}, folder)
    previews = A.save_previews(data.get("apercus") or {}, folder)
    (folder / "livre.json").write_text(json.dumps({"form": form, "guides": {k: p.name for k, p in guides.items()},
                                                   "apercus": {k: p.name for k, p in previews.items()}}, ensure_ascii=False), encoding="utf-8")
    db.create(id=oid, formule=formule, email=email, adresse=addr, statut="attente_paiement",
              montant=paiement.total(formule, addr.get("pays"), calendrier=avec_cal, coloriage=avec_colo), origine=oid,
              numero=0 if formule in EXTRAS else 1)
    if not paiement.configured():
        return jsonify(id=oid, url=f"/creer?commande={oid}&test=1")
    try:
        sid, url = paiement.checkout(oid, formule, email, base_url(), pays=addr.get("pays"), calendrier=paiement.avec_calendrier(formule, avec_cal),
                                     coloriage=avec_colo and formule != "coloriage")
    except paiement.StripeError as e:
        db.update(oid, statut="erreur", erreur=str(e))
        return jsonify(erreur=str(e)), 502
    db.update(oid, stripe_session=sid)
    return jsonify(id=oid, url=url)


def load_book(origin):
    """Données du livre enregistrées à la commande (formulaire + références visuelles du navigateur)."""
    folder = STORE / origin
    d = json.loads((folder / "livre.json").read_text(encoding="utf-8"))
    guides = {k: folder / v for k, v in d["guides"].items() if (folder / v).exists()}
    previews = {k: folder / v for k, v in d["apercus"].items() if (folder / v).exists()}
    return d["form"], A.browser_refs(guides, previews)


def confirm_paid(oid, stripe_sub=None):
    """Paiement reçu (une seule fois, même avec un double webhook) : toutes les commandes du pack sont créées et lancées.
    Les livres sont fabriqués, relus, puis partent ensemble dans un seul colis."""
    if not db.transition(oid, "attente_paiement", "payee", stripe_sub=stripe_sub):
        return False
    o = db.get(oid)
    log(f"commande {oid} payée ({o['formule']})")
    for b in creer_pack(oid):
        start_book(b, auto=True)
    return True


def livres_du_pack(origine):
    """Livres d'une même commande (hors essais et hors calendrier), dans l'ordre des numéros."""
    return sorted([x for x in db.lister(1000) if x["origine"] == origine and not (x["formule"] or "").startswith("essai")
                   and x["formule"] not in EXTRAS], key=lambda x: x["numero"] or 1)


def extras_du_pack(origine):
    """Calendrier, cahier de coloriage de la commande : ils partent dans le même colis que les livres."""
    return sorted([x for x in db.lister(1000) if x["origine"] == origine and x["formule"] in EXTRAS], key=lambda x: x["formule"])


calendriers_du_pack = extras_du_pack


def creer_pack(oid):
    """Crée les livres 2..N du pack (une fois) et attribue leurs numéros de collection dans l'ordre. Renvoie les ids à fabriquer."""
    o = db.get(oid)
    form, _ = load_book(oid)
    if o["formule"] in EXTRAS:                                   # calendrier ou cahier seul : la commande est le produit
        ids = [oid]
        for k in EXTRAS:                                         # … et l'autre produit éventuellement ajouté
            if form.get(k) and k != o["formule"]:
                cid = f"{oid}-{k[:3]}"
                if not db.get(cid):
                    db.create(id=cid, formule=k, email=o["email"], adresse=o["adresse"], statut="payee", montant=0, origine=oid, numero=0)
                ids.append(cid)
        return ids
    f = paiement.FORMULES.get(o["formule"]) or {"livres": 1}
    n = f["livres"]
    form, _ = load_book(oid)
    fetes = [c for c in (form.get("fetes") or "").split(",") if c in U.PAR_CLE]
    if o["formule"] == "fetes" and fetes:                         # un livre par fête choisie, dans l'ordre du calendrier
        import datetime
        auj = datetime.date.today()
        def prochaine(c):
            try:
                ds = [d for d in U.dates_fete(c, anniv=form.get("anniversaire")) if d >= auj]
                return min(ds) if ds else datetime.date.max
            except Exception:
                return datetime.date.max
        fetes = sorted(fetes, key=prochaine)
        db.update(oid, univers=U.PAR_CLE[fetes[0]]["nom"])
    ids = [oid]
    existants = {x["numero"]: x["id"] for x in livres_du_pack(oid)}
    for k in range(2, n + 1):
        if k in existants:
            ids.append(existants[k]); continue
        cid = f"{oid}-{k:02d}"
        univers = U.PAR_CLE[fetes[k - 1]]["nom"] if o["formule"] == "fetes" and len(fetes) >= k else None
        db.create(id=cid, formule=o["formule"], email=o["email"], adresse=o["adresse"], statut="payee", montant=0,
                  origine=oid, numero=k, univers=univers)
        ids.append(cid)
    for cid in ids:                                              # numéros de collection 1, 2, 3… dans l'ordre du pack
        db.assign_volume(cid)
    for k in EXTRAS:                                             # calendrier / cahier ajouté aux livres : même colis
        if form.get(k):
            cid = f"{oid}-{k[:3]}"
            if not db.get(cid):
                db.create(id=cid, formule=k, email=o["email"], adresse=o["adresse"], statut="payee", montant=0, origine=oid, numero=0)
            ids.append(cid)
    return ids


def check_fetes(s, jour=None):
    """Pack fêtes : lance le livre de chaque fête qui approche (une seule fois par fête et par an), dans la limite du pack."""
    if not s or s["formule"] != "fetes" or s["statut"] != "actif":
        return []
    form, _ = load_book(s["commande_origine"])
    cles = [c for c in (form.get("fetes") or "").split(",") if c in U.PAR_CLE]
    faites = json.loads(s.get("faites") or "[]")
    lances = []
    for k, nom, d in U.fetes_dues(cles, faites, jour=jour, anniv=form.get("anniversaire")):
        s = db.sub_get(s["id"])
        if (s["livres_restants"] or 0) <= 0:
            break
        faites.append(k)
        db.sub_update(s["id"], faites=json.dumps(faites))
        lances.append(next_book(s, univers=nom))
    return lances


_start_lock = threading.Lock()


def start_book(oid, auto=False, reprise=False):
    with _start_lock:                             # vérification + lancement d'un seul tenant (requêtes simultanées)
        return _start_book(oid, auto, reprise)


def _start_book(oid, auto=False, reprise=False):
    o = db.get(oid)
    if A.JOBS.get(o["job_id"] or "", {}).get("etat") in ("en_cours", "validation"):
        return False                              # double clic / double webhook : un seul travail par livre
    if o["job_id"] and fabrication.est_finalise(A.OUT / o["job_id"]):
        raise RuntimeError("livre finalisé : il est servi tel quel, jamais refabriqué (une modification = nouvelle version, à la main)")
    essai = o["formule"].split("_", 1)[1] if (o["formule"] or "").startswith("essai_") else None
    o = db.get(oid)
    form, refs = load_book(o["origine"])
    if o["formule"] in EXTRAS:                    # calendrier, coloriage : mêmes avatars, leur propre chaîne
        form = dict(form, produit=o["formule"])
    elif o["origine"] != oid:                     # livre du mois suivant : nouveau thème, nouvel univers
        n = o["numero"]
        form = dict(form, numero=f"{n:02d}", theme=THEMES[(THEMES.index(form["theme"]) + n - 1) % len(THEMES)] if form.get("theme") in THEMES else THEMES[n % len(THEMES)],
                    univers=UNIVERS[(UNIVERS.index(form["univers"]) + n - 1) % len(UNIVERS)] if form.get("univers") in UNIVERS else UNIVERS[n % len(UNIVERS)])
        form.pop("precision", None)               # le mot du parent concernait le premier livre
        choix = (form.get("suite") or [])[n - 2] if 0 <= n - 2 < len(form.get("suite") or []) else {}
        if choix.get("theme"):                    # aventure choisie par le parent à la commande
            form["theme"] = choix["theme"]
        if choix.get("univers") in UNIVERS:
            form["univers"] = choix["univers"]
    else:
        form = dict(form, numero=f"{o['numero']:02d}")
    if o.get("univers") and o["formule"] not in EXTRAS:   # livre de fête : univers imposé
        form = dict(form, univers=o["univers"])
    if o["formule"] not in EXTRAS and U.cle_de(form.get("univers")) == "anniversaire":   # il a un an de plus le jour J
        try:
            depuis = int((time.time() - db.get(o["origine"] or oid)["cree"]) // (365.25 * 86400))
            form = dict(form, age=str(int(form["age"]) + 1 + depuis))
            if str(form.get("naissance") or "").isdigit():      # année de naissance connue : l'âge exact du jour J
                import datetime
                form = dict(form, age=str(max(2, min(10, datetime.date.today().year + (1 if datetime.date.today().strftime("%m-%d") > (form.get("anniversaire") or "12-31") else 0) - int(form["naissance"])))))
        except (ValueError, TypeError, KeyError):
            pass
    if o["formule"] not in EXTRAS:
        form = dict(form, volume_number=db.assign_volume(oid))  # volumeNumber : attribué une fois, jamais changé
    job_id = o["job_id"] or oid
    if not reprise and (A.OUT / job_id).exists() and any((A.OUT / job_id).glob("*.png")):
        # « refaire » : l'ancien dossier est gardé à part, la nouvelle version a son propre dossier, le MÊME budget (la commande)
        n = 2
        while (A.OUT / f"{oid}-v{n}").exists(): n += 1
        job_id = f"{oid}-v{n}"
    folder = A.OUT / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".commande").write_text(oid)
    db.update(oid, statut="generation", job_id=job_id, erreur=None, tentatives=(o.get("tentatives") or 0) + 1 if reprise else 1)
    A.start_job(job_id, form, refs, auto=auto, on_end=lambda j, job: book_done(oid, job), reprise=reprise, essai=essai)
    return True


def book_done(oid, job):
    if job["etat"] != "termine":
        db.update(oid, statut="erreur", erreur="Fabrication : " + str(job.get("erreur", "inconnue")), cout=job.get("cout"))
        log(f"commande {oid} : erreur de fabrication {job.get('erreur')}")
        return
    db.update(oid, statut="a_verifier", pdf=job["pdf"], titre=job["titre"], controle=job.get("controle") or [], cout=job.get("cout"))
    for f in (A.OUT / job.get("_id", oid)).glob("*_brut.png"):      # place disque : on ne garde que les images finales
        f.unlink(missing_ok=True)
    for f in (A.OUT / job.get("_id", oid)).glob("*_essai*.png"):
        f.unlink(missing_ok=True)
    for x in ("rendu", "refs"):                                    # pages de rendu et copies de références : temporaires
        shutil.rmtree(A.OUT / (db.get(oid)["job_id"] or oid) / x, ignore_errors=True)
    log(f"commande {oid} : livre prêt « {job['titre']} », " + ("finalisé" if job.get("finalise") else "à relire"))
    if job.get("finalise"):
        _mail_pret_async(oid)
    if auto_print() and not job.get("controle") and not db.get(oid)["formule"].startswith("essai"):
        try:
            send_to_print(oid)
        except Exception as e:
            db.update(oid, erreur=f"Impression automatique : {e}")


@bp.get("/api/commandes/<oid>")
def order_status(oid):
    o = db.get(oid) or abort(404)
    sid = request.args.get("session_id")
    if o["statut"] == "attente_paiement" and sid and sid == o["stripe_session"] and paiement.configured():
        try:                                       # retour de Stripe : on vérifie directement (utile sans webhook en local)
            s = paiement.session(sid)
            if s.get("payment_status") in ("paid", "no_payment_required") or s.get("status") == "complete":
                confirm_paid(oid, s.get("subscription"))
                o = db.get(oid)
        except paiement.StripeError as e:
            log(f"vérification Stripe {oid} : {e}")
    try:
        f0 = load_book(o["origine"] or oid)[0]
        avec_cal = o["formule"] == "calendrier" or bool(f0.get("calendrier"))
        avec_colo = o["formule"] == "coloriage" or bool(f0.get("coloriage"))
    except Exception:
        avec_cal = avec_colo = False
    return jsonify(id=oid, statut=o["statut"], formule=o["formule"], job=o["job_id"], titre=o["titre"], calendrier=avec_cal, coloriage=avec_colo,
                   test=not paiement.configured())


@bp.post("/api/commandes/<oid>/paiement-test")
def order_test_payment(oid):
    """Paiement simulé : uniquement quand Stripe n'est pas configuré (essais en local)."""
    if paiement.configured():
        abort(403)
    db.get(oid) or abort(404)
    confirm_paid(oid)
    return jsonify(ok=True)


@bp.post("/api/stripe/webhook")
def stripe_webhook():
    try:
        ev = paiement.verify_webhook(request.get_data(), request.headers.get("Stripe-Signature"))
    except paiement.StripeError as e:
        return jsonify(erreur=str(e)), 400
    t, o = ev.get("type"), (ev.get("data") or {}).get("object") or {}
    try:
        if t in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            oid = (o.get("metadata") or {}).get("commande") or o.get("client_reference_id")
            if oid and db.get(oid) and o.get("payment_status") in ("paid", "no_payment_required"):
                confirm_paid(oid, o.get("subscription"))
        elif t == "invoice.paid" and o.get("billing_reason") == "subscription_cycle":
            s = db.sub_find(stripe_sub=paiement.invoice_subscription(o))
            if s and s["formule"] == "fetes":                     # mensualité du pack : pas de livre, on compte
                n = (s.get("paiements") or 1) + 1
                db.sub_update(s["id"], paiements=n)
                if n >= 12:
                    paiement.stop_after_period(s["stripe_sub"])
            elif s and s["statut"] == "actif":
                next_book(s)
        elif t == "customer.subscription.deleted":
            s = db.sub_find(stripe_sub=o.get("id"))
            if s and not (s["formule"] == "fetes" and (s.get("paiements") or 0) >= 12):
                db.sub_update(s["id"], statut="arrete")         # pack fêtes payé en entier : les livres restants restent dus
    except Exception:
        traceback.print_exc()
        return jsonify(erreur="traitement"), 500
    return jsonify(ok=True)


def next_book(s, univers=None):
    """Livre suivant d'un abonnement (numéro +1), fabriqué sans validation du parent. `univers` : imposé (livre de fête)."""
    n = (s["numero"] or 0) + 1
    o = db.get(s["commande_origine"])
    oid = s["commande_origine"] if (s["formule"] == "fetes" and n == 1) else uuid.uuid4().hex[:12]   # 1er livre du pack = la commande
    if oid == s["commande_origine"]:
        db.update(oid, statut="payee", univers=univers, numero=1)
    else:
        db.create(id=oid, formule=s["formule"], email=o["email"], adresse=o["adresse"], statut="payee", montant=0,
                  abonnement_id=s["id"], origine=s["commande_origine"], numero=n, stripe_sub=s["stripe_sub"], univers=univers)
    left = s["livres_restants"] - 1 if s["livres_restants"] is not None else None
    db.sub_update(s["id"], numero=n, livres_restants=left,
                  prochain=(time.time() + MOIS) if s["prochain"] is not None and (left is None or left > 0) else None,
                  statut="termine" if left == 0 else s["statut"])
    log(f"abonnement {s['id']} : livre n°{n} (commande {oid}){' – ' + univers if univers else ''}")
    if left == 0 and s["formule"] == "mensuel" and s.get("stripe_sub") and paiement.configured():
        try:                                       # abonnement offert : dernier livre lancé, plus aucun prélèvement
            paiement.stop_after_period(s["stripe_sub"])
        except Exception:
            traceback.print_exc()
    start_book(oid, auto=True)
    return oid


def _scheduler():
    """Toutes les heures : livres des abonnements (mensuel sans Stripe, fêtes qui approchent) et suivi des impressions Lulu."""
    while True:
        time.sleep(int(os.getenv("SCHEDULER_SECONDS", "3600")))
        try:
            for s in db.due_subs():
                next_book(s)
            for s in db.subs("actif"):
                if s["formule"] == "fetes":
                    check_fetes(s)
            purge_old()
            if lulu.configured():
                for o in db.lister(statut="envoyee_impression"):
                    refresh_print(o["id"])
        except Exception:
            traceback.print_exc()


def _taille(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def place_disque():
    """Ce qui occupe le disque (volume Railway), par catégorie, en Mo."""
    D = budget.DATA
    cats = {"livres et produits (output)": A.OUT, "sauvegardes (zip)": D / "sauvegardes", "commandes (avatars)": STORE,
            "portraits en cache": Path(A.generator.REF_DIR), "avatars en cache": Path(A.generator.CACHE)}
    out = {k: round(_taille(v) / 1e6, 1) for k, v in cats.items()}
    tmp = 0
    for d in A.OUT.iterdir() if A.OUT.exists() else []:
        if d.is_dir():
            tmp += sum(_taille(d / x) for x in ("rendu", "refs", "refusees")) + sum(f.stat().st_size for f in d.glob("*_brut.png"))
    out["dont fichiers temporaires effaçables"] = round(tmp / 1e6, 1)
    try:
        st = shutil.disk_usage(D)
        out["_disque"] = {"total_mo": round(st.total / 1e6), "libre_mo": round(st.free / 1e6), "utilise_mo": round(st.used / 1e6)}
    except OSError:
        pass
    return out


def nettoyer_disque():
    """Libère de la place SANS toucher à ce qui sert : pages de rendu intermédiaires, copies de références, images brutes,
    images refusées archivées, essais de plus de 3 jours, livres jamais commandés. Les livres, calendriers et cahiers, leurs
    images, PDF, aperçus, portraits et sauvegardes sont gardés."""
    libere = 0
    en_cours = {o["job_id"] for o in db.lister(1000) if A.JOBS.get(o["job_id"] or "", {}).get("etat") in ("en_cours", "validation")}
    essais_vieux = {o["job_id"] for o in db.lister(1000) if (o["formule"] or "").startswith("essai") and o["maj"] < time.time() - 3 * 86400}
    for d in (A.OUT.iterdir() if A.OUT.exists() else []):
        if not d.is_dir() or d.name in en_cours:
            continue
        if d.name in essais_vieux or (not (d / ".commande").exists() and d.stat().st_mtime < time.time() - 86400):
            libere += _taille(d); shutil.rmtree(d, ignore_errors=True); continue
        for x in ("rendu", "refs", "refusees", "_calibrage"):
            if (d / x).exists():
                libere += _taille(d / x); shutil.rmtree(d / x, ignore_errors=True)
        for f in list(d.glob("*_brut.png")) + list(d.glob("_vignette_admin_*.jpg")):
            libere += f.stat().st_size; f.unlink(missing_ok=True)
    return round(libere / 1e6, 1)


def purge_old(days=int(os.getenv("PURGE_JOURS", "30"))):
    """Livres expédiés depuis plus de `days` jours : fichiers effacés (données de l'enfant, place disque)."""
    limit = time.time() - days * 86400
    for o in db.lister(1000, statut="expediee"):
        if o["maj"] < limit and o["job_id"] and (A.OUT / o["job_id"]).exists():
            shutil.rmtree(A.OUT / o["job_id"], ignore_errors=True)
            db.update(o["id"], pdf=None)


# ------------------------------------------------------------------ impression
def est_calendrier(folder):
    return produit_de(folder) is not None


def build_cover(oid):
    """Couverture Lulu en une pièce (4e | tranche | 1re) aux dimensions données par Lulu pour 24 pages."""
    o = db.get(oid)
    folder = A.OUT / o["job_id"]
    mod = produit_de(folder)
    if mod:                                       # calendrier / coloriage : couverture aux dimensions Lulu du produit
        dims = calendrier.dimensions_couverture() if mod is calendrier else coloriage.dimensions_couverture(coloriage.pages_impression(folder))
        info = mod.couverture_impression(folder, dims)
        info["dimensions_lulu"] = bool(dims)
        return info
    if (folder / "livre.json").exists() and not (folder / "histoire.json").exists():
        # livre du procédé actuel : couverture à plat recomposée par code à partir des fichiers enregistrés (aucun appel IA)
        book = json.loads((folder / "livre.json").read_text(encoding="utf-8"))
        form, _ = load_book(o["origine"])
        dims = fabrication.dimensions_couverture()
        info = fabrication.couverture_a_plat(book, folder / "impression_couverture.pdf", folder, book.get("volumeNumber") or o.get("volume_number") or 1,
                                             form.get("prenom") or "", dims)
        info["dimensions_lulu"] = bool(dims)
        return info
    story = json.loads((folder / "histoire.json").read_text(encoding="utf-8")) if (folder / "histoire.json").exists() else None
    if story is None:
        raise RuntimeError("histoire.json introuvable : livre démo ?")
    pages = 24
    if lulu.configured():
        w, h = lulu.cover_dimensions(pages)
        exact = True
    else:                                           # estimation (couverture rigide : ~0,75 po de rabat, tranche ~0,25 po)
        w, h = 2 * (A.layout.PAGE + 54) + 18, A.layout.PAGE + 108
        exact = False
    cover = folder / "image_00.png"
    amb = A.layout.procedural_ambiance(A.layout.load(cover), story.get("univers"), 99)
    info = A.layout.build_cover(story, cover, amb, folder / "impression_couverture.pdf", w, h)
    info["dimensions_lulu"] = exact
    return info


def _verifier_imprimable(b):
    """Un livre du pack est-il prêt pour l'imprimeur ? (finalisé, couverture au gabarit, numéro du dos validé)"""
    if b["statut"] not in ("a_verifier", "erreur") or not b["job_id"]:
        raise RuntimeError(f"livre n°{b['numero']} : statut {b['statut']}, pas prêt")
    folder = A.OUT / b["job_id"]
    if est_calendrier(folder):
        if not fabrication.est_finalise(folder):
            raise RuntimeError(f"{NOMS_EXTRAS.get(b['formule'], 'produit')} non finalisé (à relire) : valide-le avant l'impression.")
        info = build_cover(b["id"])
        if not info["pret_a_imprimer"]:
            raise RuntimeError(f"{NOMS_EXTRAS.get(b['formule'], 'produit').capitalize()} NON prêt à imprimer : " + " ".join(info["problemes"]))
    elif (folder / "livre.json").exists() and not (folder / "histoire.json").exists():
        if not fabrication.est_finalise(folder):
            raise RuntimeError(f"livre n°{b['numero']} non finalisé (à relire) : valide-le avant l'impression.")
        info = build_cover(b["id"])
        if not info["pret_a_imprimer"]:
            raise RuntimeError("Couverture NON prête à imprimer : " + " ".join(info["problemes"]))
    elif not (folder / "impression_interieur.pdf").exists():
        raise RuntimeError("impression_interieur.pdf introuvable")
    else:
        build_cover(b["id"])


def send_to_print(oid):
    """Envoie TOUTE la commande (livres + calendrier) chez l'imprimeur en un seul travail (un seul colis).
    Refusé tant qu'un livre ou le calendrier n'est pas prêt."""
    o = db.get(oid)
    if (o["formule"] or "").startswith("essai"):
        raise RuntimeError("livre d'essai : pas d'impression")
    origine = o["origine"] or oid
    livres, cals = livres_du_pack(origine), extras_du_pack(origine)
    tete = db.get(origine)
    attendus = (paiement.FORMULES.get(tete["formule"]) or {"livres": len(livres)})["livres"]
    if len(livres) < attendus:
        raise RuntimeError(f"pack incomplet : {len(livres)}/{attendus} livres créés")
    tout = livres + cals
    if any(b["statut"] in ("envoyee_impression", "expediee") for b in tout):
        raise RuntimeError("cette commande est déjà chez l'imprimeur")
    pas_prets = [b for b in tout if b["statut"] not in ("a_verifier", "erreur") or not b["job_id"]
                 or (((A.OUT / b["job_id"] / "livre.json").exists() or est_calendrier(A.OUT / b["job_id"]))
                     and not fabrication.est_finalise(A.OUT / b["job_id"]))]
    if pas_prets:
        raise RuntimeError("Non finalisé (à relire) : valide-le avant l'impression." if len(tout) == 1 else
                           f"{len(tout) - len(pas_prets)}/{len(tout)} prêts : le colis part quand tout est finalisé (validé)")
    if not lulu.configured():
        raise RuntimeError("Clés Lulu absentes (.env : LULU_CLIENT_KEY, LULU_CLIENT_SECRET).")
    pub = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not pub.startswith("https://"):
        raise RuntimeError("Lulu doit télécharger les PDF : renseigne PUBLIC_URL (adresse https publique du site).")
    for b in tout:
        _verifier_imprimable(b)
    items = []
    for b in tout:
        jeton = b["jeton"] or secrets.token_urlsafe(24)
        db.update(b["id"], jeton=jeton)
        it = {"id": b["id"], "titre": b["titre"] or "Mon Héros du Mois",
              "interieur": f"{pub}/impression/{b['id']}/{jeton}/interieur.pdf", "couverture": f"{pub}/impression/{b['id']}/{jeton}/couverture.pdf"}
        if b["formule"] in EXTRAS:
            it["pod"] = EXTRAS[b["formule"]].POD
        items.append(it)
    cost = lulu.cost_lignes([(24, lulu.POD_PACKAGE, len(livres))] + [(pages_extra(b["formule"], A.OUT / b["job_id"]), EXTRAS[b["formule"]].POD, 1) for b in cals],
                            tete["adresse"], tete["email"])
    job = lulu.create_print_job(origine, items, tete["adresse"], tete["email"])
    st = (job.get("status") or {}).get("name")
    quoi = " + ".join(([f"{len(livres)} livre(s)"] if livres else []) + [NOMS_EXTRAS[b["formule"]] for b in cals])
    for b in tout:
        db.update(b["id"], statut="envoyee_impression", lulu_id=str(job.get("id")), lulu_statut=st,
                  lulu_cout=f"{cost['total_ttc']} {cost['devise']} (colis : {quoi})" if b["id"] == origine else None, erreur=None)
    log(f"commande {origine} ({quoi}) envoyée à Lulu ({lulu.env()}) : travail {job.get('id')}, {cost['total_ttc']} {cost['devise']}")
    return job


def verifier_fichiers_lulu(oid, attente=55):
    """Outil de validation de Lulu sur les fichiers RÉELS de ce livre ou de ce calendrier (aucune commande, aucun paiement).
    Calendrier accepté (intérieur et couverture) : noté une fois pour toutes pour ce code produit."""
    o = db.get(oid)
    folder = A.OUT / (o["job_id"] or "_")
    if not (folder / "impression_interieur.pdf").exists() or not (folder / "impression_couverture.pdf").exists():
        raise RuntimeError("fichiers d'impression absents")
    if not lulu.configured():
        raise RuntimeError("Clés Lulu absentes")
    pub = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not pub.startswith("https://"):
        raise RuntimeError("Lulu doit télécharger les PDF : renseigne PUBLIC_URL (adresse https publique du site).")
    mod = produit_de(folder)
    cal = mod is not None
    if cal:
        build_cover(oid)
    jeton = o["jeton"] or secrets.token_urlsafe(24)
    db.update(oid, jeton=jeton)
    pod, pages = (mod.POD, pages_extra(o["formule"], folder)) if cal else (lulu.POD_PACKAGE, fabrication.PAGES_IMPRESSION)
    ids = {"interior": lulu.valider("interior", f"{pub}/impression/{oid}/{jeton}/interieur.pdf", pod).get("id"),
           "cover": lulu.valider("cover", f"{pub}/impression/{oid}/{jeton}/couverture.pdf", pod, pages).get("id")}
    res, t0 = {}, time.time()
    while time.time() - t0 < attente:
        time.sleep(5)
        for k, vid in ids.items():
            if res.get(k, {}).get("status") not in ("VALIDATED", "NORMALIZED", "ERROR"):
                res[k] = lulu.etat_validation(k, vid)
        if all(r.get("status") in ("VALIDATED", "NORMALIZED", "ERROR") for r in res.values()) and len(res) == 2:
            break
    ok = len(res) == 2 and all(r.get("status") in ("VALIDATED", "NORMALIZED") for r in res.values())
    if ok and cal:
        (budget.DATA / f"lulu_{o['formule']}_valide.json").write_text(json.dumps({"pod": mod.POD, "le": time.strftime("%Y-%m-%d %H:%M"),
                                                                             "commande": oid, "resultats": res}, ensure_ascii=False))
    out = {k: {"statut": r.get("status") or "en cours", "pages": r.get("page_count"), "erreurs": r.get("errors") or r.get("error")}
           for k, r in res.items()}
    return {"ok": ok, "calendrier": cal, "pod": pod, "resultats": out, "en_cours": not ok and any(v["statut"] == "en cours" for v in out.values())}


def refresh_print(oid):
    o = db.get(oid)
    st = lulu.status(o["lulu_id"])
    kw = dict(lulu_statut=st["statut"], suivi=st["suivi"] or None)
    if st["statut"] == "SHIPPED":
        kw["statut"] = "expediee"
    elif st["statut"] in ("REJECTED", "ERROR", "CANCELED"):
        kw.update(statut="erreur", erreur=f"Lulu : {st['statut']} {st.get('message') or ''}")
    return db.update(oid, **kw)


@bp.get("/impression/<oid>/<jeton>/<name>")
def print_file(oid, jeton, name):
    """Fichiers téléchargés par Lulu (lien secret propre à chaque commande)."""
    o = db.get(oid)
    if not o or not o["jeton"] or not secrets.compare_digest(o["jeton"], jeton) or name not in ("interieur.pdf", "couverture.pdf"):
        abort(404)
    p = A.OUT / o["job_id"] / f"impression_{name}"
    return send_file(p, mimetype="application/pdf") if p.exists() else abort(404)


# ------------------------------------------------------------------ administration
def admin_ok():
    code = os.getenv("ADMIN_CODE", "")
    given = request.args.get("code") or request.headers.get("X-Admin") or request.form.get("code") or ""
    if code:
        return secrets.compare_digest(code, given)
    if os.getenv("PUBLIC_URL") or os.getenv("RAILWAY_ENVIRONMENT"):
        return False                                       # site en ligne : ADMIN_CODE obligatoire
    return request.remote_addr in ("127.0.0.1", "::1")      # sans ADMIN_CODE : uniquement depuis ton ordinateur


@bp.get("/admin")
def admin():
    if not admin_ok():
        abort(403)
    return send_file(A.ROOT / "static" / "admin.html")


@bp.get("/admin/api/commandes")
def admin_list():
    if not admin_ok():
        abort(403)
    rows = db.lister()
    for r in rows:
        r.pop("jeton", None)
        r["fichiers"] = sorted([p.name for p in (A.OUT / (r["job_id"] or "_")).glob("*.pdf") if p.name != "apercu.pdf" or r["pdf"] == "apercu.pdf"],
                               key=lambda n: n.startswith("impression_")) + \
                        (["controle.json"] if (A.OUT / (r["job_id"] or "_") / "controle.json").exists() else []) + \
                        sorted(p.name for p in (A.OUT / (r["job_id"] or "_")).glob("planche_contact_*.jpg"))
        folder = A.OUT / (r["job_id"] or "_")
        r["finalise"] = folder.exists() and fabrication.est_finalise(folder)
        r["vignette"] = folder.exists() and bool(_couverture(folder))
        job = A.JOBS.get(r["job_id"] or "") or {}
        r["en_cours"] = job.get("etat") in ("en_cours", "validation")
        r["progression"], r["etape"] = job.get("progression"), job.get("etape")
        try:
            lid = procede.livre_id(folder) if folder.exists() else r["id"]
            r["budget"] = budget.depense(lid)
        except Exception:
            r["budget"] = None
        r["refusees"] = folder.exists() and any(json.loads(f.read_text(encoding="utf-8")).get("bloquants")
                                                for f in list(folder.glob("spread-*.json")) + list(folder.glob("cal-*.json")) + list(folder.glob("colo-*.json")))
        r["calendrier"] = r["formule"] == "calendrier"
        r["coloriage"] = r["formule"] == "coloriage"
        r["extra"] = r["formule"] in EXTRAS
        r["plafond"] = EXTRAS[r["formule"]].PLAFOND if r["formule"] in EXTRAS else budget.PLAFOND
        try:
            r["prenom"] = json.loads((STORE / r["origine"] / "livre.json").read_text(encoding="utf-8"))["form"].get("prenom")
        except Exception:
            r["prenom"] = None
    packs = {}
    for r in rows:
        if not (r["formule"] or "").startswith("essai"):
            packs.setdefault(r["origine"] or r["id"], []).append(r)
    for r in rows:
        g = packs.get(r["origine"] or r["id"]) or [r]
        tete = next((x for x in g if x["id"] == (r["origine"] or r["id"])), r)
        r["pack_total"] = (paiement.FORMULES.get(tete["formule"]) or {"livres": len(g)})["livres"]
        r["pack_prets"] = sum(1 for x in g if x.get("finalise") and x["formule"] not in EXTRAS)
        r["pack_cal"] = sum(1 for x in g if x["formule"] in EXTRAS)
        r["pack_cal_prets"] = sum(1 for x in g if x["formule"] in EXTRAS and x.get("finalise"))
        r["pack_extras"] = [x["formule"] for x in g if x["formule"] in EXTRAS]
        r["pack_mail"] = tete.get("mail_pret")
    return jsonify(plafond=budget.PLAFOND, commandes=rows, abonnements=db.subs(),
                   config={"stripe": "live" if paiement.live() else "test" if paiement.configured() else "simulé",
                           "lulu": lulu.env() if lulu.configured() else "non configuré", "pod": lulu.POD_PACKAGE,
                           "pod_calendrier": calendrier.POD, "calendrier_valide": calendrier.fichiers_valides(),
                           "pod_coloriage": coloriage.POD, "coloriage_valide": coloriage.fichiers_valides(),
                           "public_url": os.getenv("PUBLIC_URL", ""), "auto_impression": auto_print(),
                           "depense_jour": A.generator.spent_today(), "budget_jour": A.generator.BUDGET_JOUR})


def _couverture(folder):
    a = folder / "apercus" / "couverture.png"
    if a.exists():
        return a
    c = sorted(folder.glob("couverture-*.png"))
    return c[0] if c else None


@bp.get("/admin/vignette/<oid>")
def admin_vignette(oid):
    """Petite image de la couverture pour l'admin (faite une fois, à partir du fichier du livre ; aucun appel IA)."""
    if not admin_ok():
        abort(403)
    o = db.get(oid) or abort(404)
    folder = A.OUT / (o["job_id"] or "_")
    src = _couverture(folder) if folder.exists() else None
    if not src:
        abort(404)
    v = folder / f"_vignette_admin_{src.stem}.jpg"
    if not v.exists():
        from PIL import Image
        im = Image.open(src).convert("RGB"); im.thumbnail((360, 360)); im.save(v, quality=86)
    return send_file(v, max_age=300)


@bp.get("/admin/fichier/<oid>/<name>")
def admin_file(oid, name):
    if not admin_ok():
        abort(403)
    o = db.get(oid) or abort(404)
    if not re.match(r"^[\w\-. ]+\.(pdf|json|png|jpg)$", name) or "/" in name:
        abort(404)
    p = A.OUT / (o["job_id"] or "_") / name
    return send_file(p) if p.exists() else abort(404)


@bp.get("/admin/archive/<oid>")
def admin_archive(oid):
    """Tout le dossier d'un livre (configuration, histoire, storyboard, portraits, images, contrôle) en un zip, pour la relecture."""
    if not admin_ok():
        abort(403)
    import zipfile, io
    o = db.get(oid) or abort(404)
    folder = A.OUT / (o["job_id"] or "_")
    if not folder.exists():
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(folder.rglob("*")):                 # dont prompts/ et rendu/ (pages rendues, planches contact)
            if p.is_file() and not p.name.startswith("impression_"):
                z.write(p, f"livre_{oid}/{p.relative_to(folder)}")
        for p in (STORE / o["origine"]).glob("*"):
            z.write(p, f"livre_{oid}/commande/{p.name}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"livre_{oid}.zip")


@bp.post("/admin/api/vignettes")
def admin_vignettes():
    """Génère en arrière-plan les vignettes illustrées manquantes des univers et des fêtes (OpenAI)."""
    if not admin_ok():
        abort(403)
    import vignettes
    todo = [u["cle"] for u in vignettes.manquantes()]
    if todo:
        threading.Thread(target=lambda: (lambda r: log(f"vignettes générées : {r}"))(vignettes.generer(log)), daemon=True).start()
    return jsonify(lancees=todo)


@bp.get("/admin/api/tarifs")
def admin_tarifs():
    if not admin_ok():
        abort(403)
    return jsonify(etat=budget.etat_tarifs(), tarifs=budget.tarifs())


@bp.post("/admin/api/lulu/comparer")
def admin_lulu_comparer():
    """Devis Lulu pour plusieurs fabrications (aucune commande, aucun paiement), avec l'adresse de la dernière commande."""
    if not admin_ok():
        abort(403)
    if not lulu.configured():
        return jsonify(erreur="Clés Lulu absentes"), 400
    o = next((x for x in db.lister(200) if x.get("adresse") and (x["adresse"] or {}).get("pays")), None)
    addr = (o or {}).get("adresse") or {"nom": "Test", "adresse1": "1 rue de la Mairie", "code_postal": "77000", "ville": "Melun",
                                         "pays": "FR", "telephone": "0600000000"}
    try:
        return jsonify(ok=True, ville=addr.get("ville"), options=lulu.comparer(24, addr, (o or {}).get("email") or CONTACT))
    except Exception as e:
        return jsonify(erreur=str(e)), 400


@bp.post("/admin/api/lulu/calendrier")
def admin_lulu_calendrier():
    """Test en bac à sable : quels codes de calendrier l'API Lulu accepte, et à quel prix (devis seulement)."""
    if not admin_ok():
        abort(403)
    if not lulu.configured():
        return jsonify(erreur="Clés Lulu absentes"), 400
    o = next((x for x in db.lister(200) if x.get("adresse") and (x["adresse"] or {}).get("pays")), None)
    addr = (o or {}).get("adresse") or {"nom": "Test", "adresse1": "1 rue de la Mairie", "code_postal": "77000", "ville": "Melun",
                                         "pays": "FR", "telephone": "0600000000"}
    res = lulu.tester_calendriers(addr, (o or {}).get("email") or CONTACT)
    log("test calendriers Lulu : " + json.dumps(res, ensure_ascii=False)[:2000])
    return jsonify(ok=True, resultats=res)


@bp.post("/admin/api/lulu/coloriage")
def admin_lulu_coloriage():
    """Test en bac à sable : quels codes de cahier de coloriage (Lettre US, spirale, N&B) l'API Lulu accepte, et à quel prix."""
    if not admin_ok():
        abort(403)
    if not lulu.configured():
        return jsonify(erreur="Clés Lulu absentes"), 400
    o = next((x for x in db.lister(200) if x.get("adresse") and (x["adresse"] or {}).get("pays")), None)
    addr = (o or {}).get("adresse") or {"nom": "Test", "adresse1": "1 rue de la Mairie", "code_postal": "77000", "ville": "Melun",
                                         "pays": "FR", "telephone": "0600000000"}
    res = lulu.tester_calendriers(addr, (o or {}).get("email") or CONTACT, codes=lulu.COLORIAGES, pages_list=(coloriage.pages_impression("_"),))
    log("test coloriage Lulu : " + json.dumps(res, ensure_ascii=False)[:2000])
    return jsonify(ok=True, resultats=res)


@bp.get("/admin/api/disque")
def admin_disque():
    if not admin_ok():
        abort(403)
    return jsonify(place_disque())


@bp.post("/admin/api/disque/nettoyer")
def admin_disque_nettoyer():
    if not admin_ok():
        abort(403)
    mo = nettoyer_disque()
    log(f"nettoyage du disque : {mo} Mo libérés")
    return jsonify(ok=True, libere_mo=mo, place=place_disque())


@bp.post("/admin/api/tarifs/confirmer")
def admin_tarifs_confirmer():
    """Tu as vérifié les prix sur platform.openai.com/docs/pricing : tu les confirmes (ou tu les corriges ici)."""
    if not admin_ok():
        abort(403)
    body = request.get_json(force=True, silent=True) or {}
    t = budget.tarifs()
    for m, vals in (body.get("modeles") or {}).items():
        if m in t["modeles"]:
            for k in ("texte_entree", "image_entree", "sortie_image", "sortie"):
                if isinstance(vals.get(k), (int, float)) and vals[k] > 0:
                    t["modeles"][m][k] = float(vals[k])
    t["confirme_le"] = time.strftime("%Y-%m-%d %H:%M"); t["confirme_par"] = "admin"
    budget.enregistrer_tarifs(t)
    return jsonify(ok=True, etat=budget.etat_tarifs())


@bp.post("/admin/api/tarifs/calibrer")
def admin_tarifs_calibrer():
    """UN appel payant (~0,02 $, au plus 0,17 $), lancé seulement par toi : mesure les jetons d'une image de référence."""
    if not admin_ok():
        abort(403)
    if not budget.tarifs().get("confirme_le"):
        return jsonify(erreur="Confirme d'abord les tarifs"), 400
    try:
        return jsonify(ok=True, info=procede.calibrer(A.OUT / "_calibrage"), etat=budget.etat_tarifs())
    except Exception as e:
        return jsonify(erreur=str(e)), 400


@bp.post("/admin/api/appels/<int:aid>/regler")
def admin_regler_appel(aid):
    """Appel au résultat incertain : tu saisis le coût constaté sur le tableau de bord OpenAI (0 si rien n'a été facturé)."""
    if not admin_ok():
        abort(403)
    a = budget.appel_get(aid) or abort(404)
    if a["statut"] != "incertain":
        return jsonify(erreur=f"appel {aid} : statut {a['statut']}"), 400
    reel = float((request.get_json(force=True, silent=True) or {}).get("reel", -1))
    if reel < 0:
        return jsonify(erreur="coût réel manquant"), 400
    budget.regler_incertain(aid, reel)
    return jsonify(ok=True, depense=budget.depense(a["livre"]))


@bp.post("/admin/api/<oid>/<action>")
def admin_action(oid, action):
    if not admin_ok():
        abort(403)
    o = db.get(oid) or abort(404)
    try:
        if action == "couverture":
            return jsonify(ok=True, info=build_cover(oid))
        if action == "cout":
            n, ex = len(livres_du_pack(o["origine"] or oid)), extras_du_pack(o["origine"] or oid)
            lignes = [(24, lulu.POD_PACKAGE, n)] + [(pages_extra(b["formule"], A.OUT / (b["job_id"] or "_")), EXTRAS[b["formule"]].POD, 1) for b in ex]
            return jsonify(ok=True, info=dict(lulu.cost_lignes(lignes, o["adresse"], o["email"]), livres=n, calendriers=len(ex),
                                              extras=[NOMS_EXTRAS[b["formule"]] for b in ex]))
        if action == "verifier-lulu":
            return jsonify(ok=True, info=verifier_fichiers_lulu(oid))
        if action == "recomposer":                # calendrier : pages recomposées à partir des 13 images enregistrées (aucun appel IA)
            folder = A.OUT / (o["job_id"] or "_")
            mod = produit_de(folder)
            if not mod:
                raise RuntimeError("seulement pour un calendrier ou un cahier de coloriage")
            form, _ = load_book(o["origine"])
            fab = mod.recomposer(folder, form)
            return jsonify(ok=True, info={"pdf": fab["pdf"]})
        if action == "imprimer":
            job = send_to_print(oid)
            return jsonify(ok=True, info={"lulu": job.get("id"), "env": lulu.env()})
        if action == "suivi":
            return jsonify(ok=True, info=refresh_print(oid))
        if action == "relancer":
            if o["statut"] not in ("erreur", "generation", "payee", "a_verifier"):
                raise RuntimeError("seulement avant l'envoi à l'impression")
            if A.JOBS.get(o["job_id"] or "", {}).get("etat") in ("en_cours", "validation"):
                raise RuntimeError("fabrication en cours : attends la fin avant de relancer")
            if o["job_id"] and fabrication.est_finalise(A.OUT / o["job_id"]):
                raise RuntimeError("livre finalisé : il n'est jamais refabriqué")
            # en erreur ou bloquée : on reprend là où elle s'est arrêtée ; « Refaire le livre » (à relire) repart de zéro
            start_book(oid, auto=True, reprise=o["statut"] != "a_verifier")
            return jsonify(ok=True)
        if action == "finaliser":                 # après relecture humaine d'un livre « à relire » : fige les fichiers, aucun appel IA
            folder = A.OUT / (o["job_id"] or "_")
            mod = produit_de(folder)
            man = (mod.finaliser_apres_relecture(folder) if mod else procede.finaliser_apres_relecture(folder))
            _mail_pret_async(oid)
            return jsonify(ok=True, info={"finalise_le": man["finalise_le"], "fichiers": len(man["fichiers"])})
        if action == "refaire-refusees":         # décision humaine : refaire les illustrations refusées, dans les 3 $ du livre
            folder = A.OUT / (o["job_id"] or "_")
            if o["statut"] not in ("erreur", "a_verifier") or not folder.exists():
                raise RuntimeError("seulement pour un livre en erreur ou à relire")
            if fabrication.est_finalise(folder):
                raise RuntimeError("livre finalisé : il n'est jamais refabriqué")
            if A.JOBS.get(o["job_id"] or "", {}).get("etat") in ("en_cours", "validation"):
                raise RuntimeError("fabrication en cours")
            arch = folder / "refusees" / time.strftime("%Y%m%d-%H%M%S"); n = 0
            for rp in list(folder.glob("spread-*.json")) + list(folder.glob("cal-*.json")) + list(folder.glob("colo-*.json")):
                if json.loads(rp.read_text(encoding="utf-8")).get("bloquants"):
                    arch.mkdir(parents=True, exist_ok=True)
                    for f in (rp, rp.with_suffix(".png")):
                        if f.exists(): f.rename(arch / f.name)
                    n += 1
            if not n:
                raise RuntimeError("aucune illustration refusée à refaire")
            start_book(oid, auto=True, reprise=True)   # tout le reste (histoire, portraits, couverture, pages acceptées) est réutilisé
            return jsonify(ok=True, info={"refaites": n, "anciennes_gardees_dans": str(arch.relative_to(folder))})
        if action == "mail-pret":                 # envoi (ou renvoi) à la main du mail « livre prêt »
            if not mail_configure():
                raise RuntimeError("envoi de mails non configuré (BREVO_API_KEY absent dans Railway)")
            db.annuler_mail_pret(o["origine"] or oid)
            DERNIERE_ERREUR_MAIL.pop(oid, None)
            if not mail_livre_pret(oid):
                fin = fabrication.est_finalise(A.OUT / (o["job_id"] or "_"))
                raise RuntimeError("mail non envoyé : " + (DERNIERE_ERREUR_MAIL.get(oid) or ("livre non finalisé" if not fin else "les autres livres du pack ne sont pas encore validés, ou livre d'essai")))
            return jsonify(ok=True, info={"envoye_a": o["email"]})
        if action == "budget":
            folder = A.OUT / (o["job_id"] or "_")
            lid = procede.livre_id(folder) if folder.exists() else oid
            bj = folder / "budget.json"
            pl = EXTRAS[o["formule"]].PLAFOND if o["formule"] in EXTRAS else budget.PLAFOND
            return jsonify(ok=True, info={"livre": lid, "plafond": pl, "depense": budget.depense(lid), "appels": budget.appels(lid),
                                          "borne": json.loads(bj.read_text(encoding="utf-8")) if bj.exists() else None,
                                          "tarifs": budget.etat_tarifs()})
        if action == "valider-paiement-test" and not paiement.configured():
            confirm_paid(oid)
            return jsonify(ok=True)
        if action in ("test-calendrier", "test-coloriage"):
            # calendrier / cahier de TEST à partir des avatars de cette commande : vraie fabrication (coût IA réel), aucun paiement,
            # une commande à part (elle ne rejoint pas le colis du client) ; imprimable comme une vraie commande pour un exemplaire test
            import datetime
            k = action.split("-")[1]
            form, _ = load_book(o["origine"] or oid)
            tid = uuid.uuid4().hex[:12]
            shutil.copytree(STORE / (o["origine"] or oid), STORE / tid)
            d = json.loads((STORE / tid / "livre.json").read_text(encoding="utf-8"))
            for x in EXTRAS:
                d["form"].pop(x, None)
            d["form"].pop("cadeau_de", None); d["form"].pop("cadeau_message", None)
            if k == "calendrier":
                d["form"]["calendrier"] = {"debut": calendrier.debut_par_defaut(), "dates": [], "pays": (o["adresse"] or {}).get("pays", "FR"),
                                           "commande_le": datetime.date.today().isoformat()}
            else:
                d["form"]["coloriage"] = {"pages": coloriage.choisir([])}
            d["form"]["formule"] = k
            (STORE / tid / "livre.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            db.create(id=tid, formule=k, email=o["email"], adresse=o["adresse"], statut="payee", montant=0, origine=tid, numero=0)
            start_book(tid, auto=True)
            return jsonify(ok=True, info={"test": tid, "produit": k})
        if action in ("essai-brouillon", "essai-apercu") and o["formule"] in EXTRAS:
            raise RuntimeError("pas d'essai pour un calendrier ou un cahier de coloriage")
        if action in ("essai-brouillon", "essai-apercu"):
            # livre d'essai à partir de la même configuration, sans paiement ni impression
            tid = uuid.uuid4().hex[:12]
            db.create(id=tid, formule="essai_" + action.split("-")[1], email=o["email"], adresse=o["adresse"], statut="payee",
                      montant=0, origine=o["origine"], numero=o["numero"])
            start_book(tid, auto=True)
            return jsonify(ok=True, info={"essai": tid})
        if action == "mois-suivant":
            s = db.sub_get(o["abonnement_id"] or "") or abort(404)
            return jsonify(ok=True, info=next_book(s))
        if action == "arreter-abonnement":
            s = db.sub_get(o["abonnement_id"] or "") or abort(404)
            if s["stripe_sub"] and paiement.configured():
                paiement.cancel_subscription(s["stripe_sub"])
            db.sub_update(s["id"], statut="arrete", prochain=None)
            return jsonify(ok=True)
        if action == "effacer":                   # données de l'enfant (RGPD), après livraison
            if o["statut"] not in ("expediee", "annulee", "erreur"):
                raise RuntimeError("effacement possible une fois le livre expédié")
            shutil.rmtree(A.OUT / (o["job_id"] or "_"), ignore_errors=True)
            if not any(x["origine"] == o["origine"] and x["statut"] not in ("expediee", "annulee") and x["id"] != oid for x in db.lister(1000)):
                s = db.sub_get(o["abonnement_id"] or "")
                if not s or s["statut"] != "actif":
                    shutil.rmtree(STORE / o["origine"], ignore_errors=True)
            db.update(oid, statut="annulee" if o["statut"] != "expediee" else "expediee", pdf=None, erreur="données effacées")
            return jsonify(ok=True)
        if action == "supprimer":                 # suppression définitive (commande de test, doublon…) : ligne + fichiers
            if A.JOBS.get(o["job_id"] or "", {}).get("etat") in ("en_cours", "validation"):
                raise RuntimeError("fabrication en cours : attends la fin avant de supprimer")
            if o["job_id"]:
                shutil.rmtree(A.OUT / o["job_id"], ignore_errors=True)
                A.JOBS.pop(o["job_id"], None)
            db.supprimer(oid)
            ori = o["origine"]
            if ori and not any(x["origine"] == ori for x in db.lister(100000)):
                s = db.sub_get(o["abonnement_id"] or "")
                if not s or s["statut"] != "actif":
                    shutil.rmtree(STORE / ori, ignore_errors=True)
            return jsonify(ok=True)
        abort(404)
    except (RuntimeError, lulu.LuluError, paiement.StripeError, budget.BudgetLivreError) as e:
        return jsonify(erreur=str(e)), 400


@bp.get("/cgv")
def cgv():
    return send_file(A.ROOT / "static" / "cgv.html")


# ---------------------------------------------------------------- formulaire de contact du site
CONTACT = os.getenv("CONTACT_EMAIL", "monherosdumois@gmail.com")
SUJETS = {"question": "Une question", "commande": "Ma commande", "cadeau": "Offrir un livre", "autre": "Autre"}


def mail_configure():
    return bool(os.getenv("BREVO_API_KEY") or os.getenv("SMTP_PASSWORD"))


def send_mail(subject, body, reply_to=None, to=None, html=None, images=None, image_urls=None):
    """Envoi d'un mail. Railway bloque le SMTP (ports 465/587) : on passe par l'API HTTPS de Brevo si BREVO_API_KEY est
    renseigné, sinon par SMTP (Gmail) si SMTP_PASSWORD l'est ; sinon rien. to : destinataire (par défaut toi).
    html + images {cid: chemin} (SMTP, images intégrées) ou image_urls {cid: url} (Brevo, images hébergées par le site)."""
    user = os.getenv("SMTP_USER", CONTACT)
    if os.getenv("BREVO_API_KEY"):
        import urllib.request, urllib.error
        if html:
            for cid, url in (image_urls or {}).items():
                html = html.replace(f"cid:{cid}", url)
        data = {"sender": {"name": "Mon Héros du Mois", "email": os.getenv("MAIL_FROM", user)}, "to": [{"email": to or CONTACT}],
                "subject": subject, "textContent": body}
        if html: data["htmlContent"] = html
        if reply_to: data["replyTo"] = {"email": reply_to}
        req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(data).encode(), method="POST",
                                     headers={"api-key": os.getenv("BREVO_API_KEY"), "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return 200 <= r.status < 300
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Brevo {e.code} : {e.read().decode(errors='replace')[:300]}")
    pw = os.getenv("SMTP_PASSWORD")
    if not pw:
        return False
    import smtplib, mimetypes
    from email.message import EmailMessage
    m = EmailMessage(); m["Subject"] = subject; m["From"] = f"Mon Héros du Mois <{user}>"; m["To"] = to or CONTACT
    if reply_to: m["Reply-To"] = reply_to
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
        part = m.get_payload()[-1]
        for cid, path in (images or {}).items():
            typ = (mimetypes.guess_type(str(path))[0] or "image/jpeg").split("/")
            part.add_related(Path(path).read_bytes(), maintype=typ[0], subtype=typ[1], cid=f"<{cid}>")
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls(); s.login(user, pw); s.send_message(m)
    return True


def _jours_ouvres(t, n):
    import datetime
    d = datetime.date.fromtimestamp(t)
    while n > 0:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d


def _date_fr(d):
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    return f"{jours[d.weekday()]} {d.day} {mois[d.month - 1]}"


DERNIERE_ERREUR_MAIL = {}


def mail_livre_pret(oid):
    """Mail automatique au client quand TOUS les livres de sa commande sont validés : couvertures, titres, livraison estimée.
    Un seul mail par commande (même pour un pack de 12)."""
    o = db.get(oid)
    if not o:
        return False
    origine = o["origine"] or oid
    tete = db.get(origine) or o
    if (tete["formule"] or "").startswith("essai") or not tete.get("email"):
        return False
    livres, cals = livres_du_pack(origine), extras_du_pack(origine)
    attendus = (paiement.FORMULES.get(tete["formule"]) or {"livres": 1})["livres"]
    if len(livres) < attendus or not all(b["job_id"] and fabrication.est_finalise(A.OUT / b["job_id"]) for b in livres + cals):
        return False                                      # la commande n'est pas encore complète : le mail part avec le dernier
    if not mail_configure():
        log(f"commande {origine} : mail « livre prêt » non envoyé (envoi de mails non configuré)")
        return False
    if not db.marquer_mail_pret(origine):
        return False                                      # déjà envoyé
    try:
        from PIL import Image
        form, _ = load_book(origine)
        prenom = form.get("prenom") or "votre enfant"
        site = (os.getenv("PUBLIC_URL") or "https://heros-du-mois-production.up.railway.app").rstrip("/")
        now = time.time()
        d1 = max(_jours_ouvres(tete["cree"], 7), _jours_ouvres(now, 5)); d2 = max(_jours_ouvres(tete["cree"], 15), _jours_ouvres(now, 10))
        cadeau_de = form.get("cadeau_de")
        fiches, images, urls = [], {}, {}
        for i, b in enumerate(livres + cals):
            folder = A.OUT / b["job_id"]
            man = json.loads((folder / "final.json").read_text(encoding="utf-8"))
            src = folder / "apercus" / "couverture.png"
            img = folder / "_mail_couverture.jpg"
            if src.exists() and not img.exists():
                im = Image.open(src).convert("RGB"); im.thumbnail((640, 640)); im.save(img, quality=88)
            cid = f"couverture{i + 1}"
            if img.exists():
                images[cid] = img; urls[cid] = f"{site}/api/livres/{b['job_id']}/apercu/couverture.png"
            fiches.append({"titre": man.get("titre") or b.get("titre") or "son livre", "n": man.get("volumeNumber") or b.get("volume_number") or i + 1,
                           "cid": cid if img.exists() else None, "cal": b["formule"] in EXTRAS, "formule": b["formule"]})
        un = len(fiches) == 1
        nl = len(livres)
        noms = ([("le livre" if nl == 1 else f"les {nl} livres")] if nl else []) + [NOMS_EXTRAS[b["formule"]] for b in cals]
        quoi = noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]
        titre_mail = (quoi[0].upper() + quoi[1:] + f" de {prenom} " + ("est prêt" if un else "sont prêts"))
        texte = (f"Bonjour,\n\n{titre_mail} :\n" + "\n".join(f"– « {f['titre']} »" + ("" if f["cal"] else f" (livre n° {f['n']})") for f in fiches) +
                 f"\n\n{'Il a été relu et part' if un else 'Ils ont été relus et partent'} maintenant à l'impression, dans un seul colis. "
                 f"Livraison estimée entre le {_date_fr(d1)} et le {_date_fr(d2)}.\n\nUne question ? Répondez simplement à ce mail.\n\n"
                 f"À très vite,\nL'équipe Mon Héros du Mois\n{site}")
        if un:
            f = fiches[0]
            visuels = (f'<img src="cid:{f["cid"]}" alt="" width="420" style="display:block;margin:0 auto 18px;width:100%;max-width:420px;border-radius:10px;'
                       f'box-shadow:0 8px 24px rgba(31,37,87,.25)">' if f["cid"] else "") + \
                      f'<p style="font-size:19px;text-align:center;margin:0 0 4px"><b>« {escape(f["titre"])} »</b></p>' \
                      f'<p style="font:14px system-ui,sans-serif;text-align:center;color:#6B6F8E;margin:0 0 22px">' \
                      f'{("Calendrier mural · 12 mois illustrés" if f["formule"] == "calendrier" else "Cahier de coloriage · 30 dessins à colorier") if f["cal"] else "Livre n° " + str(f["n"]) + " de sa collection"}' \
                      f'{(" · offert par " + escape(cadeau_de)) if cadeau_de else ""}</p>'
        else:
            cases = "".join(f'<td style="width:50%;padding:6px;vertical-align:top;text-align:center">'
                            + (f'<img src="cid:{f["cid"]}" alt="" width="250" style="width:100%;max-width:250px;border-radius:8px;box-shadow:0 6px 16px rgba(31,37,87,.2)">' if f["cid"] else "")
                            + f'<div style="font:600 13px system-ui,sans-serif;margin-top:6px">{("📅" if f["formule"] == "calendrier" else "🖍️") if f["cal"] else "n° " + str(f["n"]) + " ·"} {escape(f["titre"])}</div></td>'
                            + ("</tr><tr>" if i % 2 == 1 else "") for i, f in enumerate(fiches))
            visuels = (f'<table role="presentation" style="width:100%;border-collapse:collapse;margin:0 0 18px"><tr>{cases}</tr></table>'
                       + (f'<p style="font:14px system-ui,sans-serif;text-align:center;color:#6B6F8E;margin:0 0 22px">Offert par {escape(cadeau_de)}</p>' if cadeau_de else ""))
        html = f"""<!doctype html><html><body style="margin:0;background:#FBF5EA;font-family:Georgia,serif;color:#1F2557">
<div style="max-width:560px;margin:0 auto;padding:28px 18px">
 <p style="font:600 13px system-ui,sans-serif;letter-spacing:.12em;color:#B8892B;text-align:center;margin:0 0 6px">MON HÉROS DU MOIS</p>
 <h1 style="font-size:26px;text-align:center;margin:0 0 18px">{escape(titre_mail)}&nbsp;✨</h1>
 {visuels}
 <div style="background:#fff;border-radius:14px;padding:16px 18px;font:15px/1.5 system-ui,sans-serif">
  <p style="margin:0 0 8px">✅ {escape(quoi[0].upper() + quoi[1:])} {'a été créé et relu' if un else 'ont été créés et relus'} avec soin.</p>
  <p style="margin:0 0 8px">🖨️ {'Il part' if un else 'Ils partent'} maintenant à l'impression, dans un seul colis.</p>
  <p style="margin:0">📦 Livraison estimée <b>entre le {_date_fr(d1)} et le {_date_fr(d2)}</b>.</p>
 </div>
 <p style="font:14px system-ui,sans-serif;color:#6B6F8E;text-align:center;margin:22px 0 0">Une question&nbsp;? Répondez simplement à ce mail.<br><a href="{site}" style="color:#3D6BD8">{site.replace('https://', '')}</a></p>
</div></body></html>"""
        ok = send_mail(f"📚 {titre_mail} !", texte, reply_to=CONTACT, to=tete["email"], html=html, images=images or None, image_urls=urls)
        if not ok:
            raise RuntimeError("le service d'envoi a refusé le mail")
        log(f"commande {origine} : mail « livre prêt » envoyé à {tete['email']} ({len(fiches)} livre(s))")
        return ok
    except Exception as e:
        db.annuler_mail_pret(origine)                 # pas envoyé : il pourra repartir à la prochaine validation
        DERNIERE_ERREUR_MAIL[oid] = f"{type(e).__name__}: {e}"
        log(f"commande {origine} : mail « livre prêt » impossible : {type(e).__name__}: {e}")
        return False


def _mail_pret_async(oid):
    threading.Thread(target=mail_livre_pret, args=(oid,), daemon=True).start()


@bp.post("/api/contact")
def contact():
    d = request.get_json(force=True, silent=True) or {}
    if d.get("site"):                                     # champ piège invisible : robot
        return jsonify(ok=True)
    clean = lambda v, n: re.sub(r"[ \t]+", " ", str(v or "")).strip()[:n]
    nom, email, msg = clean(d.get("nom"), 80), clean(d.get("email"), 190), clean(d.get("message"), 3000)
    sujet = SUJETS.get(d.get("sujet"), SUJETS["question"])
    if not EMAIL.match(email):
        return jsonify(erreur="Adresse e-mail invalide."), 400
    if len(msg) < 5:
        return jsonify(erreur="Écrivez votre message."), 400
    if db.messages_recent(email, time.time() - 3600) >= 5:
        return jsonify(erreur="Trop de messages envoyés, réessayez dans une heure."), 429
    mid = db.message_add(nom, email, sujet, msg)
    try:
        if send_mail(f"[Site] {sujet} – {nom or email}", f"De : {nom} <{email}>\nSujet : {sujet}\n\n{msg}", reply_to=email):
            db.message_update(mid, envoye=1)
    except Exception:
        traceback.print_exc()
    log(f"message de contact n°{mid} ({sujet})")
    return jsonify(ok=True)


@bp.get("/admin/api/messages")
def admin_messages():
    if not admin_ok():
        abort(403)
    return jsonify(messages=db.messages(), envoi=mail_configure())
