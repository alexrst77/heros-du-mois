# -*- coding: utf-8 -*-
"""Commande -> paiement (Stripe) -> fabrication du livre -> relecture -> impression (Lulu) -> suivi.
Abonnements : mensuel (Stripe facture chaque mois, un livre à chaque facture payée) ou annuel (12 livres, un par mois).
Aucun appel OpenAI avant le paiement. Aucune impression sans ton accord (sauf AUTO_IMPRESSION=1)."""
import os, re, json, time, uuid, shutil, secrets, threading, traceback
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, abort, redirect, Response
import commandes as db, paiement, lulu

bp = Blueprint("boutique", __name__)
A = None                      # module app (injecté par setup)
STORE = db.DATA / "commandes"; STORE.mkdir(exist_ok=True)
MOIS = 30 * 86400
THEMES = ["La peur du noir", "La rentrée à l'école", "Apprendre à partager", "Oser se faire des amis", "La confiance en soi",
          "Gérer la colère", "Une aventure pour rire", "La patience", "Prendre soin de la nature", "Dire la vérité",
          "Essayer quelque chose de nouveau", "Aider les autres"]
UNIVERS = ["Une forêt enchantée", "L'espace et les étoiles", "Le fond de la mer", "Le temps des dinosaures",
           "Un château de chevaliers", "La jungle", "Le pôle Nord"]
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
            log(f"commande {o['id']} : fabrication interrompue, relance")
            try:
                start_book(o["id"], auto=True)
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

    oid = uuid.uuid4().hex[:12]
    folder = STORE / oid; folder.mkdir(parents=True)
    guides = A.save_avatar_pngs(data.get("avatar_png") or {}, folder)
    previews = A.save_previews(data.get("apercus") or {}, folder)
    (folder / "livre.json").write_text(json.dumps({"form": form, "guides": {k: p.name for k, p in guides.items()},
                                                   "apercus": {k: p.name for k, p in previews.items()}}, ensure_ascii=False), encoding="utf-8")
    db.create(id=oid, formule=formule, email=email, adresse=addr, statut="attente_paiement",
              montant=paiement.FORMULES[formule]["prix"], origine=oid, numero=int(form.get("numero") or 1) if str(form.get("numero", "1")).isdigit() else 1)
    if not paiement.configured():
        return jsonify(id=oid, url=f"/?commande={oid}&test=1")
    try:
        sid, url = paiement.checkout(oid, formule, email, base_url())
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
    """Paiement reçu : enregistre l'abonnement éventuel et lance la fabrication (une seule fois)."""
    if not db.transition(oid, "attente_paiement", "payee", stripe_sub=stripe_sub):
        return False
    o = db.get(oid)
    log(f"commande {oid} payée ({o['formule']})")
    f = paiement.FORMULES[o["formule"]]
    if o["formule"] != "livre":
        sid = uuid.uuid4().hex[:12]
        monthly_by_stripe = o["formule"] == "mensuel" and paiement.configured()
        db.sub_create(id=sid, commande_origine=oid, formule=o["formule"], statut="actif", email=o["email"],
                      livres_restants=(f["livres"] - 1) if f["livres"] else None, numero=o["numero"],
                      prochain=None if monthly_by_stripe else time.time() + MOIS, stripe_sub=stripe_sub)
        db.update(oid, abonnement_id=sid)
    start_book(oid, auto=True)        # le client a fini : la création se fait de notre côté, sans validation de sa part
    return True


def start_book(oid, auto=False):
    o = db.get(oid)
    form, refs = load_book(o["origine"])
    if o["origine"] != oid:                       # livre du mois suivant : nouveau thème, nouvel univers
        n = o["numero"]
        form = dict(form, numero=f"{n:02d}", theme=THEMES[(THEMES.index(form["theme"]) + n - 1) % len(THEMES)] if form.get("theme") in THEMES else THEMES[n % len(THEMES)],
                    univers=UNIVERS[(UNIVERS.index(form["univers"]) + n - 1) % len(UNIVERS)] if form.get("univers") in UNIVERS else UNIVERS[n % len(UNIVERS)])
        form.pop("precision", None)               # le mot du parent concernait le premier livre
    else:
        form = dict(form, numero=f"{o['numero']:02d}")
    job_id = oid
    folder = A.OUT / job_id
    shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
    (folder / ".commande").write_text(oid)
    db.update(oid, statut="generation", job_id=job_id, erreur=None)
    A.start_job(job_id, form, refs, auto=auto, on_end=lambda j, job: book_done(oid, job))


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
    log(f"commande {oid} : livre prêt « {job['titre']} », à relire")
    if auto_print() and not job.get("controle"):
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
    return jsonify(id=oid, statut=o["statut"], formule=o["formule"], job=o["job_id"], titre=o["titre"],
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
            if s and s["statut"] == "actif":
                next_book(s)
        elif t == "customer.subscription.deleted":
            s = db.sub_find(stripe_sub=o.get("id"))
            if s:
                db.sub_update(s["id"], statut="arrete")
    except Exception:
        traceback.print_exc()
        return jsonify(erreur="traitement"), 500
    return jsonify(ok=True)


def next_book(s):
    """Livre du mois suivant d'un abonnement (numéro +1), fabriqué sans validation du parent."""
    n = (s["numero"] or 1) + 1
    oid = uuid.uuid4().hex[:12]
    o = db.get(s["commande_origine"])
    db.create(id=oid, formule=s["formule"], email=o["email"], adresse=o["adresse"], statut="payee", montant=0,
              abonnement_id=s["id"], origine=s["commande_origine"], numero=n, stripe_sub=s["stripe_sub"])
    left = s["livres_restants"] - 1 if s["livres_restants"] is not None else None
    db.sub_update(s["id"], numero=n, livres_restants=left,
                  prochain=(time.time() + MOIS) if s["prochain"] is not None and (left is None or left > 0) else None,
                  statut="termine" if left == 0 else s["statut"])
    log(f"abonnement {s['id']} : livre n°{n} (commande {oid})")
    start_book(oid, auto=True)
    return oid


def _scheduler():
    """Toutes les heures : livres du mois des abonnements annuels, et suivi des impressions Lulu."""
    while True:
        time.sleep(int(os.getenv("SCHEDULER_SECONDS", "3600")))
        try:
            for s in db.due_subs():
                next_book(s)
            purge_old()
            if lulu.configured():
                for o in db.lister(statut="envoyee_impression"):
                    refresh_print(o["id"])
        except Exception:
            traceback.print_exc()


def purge_old(days=int(os.getenv("PURGE_JOURS", "30"))):
    """Livres expédiés depuis plus de `days` jours : fichiers effacés (données de l'enfant, place disque)."""
    limit = time.time() - days * 86400
    for o in db.lister(1000, statut="expediee"):
        if o["maj"] < limit and o["job_id"] and (A.OUT / o["job_id"]).exists():
            shutil.rmtree(A.OUT / o["job_id"], ignore_errors=True)
            db.update(o["id"], pdf=None)


# ------------------------------------------------------------------ impression
def build_cover(oid):
    """Couverture Lulu en une pièce (4e | tranche | 1re) aux dimensions données par Lulu pour 24 pages."""
    o = db.get(oid)
    folder = A.OUT / o["job_id"]
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


def send_to_print(oid):
    o = db.get(oid)
    if o["statut"] not in ("a_verifier", "erreur") or not o["job_id"]:
        raise RuntimeError(f"statut {o['statut']} : rien à imprimer")
    if not lulu.configured():
        raise RuntimeError("Clés Lulu absentes (.env : LULU_CLIENT_KEY, LULU_CLIENT_SECRET).")
    pub = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not pub.startswith("https://"):
        raise RuntimeError("Lulu doit télécharger les PDF : renseigne PUBLIC_URL (adresse https publique du site).")
    folder = A.OUT / o["job_id"]
    if not (folder / "impression_interieur.pdf").exists():
        raise RuntimeError("impression_interieur.pdf introuvable")
    build_cover(oid)
    jeton = o["jeton"] or secrets.token_urlsafe(24)
    db.update(oid, jeton=jeton)
    cost = lulu.cost(24, o["adresse"], o["email"])
    job = lulu.create_print_job(oid, o["titre"] or "Mon Héros du Mois",
                                f"{pub}/impression/{oid}/{jeton}/interieur.pdf", f"{pub}/impression/{oid}/{jeton}/couverture.pdf",
                                o["adresse"], o["email"])
    st = (job.get("status") or {}).get("name")
    db.update(oid, statut="envoyee_impression", lulu_id=str(job.get("id")), lulu_statut=st,
              lulu_cout=f"{cost['total_ttc']} {cost['devise']}", erreur=None)
    log(f"commande {oid} envoyée à Lulu ({lulu.env()}) : travail {job.get('id')}, {cost['total_ttc']} {cost['devise']}")
    return job


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
        r["fichiers"] = [p.name for p in (A.OUT / (r["job_id"] or "_")).glob("*.pdf")] + \
                        (["controle.json"] if (A.OUT / (r["job_id"] or "_") / "controle.json").exists() else [])
    return jsonify(commandes=rows, abonnements=db.subs(),
                   config={"stripe": "live" if paiement.live() else "test" if paiement.configured() else "simulé",
                           "lulu": lulu.env() if lulu.configured() else "non configuré", "pod": lulu.POD_PACKAGE,
                           "public_url": os.getenv("PUBLIC_URL", ""), "auto_impression": auto_print()})


@bp.get("/admin/fichier/<oid>/<name>")
def admin_file(oid, name):
    if not admin_ok():
        abort(403)
    o = db.get(oid) or abort(404)
    if not re.match(r"^[\w\-. ]+\.(pdf|json|png)$", name) or "/" in name:
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
        for p in sorted(folder.iterdir()):
            if p.is_file() and not p.name.startswith("impression_"):
                z.write(p, f"livre_{oid}/{p.name}")
        for p in (STORE / o["origine"]).glob("*"):
            z.write(p, f"livre_{oid}/commande/{p.name}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"livre_{oid}.zip")


@bp.post("/admin/api/<oid>/<action>")
def admin_action(oid, action):
    if not admin_ok():
        abort(403)
    o = db.get(oid) or abort(404)
    try:
        if action == "couverture":
            return jsonify(ok=True, info=build_cover(oid))
        if action == "cout":
            return jsonify(ok=True, info=lulu.cost(24, o["adresse"], o["email"]))
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
            start_book(oid, auto=True)
            return jsonify(ok=True)
        if action == "valider-paiement-test" and not paiement.configured():
            confirm_paid(oid)
            return jsonify(ok=True)
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
        abort(404)
    except (RuntimeError, lulu.LuluError, paiement.StripeError) as e:
        return jsonify(erreur=str(e)), 400


@bp.get("/cgv")
def cgv():
    return send_file(A.ROOT / "static" / "cgv.html")
