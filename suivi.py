# -*- coding: utf-8 -*-
"""Suivi des visiteurs et relances (onglet « Clients » de l'admin).

- Parcours : mesure d'audience interne, sans cookie tiers ni outil externe. Chaque navigateur reçoit un identifiant aléatoire
  (localStorage « mhm-v », aucune donnée personnelle) ; on garde seulement : nombre de visites, pages vues, étape la plus loin
  atteinte dans le configurateur, aperçu demandé, source (site d'origine). Rattaché à un compte si la personne est connectée,
  et à la commande si elle lance le paiement (pour savoir où les gens s'arrêtent). Effacé après 13 mois.
- Relances : UN seul e-mail « finis ton univers », envoyé à la main par Alex depuis l'admin :
  commande non payée (lien qui rouvre directement le paiement), ou compte avec un héros enregistré mais sans commande."""
import os, re, json, time, hmac, hashlib, secrets
from html import escape
from urllib.parse import urlparse, parse_qs
from flask import Blueprint, request, jsonify, redirect, abort
import commandes as db

bp = Blueprint("suivi", __name__)
RANG = {"visite": 0, "enfant": 1, "compagnons": 2, "creations": 3, "commande": 4, "paiement": 5}
ETAPES = ["Site visité", "Configurateur ouvert", "Famille et animaux", "Créations choisies", "Page commande", "Paiement lancé"]
SESSION = 30 * 60
GARDE = 400 * 86400

with db._db() as _c:
    _c.executescript("""
create table if not exists parcours (vid text primary key, client_id text, premiere real, derniere real, visites integer default 1,
  pages integer default 0, etape integer default 0, apercu integer default 0, source text, mobile integer default 0, commande text);
create table if not exists relances (cle text primary key, envoye real, email text, sujet text);
""")


def _secret():
    f = db.DATA / ".secret_relance"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def jeton(oid):
    return hmac.new(_secret(), f"reprendre:{oid}".encode(), hashlib.sha256).hexdigest()[:24]


def _source(ref, query):
    q = parse_qs((query or "").lstrip("?"))
    for k in ("utm_source", "fbclid", "gclid"):
        if q.get(k):
            return {"fbclid": "facebook (pub)", "gclid": "google (pub)"}.get(k, q[k][0][:40])
    h = (urlparse(ref or "").hostname or "").lower().removeprefix("www.")
    if not h or "monherosdumois" in h or "railway.app" in h or h in ("localhost", "127.0.0.1"):
        return "direct"
    return h[:60]


@bp.post("/api/p")
def evenement():
    d = request.get_json(force=True, silent=True) or {}
    v, e = str(d.get("v") or ""), str(d.get("e") or "")
    if not re.fullmatch(r"[a-f0-9]{24}", v) or e not in RANG and e != "apercu":
        return ("", 204)
    import comptes
    try:
        cl = comptes.client_courant()
    except Exception:
        cl = None
    now = time.time()
    mobile = 1 if re.search(r"Mobi|Android|iPhone", request.headers.get("User-Agent", "")) else 0
    with db._lock, db._db() as c:
        r = c.execute("select * from parcours where vid=?", (v,)).fetchone()
        if not r:
            c.execute("insert into parcours (vid, client_id, premiere, derniere, visites, pages, etape, apercu, source, mobile) values (?,?,?,?,?,?,?,?,?,?)",
                      (v, cl["id"] if cl else None, now, now, 1, 1, RANG.get(e, 0), int(e == "apercu"), _source(d.get("r"), d.get("u")), mobile))
        else:
            c.execute("update parcours set derniere=?, visites=visites+?, pages=pages+1, etape=max(etape, ?), apercu=max(apercu, ?), "
                      "client_id=coalesce(?, client_id) where vid=?",
                      (now, 1 if now - (r["derniere"] or 0) > SESSION else 0, RANG.get(e, 0), int(e == "apercu"), cl["id"] if cl else None, v))
        if secrets.randbelow(200) == 0:
            c.execute("delete from parcours where derniere < ?", (now - GARDE,))
    return ("", 204)


def noter_paiement(vid, oid):
    """La personne lance le paiement : étape 5 et commande rattachée à son parcours."""
    if not re.fullmatch(r"[a-f0-9]{24}", str(vid or "")):
        return
    now = time.time()
    with db._lock, db._db() as c:
        if c.execute("update parcours set etape=max(etape, 5), commande=?, derniere=? where vid=?", (oid, now, vid)).rowcount == 0:
            c.execute("insert into parcours (vid, premiere, derniere, visites, pages, etape, source, commande) values (?,?,?,?,?,?,?,?)",
                      (vid, now, now, 1, 1, 5, "direct", oid))


# ------------------------------------------------------------------ admin
def _prenom(oid):
    import boutique as B
    try:
        return json.loads((B.STORE / oid / "livre.json").read_text(encoding="utf-8"))["form"].get("prenom")
    except Exception:
        return None


def donnees(jours=30):
    now = time.time(); depuis = now - jours * 86400
    with db._db() as c:
        P = [dict(r) for r in c.execute("select * from parcours where derniere > ?", (depuis,))]
        tous_p = [dict(r) for r in c.execute("select vid, client_id, visites, derniere, etape, apercu, commande from parcours where client_id is not null or commande is not null")]
        clients = [dict(r) for r in c.execute("select * from clients order by cree desc")]
        heros = {}
        for r in c.execute("select client_id, nom, maj from heros order by maj desc"):
            heros.setdefault(r["client_id"], []).append({"nom": r["nom"], "maj": r["maj"]})
        cmds = [dict(r) for r in c.execute("select id, cree, email, formule, statut, montant, client_id, origine, stripe_session from commandes "
                                           "where (origine is null or origine = id) and formule not like 'essai%'")]
        relances = {r["cle"]: r["envoye"] for r in c.execute("select cle, envoye from relances")}
    import factures
    payee = lambda o: o["statut"] not in ("attente_paiement", "erreur", "annulee") and bool(o["montant"])
    reel = lambda o: payee(o) and (factures.paiement_reel(o) if hasattr(factures, "paiement_reel") else True)
    # entonnoir : visiteurs uniques des N derniers jours, étape la plus loin atteinte
    ent = [sum(1 for p in P if p["etape"] >= i) for i in range(len(ETAPES))]
    ok_ids = {o["id"] for o in cmds if payee(o)}
    payes = sum(1 for p in P if p["commande"] in ok_ids)          # visiteurs suivis qui ont payé (même base que l'entonnoir)
    sources = {}
    for p in P:
        sources[p["source"] or "direct"] = sources.get(p["source"] or "direct", 0) + 1
    # clients (comptes)
    par_client = {}
    for p in tous_p:
        if p["client_id"]:
            s = par_client.setdefault(p["client_id"], {"visites": 0, "derniere": 0, "etape": 0, "apercu": 0})
            s["visites"] += p["visites"] or 0; s["derniere"] = max(s["derniere"], p["derniere"] or 0)
            s["etape"] = max(s["etape"], p["etape"] or 0); s["apercu"] = max(s["apercu"], p["apercu"] or 0)
    liste = []
    for cl in clients:
        mes = [o for o in cmds if o["client_id"] == cl["id"] or (o["email"] or "").lower() == cl["email"]]
        ok = [o for o in mes if payee(o)]
        s = par_client.get(cl["id"], {})
        liste.append({"id": cl["id"], "email": cl["email"], "nom": cl["nom"], "cree": cl["cree"],
                      "derniere": max(cl["vu"] or 0, s.get("derniere") or 0), "visites": s.get("visites") or 0,
                      "etape": ETAPES[s.get("etape") or 0], "apercu": bool(s.get("apercu")),
                      "heros": [h["nom"] for h in heros.get(cl["id"], [])], "commandes": len(ok), "total": sum(o["montant"] or 0 for o in ok),
                      "non_payees": sum(1 for o in mes if o["statut"] == "attente_paiement"),
                      "relance": relances.get("cli:" + cl["id"]),
                      "relancable": not ok and bool(heros.get(cl["id"]))})
    # commandes non finalisées (paiement lancé mais pas payé)
    par_cmd = {p["commande"]: p for p in tous_p if p["commande"]}
    payees_emails = {(o["email"] or "").lower() for o in cmds if payee(o)}
    attente = []
    for o in sorted(cmds, key=lambda o: -o["cree"]):
        if o["statut"] != "attente_paiement":
            continue
        p = par_cmd.get(o["id"]) or {}
        attente.append({"id": o["id"], "cree": o["cree"], "email": o["email"], "formule": o["formule"], "montant": o["montant"],
                        "prenom": _prenom(o["id"]), "visites": p.get("visites"), "apercu": bool(p.get("apercu")),
                        "a_paye_depuis": (o["email"] or "").lower() in payees_emails,
                        "stripe": bool(o["stripe_session"]), "relance": relances.get("cmd:" + o["id"])})
    return {"jours": jours, "entonnoir": [{"etape": e, "n": n} for e, n in zip(ETAPES, ent)] + [{"etape": "Payé", "n": payes}],
            "sources": sorted(sources.items(), key=lambda x: -x[1])[:8],
            "visiteurs": len(P), "mobile": sum(1 for p in P if p["mobile"]),
            "clients": liste, "nouveaux_7j": sum(1 for c in clients if (c["cree"] or 0) > now - 7 * 86400),
            "clients_payants": sum(1 for c in liste if c["commandes"]),
            "attente": attente, "mail": __import__("boutique").mail_configure()}


def _mail_html(titre, intro, bouton, lien, site):
    return f"""<!doctype html><html><body style="margin:0;background:#F7F2FF;font-family:Georgia,serif;color:#24184D">
<div style="max-width:560px;margin:0 auto;padding:28px 18px;text-align:center">
 <p style="font:700 13px system-ui,sans-serif;letter-spacing:.12em;color:#5A33C9;margin:0 0 8px">MON HÉROS DU MOIS</p>
 <h1 style="font-size:26px;margin:0 0 14px">{escape(titre)}</h1>
 <div style="background:#fff;border-radius:16px;padding:20px 18px;font:16px/1.5 system-ui,sans-serif;text-align:left">{intro}</div>
 <p style="margin:22px 0"><a href="{escape(lien)}" style="display:inline-block;background:#FFC23D;color:#24184D;font:800 17px system-ui,sans-serif;text-decoration:none;padding:14px 26px;border-radius:999px">{escape(bouton)}</a></p>
 <p style="font:13px system-ui,sans-serif;color:#6B6F8E;margin:0">Une question ? Répondez simplement à ce mail.<br>Vous ne recevrez pas d'autre rappel pour cette création.<br>
 <a href="{site}" style="color:#5A33C9">{site.replace('https://', '')}</a></p>
</div></body></html>"""


def relancer(genre, ident):
    """Envoie LA relance (une seule par commande ou par compte). Renvoie (ok, message)."""
    import boutique as B
    site = (os.getenv("PUBLIC_URL") or "https://www.monherosdumois.fr").rstrip("/")
    if not B.mail_configure():
        return False, "Aucun envoi de mail configuré (BREVO_API_KEY dans Railway)."
    with db._db() as c:
        if c.execute("select 1 from relances where cle=?", (f"{genre}:{ident}",)).fetchone():
            return False, "Déjà relancé : une seule relance par création."
    if genre == "cmd":
        o = db.get(ident)
        if not o or o["statut"] != "attente_paiement" or not o.get("email"):
            return False, "Cette commande n'attend plus de paiement."
        prenom = _prenom(ident) or "votre enfant"
        lien = f"{site}/reprendre/{ident}?j={jeton(ident)}"
        sujet = f"✨ L'univers de {prenom} vous attend"
        intro = (f"<p style='margin:0 0 10px'>Bonjour,</p><p style='margin:0 0 10px'>Vous avez créé l'univers de <b>{escape(prenom)}</b> sur Mon Héros du Mois, "
                 f"mais la commande ne s'est pas terminée.</p><p style='margin:0'>Tout est gardé : personnages, histoires et adresse. "
                 f"Il ne reste que le paiement, en un clic.</p>")
        texte = (f"Bonjour,\n\nVous avez créé l'univers de {prenom} sur Mon Héros du Mois, mais la commande ne s'est pas terminée.\n"
                 f"Tout est gardé : personnages, histoires et adresse. Il ne reste que le paiement :\n{lien}\n\n"
                 f"Une question ? Répondez simplement à ce mail. Vous ne recevrez pas d'autre rappel pour cette création.\n\nL'équipe Mon Héros du Mois")
        email, bouton = o["email"], f"Finir l'univers de {prenom}"
    elif genre == "cli":
        with db._db() as c:
            cl = c.execute("select * from clients where id=?", (ident,)).fetchone()
            h = c.execute("select nom from heros where client_id=? order by maj desc", (ident,)).fetchone()
        if not cl or not h:
            return False, "Compte introuvable ou sans héros enregistré."
        prenom, email, lien = h["nom"] or "votre héros", cl["email"], f"{site}/compte"
        sujet = f"✨ {prenom} attend la suite de son aventure"
        intro = (f"<p style='margin:0 0 10px'>Bonjour,</p><p style='margin:0 0 10px'><b>{escape(prenom)}</b> est enregistré dans votre compte "
                 f"Mon Héros du Mois, prêt pour l'aventure.</p><p style='margin:0'>Retrouvez-le en un clic pour voir sa couverture et finir son univers.</p>")
        texte = (f"Bonjour,\n\n{prenom} est enregistré dans votre compte Mon Héros du Mois, prêt pour l'aventure.\n"
                 f"Retrouvez-le pour finir son univers : {lien}\n\nUne question ? Répondez simplement à ce mail. "
                 f"Vous ne recevrez pas d'autre rappel.\n\nL'équipe Mon Héros du Mois")
        bouton = f"Retrouver {prenom}"
    else:
        return False, "Relance inconnue."
    try:
        ok = B.send_mail(sujet, texte, reply_to=B.CONTACT, to=email, html=_mail_html(sujet.lstrip("✨ "), intro, bouton, lien, site))
    except Exception as e:
        return False, f"Envoi impossible : {e}"
    if ok:
        with db._lock, db._db() as c:
            c.execute("insert or replace into relances values (?,?,?,?)", (f"{genre}:{ident}", time.time(), email, sujet))
        B.log(f"relance « {sujet} » envoyée à {email}")
    return bool(ok), "Relance envoyée ✉️" if ok else "Le mail n'est pas parti."


@bp.get("/admin/api/clients")
def admin_clients():
    import boutique as B
    if not B.admin_ok():
        abort(403)
    return jsonify(donnees(int(request.args.get("jours") or 30)))


@bp.post("/admin/api/relance")
def admin_relance():
    import boutique as B
    if not B.admin_ok():
        abort(403)
    d = request.get_json(force=True, silent=True) or {}
    ok, msg = relancer(str(d.get("genre") or ""), str(d.get("id") or "")[:32])
    return jsonify(ok=ok, message=msg), (200 if ok else 400)


@bp.get("/reprendre/<oid>")
def reprendre(oid):
    """Lien de la relance : rouvre le paiement de la commande telle qu'elle a été composée (même montant, mêmes créations)."""
    import boutique as B, paiement
    if not re.fullmatch(r"[a-f0-9]{12}", oid) or not hmac.compare_digest(request.args.get("j", ""), jeton(oid)):
        abort(404)
    o = db.get(oid) or abort(404)
    if o["statut"] != "attente_paiement":
        return redirect(f"/creer?commande={oid}")
    if not paiement.configured():
        return redirect("/creer")
    try:
        d = json.loads((B.STORE / oid / "livre.json").read_text(encoding="utf-8"))
        form = d["form"]; f = o["formule"]
        avec_cal = f == "calendrier" or bool(form.get("calendrier"))
        avec_colo = f == "coloriage" or bool(form.get("coloriage"))
        objs, promo, pays = form.get("objets") or [], form.get("code_promo"), (o.get("adresse") or {}).get("pays")
        if paiement.total(f, pays, calendrier=avec_cal, coloriage=avec_colo, objets=objs, promo=promo) != o["montant"]:
            B.log(f"reprise {oid} : montant changé depuis la commande, retour au configurateur"); return redirect("/creer")
        sid, url = paiement.checkout(oid, f, o["email"], B.base_url(), pays=pays, calendrier=paiement.avec_calendrier(f, avec_cal),
                                     coloriage=avec_colo and f != "coloriage", objets=objs, promo=promo,
                                     remise_cents=paiement.remise(f, pays, calendrier=avec_cal, coloriage=avec_colo, objets=objs, promo=promo))
        db.update(oid, stripe_session=sid)
        B.log(f"commande {oid} : paiement rouvert depuis la relance")
        return redirect(url)
    except Exception as e:
        B.log(f"reprise {oid} impossible : {type(e).__name__}: {e}")
        return redirect("/creer")
