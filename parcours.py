# -*- coding: utf-8 -*-
"""Parcours « Créer son livre » : brouillon -> achat du livre numérique -> génération -> relecture -> livre relié (avec déduction).

Modèle de données (tables ajoutées, aucune table existante modifiée sauf une colonne « quantite » dans commandes) :
- projets    : le brouillon puis le livre (choix du configurateur), accès par jeton secret et/ou par le compte client ;
- photos     : photos privées (fichier hors du dossier public), consentement daté, suppression à la demande ou après PHOTO_JOURS ;
- credits    : montant numérique réellement payé, lié au projet et à SA commande numérique ; utilisable UNE fois (réservé au paiement
               du livre relié, consommé au paiement confirmé, libéré si le paiement est abandonné, annulé si le numérique est remboursé) ;
- versions   : versions du livre après corrections de texte (la v1 est le livre généré, jamais modifiée) ;
- corrections: demandes de retouche d'illustration (limitées, traitées depuis l'admin) ;
- etapes_stats : passages par étape du configurateur, SANS aucune donnée personnelle (ni texte, ni photo, ni prénom).

Les prix, les droits d'accès et la déduction sont calculés ici, côté serveur."""
import os, re, json, time, uuid, secrets, hashlib, hmac, shutil, threading, io
from pathlib import Path
from flask import Blueprint, request, jsonify, abort, send_file, redirect
import commandes as db
import catalogue as C
import paiement

bp = Blueprint("parcours", __name__)
PHOTOS = db.DATA / "photos_privees"; PHOTOS.mkdir(parents=True, exist_ok=True)
MAX_DONNEES = 60000
ETAPES = ["age", "theme", "sujet", "message", "heros", "personnages", "style", "police", "cherche", "langue", "evenements", "dedicace", "recap",
          "paiement"]

SCHEMA = """
create table if not exists projets (id text primary key, jeton text, client_id text, email text, cree real, maj real, statut text,
  etape text, donnees text, commande_numerique text, titre text);
create table if not exists photos (id text primary key, projet_id text, role text, fichier text, cree real, consentement real, supprime real);
create table if not exists credits (id text primary key, projet_id text, commande_numerique text unique, montant integer, cree real,
  statut text, commande_papier text, maj real);
create table if not exists versions (id text primary key, projet_id text, numero integer, cree real, motif text, fichier text, pdf text);
create table if not exists corrections (id text primary key, projet_id text, page integer, demande text, statut text, cree real, reponse text, fichier text);
create table if not exists etapes_stats (jour text, etape text, visiteur text, primary key (jour, etape, visiteur));
"""
with db._db() as _c:
    _c.executescript(SCHEMA)
    for _t, _col in (("commandes", "quantite integer"), ("commandes", "projet_id text")):
        try:
            _c.execute(f"alter table {_t} add column {_col}")
        except Exception:
            pass


def log(m):
    try:
        import boutique
        boutique.log(m)
    except Exception:
        print(m)


def _row(r, json_cols=("donnees",)):
    if r is None:
        return None
    d = dict(r)
    for k in json_cols:
        if k in d:
            d[k] = json.loads(d[k]) if d[k] else {}
    return d


# ------------------------------------------------------------------ accès
def get(pid):
    with db._db() as c:
        return _row(c.execute("select * from projets where id=?", (pid,)).fetchone())


def _client():
    try:
        import comptes
        return comptes.client_courant()
    except Exception:
        return None


def autorise(p, jeton=None):
    """Le projet appartient-il à la personne qui le demande ? Jeton secret du brouillon, ou compte client rattaché."""
    if not p:
        return False
    j = jeton if jeton is not None else (request.args.get("j") or request.headers.get("X-Projet-Jeton") or "")
    if j and hmac.compare_digest(str(j), p["jeton"] or ""):
        return True
    cl = _client()
    return bool(cl and p.get("client_id") and cl["id"] == p["client_id"])


def charger(pid, jeton=None):
    if not re.fullmatch(r"[a-f0-9]{16}", pid or ""):
        abort(404)
    p = get(pid)
    if not autorise(p, jeton):
        abort(404)                         # jamais « interdit » : on ne confirme pas qu'un projet existe
    return p


def maj(pid, **kw):
    kw["maj"] = time.time()
    if "donnees" in kw:
        kw["donnees"] = json.dumps(kw["donnees"], ensure_ascii=False)
    with db._lock, db._db() as c:
        c.execute(f"update projets set {','.join(k + '=?' for k in kw)} where id=?", (*kw.values(), pid))
    return get(pid)


def lien(p, chemin="/creer"):
    site = (os.getenv("PUBLIC_URL") or request.host_url).rstrip("/")
    return f"{site}{chemin}?projet={p['id']}&j={p['jeton']}" if chemin == "/creer" else f"{site}{chemin}/{p['id']}?j={p['jeton']}"


# ------------------------------------------------------------------ catalogue
@bp.get("/api/catalogue")
def api_catalogue():
    out = C.public()
    out["prix"] = prix_public()
    return jsonify(out)


def prix_public():
    """Prix affichés AVANT le premier paiement (aucun prix inventé : ceux de paiement.py)."""
    num = paiement.FORMULES["ebook"]["prix"]
    relie = paiement.FORMULES["relie"]["prix_livre"]
    return {"numerique": num, "relie": relie, "complement": max(0, relie - num), "port_fr_1": paiement.port_relie(1, "FR"),
            "port_fr_3": paiement.port_relie(3, "FR"), "supplement_pays": paiement.SUPPLEMENT_PAYS, "quantites": list(paiement.QUANTITES_RELIE),
            "pages": {"histoire": 18, "lecture": 20, "impression": 24}}


# ------------------------------------------------------------------ brouillon
@bp.post("/api/projets")
def creer():
    cl = _client()
    pid = secrets.token_hex(8)
    jeton = secrets.token_urlsafe(24)
    d = request.get_json(force=True, silent=True) or {}
    donnees = nettoyer(d.get("donnees") or {})
    with db._lock, db._db() as c:
        c.execute("insert into projets (id, jeton, client_id, email, cree, maj, statut, etape, donnees) values (?,?,?,?,?,?,?,?,?)",
                  (pid, jeton, cl["id"] if cl else None, cl["email"] if cl else None, time.time(), time.time(), "brouillon",
                   str(d.get("etape") or "age")[:20], json.dumps(donnees, ensure_ascii=False)))
    return jsonify(id=pid, jeton=jeton, lien=lien(get(pid)))


@bp.get("/api/projets/<pid>")
def lire(pid):
    p = charger(pid)
    return jsonify(public_projet(p))


def public_projet(p):
    d = dict(p["donnees"] or {})
    return {"id": p["id"], "statut": p["statut"], "etape": p["etape"], "donnees": d, "a_revoir": C.valider(d),
            "commande": p.get("commande_numerique"), "photos": photos_de(p["id"])}


@bp.put("/api/projets/<pid>")
def enregistrer(pid):
    """Sauvegarde automatique du brouillon. Après l'achat, les choix sont figés (le livre se corrige dans « Mon livre »)."""
    p = charger(pid)
    if p["statut"] != "brouillon":
        return jsonify(erreur="Ce livre est déjà commandé : ses choix sont enregistrés. Les corrections se font dans « Mon livre »."), 409
    d = request.get_json(force=True, silent=True) or {}
    brut = json.dumps(d.get("donnees") or {}, ensure_ascii=False)
    if len(brut) > MAX_DONNEES:
        return jsonify(erreur="Projet trop volumineux."), 413
    donnees = nettoyer(d.get("donnees") or {})
    etape = d.get("etape") if d.get("etape") in ETAPES else p["etape"]
    cl = _client()
    kw = {"donnees": donnees, "etape": etape}
    if cl and not p.get("client_id"):                       # connecté en cours de route : le brouillon est rattaché au compte
        kw.update(client_id=cl["id"], email=cl["email"])
    maj(pid, **kw)
    noter_etape(etape)
    return jsonify(ok=True, a_revoir=C.valider(donnees))


def _txt(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _multi(v, n):
    """Texte sur plusieurs lignes (dédicace, souvenirs) : lignes gardées, espaces nettoyés."""
    lignes = [re.sub(r"[ \t]+", " ", x).strip() for x in str(v or "").replace("\r", "").split("\n")]
    return "\n".join(lignes).strip()[:n]


def nettoyer(d):
    """Ne garde que les champs connus, bornés. Les identifiants d'options sont vérifiés plus tard contre le catalogue (C.valider)."""
    d = d if isinstance(d, dict) else {}
    out = {k: _txt(d.get(k), 40) for k in ("age_lecteur", "theme", "sujet", "message", "style", "police", "cherche", "langue") if d.get(k)}
    h = d.get("heros") if isinstance(d.get("heros"), dict) else {}
    out["heros"] = {"prenom": _txt(h.get("prenom"), 20), "age": _txt(h.get("age"), 3), "genre": h.get("genre") if h.get("genre") in ("fille", "garcon") else "",
                    "pronoms": h.get("pronoms") if h.get("pronoms") in ("il", "elle", "prenom") else "",
                    "passions": _txt(h.get("passions"), 120), "plat": _txt(h.get("plat"), 60), "details": _txt(h.get("details"), 120),
                    "voie": h.get("voie") if h.get("voie") in ("avatar", "photo") else "",
                    "avatar": h.get("avatar") if isinstance(h.get("avatar"), dict) else None,
                    "photo": _txt(h.get("photo"), 20)}
    perso = []
    for x in (d.get("personnages") or [])[:C.LIMITES["personnages_max"]]:
        if not isinstance(x, dict) or x.get("type") not in C.TYPES_PERSONNAGES:
            continue
        perso.append({"type": x["type"], "relation": _txt(x.get("relation"), 30), "nom": _txt(x.get("nom"), 20), "age": _txt(x.get("age"), 3),
                      "genre": x.get("genre") if x.get("genre") in ("fille", "garcon") else "", "desc": _txt(x.get("desc"), 200),
                      "avatar": x.get("avatar") if isinstance(x.get("avatar"), dict) else None, "photo": _txt(x.get("photo"), 20),
                      "voie": x.get("voie") if x.get("voie") in ("avatar", "photo", "description") else "description"})
    out["personnages"] = perso
    e = d.get("evenements") if isinstance(d.get("evenements"), dict) else {}
    out["evenements"] = {"types": [t for t in (e.get("types") or []) if t in C.EVENEMENTS][:6], "texte": _multi(e.get("texte"), 600)}
    k = d.get("dedicace") if isinstance(d.get("dedicace"), dict) else {}
    out["dedicace"] = {"de": _txt(k.get("de"), 50), "texte": _multi(k.get("texte"), 400)}
    out["photo_ok"] = bool(d.get("photo_ok"))
    return out


def noter_etape(etape):
    """Statistiques d'abandon : (jour, étape, visiteur anonyme). Aucune donnée personnelle."""
    try:
        import apercu
        vis = apercu.visiteur(request)[:16]
        with db._lock, db._db() as c:
            c.execute("insert or ignore into etapes_stats (jour, etape, visiteur) values (?,?,?)", (time.strftime("%Y-%m-%d"), etape, vis))
    except Exception:
        pass


@bp.post("/api/parcours/etape")
def api_etape():
    e = (request.get_json(force=True, silent=True) or {}).get("etape")
    if e in ETAPES:
        noter_etape(e)
    return jsonify(ok=True)


# ------------------------------------------------------------------ photos privées
def photos_de(pid):
    with db._db() as c:
        return [{"id": r["id"], "role": r["role"]} for r in c.execute("select * from photos where projet_id=? and supprime is null", (pid,))]


def chemin_photo(pid, phid):
    with db._db() as c:
        r = c.execute("select * from photos where id=? and projet_id=? and supprime is null", (phid, pid)).fetchone()
    return (PHOTOS / r["fichier"]) if r and (PHOTOS / r["fichier"]).exists() else None


@bp.post("/api/projets/<pid>/photos")
def deposer_photo(pid):
    """Photo de l'enfant ou d'un proche : ré-encodée (sans métadonnées, 1600 px au plus), stockée hors du dossier public."""
    from PIL import Image, ImageOps
    p = charger(pid)
    if p["statut"] != "brouillon":
        return jsonify(erreur="Ce livre est déjà commandé."), 409
    if request.form.get("consentement") != "oui":
        return jsonify(erreur="Confirmez que vous êtes autorisé·e à utiliser cette photo."), 400
    f = request.files.get("photo")
    if not f:
        return jsonify(erreur="Aucune photo reçue."), 400
    data = f.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        return jsonify(erreur="Photo trop lourde (12 Mo au plus)."), 413
    try:
        im = Image.open(io.BytesIO(data)); im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        return jsonify(erreur="Ce fichier n'est pas une photo lisible (JPEG, PNG ou HEIC converti)."), 400
    try:                                                   # recadrage choisi par le parent (fractions de l'image)
        cx = [float(request.form.get(k, d)) for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1))]
        x, y, w, h = [max(0.0, min(1.0, v)) for v in cx]
        if w > .05 and h > .05:
            W, H = im.size
            im = im.crop((int(x * W), int(y * H), int(min(1, x + w) * W), int(min(1, y + h) * H)))
    except ValueError:
        pass
    if min(im.size) < 256:
        return jsonify(erreur="Photo trop petite : il faut au moins 256 pixels de côté, visage net."), 400
    im.thumbnail((1600, 1600))
    role = re.sub(r"[^a-z0-9_]", "", request.form.get("role", "heros"))[:20] or "heros"
    phid = secrets.token_hex(6)
    (PHOTOS / pid).mkdir(exist_ok=True)
    nom = f"{pid}/{role}-{phid}.jpg"
    im.save(PHOTOS / nom, quality=90)                      # nouvelles données : aucune métadonnée EXIF (lieu, appareil) conservée
    with db._lock, db._db() as c:
        c.execute("update photos set supprime=? where projet_id=? and role=? and supprime is null", (time.time(), pid, role))
        c.execute("insert into photos (id, projet_id, role, fichier, cree, consentement, supprime) values (?,?,?,?,?,?,?)", (phid, pid, role, nom, time.time(), time.time(), None))
    for old in (PHOTOS / pid).glob(f"{role}-*.jpg"):       # l'ancienne photo de ce rôle est effacée du disque
        if old.name != Path(nom).name:
            old.unlink(missing_ok=True)
    return jsonify(id=phid, role=role)


@bp.get("/api/projets/<pid>/photos/<phid>")
def voir_photo(pid, phid):
    charger(pid)
    f = chemin_photo(pid, re.sub(r"[^a-f0-9]", "", phid))
    if not f:
        abort(404)
    r = send_file(f, mimetype="image/jpeg", max_age=0)
    r.headers["Cache-Control"] = "private, no-store"
    return r


@bp.delete("/api/projets/<pid>/photos/<phid>")
def supprimer_photo(pid, phid):
    charger(pid)
    effacer_photo(pid, re.sub(r"[^a-f0-9]", "", phid))
    return jsonify(ok=True)


def effacer_photo(pid, phid=None):
    with db._lock, db._db() as c:
        rows = c.execute("select * from photos where projet_id=? and supprime is null" + (" and id=?" if phid else ""),
                         (pid, phid) if phid else (pid,)).fetchall()
        for r in rows:
            (PHOTOS / r["fichier"]).unlink(missing_ok=True)
            c.execute("update photos set supprime=? where id=?", (time.time(), r["id"]))
    return len(rows)


def purger_photos():
    """Photos des livres prêts depuis plus de PHOTO_JOURS jours, et des brouillons abandonnés : effacées du disque."""
    limite = time.time() - C.LIMITES["photo_jours"] * 86400
    brouillon = time.time() - C.LIMITES["brouillon_jours"] * 86400
    n = 0
    with db._db() as c:
        ps = [dict(r) for r in c.execute("select id, statut, maj from projets")]
    for p in ps:
        if (p["statut"] == "pret" and p["maj"] < limite) or (p["statut"] in ("brouillon", "attente_paiement") and p["maj"] < brouillon):
            n += effacer_photo(p["id"])
    return n


# ------------------------------------------------------------------ dédicace (« Aidez-moi à écrire » : modèles, aucun appel IA)
MODELES_DEDICACE = [            # {p} prénom ; variantes accordées selon le genre indiqué (aucun appel IA, texte toujours modifiable)
    ("Pour {p}, le héros de cette histoire.\nQue chaque page te rappelle combien tu es aimé.",
     "Pour {p}, l'héroïne de cette histoire.\nQue chaque page te rappelle combien tu es aimée.",
     "Pour {p}, au cœur de cette histoire.\nQue chaque page te rappelle combien on t'aime."),
    ("À {p},\nparce que les plus belles aventures commencent par « il était une fois »… et par toi.",) * 3,
    ("Pour toi, {p}.\nGarde toujours les yeux grands ouverts sur le monde et le cœur plein de rêves.",) * 3,
    ("{p}, ce livre est le tien.\nTu y es courageux, curieux, et surtout toi-même.",
     "{p}, ce livre est le tien.\nTu y es courageuse, curieuse, et surtout toi-même.",
     "{p}, ce livre est le tien.\nTu y es plein de courage, de curiosité, et surtout toi-même."),
    ("À notre petit {p},\npour que tu saches que tu peux tout imaginer, et tout oser.",
     "À notre petite {p},\npour que tu saches que tu peux tout imaginer, et tout oser.",
     "À {p},\npour que tu saches que tu peux tout imaginer, et tout oser."),
]


@bp.post("/api/projets/<pid>/dedicace")
def aide_dedicace(pid):
    """« Aidez-moi à écrire » : une proposition de dédicace, modifiable ; un nouvel appui propose la suivante."""
    p = charger(pid)
    h = (p["donnees"] or {}).get("heros") or {}
    prenom = h.get("prenom") or "toi"
    g = 2 if h.get("pronoms") == "prenom" else 1 if (h.get("pronoms") == "elle" or (not h.get("pronoms") and h.get("genre") == "fille")) else 0
    i = int((request.get_json(force=True, silent=True) or {}).get("i") or 0) % len(MODELES_DEDICACE)
    return jsonify(texte=MODELES_DEDICACE[i][g].format(p=prenom), suivant=(i + 1) % len(MODELES_DEDICACE))


# ------------------------------------------------------------------ du projet à la commande (formulaire de la fabrication)
def formulaire(p):
    """Projet -> formulaire de fabrication (celui que lit procede.py). Tous les choix sont transmis, aucun n'est décoratif.
    Renvoie (form, erreurs)."""
    import generator as G
    d = p["donnees"] or {}
    errs = []
    a_revoir = C.valider(d)
    if a_revoir:
        errs.append("À compléter : " + ", ".join(a_revoir))
    h = d.get("heros") or {}
    prenom = G._name(h.get("prenom") or "")
    if not prenom:
        errs.append("Prénom du héros manquant")
    age = h.get("age") or ""
    if not (age.isdigit() and 0 <= int(age) <= 17):
        errs.append("Âge du héros entre 0 et 17 ans")
    if h.get("voie") not in ("avatar", "photo"):
        errs.append("Choisissez « Créer son avatar » ou « Utiliser une photo »")
    if h.get("voie") == "photo" and not chemin_photo(p["id"], h.get("photo") or ""):
        errs.append("Photo du héros manquante")
    if errs:
        return None, errs
    ages = C.par_cle(C.ages(), d["age_lecteur"])
    t, s = C.sujet(d["theme"], d["sujet"])
    msg = C.par_cle(C.messages(), d["message"])
    import univers as U
    univ = U.PAR_CLE.get(s.get("univers") or "")
    # avatar : héros + frères et sœurs + animaux + doudou (éditeur existant, valeurs vérifiées par sanitize_avatar)
    av_h = h.get("avatar") or {}
    # valeurs que l'éditeur masque (couleur des lunettes sans lunettes, oreilles d'un chat…) : complétées par les valeurs neutres de
    # l'éditeur ; tout ce que le parent a choisi est gardé tel quel et vérifié par sanitize_avatar
    DEF_E = {"peau": "p2", "coiffure": "court", "couleur_cheveux": "chatain", "yeux": "marron", "lunettes": "aucune", "couleur_lunettes": "rouge",
             "taches": "non", "tenue": "tshirt", "couleur_tenue": "jaune"}
    def animal(a):
        base = dict(G.OPTIONS["modeles"]["animal"].get(a.get("type") or "chat") or {})
        return {**{"type": "chat", "taille": "moyen", "oreilles": "dressees", "motif": "uni", "couleur2": "blanc", "yeux": "sombres", "collier": "aucun"}, **base, **a}
    DEF_D = {"type": "lapin", "couleur": "bleu", "accessoire": "aucun", "couleur_accessoire": "rouge"}
    avatar = {"enfant": {**DEF_E, **av_h, "genre": h.get("genre") or av_h.get("genre")}, "doudou": None, "animaux": [], "fratrie": []}
    proches = []
    for x in d.get("personnages") or []:
        rel = x.get("relation") or ""
        if x["type"] == "personne" and rel in ("frère", "sœur") and x.get("voie") == "avatar" and x.get("avatar"):
            avatar["fratrie"].append({**DEF_E, **x["avatar"], "prenom": x["nom"], "age": x.get("age") or "6", "genre": "fille" if rel == "sœur" else "garcon"})
        elif x["type"] == "animal" and x.get("avatar"):
            avatar["animaux"].append({**animal(x["avatar"]), "nom": x["nom"]})
        elif x["type"] == "objet" and rel == "doudou" and x.get("avatar") and not avatar["doudou"]:
            avatar["doudou"] = {**DEF_D, **x["avatar"], "nom": x["nom"], "actif": True}
        else:
            ph = chemin_photo(p["id"], x.get("photo") or "") if x.get("voie") == "photo" else None
            proches.append({"type": "objet" if x["type"] == "objet" else "personne", "nom": x["nom"], "relation": rel, "age": x.get("age"),
                            "desc": x.get("desc"), "photo": str(ph) if ph else None})
    if avatar["doudou"] is None:
        avatar.pop("doudou")
    n_proches = sum(1 for x in proches if x["type"] == "personne")
    if n_proches > C.LIMITES["proches_max"]:
        return None, [f"Au plus {C.LIMITES['proches_max']} proches (en plus des frères et sœurs)"]
    probs = []
    av = G.sanitize_avatar(avatar, prenom, age, probs)
    if av is None or probs:
        return None, ["Avatar incomplet : " + "; ".join(probs[:3])]
    ev = d.get("evenements") or {}
    evenements = ((", ".join(ev.get("types") or []) + " : ") if ev.get("types") else "") + (ev.get("texte") or "")
    ch = d.get("cherche") or "non"
    item = None
    if ch == "auto":
        item = C.cherche()[int(hashlib.sha1(p["id"].encode()).hexdigest(), 16) % len(C.cherche())]   # choix automatique, stable
    elif ch != "non":
        item = C.par_cle(C.cherche(), ch)
    form = {"prenom": prenom, "age": str(age), "genre": av["enfant"]["genre"], "avatar": av, "heros_livre": "enfant",
            "theme": s.get("theme") or s["nom"], "univers": univ["nom"] if univ else s["nom"], "passions": h.get("passions") or "",
            "precision": "", "numero": "01", "formule": "ebook", "ebook": True,
            "parcours": {"projet": p["id"], "age_lecteur": ages["cle"], "age_label": ages["age_label"], "mots": ages["mots"],
                         "consigne_age": ages["pour_histoire"], "theme_cle": t["cle"], "sujet": s["nom"],
                         "decor_en": s.get("decor_en") or (univ or {}).get("image"),
                         "message": msg["nom"], "consigne_message": None if msg.get("inspire") else C.CONSIGNE_MESSAGE.format(nom=msg["nom"]),
                         "style": d["style"], "police": d["police"], "langue": d.get("langue") or "fr",
                         "cherche": item["cle"] if item else "non", "cherche_en": item["en"] if item else None, "cherche_nom": item["nom"] if item else None,
                         "evenements": evenements.strip(" :"), "plat": h.get("plat") or "", "details": h.get("details") or "",
                         "pronoms": {"il": "il", "elle": "elle", "prenom": "éviter les pronoms genrés, utiliser le prénom"}.get(h.get("pronoms") or ""),
                         "photo_heros": str(chemin_photo(p["id"], h.get("photo"))) if h.get("voie") == "photo" else None,
                         "proches": [{"nom": x["nom"], "relation": x["relation"], "age": x["age"], "desc": x["desc"], "photo": x["photo"],
                                      "type": x["type"]} for x in proches],
                         "dedicace": {k: v for k, v in (d.get("dedicace") or {}).items() if v}}}
    cfg = G.build_config(form)
    if cfg.get("problemes"):
        return None, cfg["problemes"][:3]
    return form, []


@bp.post("/api/projets/<pid>/verifier")
def verifier(pid):
    p = charger(pid)
    form, errs = formulaire(p)
    return jsonify(ok=not errs, erreurs=errs, prix=prix_public())


# ------------------------------------------------------------------ aperçu du héros avant paiement (limité, réutilise apercu.py)
@bp.post("/api/projets/<pid>/apercu")
def apercu_projet(pid):
    import apercu, app as A
    p = charger(pid)
    form, errs = formulaire(p)
    if errs:
        return jsonify(erreur=" ; ".join(errs)), 400
    rep, code = apercu.lancer_form(A, form, apercu.visiteur(request))
    return jsonify(rep), code


# ------------------------------------------------------------------ achat du livre NUMÉRIQUE (seul paiement du parcours)
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}$", re.I)


@bp.post("/api/projets/<pid>/acheter")
def acheter(pid):
    """Crée la commande du livre numérique (formule « ebook », prix PRIX_EBOOK) et ouvre le paiement. Rien n'est payé ici sans
    l'action du parent sur Stripe ; aucune version papier n'est ajoutée."""
    import boutique as B, app as A, apercu
    p = charger(pid)
    d = request.get_json(force=True, silent=True) or {}
    if p["statut"] != "brouillon":
        o = db.get(p.get("commande_numerique") or "")
        if o and o["statut"] == "attente_paiement" and o.get("stripe_session") and paiement.configured():
            try:                                                # paiement déjà ouvert : on le reprend, jamais un second
                s = paiement.session(o["stripe_session"])
                if s.get("status") == "open":
                    return jsonify(id=o["id"], url=s["url"])
            except Exception:
                pass
        if o and o["statut"] != "attente_paiement":
            return jsonify(erreur="Ce livre est déjà payé.", suivi=lien(p, "/mon-livre")), 409
    email = _txt(d.get("email"), 190)
    if not EMAIL.match(email):
        return jsonify(erreur="Adresse e-mail invalide."), 400
    if d.get("cgv") is not True:
        return jsonify(erreur="Merci d'accepter les conditions générales de vente."), 400
    if d.get("renonce_retractation") is not True:
        return jsonify(erreur="Cochez la case : vous demandez la création immédiate du livre numérique et renoncez au droit de rétractation."), 400
    if any(x for x in photos_de(pid)) and not (p["donnees"] or {}).get("photo_ok"):
        return jsonify(erreur="Confirmez que vous êtes autorisé·e à utiliser les photos transmises."), 400
    form, errs = formulaire(p)
    if errs:
        return jsonify(erreur=" ; ".join(errs)), 400
    promo = paiement.promo_valide(d.get("code_promo"))
    if d.get("code_promo") and not promo:
        return jsonify(erreur="Ce code promo n'existe pas."), 400
    promo = promo[0] if promo else None
    if promo:
        form["code_promo"] = promo
    if d.get("apercu"):                                      # couverture vue avant le paiement : elle devient celle du livre
        try:
            import generator as G
            pa = apercu.pour_commande(d["apercu"], G.build_config(form), form.get("univers"))
            if pa:
                form["couverture_apercu"] = pa
        except Exception as e:
            log(f"projet {pid} : aperçu non repris ({e})")
    oid = uuid.uuid4().hex[:12]
    folder = B.STORE / oid; folder.mkdir(parents=True)
    lignes = paiement.lignes("ebook", "FR", promo=promo)
    (folder / "livre.json").write_text(json.dumps({"form": form, "guides": {}, "apercus": {}, "lignes": lignes, "projet": pid},
                                                  ensure_ascii=False), encoding="utf-8")
    montant = paiement.total("ebook", "FR", promo=promo)
    cl = _client()
    db.create(id=oid, formule="ebook", email=email, adresse={"nom": "", "pays": "FR"}, statut="attente_paiement", montant=montant, origine=oid,
              numero=1, projet_id=pid, client_id=cl["id"] if cl else p.get("client_id"))
    maj(pid, statut="attente_paiement", commande_numerique=oid, email=email, etape="paiement")
    noter_etape("paiement")
    if not paiement.configured():
        return jsonify(id=oid, url=f"/mon-livre/{pid}?j={p['jeton']}&test=1")
    try:
        sid, url = paiement.checkout(oid, "ebook", email, B.base_url(), promo=promo, remise_cents=paiement.remise("ebook", "FR", promo=promo),
                                     ebook=True, retour=f"{B.base_url()}/mon-livre/{pid}?j={p['jeton']}")
    except paiement.StripeError as e:
        db.update(oid, statut="erreur", erreur=str(e)); maj(pid, statut="brouillon")
        return jsonify(erreur=str(e)), 502
    db.update(oid, stripe_session=sid)
    return jsonify(id=oid, url=url)


def apres_paiement_numerique(oid):
    """Appelé par boutique.confirm_paid (paiement confirmé côté serveur, une seule fois) : crédit créé, projet passé en génération."""
    o = db.get(oid)
    pid = o.get("projet_id")
    if not pid:
        return
    with db._lock, db._db() as c:                           # unique (commande_numerique) : jamais deux crédits pour un paiement
        c.execute("insert or ignore into credits (id, projet_id, commande_numerique, montant, cree, statut, commande_papier, maj) values (?,?,?,?,?,?,?,?)",
                  (secrets.token_hex(6), pid, oid, int(o["montant"] or 0), time.time(), "disponible", None, time.time()))
    maj(pid, statut="generation")


def credit_de(pid):
    with db._db() as c:
        r = c.execute("select * from credits where projet_id=? order by cree limit 1", (pid,)).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ suivi et « Mon livre »
ETATS = [("paye", "Paiement confirmé"), ("histoire", "Histoire en préparation"), ("illustrations", "Illustrations en cours"),
         ("mise_en_page", "Mise en page"), ("pret", "Livre disponible")]
PHASES = {"queued": "histoire", "references": "histoire", "storyboard": "histoire", "illustrating": "illustrations", "reviewing": "illustrations",
          "assembling": "mise_en_page"}


def etat_livre(p):
    """États RÉELS : statut de la commande et phase de la fabrication (aucune progression simulée, aucun délai promis)."""
    import app as A, fabrication
    o = db.get(p.get("commande_numerique") or "")
    if not o or o["statut"] == "attente_paiement":
        return {"etat": "attente_paiement", "etapes": ETATS, "atteint": None}
    if o["statut"] == "annulee":
        return {"etat": "annulee", "etapes": ETATS, "atteint": None}
    job = A.JOBS.get(o.get("job_id") or "", {})
    pret = bool(o.get("job_id") and fabrication.est_finalise(A.OUT / o["job_id"]))
    if pret:
        return {"etat": "pret", "etapes": ETATS, "atteint": "pret"}
    if o["statut"] in ("a_verifier", "erreur") or job.get("phase") in ("needs_review", "failed"):
        return {"etat": "relecture", "etapes": ETATS, "atteint": "mise_en_page",
                "message": "Notre équipe relit le livre avant de vous l'envoyer : vous recevrez un e-mail dès qu'il est disponible."}
    return {"etat": "en_cours", "etapes": ETATS, "atteint": PHASES.get(job.get("phase") or "", "paye"), "detail": job.get("etape")}


def livre_courant(p):
    """(dossier, livre.json, version) de la dernière version du livre (v1 : le livre généré)."""
    import app as A
    o = db.get(p.get("commande_numerique") or "")
    if not o or not o.get("job_id"):
        return None, None, 0
    folder = A.OUT / o["job_id"]
    with db._db() as c:
        v = c.execute("select * from versions where projet_id=? order by numero desc limit 1", (p["id"],)).fetchone()
    if v and (folder / v["fichier"]).exists():
        return folder, json.loads((folder / v["fichier"]).read_text(encoding="utf-8")), v["numero"]
    if (folder / "livre.json").exists():
        return folder, json.loads((folder / "livre.json").read_text(encoding="utf-8")), 1
    return folder, None, 0


@bp.get("/mon-livre/<pid>")
def page_mon_livre(pid):
    charger(pid)
    r = send_file(Path(__file__).parent / "static" / "mon-livre.html", max_age=0)
    r.headers["Cache-Control"] = "private, no-store"
    return r


@bp.get("/api/mon-livre/<pid>")
def api_mon_livre(pid):
    import fabrication, app as A
    p = charger(pid)
    o = db.get(p.get("commande_numerique") or "")
    if o and o["statut"] == "attente_paiement" and request.args.get("session_id") and paiement.configured():
        try:                                                # retour de Stripe : on vérifie nous-mêmes (le webhook peut tarder)
            s = paiement.session(request.args["session_id"])
            if (s.get("metadata") or {}).get("commande") == o["id"] and s.get("payment_status") == "paid":
                import boutique as B
                B.confirm_paid(o["id"])
        except Exception as e:
            log(f"mon-livre {pid} : vérification Stripe impossible : {e}")
        p = get(pid); o = db.get(o["id"])
    if o and o["statut"] == "attente_paiement" and request.args.get("annule"):
        maj(pid, statut="brouillon")                       # paiement abandonné : le brouillon redevient modifiable
        p = get(pid)
    e = etat_livre(p)
    out = {"id": pid, "etat": e, "titre": p.get("titre"), "statut_projet": p["statut"], "prix": prix_public(), "commande": p.get("commande_numerique"),
           "limites": {k: C.LIMITES[k] for k in ("corrections_texte", "corrections_image")}, "lien_brouillon": lien(p) if p["statut"] == "brouillon" else None}
    if e["etat"] == "pret":
        folder, book, v = livre_courant(p)
        if book:
            if p["statut"] != "pret":                     # date « prêt » figée : elle décide de l'effacement des photos
                maj(pid, statut="pret", titre=book.get("title"))
            j = p["jeton"]
            out.update(titre=book["title"], version=v, police=book.get("police"),
                       couverture=f"/api/mon-livre/{pid}/img/{book['cover']}?j={j}",
                       doubles=[f"/api/mon-livre/{pid}/img/{x}?j={j}" for x in book["spreads"]],
                       pages=[x["text"] for x in book["pages"]], dedicace=book.get("dedicace"),
                       cherche=book.get("cherche"), pdf=f"/api/mon-livre/{pid}/livre.pdf?j={j}",
                       corrections_texte_restantes=max(0, C.LIMITES["corrections_texte"] - max(0, v - 1)),
                       corrections_image=corrections_de(pid),
                       credit=credit_public(pid), commandes_papier=commandes_papier(pid))
    return jsonify(out)


def credit_public(pid):
    c = credit_de(pid)
    return {"montant": c["montant"], "statut": c["statut"]} if c else None


@bp.get("/api/mon-livre/<pid>/img/<name>")
def image_livre(pid, name):
    p = charger(pid)
    folder, book, _ = livre_courant(p)
    if not book or name not in [book["cover"]] + [x for x in book["spreads"] if x]:
        abort(404)
    from PIL import Image
    cache = folder / "web"; cache.mkdir(exist_ok=True)
    w = cache / (Path(name).stem + ".jpg")
    if not w.exists():
        im = Image.open(folder / name).convert("RGB"); im.thumbnail((1600, 1600)); im.save(w, quality=84)
    r = send_file(w, mimetype="image/jpeg", max_age=3600)
    r.headers["Cache-Control"] = "private, max-age=3600"
    return r


@bp.get("/api/mon-livre/<pid>/livre.pdf")
def pdf_livre(pid):
    p = charger(pid)
    folder, book, v = livre_courant(p)
    if not book or etat_livre(p)["etat"] != "pret":
        abort(404)
    if v > 1:
        with db._db() as c:
            r = c.execute("select pdf from versions where projet_id=? and numero=?", (pid, v)).fetchone()
        f = folder / r["pdf"]
    else:
        import app as A
        o = db.get(p["commande_numerique"])
        f = A.OUT / o["job_id"] / o["pdf"]
    nom = re.sub(r"[^\w\-]+", "-", book["title"], flags=re.U).strip("-")[:60] or "livre"
    return send_file(f, mimetype="application/pdf", as_attachment=True, download_name=f"{nom}.pdf", max_age=0)


# ------------------------------------------------------------------ corrections
@bp.post("/api/mon-livre/<pid>/textes")
def corriger_textes(pid):
    """Nouvelle version du texte (pages, dédicace) : aucune image refaite, PDF recomposé, versions précédentes gardées."""
    import moteur_livre as M
    p = charger(pid)
    folder, book, v = livre_courant(p)
    if not book or etat_livre(p)["etat"] != "pret":
        return jsonify(erreur="Le livre n'est pas encore disponible."), 400
    if v - 1 >= C.LIMITES["corrections_texte"]:
        return jsonify(erreur=f"Vous avez utilisé vos {C.LIMITES['corrections_texte']} corrections de texte. Écrivez-nous pour une modification."), 429
    d = request.get_json(force=True, silent=True) or {}
    pages = d.get("pages")
    if not isinstance(pages, list) or len(pages) != len(book["pages"]):
        return jsonify(erreur="Pages illisibles."), 400
    nb = json.loads(json.dumps(book))
    jeton, j2 = M.POLICE.set(book.get("police")), M.CORPS.set(float(book.get("corps") or 1.0))
    try:
        for i, t in enumerate(pages):
            t = re.sub(r"\s+", " ", str(t or "")).strip()[:600]
            if not t:
                return jsonify(erreur=f"Page {i + 1} : le texte ne peut pas être vide."), 400
            if M.text_height(t) > M.TEXT_MAX:
                return jsonify(erreur=f"Page {i + 1} : texte trop long pour la page (7 lignes au plus). Raccourcissez-le un peu."), 400
            nb["pages"][i]["text"] = t
    finally:
        M.POLICE.reset(jeton); M.CORPS.reset(j2)
    if isinstance(d.get("dedicace"), dict):
        ded = {"de": _txt(d["dedicace"].get("de"), 50), "texte": _multi(d["dedicace"].get("texte"), 400)}
        nb["dedicace"] = ded if ded["texte"] else None
    if nb == book:
        return jsonify(erreur="Aucune modification."), 400
    n = v + 1
    (folder / "versions").mkdir(exist_ok=True)
    fj, fp = f"versions/livre-v{n}.json", f"versions/livre-v{n}.pdf"
    (folder / fj).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = M.render(nb, folder / fp, base=folder, work=folder / "versions" / f"rendu-v{n}")
    shutil.rmtree(folder / "versions" / f"rendu-v{n}", ignore_errors=True)
    if rep.get("problemes_rendu"):
        (folder / fj).unlink(missing_ok=True); (folder / fp).unlink(missing_ok=True)
        return jsonify(erreur="Mise en page impossible : " + "; ".join(rep["problemes_rendu"][:2])), 400
    with db._lock, db._db() as c:
        c.execute("insert into versions (id, projet_id, numero, cree, motif, fichier, pdf) values (?,?,?,?,?,?,?)", (secrets.token_hex(6), pid, n, time.time(), "texte", fj, fp))
    log(f"projet {pid} : version {n} du texte")
    return jsonify(ok=True, version=n)


def corrections_de(pid):
    with db._db() as c:
        rows = [dict(r) for r in c.execute("select page, demande, statut, cree, reponse from corrections where projet_id=? order by cree", (pid,))]
    return {"demandes": rows, "restantes": max(0, C.LIMITES["corrections_image"] - len(rows))}


@bp.post("/api/mon-livre/<pid>/correction-image")
def demander_correction(pid):
    """Demande de retouche d'UNE illustration : enregistrée et traitée par l'équipe (aucune génération automatique)."""
    p = charger(pid)
    if etat_livre(p)["etat"] != "pret":
        return jsonify(erreur="Le livre n'est pas encore disponible."), 400
    if corrections_de(pid)["restantes"] <= 0:
        return jsonify(erreur=f"Les {C.LIMITES['corrections_image']} demandes de retouche incluses ont été utilisées. Écrivez-nous pour en parler."), 429
    d = request.get_json(force=True, silent=True) or {}
    try:
        page = int(d.get("double_page"))
    except (TypeError, ValueError):
        page = 0
    if not 0 <= page <= 9:
        return jsonify(erreur="Choisissez l'illustration à retoucher."), 400
    txt = _txt(d.get("demande"), 400)
    if len(txt) < 8:
        return jsonify(erreur="Décrivez ce qu'il faut corriger."), 400
    with db._lock, db._db() as c:
        c.execute("insert into corrections (id, projet_id, page, demande, statut, cree, reponse) values (?,?,?,?,?,?,?)",
                  (secrets.token_hex(6), pid, page, txt, "demandee", time.time(), None))
    log(f"projet {pid} : retouche demandée ({'couverture' if page == 0 else 'double page ' + str(page)})")
    try:
        import boutique as B
        if B.mail_configure():
            B.send_mail(f"Retouche d'illustration demandée (projet {pid})", f"{'Couverture' if page == 0 else 'Double page ' + str(page)} : {txt}\n\n"
                        f"Admin : {B.base_url()}/admin", to=os.getenv("ALERTE_EMAIL") or B.CONTACT)
    except Exception:
        pass
    return jsonify(ok=True, **corrections_de(pid))


# ------------------------------------------------------------------ livre relié (complément, déduction du numérique)
def commandes_papier(pid):
    with db._db() as c:
        rows = [dict(r) for r in c.execute("select id, statut, montant, quantite, cree, suivi from commandes where projet_id=? and formule='relie' "
                                           "and statut!='attente_paiement' order by cree", (pid,))]
    for r in rows:
        r["suivi"] = json.loads(r["suivi"]) if r.get("suivi") else None
    return rows


def _liberer_reservations(pid=None):
    """Crédits réservés par un paiement relié jamais finalisé (session abandonnée depuis plus d'une heure) : de nouveau disponibles."""
    with db._db() as c:
        rows = [dict(r) for r in c.execute("select * from credits where statut='reserve'" + (" and projet_id=?" if pid else ""), (pid,) if pid else ())]
    for r in rows:
        o = db.get(r["commande_papier"] or "")
        if not o or (o["statut"] == "attente_paiement" and time.time() - o["cree"] > 3600) or o["statut"] in ("annulee", "erreur"):
            with db._lock, db._db() as c:
                c.execute("update credits set statut='disponible', commande_papier=null, maj=? where id=? and statut='reserve'", (time.time(), r["id"]))


def liberer_credit(oid):
    """Session Stripe expirée ou annulée pour une commande reliée : la déduction redevient disponible."""
    with db._lock, db._db() as c:
        c.execute("update credits set statut='disponible', commande_papier=null, maj=? where commande_papier=? and statut='reserve'", (time.time(), oid))


@bp.post("/api/mon-livre/<pid>/devis-relie")
def devis(pid):
    p = charger(pid)
    d = request.get_json(force=True, silent=True) or {}
    _liberer_reservations(pid)
    cr = credit_de(pid)
    credit = cr["montant"] if cr and cr["statut"] == "disponible" else 0
    try:
        q = paiement.devis_relie(int(d.get("quantite") or 1), credit, d.get("pays") or "FR", d.get("code_promo"))
    except ValueError:
        return jsonify(erreur="Quantité non proposée."), 400
    except Exception as e:
        return jsonify(erreur=str(e)), 503
    q["credit_deja_utilise"] = bool(cr and cr["statut"] == "utilise")
    return jsonify(q)


@bp.post("/api/mon-livre/<pid>/commander-relie")
def commander_relie(pid):
    """Commande reliée : version validée FIGÉE (copie du livre), déduction réservée de façon atomique, paiement du complément."""
    import boutique as B, app as A, fabrication, procede as P
    p = charger(pid)
    if etat_livre(p)["etat"] != "pret":
        return jsonify(erreur="Le livre n'est pas encore disponible."), 400
    d = request.get_json(force=True, silent=True) or {}
    if d.get("valide") is not True:
        return jsonify(erreur="Confirmez que vous avez relu le livre : c'est cette version qui sera imprimée."), 400
    if d.get("cgv") is not True:
        return jsonify(erreur="Merci d'accepter les conditions générales de vente."), 400
    addr, err = B.parse_address(d.get("adresse"))
    if err:
        return jsonify(erreur=err), 400
    _liberer_reservations(pid)
    o_num = db.get(p["commande_numerique"])
    nid = uuid.uuid4().hex[:12]
    cr = credit_de(pid)
    credit = 0
    if cr and cr["statut"] == "disponible":                 # réservation atomique : deux onglets ne peuvent pas l'utiliser deux fois
        with db._lock, db._db() as c:
            ok = c.execute("update credits set statut='reserve', commande_papier=?, maj=? where id=? and statut='disponible'",
                           (nid, time.time(), cr["id"])).rowcount == 1
        credit = cr["montant"] if ok else 0
    try:
        q = paiement.devis_relie(int(d.get("quantite") or 1), credit, addr["pays"], d.get("code_promo"))
    except Exception as e:
        liberer_credit(nid)
        return jsonify(erreur="Quantité non proposée." if isinstance(e, ValueError) else str(e)), 400
    # version figée : copie du dossier du livre (images partagées par lien physique), livre.json de la version relue
    folder, book, v = livre_courant(p)
    gel = A.OUT / f"{o_num['job_id']}-p{nid}"
    try:
        gel.mkdir(parents=True)
        for f in [book["cover"]] + book["spreads"]:
            try:
                os.link(folder / f, gel / f)
            except OSError:
                shutil.copy(folder / f, gel / f)
        for f in ("instantane.json", "storyboard.json", "references.json", "controle.json", "budget.json"):
            if (folder / f).exists():
                shutil.copy(folder / f, gel / f)
        (gel / "livre.json").write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        numero = book.get("volumeNumber") or 1
        pdf = gel / (o_num["pdf"] or "livre.pdf")
        rep = __import__("moteur_livre").render(book, pdf, base=gel, work=gel / "rendu")
        shutil.rmtree(gel / "rendu", ignore_errors=True)
        fab = P.fabrication_files(book, gel, pdf, numero, book.get("coverTitle", {}).get("lines", [""])[0] or "")
        ap = fab.pop("apercus")
        res = {"titre": book["title"], "pages": rep.get("pages"), "mineurs": [], "cout": 0}
        P.finaliser(gel, book, pdf, numero, res, ap)
    except Exception as e:
        liberer_credit(nid); shutil.rmtree(gel, ignore_errors=True)
        log(f"projet {pid} : version figée impossible : {e}")
        return jsonify(erreur="Préparation du fichier d'impression impossible pour le moment. Réessayez dans quelques minutes."), 503
    store = B.STORE / nid; store.mkdir(parents=True)
    lignes = [(f"Livre relié « {book['title']} »", q["quantite"], q["prix_unitaire"], "livre")]
    if q["deduction"]:
        lignes.append(("Déduction du livre numérique déjà payé", 1, -q["deduction"], "remise"))
    if q["remise"]:
        lignes.append((f"Remise code {q['code_promo']}", 1, -q["remise"], "remise"))
    if q["port"]:
        lignes.append(("Livraison", 1, q["port"], "port"))
    form = {"prenom": (book.get("coverTitle", {}).get("lines") or [""])[0], "formule": "relie", "source_ebook": o_num["id"], "projet": pid,
            "version": v, "quantite": q["quantite"]}
    (store / "livre.json").write_text(json.dumps({"form": form, "guides": {}, "apercus": {}, "lignes": lignes, "projet": pid, "devis": q},
                                                 ensure_ascii=False), encoding="utf-8")
    db.create(id=nid, formule="relie", email=o_num["email"], adresse=addr, statut="attente_paiement", montant=q["total"], origine=nid, numero=1,
              projet_id=pid, quantite=q["quantite"], client_id=o_num.get("client_id"), job_id=gel.name, pdf=pdf.name, titre=book["title"],
              volume_number=o_num.get("volume_number"))
    retour = f"{B.base_url()}/mon-livre/{pid}?j={p['jeton']}"
    if not paiement.configured():
        return jsonify(id=nid, url=f"/mon-livre/{pid}?j={p['jeton']}&relie={nid}&test=1", devis=q)
    try:
        lst = [(f"Mon Héros du Mois – livre relié « {book['title']} »", q["prix_unitaire"], q["quantite"])]
        if q["port"]:
            lst.append(("Livraison", q["port"], 1))
        nom = " + ".join(([f"Déduction e-book {q['deduction'] / 100:.2f} €".replace(".", ",")] if q["deduction"] else []) +
                         ([f"code {q['code_promo']}"] if q["remise"] else []))
        sid, url = paiement.checkout_libre(nid, o_num["email"], B.base_url(), lst, q["deduction"] + q["remise"], nom, retour,
                                           {"formule": "relie", "projet": pid})
    except paiement.StripeError as e:
        liberer_credit(nid); db.update(nid, statut="erreur", erreur=str(e))
        return jsonify(erreur=str(e)), 502
    db.update(nid, stripe_session=sid)
    return jsonify(id=nid, url=url, devis=q)


def apres_paiement_relie(oid):
    """Paiement du livre relié confirmé (une seule fois) : crédit consommé, commande prête pour ta relecture puis Lulu."""
    with db._lock, db._db() as c:
        c.execute("update credits set statut='utilise', maj=? where commande_papier=? and statut in ('reserve','disponible')", (time.time(), oid))
    db.update(oid, statut="a_verifier")
    log(f"commande reliée {oid} payée : fichier figé {db.get(oid)['job_id']}, prête à imprimer après relecture")


# ------------------------------------------------------------------ administration
def admin_stats(jours=30):
    """Abandons par étape (visiteurs distincts), achats numériques, passage au papier. Aucune donnée personnelle."""
    depuis = time.strftime("%Y-%m-%d", time.localtime(time.time() - jours * 86400))
    with db._db() as c:
        par = {r[0]: r[1] for r in c.execute("select etape, count(distinct visiteur) from etapes_stats where jour>=? group by etape", (depuis,))}
        proj = c.execute("select count(*) from projets where cree>?", (time.time() - jours * 86400,)).fetchone()[0]
        num = c.execute("select count(*) from commandes where formule='ebook' and projet_id is not null and statut!='attente_paiement' and cree>?",
                        (time.time() - jours * 86400,)).fetchone()[0]
        pap = c.execute("select count(distinct projet_id) from commandes where formule='relie' and statut!='attente_paiement' and cree>?",
                        (time.time() - jours * 86400,)).fetchone()[0]
        credits = [dict(r) for r in c.execute("select * from credits order by cree desc limit 100")]
        corr = [dict(r) for r in c.execute("select * from corrections order by cree desc limit 100")]
    return {"jours": jours, "etapes": [{"etape": e, "visiteurs": par.get(e, 0)} for e in ETAPES], "projets": proj, "achats_numeriques": num,
            "passages_papier": pap, "taux_papier": round(pap / num * 100, 1) if num else None, "credits": credits, "corrections": corr}


@bp.get("/admin/api/parcours")
def admin_parcours():
    import boutique as B
    if not B.admin_ok():
        abort(403)
    cat = {"ages": C.ages(), "themes": C.themes(), "messages": C.messages(), "styles": [dict(s) for s in C.styles()], "polices": C.polices(),
           "cherche": C.cherche(), "langues": C.langues(), "limites": C.LIMITES, "scene_demo": C.SCENE_DEMO}
    return jsonify(stats=admin_stats(int(request.args.get("jours") or 30)), catalogue=cat, prix=prix_public())


@bp.post("/admin/api/catalogue")
def admin_catalogue():
    import boutique as B
    if not B.admin_ok():
        abort(403)
    d = request.get_json(force=True, silent=True) or {}
    rub = d.get("rubrique")
    if rub not in ("ages", "themes", "sujets", "messages", "styles", "polices", "cherche", "langues"):
        return jsonify(erreur="rubrique inconnue"), 400
    if rub == "langues" and d.get("champs", {}).get("actif") and d.get("cle") != "fr":
        return jsonify(erreur="Seul le français est pris en charge par la génération et les contrôles."), 400
    if rub == "styles" and d.get("champs", {}).get("actif") and not C.apercu_style(d.get("cle")) and d.get("cle") != "gouache":
        return jsonify(erreur="Générez et vérifiez d'abord l'aperçu de ce style."), 400
    C.enregistrer(rub, str(d.get("cle"))[:60], d.get("champs") or {})
    return jsonify(ok=True)


@bp.post("/admin/api/corrections/<cid>")
def admin_correction(cid):
    import boutique as B
    if not B.admin_ok():
        abort(403)
    d = request.get_json(force=True, silent=True) or {}
    with db._lock, db._db() as c:
        c.execute("update corrections set statut=?, reponse=? where id=?", (d.get("statut") if d.get("statut") in ("demandee", "en_cours", "faite", "refusee") else "demandee",
                                                                         _txt(d.get("reponse"), 400), cid))
    return jsonify(ok=True)


@bp.post("/admin/api/credits/<crid>/annuler")
def admin_annuler_credit(crid):
    """Livre numérique remboursé : la déduction n'est plus utilisable (sauf si elle a déjà servi)."""
    import boutique as B
    if not B.admin_ok():
        abort(403)
    with db._lock, db._db() as c:
        n = c.execute("update credits set statut='annule', maj=? where id=? and statut in ('disponible','reserve')", (time.time(), crid)).rowcount
    return jsonify(ok=bool(n))


@bp.get("/admin/style/<cle>.webp")
def admin_style_img(cle):
    f = C.apercu_style(re.sub(r"[^a-z0-9]", "", cle))
    return send_file(f, max_age=3600) if f else abort(404)


@bp.get("/style/<cle>.webp")
def style_img(cle):
    """Aperçu public d'un style (scène de démonstration, sans personne réelle)."""
    f = C.apercu_style(re.sub(r"[^a-z0-9]", "", cle))
    if not f and cle == "gouache":
        f = Path(__file__).parent / "kit" / "style" / "jour-mila-2.jpg"
    return send_file(f, max_age=86400) if f else abort(404)


@bp.post("/admin/api/styles/generer")
def admin_generer_styles():
    """Aperçus des styles : la MÊME scène de démonstration dans chaque style (une image moyenne qualité par style manquant).
    Les aperçus générés restent inactifs : tu les actives un par un après les avoir regardés."""
    import boutique as B
    if not B.admin_ok():
        abort(403)
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify(erreur="OPENAI_API_KEY absente : génération impossible."), 503
    cles = [s["cle"] for s in C.styles() if not s["apercu"]]
    d = request.get_json(force=True, silent=True) or {}
    if d.get("cle"):
        cles = [d["cle"]] if d["cle"] in [s["cle"] for s in C.STYLES] else []
    threading.Thread(target=_generer_styles, args=(cles,), daemon=True).start()
    return jsonify(ok=True, styles=cles)


def _generer_styles(cles):
    import generator as G, budget as BU
    from PIL import Image
    C.DOSSIER_STYLES.mkdir(parents=True, exist_ok=True)
    for k in cles:
        st = C.par_cle(C.STYLES, k)
        livre = f"style-{k}"
        BU.PLAFONDS[livre] = 0.25
        jeton = BU.LIVRE.set(livre)
        try:
            G.check_budget()
            prompt = (f"Square illustration for a children's picture-book website, showing an example of an art style. ART STYLE: {st['style_en']}. "
                      f"SCENE (identical for every style, for comparison): {C.SCENE_DEMO} No text, no letters, no logo, no frame, no existing character.")
            tmp = C.DOSSIER_STYLES / f".{k}.png"
            _generer_image(G, prompt, tmp)
            im = Image.open(tmp).convert("RGB"); im.thumbnail((900, 900)); im.save(C.DOSSIER_STYLES / f"{k}.webp", quality=86); tmp.unlink(missing_ok=True)
            log(f"aperçu du style {k} généré")
        except Exception as e:
            log(f"aperçu du style {k} impossible : {e}")
        finally:
            BU.LIVRE.reset(jeton)


def _generer_image(G, prompt, out):
    """Une image sans référence (scène de démonstration), au modèle d'image du site, comptée dans le budget du jour."""
    import base64
    r = G._retry(lambda: G._client().images.generate(model=G.IMAGE_MODEL, prompt=prompt, size="1024x1024", quality="medium", n=1))
    G._count("image", G.IMAGE_MODEL, getattr(r, "usage", None))
    Path(out).write_bytes(base64.b64decode(r.data[0].b64_json))


# ------------------------------------------------------------------ retouche d'UNE illustration (lancée par Alex, coût affiché)
with db._db() as _c:
    try:
        _c.execute("alter table corrections add column fichier text")
    except Exception:
        pass
PLAFOND_RETOUCHE = float(os.getenv("PLAFOND_RETOUCHE_USD", "0.5"))     # une image (et son contrôle) par retouche


def _correction(cid):
    with db._db() as c:
        r = c.execute("select * from corrections where id=?", (cid,)).fetchone()
    return dict(r) if r else None


@bp.post("/admin/api/corrections/<cid>/retoucher")
def admin_retoucher(cid):
    """Refait UNE illustration du livre (couverture ou double page), avec la consigne d'Alex, dans le style et avec les mêmes
    références. Le livre n'est pas modifié : l'image attend « Publier » (nouvelle version)."""
    import boutique as B
    if not B.admin_ok():
        abort(403)
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify(erreur="OPENAI_API_KEY absente."), 503
    cr = _correction(cid) or abort(404)
    consigne = _txt((request.get_json(force=True, silent=True) or {}).get("consigne") or cr["demande"], 400)
    with db._lock, db._db() as c:
        c.execute("update corrections set statut='en_cours' where id=?", (cid,))
    threading.Thread(target=_retoucher, args=(cid, consigne), daemon=True).start()
    return jsonify(ok=True, plafond_usd=PLAFOND_RETOUCHE)


def _retoucher(cid, consigne):
    import procede as P, budget as BU, generator as G
    cr = _correction(cid)
    p = get(cr["projet_id"])
    folder, book, v = livre_courant(p)
    livre = f"retouche-{cid}"
    BU.PLAFONDS[livre] = PLAFOND_RETOUCHE
    jeton = BU.LIVRE.set(livre)
    try:
        snap = json.loads((folder / "instantane.json").read_text(encoding="utf-8"))
        b = json.loads((folder / "storyboard.json").read_text(encoding="utf-8"))
        portraits = {f.stem.replace("portrait_", ""): f for f in folder.glob("portrait_*.png")}
        q = G._m("q_scene", G.SCENE_QUALITY)
        if cr["page"] == 0:
            crefs = P.refs_for(b["coverCharacterIds"], portraits, None, folder, "couverture", snap)
            prompt = P.cover_prompt(b, snap, crefs) + "\nCORRECTIONS REQUIRED (requested by the parent): " + consigne
            out = folder / f"couverture-retouche-{cid}.png"
            P.image(prompt, crefs, out, P.COVER_SIZE, G._m("q_main", G.IMAGE_QUALITY), f"retouche {cid}", etape="retouche couverture")
        else:
            s = b["spreads"][cr["page"] - 1]
            refs, _ = P.spread_target(s, snap, portraits, folder / book["cover"], folder, q)
            prompt = P.pano_prompt(s, snap, b, refs, fix=[consigne])
            out = folder / f"spread-{s['id']}-retouche-{cid}.png"
            P.image(prompt, refs, out, P.PANO_SIZE, q, f"retouche {cid}", etape=f"retouche double page {s['id']}")
        with db._lock, db._db() as c:
            c.execute("update corrections set statut='a_valider', fichier=? where id=?", (out.name, cid))
        log(f"retouche {cid} prête à valider ({BU.depense(livre)['total']:.2f} $)")
    except Exception as e:
        with db._lock, db._db() as c:
            c.execute("update corrections set statut='demandee', reponse=? where id=?", (f"Retouche impossible : {e}"[:400], cid))
        log(f"retouche {cid} impossible : {e}")
    finally:
        BU.LIVRE.reset(jeton)


@bp.get("/admin/api/corrections/<cid>/image")
def admin_retouche_image(cid):
    import boutique as B
    if not B.admin_ok():
        abort(403)
    cr = _correction(cid) or abort(404)
    folder, _, _ = livre_courant(get(cr["projet_id"]))
    f = folder / (cr.get("fichier") or "_")
    return send_file(f, max_age=0) if cr.get("fichier") and f.exists() else abort(404)


@bp.post("/admin/api/corrections/<cid>/publier")
def admin_publier_retouche(cid):
    """L'image retouchée remplace l'ancienne dans une NOUVELLE version du livre (les versions précédentes et les commandes reliées
    déjà passées ne changent pas)."""
    import boutique as B, moteur_livre as M
    if not B.admin_ok():
        abort(403)
    cr = _correction(cid) or abort(404)
    p = get(cr["projet_id"])
    folder, book, v = livre_courant(p)
    if not cr.get("fichier") or not (folder / cr["fichier"]).exists():
        return jsonify(erreur="Aucune image retouchée à publier."), 400
    nb = json.loads(json.dumps(book))
    if cr["page"] == 0:
        nb["cover"] = cr["fichier"]
    else:
        nb["spreads"][cr["page"] - 1] = cr["fichier"]
    n = v + 1
    (folder / "versions").mkdir(exist_ok=True)
    fj, fp = f"versions/livre-v{n}.json", f"versions/livre-v{n}.pdf"
    (folder / fj).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = M.render(nb, folder / fp, base=folder, work=folder / "versions" / f"rendu-v{n}")
    shutil.rmtree(folder / "versions" / f"rendu-v{n}", ignore_errors=True)
    with db._lock, db._db() as c:
        c.execute("insert into versions (id, projet_id, numero, cree, motif, fichier, pdf) values (?,?,?,?,?,?,?)", (secrets.token_hex(6), p["id"], n, time.time(), "illustration", fj, fp))
        c.execute("update corrections set statut='faite' where id=?", (cid,))
    return jsonify(ok=True, version=n, problemes=rep.get("problemes_rendu"))
