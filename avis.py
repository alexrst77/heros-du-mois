# -*- coding: utf-8 -*-
"""Avis clients VÉRIFIÉS, avec photos : seuls les clients dont la commande a été expédiée peuvent en laisser un (lien secret).

- Demande d'avis : un seul e-mail, 10 jours après l'expédition (lien secret), jamais aux désinscrits. Aussi dans « Mon compte ».
- Modération (admin) : tout avis conforme est publié, positif ou négatif ; seuls les avis hors sujet, injurieux ou contenant
  des données personnelles sont refusés. C'est ce qu'affiche le site (article L111-7-2 du Code de la consommation).
- Photos : réduites, converties en WebP, métadonnées (GPS…) retirées. Rien n'est inventé : sans avis publié, rien ne s'affiche."""
import io, json, re, time, hmac, hashlib, secrets, threading
from flask import Blueprint, request, jsonify, send_from_directory, abort, Response
from PIL import Image, ImageOps
import commandes as db

bp = Blueprint("avis", __name__)
DOSSIER = db.DATA / "avis"
FICHIER = DOSSIER / "avis.json"
DEMANDES = DOSSIER / "demandes.json"
DELAI_JOURS = 10
_lock = threading.Lock()


def _lire(p, defaut):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire(p, d):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def tous():
    return _lire(FICHIER, [])


def publies():
    return [a for a in tous() if a.get("statut") == "publie"]


def jeton(origine):
    import suivi
    return hmac.new(suivi._secret(), f"avis:{origine}".encode(), hashlib.sha256).hexdigest()[:24]


def lien(origine, site=None):
    import os
    site = (site or os.getenv("PUBLIC_URL") or "").rstrip("/")
    return f"{site}/avis/{origine}?j={jeton(origine)}"


def peut_noter(origine):
    """La commande (tête de pack) existe et au moins un de ses produits est expédié."""
    o = db.get(origine)
    if not o or (o.get("formule") or "").startswith("essai"):
        return False
    return any(x["statut"] == "expediee" for x in db.lister(100000) if x["origine"] == origine)


def deja(origine):
    return next((a for a in tous() if a["origine"] == origine), None)


def prenom_public(nom):
    """« Sophie Martin » -> « Sophie M. » : jamais le nom complet."""
    p = [x for x in re.split(r"\s+", (nom or "").strip()) if x]
    if not p:
        return "Un client"
    return p[0].capitalize() + (f" {p[-1][0].upper()}." if len(p) > 1 else "")


def enregistrer(origine, note, texte, nom, fichiers, consent):
    if not peut_noter(origine):
        raise ValueError("Cette commande ne peut pas encore recevoir d'avis.")
    if deja(origine):
        raise ValueError("Vous avez déjà donné votre avis pour cette commande, merci !")
    note = int(note)
    if not 1 <= note <= 5:
        raise ValueError("Choisissez une note de 1 à 5 étoiles.")
    texte = re.sub(r"\s+", " ", texte or "").strip()[:1200]
    if len(texte) < 10:
        raise ValueError("Écrivez quelques mots sur votre livre (10 caractères au moins).")
    if not consent:
        raise ValueError("Cochez la case pour accepter la publication de votre avis.")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    photos = []
    for f in fichiers[:4]:
        data = f.read(15 * 1024 * 1024 + 1)
        if not data:
            continue
        if len(data) > 15 * 1024 * 1024:
            raise ValueError("Photo trop lourde (15 Mo au maximum).")
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        except Exception:
            raise ValueError("Format de photo non reconnu (JPG ou PNG).")
        im.thumbnail((1400, 1400))
        nom_f = f"{origine}-{secrets.token_hex(4)}.webp"
        im.save(DOSSIER / nom_f, "WEBP", quality=82)
        photos.append(nom_f)
    o = db.get(origine)
    a = {"id": secrets.token_hex(6), "origine": origine, "note": note, "texte": texte,
         "nom": prenom_public(nom or ((o.get("adresse") or {}).get("nom") if o else "")), "photos": photos,
         "produits": sorted({x["formule"] for x in db.lister(100000) if x["origine"] == origine}),
         "date": time.strftime("%Y-%m-%d"), "statut": "attente"}
    with _lock:
        l = tous(); l.append(a); _ecrire(FICHIER, l)
    return a


def moderer(aid, statut):
    with _lock:
        l = tous()
        for a in l:
            if a["id"] == aid:
                a["statut"] = statut
                a["modere"] = time.strftime("%Y-%m-%d")
        _ecrire(FICHIER, l)


def resume():
    p = publies()
    return {"nombre": len(p), "moyenne": round(sum(a["note"] for a in p) / len(p), 1) if p else None}


# ------------------------------------------------------------------ demande d'avis (une seule, 10 jours après l'expédition)
def demander_auto(maintenant=None):
    import os, boutique, suivi
    from urllib.parse import quote_plus
    site = (os.getenv("PUBLIC_URL") or "").rstrip("/")
    maintenant = maintenant or time.time()
    if not boutique.mail_configure():
        return []
    faites = _lire(DEMANDES, {})
    envoyes = []
    tetes = {}
    for x in db.lister(100000):
        if x["origine"] and x["origine"] == x["id"]:
            tetes[x["id"]] = x
    for ori, o in tetes.items():
        if ori in faites or deja(ori) or (o.get("formule") or "").startswith("essai"):
            continue
        groupe = [x for x in db.lister(100000) if x["origine"] == ori]
        if not groupe or not all(x["statut"] in ("expediee", "annulee") for x in groupe) or not any(x["statut"] == "expediee" for x in groupe):
            continue
        if (o.get("maj") or 0) > maintenant - DELAI_JOURS * 86400 or not o.get("email") or suivi.desinscrit(o["email"]):
            continue
        prenom = ""
        try:
            prenom = (boutique.load_book(ori)[0].get("prenom") or "").strip()
        except Exception:
            pass
        corps = (f"Bonjour,\n\n{('Le livre de ' + prenom) if prenom else 'Votre commande'} est arrivé chez vous il y a quelques jours. "
                 "Est-ce qu'il lui a plu ?\n\nVotre avis nous aide énormément, et une photo du livre (même sans l'enfant) rassure les "
                 f"autres parents : beaucoup se demandent si le livre est bien réel.\n\nDonner mon avis (2 minutes) : {lien(ori)}\n\n"
                 "Merci beaucoup,\nAlexandre, Mon Héros du Mois\n\n—\nNe plus recevoir ces messages : "
                 f"{site}/stop-rappels?e={quote_plus(o['email'])}&t={suivi._jeton_mail(o['email'])}")
        try:
            if boutique.send_mail("Votre avis sur le livre" + (f" de {prenom}" if prenom else ""), corps, to=o["email"]):
                faites[ori] = time.strftime("%Y-%m-%d"); envoyes.append(ori)
        except Exception as e:
            print("demande d'avis impossible :", e)
    if envoyes:
        _ecrire(DEMANDES, faites)
    return envoyes


# ------------------------------------------------------------------ pages et API
PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Votre avis – Mon Héros du Mois</title><meta name="robots" content="noindex"><link rel="icon" type="image/png" href="/static/marque/favicon-64.png">
<link rel="stylesheet" href="/static/theme.css"><style>
body{background:var(--ciel)}.page{max-width:560px;margin:0 auto;padding:28px 16px 80px}h1{font:400 clamp(28px,4vw,38px)/1.15 var(--titre);margin:10px 0 8px}
.lead{color:var(--encre-2);margin:0 0 20px}.carte{background:var(--papier);border:1px solid var(--trait);border-radius:22px;padding:22px}
label{display:block;font-weight:800;font-size:15px;margin:14px 0 6px}input[type=text],textarea{width:100%;font:600 16px var(--texte);padding:12px 14px;border:2px solid var(--trait);border-radius:14px;background:#fff;color:var(--encre)}
textarea{min-height:130px}.etoiles{display:flex;gap:6px}.etoiles button{font-size:38px;line-height:1;border:0;background:none;cursor:pointer;color:#D9CFEA;padding:0}
.etoiles button.on{color:#F2B630}.chk{display:flex;gap:10px;align-items:flex-start;font-size:14px;margin:16px 0}.chk input{margin-top:4px}
.btn{width:100%;margin-top:6px}.err{color:var(--erreur);font-weight:700;margin-top:10px}.note{font-size:13px;color:var(--encre-2);margin-top:14px}
</style></head><body><main class="page"><a href="/"><img src="/static/marque/logo-h.webp" alt="Mon Héros du Mois" style="height:46px"></a>
__CORPS__</main></body></html>"""

FORM = """<h1>Votre avis sur son livre</h1><p class="lead">2 minutes pour aider d'autres parents à se décider. Une photo du livre reçu les rassure beaucoup.</p>
<form class="carte" id="f" enctype="multipart/form-data">
<label>Votre note</label><div class="etoiles" id="et">__ETOILES__</div>
<label for="t">Votre avis</label><textarea id="t" maxlength="1200" placeholder="Qu'en a pensé votre enfant ? Et vous, la qualité du livre, les illustrations, la livraison…" required></textarea>
<label for="n">Votre prénom (affiché avec l'initiale du nom)</label><input type="text" id="n" maxlength="60" value="__NOM__">
<label for="p">Photos du livre (facultatif, 4 au maximum)</label><input type="file" id="p" accept="image/*" multiple>
<p class="note">Si vous préférez, photographiez le livre sans le visage de votre enfant.</p>
<label class="chk"><input type="checkbox" id="c"> <span>J'accepte que mon avis, mon prénom avec l'initiale de mon nom et mes photos soient publiés sur le site Mon Héros du Mois.</span></label>
<button class="btn" type="submit" id="go">Envoyer mon avis</button><p class="err" id="err"></p>
<p class="note">Avis vérifié : seuls les clients ayant reçu leur commande peuvent laisser un avis. Tous les avis sont publiés, positifs comme négatifs, sauf s'ils sont hors sujet, injurieux ou contiennent des données personnelles.</p></form>
<script>
let N = 0; const B = [...document.querySelectorAll('#et button')];
B.forEach((b, i) => b.onclick = () => { N = i + 1; B.forEach((x, k) => x.classList.toggle('on', k < N)); });
document.getElementById('f').onsubmit = async ev => {
  ev.preventDefault(); const e = document.getElementById('err'); e.textContent = '';
  const fd = new FormData(); fd.append('note', N); fd.append('texte', document.getElementById('t').value); fd.append('nom', document.getElementById('n').value);
  fd.append('consent', document.getElementById('c').checked ? '1' : ''); [...document.getElementById('p').files].slice(0, 4).forEach(f => fd.append('photos', f));
  const g = document.getElementById('go'); g.disabled = true; g.textContent = 'Envoi…';
  try { const r = await fetch(location.pathname + location.search, { method: 'POST', body: fd }); const j = await r.json();
    if (r.ok) { document.querySelector('main').innerHTML = '<a href="/"><img src="/static/marque/logo-h.webp" alt="Mon Héros du Mois" style="height:46px"></a><h1>Merci beaucoup !</h1><p class="lead">Votre avis sera publié après une vérification rapide.</p><a class="btn" href="/">Retour au site</a>'; return; }
    e.textContent = j.erreur || 'Erreur, réessayez.'; } catch (_) { e.textContent = 'Envoi impossible (photos trop lourdes ?). Réessayez.'; }
  g.disabled = false; g.textContent = 'Envoyer mon avis';
};
</script>"""


def _page(corps):
    return Response(PAGE.replace("__CORPS__", corps), mimetype="text/html")


@bp.route("/avis/<origine>", methods=["GET", "POST"])
def page_avis(origine):
    if not re.fullmatch(r"[a-f0-9]{12}", origine) or not hmac.compare_digest(request.args.get("j", ""), jeton(origine)):
        abort(404)
    if request.method == "POST":
        try:
            enregistrer(origine, request.form.get("note") or 0, request.form.get("texte"), request.form.get("nom"),
                        request.files.getlist("photos"), bool(request.form.get("consent")))
            return jsonify(ok=True)
        except ValueError as e:
            return jsonify(erreur=str(e)), 400
    if deja(origine):
        return _page("<h1>Merci !</h1><p class='lead'>Vous avez déjà donné votre avis pour cette commande.</p><a class='btn' href='/'>Retour au site</a>")
    if not peut_noter(origine):
        return _page("<h1>Un peu de patience</h1><p class='lead'>Vous pourrez donner votre avis dès que votre commande sera expédiée.</p><a class='btn' href='/'>Retour au site</a>")
    from html import escape
    o = db.get(origine)
    nom = prenom_public((o.get("adresse") or {}).get("nom"))
    return _page(FORM.replace("__ETOILES__", "".join(f'<button type="button" aria-label="{i} étoile{"s" if i > 1 else ""}">★</button>' for i in range(1, 6)))
                 .replace("__NOM__", escape("" if nom == "Un client" else nom.split(" ")[0])))


@bp.get("/api/avis")
def api_avis():
    l = sorted(publies(), key=lambda a: a["date"], reverse=True)
    return jsonify(resume=resume(), avis=[{"note": a["note"], "texte": a["texte"], "nom": a["nom"], "date": a["date"], "produits": a.get("produits", []),
                                           "photos": [f"/avis-photo/{p}" for p in a.get("photos", [])]} for a in l])


@bp.get("/avis-photo/<nom>")
def photo(nom):
    if not re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{8}\.webp", nom):
        abort(404)
    a = next((x for x in tous() if nom in x.get("photos", [])), None)
    if not a or a.get("statut") != "publie":
        import boutique
        if not boutique.admin_ok():
            abort(404)
    r = send_from_directory(DOSSIER, nom)
    r.headers["Cache-Control"] = "public, max-age=604800"
    return r


def _admin():
    import boutique
    if not boutique.admin_ok():
        abort(403)


@bp.get("/admin/api/avis")
def admin_liste():
    _admin()
    return jsonify(avis=sorted(tous(), key=lambda a: a["date"], reverse=True), resume=resume())


@bp.post("/admin/api/avis/<aid>/<action>")
def admin_moderer(aid, action):
    _admin()
    if action not in ("publier", "refuser", "attente"):
        abort(404)
    moderer(aid, {"publier": "publie", "refuser": "refuse", "attente": "attente"}[action])
    return jsonify(ok=True)


@bp.get("/admin/api/avis-lien/<origine>")
def admin_lien(origine):
    _admin()
    return jsonify(lien=lien(origine, request.host_url), possible=peut_noter(origine))
