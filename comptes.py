# -*- coding: utf-8 -*-
"""Comptes clients (facultatifs : la commande en invité reste la voie par défaut).

- Connexion sans mot de passe : lien magique envoyé par e-mail (30 min, usage unique), ou « Continuer avec Google »
  (Google Identity Services ; actif seulement si GOOGLE_CLIENT_ID est réglé dans Railway).
- Session : cookie HttpOnly aléatoire (90 jours) ; seul son empreinte SHA-256 est stockée.
- Mon compte : héros enregistrés (configuration de l'éditeur, sans aucune photo) et commandes (même e-mail ou passées connecté).
- Suppression du compte à la demande (les commandes et factures restent : obligations légales)."""
import os, re, json, time, secrets, hashlib, urllib.request, urllib.parse
from flask import Blueprint, request, jsonify, redirect, make_response, abort
import commandes as db

bp = Blueprint("comptes", __name__)
COOKIE = "mhm_session"
DUREE = 90 * 86400
LIEN_MIN = 30
MAX_HEROS = 12
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}$", re.I)

SCHEMA = """
create table if not exists clients (id text primary key, email text unique, nom text, google_sub text, cree real, vu real, adresse text);
create table if not exists sessions (empreinte text primary key, client_id text, expire real);
create table if not exists liens (empreinte text primary key, email text, expire real, utilise real, suite text);
create table if not exists heros (id text primary key, client_id text, nom text, etat text, apercu text, cree real, maj real);
"""
with db._db() as _c:
    _c.executescript(SCHEMA)


def _h(t):
    return hashlib.sha256(t.encode()).hexdigest()


def _row(r):
    return dict(r) if r else None


def google_id():
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


# ------------------------------------------------------------------ clients et sessions
def client_par_email(email, creer=True, nom=None):
    email = email.strip().lower()
    with db._lock, db._db() as c:
        r = c.execute("select * from clients where email=?", (email,)).fetchone()
        if r or not creer:
            return _row(r)
        cid = secrets.token_hex(8)
        c.execute("insert into clients (id, email, nom, cree, vu) values (?,?,?,?,?)", (cid, email, (nom or "")[:80], time.time(), time.time()))
        return _row(c.execute("select * from clients where id=?", (cid,)).fetchone())


def ouvrir_session(resp, client_id):
    t = secrets.token_urlsafe(32)
    with db._lock, db._db() as c:
        c.execute("insert into sessions values (?,?,?)", (_h(t), client_id, time.time() + DUREE))
        c.execute("update clients set vu=? where id=?", (time.time(), client_id))
        c.execute("delete from sessions where expire < ?", (time.time(),))
    resp.set_cookie(COOKIE, t, max_age=DUREE, httponly=True, samesite="Lax", secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https")
    return resp


def client_courant():
    """Client connecté (ou None). Jamais d'erreur : un cookie invalide vaut « invité »."""
    t = request.cookies.get(COOKIE)
    if not t or len(t) > 100:
        return None
    with db._db() as c:
        r = c.execute("select c.* from sessions s join clients c on c.id=s.client_id where s.empreinte=? and s.expire>?", (_h(t), time.time())).fetchone()
    return _row(r)


# ------------------------------------------------------------------ lien magique
def _suite_ok(s):
    return s if isinstance(s, str) and re.match(r"^/(creer|compte)(\?[\w=&%-]*)?$", s or "") else "/compte"


@bp.post("/api/compte/lien")
def envoyer_lien():
    import boutique as B
    d = request.get_json(force=True, silent=True) or {}
    email = str(d.get("email", "")).strip().lower()[:190]
    if not EMAIL.match(email):
        return jsonify(erreur="Adresse e-mail invalide."), 400
    if not B.mail_configure():
        return jsonify(erreur="L'envoi d'e-mails n'est pas encore configuré : réessayez plus tard ou continuez en invité."), 503
    with db._db() as c:                                   # anti-abus : 4 liens par adresse et par heure
        n = c.execute("select count(*) from liens where email=? and expire > ?", (email, time.time() + LIEN_MIN * 60 - 3600)).fetchone()[0]
    if n >= 4:
        return jsonify(erreur="Plusieurs liens ont déjà été envoyés : regardez vos e-mails (et les indésirables), ou réessayez dans une heure."), 429
    t = secrets.token_urlsafe(32)
    with db._lock, db._db() as c:
        c.execute("insert into liens values (?,?,?,?,?)", (_h(t), email, time.time() + LIEN_MIN * 60, None, _suite_ok(d.get("suite"))))
        c.execute("delete from liens where expire < ?", (time.time() - 86400,))
    site = (os.getenv("PUBLIC_URL") or request.host_url).rstrip("/")
    url = f"{site}/compte/connexion?t={urllib.parse.quote(t)}"
    texte = (f"Bonjour,\n\nPour vous connecter à votre compte Mon Héros du Mois, ouvrez ce lien (valable {LIEN_MIN} minutes) :\n{url}\n\n"
             "Vous n'avez rien demandé ? Ignorez simplement ce message.\n\nL'équipe Mon Héros du Mois")
    html = f"""<!doctype html><html><body style="margin:0;background:#FBF5EA;font-family:Georgia,serif;color:#1F2557">
<div style="max-width:520px;margin:0 auto;padding:28px 18px;text-align:center">
 <p style="text-align:center;margin:0 0 10px"><img src="{site}/static/marque/logo-mail.png" alt="Mon Héros du Mois" width="220" style="width:220px;max-width:70%;height:auto;border:0"></p>
 <h1 style="font-size:24px;margin:0 0 16px">Votre lien de connexion</h1>
 <p style="font:15px/1.5 system-ui,sans-serif;margin:0 0 22px">Touchez le bouton pour retrouver vos héros et vos commandes.<br>Il est valable {LIEN_MIN} minutes.</p>
 <a href="{url}" style="display:inline-block;background:#FFC94A;color:#1F2557;font:800 16px system-ui,sans-serif;padding:14px 26px;border-radius:999px;text-decoration:none">Me connecter</a>
 <p style="font:13px system-ui,sans-serif;color:#6B6F8E;margin:24px 0 0">Vous n'avez rien demandé ? Ignorez simplement ce message.</p>
</div></body></html>"""
    try:
        ok = B.send_mail("🔑 Votre lien de connexion Mon Héros du Mois", texte, to=email, html=html)
    except Exception as e:
        B.log(f"lien de connexion pour {email} : envoi impossible : {e}")
        ok = False
    if not ok:
        return jsonify(erreur="L'e-mail n'a pas pu partir. Réessayez dans un instant."), 502
    return jsonify(ok=True)


@bp.get("/compte/connexion")
def connexion_lien():
    t = request.args.get("t", "")
    with db._lock, db._db() as c:
        r = c.execute("select * from liens where empreinte=?", (_h(t),)).fetchone()
        if not r or r["utilise"] or r["expire"] < time.time():
            return redirect("/compte?lien=expire")
        c.execute("update liens set utilise=? where empreinte=?", (time.time(), _h(t)))
    cl = client_par_email(r["email"])
    return ouvrir_session(make_response(redirect(_suite_ok(r["suite"]))), cl["id"])


# ------------------------------------------------------------------ Google
def verifier_google(credential):
    """Jeton d'identité Google vérifié par Google (tokeninfo) : audience = notre client, e-mail vérifié."""
    cid = google_id()
    if not cid or not credential or len(credential) > 5000:
        return None
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(credential), timeout=10) as r:
            info = json.loads(r.read().decode())
    except Exception:
        return None
    if info.get("aud") != cid or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    if str(info.get("email_verified")).lower() != "true" or not info.get("email") or int(info.get("exp", 0)) < time.time():
        return None
    return info


@bp.post("/api/compte/google")
def connexion_google():
    d = request.get_json(force=True, silent=True) or {}
    info = verifier_google(str(d.get("credential", "")))
    if not info:
        return jsonify(erreur="Connexion Google refusée. Réessayez, ou recevez un lien par e-mail."), 401
    cl = client_par_email(info["email"], nom=info.get("name"))
    with db._lock, db._db() as c:
        c.execute("update clients set google_sub=coalesce(google_sub, ?), nom=coalesce(nullif(nom,''), ?) where id=?", (info.get("sub"), (info.get("name") or "")[:80], cl["id"]))
    return ouvrir_session(make_response(jsonify(ok=True, suite=_suite_ok(d.get("suite")))), cl["id"])


@bp.post("/api/compte/deconnexion")
def deconnexion():
    t = request.cookies.get(COOKIE)
    if t:
        with db._lock, db._db() as c:
            c.execute("delete from sessions where empreinte=?", (_h(t),))
    resp = make_response(jsonify(ok=True)); resp.delete_cookie(COOKIE)
    return resp


# ------------------------------------------------------------------ mon compte
STATUTS = {"payee": "En création", "generation": "En création", "a_verifier": "Relecture par notre équipe", "erreur": "Relecture par notre équipe",
           "attente_fete": "Programmé pour sa fête", "envoyee_impression": "En impression", "expediee": "Expédié", "annulee": "Annulée"}


def commandes_de(cl):
    import paiement
    out, tous = [], db.lister(100000)
    groupes = {}
    for x in tous:
        groupes.setdefault(x["origine"] or x["id"], []).append(x)
    for o in tous:
        if (o["origine"] or o["id"]) != o["id"] or (o["formule"] or "").startswith("essai") or o["statut"] == "attente_paiement":
            continue
        if (o.get("email") or "").strip().lower() != cl["email"] and o.get("client_id") != cl["id"]:
            continue
        g = groupes.get(o["id"]) or [o]
        etats = {x["statut"] for x in g}
        statut = ("Expédié" if etats <= {"expediee"} else "En impression" if etats & {"envoyee_impression", "expediee"} else
                  STATUTS.get(o["statut"], "En cours"))
        out.append({"id": o["id"], "cree": o["cree"], "montant": o["montant"],
                    "quoi": (paiement.FORMULES.get(o["formule"]) or {}).get("nom") or o["formule"],
                    "titres": [x["titre"] for x in g if x.get("titre")][:12], "statut": statut,
                    "suivi": sorted({u for x in g for u in (x.get("suivi") or []) if isinstance(u, str) and u.startswith("http")})})
    return sorted(out, key=lambda x: -x["cree"])


@bp.get("/api/compte")
def mon_compte():
    cl = client_courant()
    base = {"google": google_id() or None}
    if not cl:
        return jsonify(connecte=False, **base)
    with db._db() as c:
        hs = [dict(r) for r in c.execute("select id, nom, apercu, maj from heros where client_id=? order by maj desc", (cl["id"],))]
    return jsonify(connecte=True, email=cl["email"], nom=cl.get("nom") or "", adresse=json.loads(cl["adresse"]) if cl.get("adresse") else None,
                   heros=hs, commandes=commandes_de(cl), **base)


@bp.get("/api/compte/heros/<hid>")
def lire_heros(hid):
    cl = client_courant() or abort(401)
    with db._db() as c:
        r = c.execute("select * from heros where id=? and client_id=?", (hid, cl["id"])).fetchone()
    if not r:
        abort(404)
    return jsonify(id=r["id"], nom=r["nom"], etat=json.loads(r["etat"]))


ETAT_CLES = ("enfant", "doudou", "animaux", "fratrie", "histoire", "calendrier", "coloriage")


@bp.post("/api/compte/heros")
def enregistrer_heros():
    """Enregistre (ou met à jour, même prénom) la configuration de l'éditeur. Aucune donnée de paiement ni d'adresse."""
    cl = client_courant()
    if not cl:
        return jsonify(erreur="Connectez-vous pour enregistrer vos héros."), 401
    d = request.get_json(force=True, silent=True) or {}
    etat = {k: d["etat"][k] for k in ETAT_CLES if isinstance(d.get("etat"), dict) and k in d["etat"]}
    nom = re.sub(r"\s+", " ", str(((etat.get("enfant") or {}).get("prenom")) or "")).strip()[:30]
    if not nom:
        return jsonify(erreur="Indiquez d'abord le prénom de l'enfant."), 400
    blob = json.dumps(etat, ensure_ascii=False)
    apercu = str(d.get("apercu") or "")
    if not apercu.startswith("data:image/") or len(apercu) > 120_000:
        apercu = ""
    if len(blob) > 60_000:
        return jsonify(erreur="Configuration trop volumineuse."), 400
    with db._lock, db._db() as c:
        r = c.execute("select id from heros where client_id=? and lower(nom)=lower(?)", (cl["id"], nom)).fetchone()
        if r:
            c.execute("update heros set etat=?, apercu=coalesce(nullif(?,''), apercu), maj=? where id=?", (blob, apercu, time.time(), r["id"]))
            hid = r["id"]
        else:
            if c.execute("select count(*) from heros where client_id=?", (cl["id"],)).fetchone()[0] >= MAX_HEROS:
                return jsonify(erreur=f"{MAX_HEROS} héros au maximum : supprimez-en un dans « Mon compte »."), 400
            hid = secrets.token_hex(6)
            c.execute("insert into heros values (?,?,?,?,?,?,?)", (hid, cl["id"], nom, blob, apercu, time.time(), time.time()))
    return jsonify(ok=True, id=hid, nom=nom)


@bp.delete("/api/compte/heros/<hid>")
def supprimer_heros(hid):
    cl = client_courant() or abort(401)
    with db._lock, db._db() as c:
        c.execute("delete from heros where id=? and client_id=?", (hid, cl["id"]))
    return jsonify(ok=True)


@bp.delete("/api/compte")
def supprimer_compte():
    """Droit à l'effacement : compte, sessions et héros enregistrés. Les commandes et factures restent (obligations comptables)."""
    cl = client_courant() or abort(401)
    with db._lock, db._db() as c:
        for t in ("heros", "sessions"):
            c.execute(f"delete from {t} where client_id=?", (cl["id"],))
        c.execute("delete from clients where id=?", (cl["id"],))
    resp = make_response(jsonify(ok=True)); resp.delete_cookie(COOKIE)
    return resp


def purger_inactifs(ans=3):
    """Comptes sans connexion depuis 3 ans : supprimés avec leurs héros et sessions (les commandes restent)."""
    limite = time.time() - ans * 365 * 86400
    with db._lock, db._db() as c:
        ids = [r["id"] for r in c.execute("select id from clients where coalesce(vu, cree) < ?", (limite,))]
        for cid in ids:
            for t in ("heros", "sessions"):
                c.execute(f"delete from {t} where client_id=?", (cid,))
            c.execute("delete from clients where id=?", (cid,))
    return len(ids)


def noter_commande(oid, adresse):
    """Commande passée connecté : rattachée au compte, et l'adresse est gardée pour pré-remplir la prochaine."""
    cl = client_courant()
    if not cl:
        return
    db.update(oid, client_id=cl["id"])
    with db._lock, db._db() as c:
        c.execute("update clients set adresse=? where id=?", (json.dumps(adresse, ensure_ascii=False), cl["id"]))


@bp.get("/compte")
def page_compte():
    from pathlib import Path
    return (Path(__file__).parent / "static" / "compte.html").read_text(encoding="utf-8"), 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
