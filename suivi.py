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
from urllib.parse import urlparse, parse_qs, quote_plus
from flask import Blueprint, request, jsonify, redirect, abort
import commandes as db

bp = Blueprint("suivi", __name__)
RANG = {"visite": 0, "enfant": 1, "compagnons": 2, "creations": 3, "commande": 4, "paiement": 5}
ETAPES = ["Site visité", "Avatar commencé", "Avatar terminé", "Créations choisies", "Page commande", "Paiement lancé"]
SESSION = 30 * 60
GARDE = 400 * 86400

with db._db() as _c:
    _c.executescript("""
create table if not exists parcours (vid text primary key, client_id text, premiere real, derniere real, visites integer default 1,
  pages integer default 0, etape integer default 0, apercu integer default 0, source text, mobile integer default 0, commande text);
create table if not exists relances (cle text primary key, envoye real, email text, sujet text);
""")
    for _sql in ("alter table parcours add column campagne text",          # utm_campaign (ex. noel_oct26)
                 "alter table parcours add column ville text", "alter table parcours add column region text",
                 "alter table parcours add column pays text",              # localisation approximative (jamais l'adresse IP)
                 "alter table relances add column clic real",              # la personne a cliqué le lien du mail
                 "create table if not exists desinscrits (email text primary key, le real)"):
        try:
            _c.execute(_sql)
        except Exception:
            pass


def _secret():
    f = db.DATA / ".secret_relance"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def jeton(oid):
    return hmac.new(_secret(), f"reprendre:{oid}".encode(), hashlib.sha256).hexdigest()[:24]


def _campagne(query):
    q = parse_qs((query or "").lstrip("?"))
    return (q.get("utm_campaign") or [""])[0][:60] or None


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
    with db._db() as c:
        r0 = c.execute("select pays from parcours where vid=?", (v,)).fetchone()
    loc = None
    if not r0 or not r0["pays"]:                       # une seule fois par visiteur : ville, région, pays (l'IP n'est pas gardée)
        try:
            import geoloc
            loc = geoloc.localiser(geoloc.ip_de(request), request.headers.get("CF-IPCountry"))
        except Exception:
            loc = None
    with db._lock, db._db() as c:
        r = c.execute("select * from parcours where vid=?", (v,)).fetchone()
        if not r:
            c.execute("insert into parcours (vid, client_id, premiere, derniere, visites, pages, etape, apercu, source, mobile, campagne) values (?,?,?,?,?,?,?,?,?,?,?)",
                      (v, cl["id"] if cl else None, now, now, 1, 1, RANG.get(e, 0), int(e == "apercu"), _source(d.get("r"), d.get("u")), mobile, _campagne(d.get("u"))))
        else:
            c.execute("update parcours set derniere=?, visites=visites+?, pages=pages+1, etape=max(etape, ?), apercu=max(apercu, ?), "
                      "client_id=coalesce(?, client_id) where vid=?",
                      (now, 1 if now - (r["derniere"] or 0) > SESSION else 0, RANG.get(e, 0), int(e == "apercu"), cl["id"] if cl else None, v))
            src = _source(d.get("r"), d.get("u"))
            if src != "direct":                        # revenu par une pub ou un lien : c'est elle qu'on retient (dernier clic)
                c.execute("update parcours set source=?, campagne=? where vid=?", (src, _campagne(d.get("u")), v))
        if loc and loc.get("pays"):
            c.execute("update parcours set ville=?, region=?, pays=? where vid=?", (loc.get("ville"), loc.get("region"), loc["pays"], v))
        if secrets.randbelow(200) == 0:
            c.execute("delete from parcours where derniere < ?", (now - GARDE,))
    return ("", 204)


# ------------------------------------------------------------------ en ligne maintenant (mémoire du serveur, rien n'est gardé)
EN_LIGNE = {}            # vid -> {arrivee, vu, page, etape, mobile}
ACTIF = 120              # vu dans les 2 dernières minutes = en ligne
PAGES_NOMS = {"/": "Accueil", "/creer": "Créateur", "/compte": "Mon compte", "/tarifs": "Tarifs", "/livraison": "Livraison", "/aide": "Centre d'aide",
              "/avis-clients": "Avis clients", "/cgv": "CGV"}
ETAPES_NOMS = {"enfant": "le héros", "compagnons": "sa famille, ses animaux", "creations": "ses créations", "commande": "la commande"}


@bp.post("/api/la")
def en_ligne_ping():
    """Signe de vie d'une page ouverte (toutes les 45 s, onglet visible) : identifiant aléatoire du visiteur, page, étape du créateur."""
    d = request.get_json(force=True, silent=True) or {}
    v = str(d.get("v") or "")
    if not re.fullmatch(r"[a-f0-9]{24}", v):
        return ("", 204)
    now = time.time()
    x = EN_LIGNE.get(v)
    if not x or now - x["vu"] > 30 * 60:
        x = {"arrivee": now}
    x.update(vu=now, page=str(d.get("p") or "/")[:80], etape=str(d.get("t") or "")[:20],
             mobile=bool(re.search(r"Mobi|Android|iPhone", request.headers.get("User-Agent", ""))))
    EN_LIGNE[v] = x
    if len(EN_LIGNE) > 5000:                       # ménage : on oublie les visiteurs partis
        for k in [k for k, y in EN_LIGNE.items() if now - y["vu"] > 3600]:
            EN_LIGNE.pop(k, None)
    return ("", 204)


def en_ligne():
    now = time.time()
    act = {v: x for v, x in EN_LIGNE.items() if now - x["vu"] <= ACTIF}
    infos = {}
    if act:
        with db._db() as c:
            q = ",".join("?" * len(act))
            for r in c.execute(f"select p.vid, p.ville, p.pays, p.source, p.visites, p.etape, c.email from parcours p left join clients c on c.id=p.client_id where p.vid in ({q})", list(act)):
                infos[r["vid"]] = dict(r)
    out = []
    for v, x in sorted(act.items(), key=lambda kv: kv[1]["arrivee"]):
        i = infos.get(v, {})
        page = PAGES_NOMS.get(x["page"].split("?")[0], x["page"].split("?")[0].strip("/").replace("-", " ").capitalize() or "Accueil")
        if x["page"].startswith("/creer") and x.get("etape") in ETAPES_NOMS:
            page = f"Créateur : {ETAPES_NOMS[x['etape']]}"
        out.append({"page": page, "depuis": round(now - x["arrivee"]), "mobile": x["mobile"], "ville": i.get("ville"), "pays": i.get("pays"),
                    "source": i.get("source"), "visites": i.get("visites") or 1, "email": i.get("email")})
    return out


@bp.get("/admin/api/en-ligne")
def admin_en_ligne():
    import boutique
    if not boutique.admin_ok():
        abort(403)
    return jsonify(personnes=en_ligne(), fenetre=ACTIF)


def origine_commande(oid):
    """« facebook (pub) · noel_oct26 » : d'où venait la personne qui a commandé (None si inconnu)."""
    with db._db() as c:
        r = c.execute("select source, campagne from parcours where commande=?", (oid,)).fetchone()
    return ((r["source"] or "direct") + (" · " + r["campagne"] if r["campagne"] else "")) if r else None


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
        tous_p = [dict(r) for r in c.execute("select vid, client_id, visites, derniere, etape, apercu, commande, ville, region, pays from parcours where client_id is not null or commande is not null")]
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
    par_app = {}                                        # même entonnoir, téléphone / ordinateur
    for nom, mob in (("mobile", 1), ("ordinateur", 0)):
        Q = [p for p in P if (p["mobile"] or 0) == mob]
        par_app[nom] = [sum(1 for p in Q if p["etape"] >= i) for i in range(len(ETAPES))] + [sum(1 for p in Q if p["commande"] in {o["id"] for o in cmds if payee(o)})]
    ok_ids = {o["id"] for o in cmds if payee(o)}
    payes = sum(1 for p in P if p["commande"] in ok_ids)          # visiteurs suivis qui ont payé (même base que l'entonnoir)
    sources = {}
    for p in P:
        sources[p["source"] or "direct"] = sources.get(p["source"] or "direct", 0) + 1
    camp = {}                                          # ventes par source / campagne (utm)
    montants = {o["id"]: (o["montant"] or 0) for o in cmds if payee(o)}
    for p in P:
        k = (p["source"] or "direct") + (" · " + p["campagne"] if p.get("campagne") else "")
        x = camp.setdefault(k, {"campagne": k, "visiteurs": 0, "configurateur": 0, "paiement": 0, "payes": 0, "ca": 0})
        x["visiteurs"] += 1; x["configurateur"] += p["etape"] >= 1; x["paiement"] += p["etape"] >= 5
        if p["commande"] in montants:
            x["payes"] += 1; x["ca"] += montants[p["commande"]]
    # où sont les visiteurs (ville / région / pays approximatifs)
    def lieux(cle):
        t = {}
        for p in P:
            k = cle(p)
            if not k:
                continue
            x = t.setdefault(k, {"lieu": k, "visiteurs": 0, "configurateur": 0, "payes": 0})
            x["visiteurs"] += 1; x["configurateur"] += (p["etape"] or 0) >= 1; x["payes"] += p["commande"] in ok_ids
        return sorted(t.values(), key=lambda x: (-x["payes"], -x["visiteurs"]))[:15]
    localises = sum(1 for p in P if p.get("pays"))
    geo = {"localises": localises, "villes": lieux(lambda p: p.get("ville") and (p["ville"] + (f" ({p['region']})" if p.get("region") else ""))),
           "regions": lieux(lambda p: p.get("region") and (p["region"] + ("" if p.get("pays") == "France" else f", {p['pays']}"))),
           "pays": lieux(lambda p: p.get("pays"))}
    # clients (comptes)
    par_client = {}
    for p in tous_p:
        if p["client_id"]:
            s = par_client.setdefault(p["client_id"], {"visites": 0, "derniere": 0, "etape": 0, "apercu": 0})
            s["visites"] += p["visites"] or 0; s["derniere"] = max(s["derniere"], p["derniere"] or 0)
            s["etape"] = max(s["etape"], p["etape"] or 0); s["apercu"] = max(s["apercu"], p["apercu"] or 0)
            if p.get("ville") or p.get("pays"):
                s["lieu"] = ", ".join(x for x in (p.get("ville"), p.get("pays")) if x)
    liste = []
    for cl in clients:
        mes = [o for o in cmds if o["client_id"] == cl["id"] or (o["email"] or "").lower() == cl["email"]]
        ok = [o for o in mes if payee(o)]
        s = par_client.get(cl["id"], {})
        liste.append({"id": cl["id"], "email": cl["email"], "nom": cl["nom"], "cree": cl["cree"],
                      "derniere": max(cl["vu"] or 0, s.get("derniere") or 0), "visites": s.get("visites") or 0,
                      "etape": ETAPES[s.get("etape") or 0], "apercu": bool(s.get("apercu")), "lieu": s.get("lieu"),
                      "heros": [h["nom"] for h in heros.get(cl["id"], [])], "commandes": len(ok), "total": sum(o["montant"] or 0 for o in ok),
                      "non_payees": sum(1 for o in mes if o["statut"] == "attente_paiement"),
                      "relance": relances.get("cli:" + cl["id"]),
                      "relancable": not ok and bool(heros.get(cl["id"]))})
    # commandes non finalisées (paiement lancé mais pas payé)
    par_cmd = {p["commande"]: p for p in tous_p if p["commande"]}
    payees_emails = {(o["email"] or "").lower() for o in cmds if payee(o)}
    attente, recuperes = [], []
    for o in sorted(cmds, key=lambda o: -o["cree"]):
        if o["statut"] != "attente_paiement":
            continue
        p = par_cmd.get(o["id"]) or {}
        apres = [x for x in cmds if payee(x) and (x["email"] or "").lower() == (o["email"] or "").lower() and (x["cree"] or 0) > (o["cree"] or 0)]
        if apres:                                       # il a payé une commande depuis : plus un abandon, une vente récupérée
            recuperes.append({"id": o["id"], "email": o["email"], "prenom": _prenom(o["id"]), "commande": apres[0]["id"],
                              "relance": relances.get("cmd:" + o["id"]), "montant": apres[0]["montant"]})
            continue
        attente.append({"id": o["id"], "cree": o["cree"], "email": o["email"], "formule": o["formule"], "montant": o["montant"],
                        "prenom": _prenom(o["id"]), "visites": p.get("visites"), "apercu": bool(p.get("apercu")),
                        "lieu": ", ".join(x for x in (p.get("ville"), p.get("pays")) if x) or None,
                        "a_paye_depuis": (o["email"] or "").lower() in payees_emails,
                        "stripe": bool(o["stripe_session"]), "relance": relances.get("cmd:" + o["id"])})
    return {"jours": jours, "par_appareil": par_app, "geo": geo, "entonnoir": [{"etape": e, "n": n} for e, n in zip(ETAPES, ent)] + [{"etape": "Payé", "n": payes}],
            "sources": sorted(sources.items(), key=lambda x: -x[1])[:8],
            "campagnes": sorted(camp.values(), key=lambda x: (-x["ca"], -x["visiteurs"]))[:15],
            "visiteurs": len(P), "mobile": sum(1 for p in P if p["mobile"]), "visites": sum(p["visites"] or 0 for p in P),
            "aujourdhui": sum(1 for p in P if (p["derniere"] or 0) >= time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))),
            "pub_meta": sum(1 for p in P if re.search(r"facebook|instagram|^fb$|^ig$|^meta", (p["source"] or "").lower())),
            "clients": liste, "nouveaux_7j": sum(1 for c in clients if (c["cree"] or 0) > now - 7 * 86400),
            "clients_payants": sum(1 for c in liste if c["commandes"]),
            "attente": attente, "recuperes": recuperes, "mail": __import__("boutique").mail_configure(),
            "relances": {k: {"nom": SEGMENTS[k], "a_relancer": len(v), "stats": stats_relances()[k]} for k, v in eligibles().items()}}


def _jeton_mail(email):
    return hmac.new(_secret(), f"stop:{email.lower()}".encode(), hashlib.sha256).hexdigest()[:20]


def desinscrit(email):
    with db._db() as c:
        return bool(c.execute("select 1 from desinscrits where email=?", ((email or "").lower(),)).fetchone())


def _suivi_lien(cle, chemin, site):
    """Lien du mail passant par /rl : on sait qui a cliqué (taux de reprise), puis redirection vers la bonne page."""
    from urllib.parse import quote
    t = hmac.new(_secret(), f"rl:{cle}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{site}/rl?c={quote(cle)}&t={t}&u={quote(chemin)}"


def _mail_html(titre, intro, bouton, lien, site, stop=""):
    return f"""<!doctype html><html><body style="margin:0;background:#F7F2FF;font-family:Georgia,serif;color:#24184D">
<div style="max-width:560px;margin:0 auto;padding:28px 18px;text-align:center">
 <p style="text-align:center;margin:0 0 10px"><img src="{site}/static/marque/logo-mail.png" alt="Mon Héros du Mois" width="220" style="width:220px;max-width:70%;height:auto;border:0"></p>
 <h1 style="font-size:26px;margin:0 0 14px">{escape(titre)}</h1>
 <div style="background:#fff;border-radius:16px;padding:20px 18px;font:16px/1.5 system-ui,sans-serif;text-align:left">{intro}</div>
 <p style="margin:22px 0"><a href="{escape(lien)}" style="display:inline-block;background:#FFC23D;color:#24184D;font:800 17px system-ui,sans-serif;text-decoration:none;padding:14px 26px;border-radius:999px">{escape(bouton)}</a></p>
 <p style="font:13px system-ui,sans-serif;color:#6B6F8E;margin:0">Une question ? Répondez simplement à ce mail.<br>Vous ne recevrez pas d'autre rappel pour cette création.<br>
 {f'<a href="{escape(stop)}" style="color:#6B6F8E">Ne plus recevoir de rappel</a> · ' if stop else ''}<a href="{site}" style="color:#5A33C9">{site.replace('https://', '')}</a></p>
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
    elif genre == "ins":                                 # inscrit, mais aucun héros enregistré ni commande
        with db._db() as c:
            cl = c.execute("select * from clients where id=?", (ident,)).fetchone()
            h = c.execute("select 1 from heros where client_id=?", (ident,)).fetchone()
        if not cl or h:
            return False, "Compte introuvable, ou il a déjà un héros enregistré."
        email, lien = cl["email"], f"{site}/creer"
        sujet = "✨ Son avatar vous attend (gratuit, 3 minutes)"
        intro = ("<p style='margin:0 0 10px'>Bonjour,</p><p style='margin:0 0 10px'>Votre compte Mon Héros du Mois est prêt, mais l'avatar de votre "
                 "enfant n'est pas encore créé.</p><p style='margin:0'>En 3 minutes, gratuitement : son visage, sa coiffure, son doudou et ses animaux. "
                 "Puis il devient le héros de ses livres.</p>")
        texte = (f"Bonjour,\n\nVotre compte Mon Héros du Mois est prêt, mais l'avatar de votre enfant n'est pas encore créé.\n"
                 f"En 3 minutes, gratuitement : {lien}\n\nUne question ? Répondez simplement à ce mail. Vous ne recevrez pas d'autre rappel.\n\nL'équipe Mon Héros du Mois")
        bouton = "Créer son avatar"
    else:
        return False, "Relance inconnue."
    if desinscrit(email):
        return False, "Cette personne a demandé à ne plus recevoir de rappel."
    cle = f"{genre}:{ident}"
    chemin = lien.replace(site, "") or "/"
    lien_suivi = _suivi_lien(cle, chemin, site)
    texte = texte.replace(lien, lien_suivi)
    stop = f"{site}/stop-rappels?e={quote_plus(email)}&t={_jeton_mail(email)}"
    texte += f"\n\nNe plus recevoir de rappel : {stop}"
    try:
        ok = B.send_mail(sujet, texte, reply_to=B.CONTACT, to=email, html=_mail_html(sujet.lstrip("✨ "), intro, bouton, lien_suivi, site, stop))
    except Exception as e:
        return False, f"Envoi impossible : {e}"
    if ok:
        with db._lock, db._db() as c:
            c.execute("insert or replace into relances (cle, envoye, email, sujet) values (?,?,?,?)", (cle, time.time(), email, sujet))
        B.log(f"relance « {sujet} » envoyée à {email}")
    return bool(ok), "Relance envoyée ✉️" if ok else "Le mail n'est pas parti."


@bp.get("/rl")
def lien_relance():
    cle, t, u = request.args.get("c", ""), request.args.get("t", ""), request.args.get("u", "/")
    ok = hmac.compare_digest(t, hmac.new(_secret(), f"rl:{cle}".encode(), hashlib.sha256).hexdigest()[:16])
    if ok:
        with db._lock, db._db() as c:
            c.execute("update relances set clic=coalesce(clic, ?) where cle=?", (time.time(), cle))
        if cle.startswith("camp:"):
            __import__("campagnes").noter_clic(cle)
    if not u.startswith("/") or u.startswith("//"):
        u = "/"
    return redirect(u)


@bp.get("/stop-rappels")
def stop_rappels():
    e, t = (request.args.get("e") or "").strip().lower(), request.args.get("t", "")
    if e and hmac.compare_digest(t, _jeton_mail(e)):
        with db._lock, db._db() as c:
            c.execute("insert or replace into desinscrits values (?,?)", (e, time.time()))
            try:
                c.execute("delete from consentements where email=?", (e,))
            except Exception:
                pass
        msg = "C'est noté : vous ne recevrez plus de rappel ni de nouveautés de notre part. Les e-mails liés à vos commandes (confirmation, livraison) restent envoyés."
    else:
        msg = "Ce lien n'est pas valable."
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><link rel=stylesheet href=/static/theme.css>"
            f"<div style='max-width:520px;margin:60px auto;padding:24px;font:17px/1.6 Nunito,system-ui'><h1 style='font-family:var(--titre)'>Désinscription</h1><p>{escape(msg)}</p>"
            f"<p><a href='/'>Retour au site</a></p></div>")


SEGMENTS = {"cmd": "Paiement non fini", "cli": "Héros enregistré, sans achat", "ins": "Inscrit, sans héros"}


def eligibles():
    """Personnes à relancer par segment : jamais relancées, pas désinscrites, inactives depuis 24 h, depuis moins de 14 jours."""
    now = time.time(); mini, maxi = now - 14 * 86400, now - 86400
    with db._db() as c:
        deja = {r[0] for r in c.execute("select cle from relances")}
        stop = {r[0] for r in c.execute("select email from desinscrits")}
        payes = {(r[0] or "").lower() for r in c.execute("select email from commandes where statut not in ('attente_paiement','erreur','annulee') and montant>0")}
        cmds = [dict(r) for r in c.execute("select id, email, cree from commandes where statut='attente_paiement' and (origine is null or origine=id) and formule not like 'essai%'")]
        cls = [dict(r) for r in c.execute("select id, email, cree, vu from clients")]
        heros = {r[0]: r[1] for r in c.execute("select client_id, max(maj) from heros group by client_id")}
    out = {k: [] for k in SEGMENTS}
    for o in cmds:
        if f"cmd:{o['id']}" not in deja and mini < o["cree"] < maxi and (o["email"] or "").lower() not in stop | payes:
            out["cmd"].append({"id": o["id"], "email": o["email"]})
    for cl in cls:
        e = (cl["email"] or "").lower()
        if e in stop or e in payes:
            continue
        if cl["id"] in heros:
            if f"cli:{cl['id']}" not in deja and mini < heros[cl["id"]] < maxi:
                out["cli"].append({"id": cl["id"], "email": e})
        elif f"ins:{cl['id']}" not in deja and mini < (cl["cree"] or 0) < maxi:
            out["ins"].append({"id": cl["id"], "email": e})
    return out


def stats_relances():
    with db._db() as c:
        R = [dict(r) for r in c.execute("select * from relances")]
        payes = [dict(r) for r in c.execute("select email, cree, montant from commandes where statut not in ('attente_paiement','erreur','annulee') and montant>0")]
    out = {}
    for k in SEGMENTS:
        L = [x for x in R if x["cle"].startswith(k + ":")]
        achats = [x for x in L if any((p["email"] or "").lower() == (x["email"] or "").lower() and p["cree"] > x["envoye"] for p in payes)]
        out[k] = {"envoyees": len(L), "clics": sum(1 for x in L if x.get("clic")), "achats": len(achats)}
    return out


@bp.post("/admin/api/relance-groupe")
def admin_relance_groupe():
    import boutique as B
    if not B.admin_ok():
        abort(403)
    g = (request.get_json(force=True, silent=True) or {}).get("genre")
    if g not in SEGMENTS:
        abort(400)
    n = sum(1 for x in eligibles()[g] if relancer(g, x["id"])[0])
    return jsonify(ok=True, envoyees=n)


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
        objs, promo, pays, eb = form.get("objets") or [], form.get("code_promo"), (o.get("adresse") or {}).get("pays"), bool(form.get("ebook"))
        if paiement.total(f, pays, calendrier=avec_cal, coloriage=avec_colo, objets=objs, promo=promo, ebook=eb) != o["montant"]:
            B.log(f"reprise {oid} : montant changé depuis la commande, retour au configurateur"); return redirect("/creer")
        sid, url = paiement.checkout(oid, f, o["email"], B.base_url(), pays=pays, calendrier=paiement.avec_calendrier(f, avec_cal),
                                     coloriage=avec_colo and f != "coloriage", objets=objs, promo=promo,
                                     remise_cents=paiement.remise(f, pays, calendrier=avec_cal, coloriage=avec_colo, objets=objs, promo=promo, ebook=eb), ebook=eb)
        db.update(oid, stripe_session=sid)
        B.log(f"commande {oid} : paiement rouvert depuis la relance")
        return redirect(url)
    except Exception as e:
        B.log(f"reprise {oid} impossible : {type(e).__name__}: {e}")
        return redirect("/creer")
