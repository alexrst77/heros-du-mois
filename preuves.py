# -*- coding: utf-8 -*-
"""« Vraies photos » : photos et vidéos de livres réellement reçus, ajoutées depuis l'admin et montrées sur l'accueil.

Rien n'est inventé : la section de l'accueil reste cachée tant qu'aucune photo n'a été ajoutée. Les photos sont réduites
(1600 px), converties en WebP et leurs métadonnées (GPS, appareil) sont retirées ; les vidéos sont gardées telles quelles."""
import io, json, re, time, secrets
from flask import Blueprint, request, jsonify, send_from_directory, abort
from PIL import Image, ImageOps
import commandes as db
import legal

bp = Blueprint("preuves", __name__)
DOSSIER = db.DATA / "preuves"
INDEX = DOSSIER / "index.json"
VIDEOS = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/mp4"}
MAX_VIDEO = 80 * 1024 * 1024
MAX_N = 24


def liste():
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(l):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(l, ensure_ascii=False, indent=1), encoding="utf-8")


def ajouter(fichier, nom, legende=""):
    """Enregistre une photo (WebP nettoyé) ou une vidéo. Renvoie l'élément ajouté."""
    l = liste()
    if len(l) >= MAX_N:
        raise ValueError(f"{MAX_N} éléments au maximum : supprimez-en un d'abord.")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    ext = ("." + nom.rsplit(".", 1)[-1].lower()) if "." in nom else ""
    cle = time.strftime("%Y%m%d") + "-" + secrets.token_hex(4)
    data = fichier.read(MAX_VIDEO + 1)
    if ext in VIDEOS:
        if len(data) > MAX_VIDEO:
            raise ValueError("Vidéo trop lourde (80 Mo au maximum) : coupez-la ou envoyez-la en qualité réduite.")
        out = f"{cle}{ext}"
        (DOSSIER / out).write_bytes(data)
        el = {"id": cle, "fichier": out, "type": "video", "mime": VIDEOS[ext]}
    else:
        try:
            im = Image.open(io.BytesIO(data))
            im = ImageOps.exif_transpose(im).convert("RGB")          # bon sens, puis plus aucune métadonnée (GPS…)
        except Exception:
            raise ValueError("Format non reconnu : envoyez une photo (JPG, PNG, HEIC converti) ou une vidéo MP4.")
        im.thumbnail((1600, 1600))
        out = f"{cle}.webp"
        im.save(DOSSIER / out, "WEBP", quality=84)
        el = {"id": cle, "fichier": out, "type": "photo", "l": im.width, "h": im.height}
    el["legende"] = re.sub(r"\s+", " ", legende or "").strip()[:140]
    el["ajoute"] = time.time()
    l.append(el)
    _ecrire(l)
    return el


def supprimer(cle):
    l = liste()
    for el in [x for x in l if x["id"] == cle]:
        try:
            (DOSSIER / el["fichier"]).unlink()
        except OSError:
            pass
    _ecrire([x for x in l if x["id"] != cle])


def deplacer(cle, sens):
    l = liste()
    i = next((k for k, x in enumerate(l) if x["id"] == cle), None)
    j = None if i is None else i + (1 if sens > 0 else -1)
    if i is not None and 0 <= j < len(l):
        l[i], l[j] = l[j], l[i]
        _ecrire(l)


def vendeur_public():
    """Ce qui rassure un client et figure déjà dans les mentions légales : nom, ville, SIRET, contact."""
    d = legal.lire()
    adr = d.get("adresse") or ""
    m = re.search(r"\b\d{5}\s+([^,]+)", adr)
    return {"nom": d.get("raison_sociale") or "", "ville": (m.group(1).strip() if m else ""), "siret": d.get("siret") or "",
            "email": d.get("email") or ""}


# ------------------------------------------------------------------ routes
@bp.get("/api/preuves")
def api_liste():
    return jsonify(preuves=[{k: x.get(k) for k in ("id", "type", "mime", "legende", "l", "h")} | {"url": f"/preuves/{x['fichier']}"} for x in liste()])


@bp.get("/preuves/<path:nom>")
def fichier(nom):
    if not re.match(r"^[0-9]{8}-[0-9a-f]{8}\.(webp|mp4|webm|mov|m4v)$", nom):
        abort(404)
    r = send_from_directory(DOSSIER, nom, conditional=True)
    r.headers["Cache-Control"] = "public, max-age=604800"
    return r


def _admin():
    import boutique
    if not boutique.admin_ok():
        abort(403)


@bp.get("/admin/api/preuves")
def admin_liste():
    _admin()
    return jsonify(preuves=[x | {"url": f"/preuves/{x['fichier']}"} for x in liste()])


@bp.post("/admin/api/preuves")
def admin_ajout():
    _admin()
    fs = request.files.getlist("fichier")
    if not fs:
        return jsonify(erreur="Aucun fichier reçu."), 400
    ok, err = [], []
    for f in fs:
        try:
            ok.append(ajouter(f.stream, f.filename or "", request.form.get("legende", "")))
        except ValueError as e:
            err.append(f"{f.filename} : {e}")
    return jsonify(ajoutes=len(ok), erreurs=err), (200 if ok else 400)


@bp.post("/admin/api/preuves/<cle>/supprimer")
def admin_suppr(cle):
    _admin()
    supprimer(cle)
    return jsonify(ok=True)


@bp.post("/admin/api/preuves/<cle>/deplacer")
def admin_deplacer(cle):
    _admin()
    deplacer(cle, int((request.get_json(silent=True) or {}).get("sens", 1)))
    return jsonify(ok=True)


@bp.post("/admin/api/preuves/<cle>/legende")
def admin_legende(cle):
    _admin()
    l = liste()
    for x in l:
        if x["id"] == cle:
            x["legende"] = re.sub(r"\s+", " ", (request.get_json(silent=True) or {}).get("legende", "")).strip()[:140]
    _ecrire(l)
    return jsonify(ok=True)
