# -*- coding: utf-8 -*-
"""Serveur « Mon Héros du Mois » : éditeur d'avatars -> histoire -> storyboard -> planche personnages (validée)
-> aperçu couverture + 2 doubles pages (validé) -> livre complet de 20 pages + contrôle qualité.
Lancement : python app.py   puis ouvrir http://localhost:8000"""
import os, sys, json, uuid, threading, time, shutil, traceback, base64, io, re
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory, abort, redirect, Response
from PIL import Image

ROOT = Path(__file__).parent
try:  # charge le fichier .env s'il existe
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
except FileNotFoundError:
    pass

import layout, generator, procede  # noqa: E402  (après le chargement du .env)

DATA = Path(os.getenv("DATA_DIR") or ROOT)                  # en ligne : le disque permanent (ex. /data)
OUT = DATA / "output"; OUT.mkdir(parents=True, exist_ok=True)
KEEP_HOURS = int(os.getenv("KEEP_HOURS", "24"))     # les données des enfants sont effacées après ce délai
ACCESS_CODE = os.getenv("ACCESS_CODE", "")            # protège ton crédit API tant que le site n'est pas public
AUTO_VALIDATE = os.getenv("AUTO_VALIDATE", "") == "1" # 1 = pas d'étapes de validation (génération d'un seul tenant)
JOBS = {}

app = Flask(__name__, static_folder=str(ROOT / "static"))


@app.before_request
def _domaine_principal():
    """Une seule adresse publique : www.domaine et l'ancienne adresse *.up.railway.app renvoient (301) vers PUBLIC_URL.
    Seulement pour les pages lues (GET/HEAD) : les webhooks Stripe/Lulu (POST) et le contrôle de santé Railway ne sont pas touchés."""
    from urllib.parse import urlsplit
    pub = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not pub or request.method not in ("GET", "HEAD"):
        return None
    cible = urlsplit(pub).netloc.lower()
    hote = request.host.split(":")[0].lower()
    if cible and hote != cible and (hote.endswith(".up.railway.app") or hote == "www." + cible):
        from flask import redirect
        return redirect(pub + request.full_path.rstrip("?"), code=301)
    return None

REQUIRED = ["prenom", "age"]
FIELDS = ["prenom", "age", "naissance", "genre", "cheveux", "yeux", "peau", "lunettes", "tenue", "doudou_nom", "doudou_type",
          "doudou_desc", "animal", "passions", "univers", "fetes", "anniversaire", "heros_livre", "theme", "precision", "numero", "demo", "code"]
PUBLIC = re.compile(r"^(portrait_[a-z0-9_]+\.png|image_\d\d\.png|apercu\.pdf|controle\.json)$")


def cleanup():
    limit = time.time() - KEEP_HOURS * 3600
    for d in OUT.iterdir():
        if d.is_dir() and d.stat().st_mtime < limit and not (d / ".commande").exists():   # les livres commandés sont gardés
            shutil.rmtree(d, ignore_errors=True)
            JOBS.pop(d.name, None)


def save_png(url, path):
    """Image envoyée par le navigateur (data URL PNG) -> fichier, après contrôle du format et de la taille."""
    try:
        if not isinstance(url, str) or not url.startswith("data:image/png;base64,") or len(url) > 1_500_000:
            return None
        im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))); im.load()
        if max(im.size) > 1200:
            return None
        rgba = im.convert("RGBA"); bg = Image.new("RGB", im.size, (246, 238, 222)); bg.paste(rgba, (0, 0), rgba)
        bg.save(path); return Path(path)
    except Exception:
        return None


def save_avatar_pngs(data, folder):
    """Guides couleurs dessinés par le navigateur, par personnage."""
    out = {}
    items = [("enfant", data.get("enfant"))] + ([("doudou", data["doudou"])] if data.get("doudou") else []) + \
            [(f"animal_{i}", a) for i, a in enumerate((data.get("animaux") or [])[:3])]
    for name, url in items:
        p = save_png(url, folder / f"guide_{name}.png")
        if p:
            out[name] = p
    return out


def save_previews(data, folder):
    """Aperçus recolorés dans le navigateur (modèle peint + couleurs du parent)."""
    out = {}
    items = [("enfant", data.get("enfant")), ("doudou", data.get("doudou"))] + \
            [(f"animal_{i}", a) for i, a in enumerate((data.get("animaux") or [])[:3])]
    for name, url in items:
        p = save_png(url, folder / f"apercu_{name}.png") if url else None
        if p:
            out[name] = p
    return out


def browser_refs(guides, previews):
    """Guides couleurs et aperçus recolorés du navigateur, rangés par identifiant stable de personnage."""
    out = {}
    for name, p in guides.items():
        out.setdefault(char_id(name), {})["guide"] = p
    for name, p in (previews or {}).items():
        out.setdefault(char_id(name), {})["apercu"] = p
    return out


def char_id(name):
    """enfant -> heros ; doudou -> doudou ; animal_0 -> animal_1 (même ordre que dans l'éditeur)."""
    if name == "enfant": return "heros"
    if name.startswith("animal_"): return f"animal_{int(name.split('_')[1]) + 1}"
    return name


def public(job):
    return {k: v for k, v in job.items() if not k.startswith("_")}


def wait_decision(job, step, payload):
    """Met le travail en pause jusqu'au choix du parent (valider / redessiner)."""
    if AUTO_VALIDATE or job.get("_auto"):      # renouvellement d'abonnement : personne ne suit en direct
        return {"action": "valider"}
    ev = threading.Event()
    job.update(etat="validation", validation=dict(etape=step, **payload), _ev=ev, _decision=None)
    ev.wait(timeout=6 * 3600)
    d = job.get("_decision") or {"action": "valider"}
    job.update(etat="en_cours", validation=None)
    return d


def run(job_id, form, refs):
    """Chaîne complète (lancée APRÈS paiement) : configuration -> histoire -> storyboard -> portraits validés
    -> aperçu validé -> 18 pages -> PDF écran + fichiers d'impression + contrôle qualité."""
    job = JOBS[job_id]; folder = OUT / job_id

    def progress(step, pct=None):
        job["etape"] = step
        if pct is not None:
            job["progression"] = pct

    def save(name, data):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    meter = generator.start_meter()       # coût OpenAI de ce livre (images + textes + contrôles)
    essai = job.get("_essai")             # None | "brouillon" (tout le livre, petite qualité) | "apercu" (couverture + 2 pages, vraie qualité)
    if essai == "brouillon":
        generator.MODE.set(generator.BROUILLON)
    try:
        if os.getenv("PROCEDE", "kit") == "kit":       # procédé des livres Mila et Noé (kit) : voir procede.py
            if form.get("produit") in ("calendrier", "coloriage", "gourde", "tasse", "sac"):   # calendrier, coloriage, objets Printful
                import importlib
                mod = importlib.import_module("objets" if form["produit"] in ("gourde", "tasse", "sac") else form["produit"])
                cfg = generator.build_config(form); save("config.json", cfg)
                if form.get("demo") or not os.getenv("OPENAI_API_KEY"):
                    res = mod.demo(form, cfg, folder, job, progress)
                else:
                    res = mod.run(form, cfg, refs, folder, job, progress)
            elif form.get("demo") or not os.getenv("OPENAI_API_KEY"):
                res = procede.demo(folder, progress)
            else:
                cfg = generator.build_config(form); save("config.json", cfg)
                res = procede.run(form, cfg, refs, folder, job, progress, essai=essai)
            if essai == "apercu":
                res["titre"] = "[aperçu] " + res["titre"]
            job.update(etat="termine", progression=100, etape="Livre prêt" if res["phase"] == "ready" else "À relire : écarts signalés",
                       pdf=res["pdf"], titre=res["titre"], controle=res["controle"], mineurs=res["mineurs"], pages=res["pages"],
                       cout=res.get("cout") if res.get("cout") is not None else round(meter["dollars"], 2), format="kit",
                       finalise=bool(res.get("finalise")))
            return
        if not (form.get("demo") or not os.getenv("OPENAI_API_KEY")):
            raise RuntimeError("Ancien procédé désactivé : il ne passe pas par le plafond de 3 $ par livre (PROCEDE=kit obligatoire)")
        portraits_pdf = None
        if form.get("demo") or not os.getenv("OPENAI_API_KEY"):
            progress("Mode démo : livre d'exemple, sans appel API", 20)
            story = json.loads((ROOT / "demo" / "story.json").read_text(encoding="utf-8"))
            story["univers"] = "Une forêt enchantée"
            story["pages"] = [{"texte": d["texte_image"] + d["texte_chapitre"][:1]} for d in story["doubles_pages"]]
            images = [ROOT / "demo" / f"image_{i:02d}.jpg" for i in range(10)]
            images += images[1:]                        # démo : 18 pages à partir des 9 illustrations de Léo
            board = None
        else:
            cfg = generator.build_config(form)
            old = lambda n: json.loads((folder / n).read_text(encoding="utf-8")) if (folder / n).exists() else None
            reprise = job.get("_reprise") and old("config.json") == cfg and old("histoire.json") and old("storyboard.json")
            if reprise:                                   # reprise après coupure : histoire et storyboard déjà payés
                story, board = old("histoire.json"), old("storyboard.json")
                generator.REUSE.add(str(folder))
            else:
                generator.REUSE.discard(str(folder))
                for f in folder.glob("image_*.png"): f.unlink()
                save("config.json", cfg)
                progress("Écriture et relecture de l'histoire", 3)
                story = generator.write_story(cfg, form); save("histoire.json", story)
                progress("Storyboard des 18 pages", 7)
                board = generator.make_storyboard(story); save("storyboard.json", board)
                save("histoire.json", story)             # le storyboard peut déclarer un personnage oublié (ex. une créature)

            # portraits de référence, un par personnage, validés par le parent (redessin personnage par personnage)
            variants, portraits = {}, {}
            todo = [c["id"] for c in story["personnages"]]
            while True:
                progress("Portraits de référence des personnages", 10)
                for c in story["personnages"]:
                    if c["id"] not in todo: continue
                    r = refs.get(c["id"], {})
                    if c["type"] == "invente":
                        src = generator.draw_invented(c, variants.get(c["id"], 0))
                    else:
                        src = generator.draw_portrait(c, r.get("guide"), variants.get(c["id"], 0), base=r.get("apercu"))
                    dst = folder / f"portrait_{c['id']}.png"; shutil.copy(src, dst); portraits[c["id"]] = dst
                d = wait_decision(job, "personnages", {"titre": "Voici les personnages du livre",
                    "texte": "Ils garderont cette apparence sur toutes les pages. Coche ceux à redessiner si besoin.",
                    "images": [{"id": c["id"], "nom": c["nom"], "fichier": f"portrait_{c['id']}.png"} for c in story["personnages"]]})
                if d.get("action") != "redessiner" or not d.get("ids"):
                    break
                todo = [x for x in d["ids"] if x in portraits]
                for x in todo: variants[x] = variants.get(x, 0) + 1
            save("portraits.json", {x: {"fichier": v.name, "cle": next((c.get("cle") for c in story["personnages"] if c["id"] == x), None),
                                        "variante": variants.get(x, 0)} for x, v in portraits.items()})
            portraits_pdf = [(portraits[c["id"]], c["nom"]) for c in story["personnages"] if c["id"] in portraits]

            while True:   # aperçu : couverture + 2 premières pages
                progress("Aperçu : couverture et deux premières pages", 25)
                cover = generator.draw_cover(board, story, portraits, folder)
                first = generator.draw_scenes(board, story, portraits, folder, [0, 1], lambda s: progress(s, 38))
                images = [cover, first[0], first[1]] + [None] * 16
                progress("Mise en page de l'aperçu", 45)
                qa_prev = layout.build_pdf(story, images, folder / "apercu.pdf", storyboard=board["pages"], pages=[0, 1])
                d = wait_decision(job, "apercu", {"pdf": "apercu.pdf", "image": "image_00.png", "titre": "Aperçu du livre",
                                                  "texte": "Couverture et deux premières pages. On continue avec ce rendu ?",
                                                  "controle": qa_prev["problemes"]})
                if d.get("action") != "redessiner":
                    break
            if essai == "apercu":                         # essai : on s'arrête à l'aperçu (couverture + 2 pages)
                qa_prev["cout_openai"] = {"dollars": round(meter["dollars"], 2), "appels": meter["appels"]}
                save("controle.json", qa_prev)
                job.update(etat="termine", progression=100, etape="Aperçu prêt", pdf="apercu.pdf",
                           titre="[aperçu] " + " ".join(story["titre"]), controle=qa_prev["problemes"],
                           mineurs=qa_prev.get("mineurs", []), pages=qa_prev["pages"], cout=round(meter["dollars"], 2))
                return
            rest = generator.draw_scenes(board, story, portraits, folder, list(range(2, 18)),
                                         lambda s: progress(s, 48 + 2 * int(s.split()[-1].split("/")[0])))
            images = [cover, first[0], first[1]] + [rest[i] for i in range(2, 18)]
            save("storyboard.json", board)
        progress("Mise en page du livre", 88)
        name = '-'.join(story['titre']).replace(' ', '-').replace('/', '-')[:80]
        pdf = folder / f"{name}.pdf"
        qa = layout.build_pdf(story, images, pdf, lambda s: progress(s), storyboard=(board or {}).get("pages"))
        progress("Fichiers d'impression", 94)
        qa_print = layout.build_pdf(story, images, folder / "impression_interieur.pdf", storyboard=(board or {}).get("pages"),
                                    mode="impression", portraits=portraits_pdf)
        # l'intérieur d'impression reprend les mêmes images : on n'y garde que ses propres problèmes de mise en page
        own = [x for x in qa_print["problemes"] if "écart bloquant" not in x and "dominante" not in x]
        qa["impression"] = {"pages": qa_print["pages"], "problemes": own}
        qa["histoire"] = story.get("controle_histoire", []) + [f"doublon supprimé : {x}" for x in story.get("doublons_supprimes", [])]
        qa["storyboard"] = (board or {}).get("controle", [])
        qa["configuration"] = json.loads((folder / "config.json").read_text())["problemes"] if (folder / "config.json").exists() else []
        qa["cout_openai"] = {"dollars": round(meter["dollars"], 2), "appels": meter["appels"],
                             "detail": {k: {"appels": v[0], "dollars": round(v[1], 2)} for k, v in meter["detail"].items()}}
        save("controle.json", qa)
        job.update(etat="termine", progression=100, etape="Livre prêt", pdf=pdf.name, titre=" ".join(story["titre"]),
                   controle=qa["problemes"] + [f"impression : {x}" for x in qa["impression"]["problemes"]] + qa["configuration"],
                   mineurs=qa.get("mineurs", []), pages=qa["pages"], cout=qa["cout_openai"]["dollars"])
    except Exception as e:
        traceback.print_exc()
        job.update(etat="erreur", erreur=str(e)[:600], cout=round(meter["dollars"], 2), phase="failed" if not job.get("phase") == "needs_review" else "needs_review")


@app.get("/")
def vitrine():
    if request.args.get("commande"):                 # anciens liens de retour de paiement
        return redirect("/creer?" + request.query_string.decode())
    base = (os.getenv("PUBLIC_URL") or request.host_url).rstrip("/")      # adresses absolues (partage, référencement)
    html = (ROOT / "static" / "vitrine.html").read_text(encoding="utf-8").replace("__BASE__", base)
    return Response(html, mimetype="text/html")


@app.get("/creer")
def index():
    return send_from_directory(app.static_folder, "index.html")


def parse_book(data):
    """Formulaire de l'éditeur -> données du livre validées. Renvoie (form, erreur)."""
    form = {k: str(data.get(k, "")).strip()[:300] for k in FIELDS if data.get(k) not in (None, "")}
    suite = data.get("suite")                       # pack : thème et univers choisis pour les livres 2, 3… N
    if isinstance(suite, list):
        form["suite"] = [{"theme": str((x or {}).get("theme", "")).strip()[:80], "univers": str((x or {}).get("univers", "")).strip()[:80]}
                         for x in suite[:11] if isinstance(x, dict)]
    for k in REQUIRED:
        if not form.get(k):
            return None, f"Champ obligatoire manquant : {k}"
    if form.get("naissance") and not (form["naissance"].isdigit() and 2000 <= int(form["naissance"]) <= 2100):
        form.pop("naissance")
    if not form["age"].isdigit() or not 2 <= int(form["age"]) <= 10:
        return None, "L'âge doit être compris entre 2 et 10 ans."
    if data.get("avatar"):
        form["avatar"] = generator.sanitize_avatar(data["avatar"], generator._name(form["prenom"]) or form["prenom"][:20], form["age"])
        form["genre"] = form["avatar"]["enfant"]["genre"]
    hl = form.get("heros_livre") or "enfant"             # héros du livre : l'enfant, son doudou ou un de ses animaux
    av = form.get("avatar") or {}
    ok = ["enfant"] + (["doudou"] if av.get("doudou") else []) + [f"animal_{i + 1}" for i in range(len(av.get("animaux") or []))]
    form["heros_livre"] = hl if hl in ok else "enfant"
    return form, None


FABRICATIONS = threading.BoundedSemaphore(int(os.getenv("FABRICATIONS_SIMULTANEES", "2")))


def start_job(job_id, form, refs, auto=False, on_end=None, reprise=False, essai=None):
    """Lance la fabrication d'un livre dans un fil séparé (reprise=True : réutilise ce qui est déjà fait dans le dossier)."""
    (OUT / job_id).mkdir(exist_ok=True)
    JOBS[job_id] = {"etat": "en_cours", "etape": "Démarrage", "progression": 1, "_auto": auto, "_reprise": reprise, "_essai": essai}

    def work():
        if not FABRICATIONS.acquire(blocking=False):      # pack de 12 : les livres attendent leur tour (débit OpenAI)
            JOBS[job_id].update(etape="En attente de son tour", progression=1)
            FABRICATIONS.acquire()
        try:
            run(job_id, form, refs)
        finally:
            FABRICATIONS.release()
        if on_end:
            on_end(job_id, JOBS[job_id])
    threading.Thread(target=work, daemon=True).start()


@app.get("/vignette/<cle>.webp")
def vignette(cle):
    import vignettes
    p = vignettes.chemin(cle) if re.match(r"^[a-z_]+$", cle) else None
    return send_file(p, max_age=86400) if p else abort(404)


@app.get("/api/tarifs")
def api_tarifs():
    import paiement
    return jsonify(paiement.grille())


@app.get("/api/coloriage")
def api_coloriage():
    import coloriage
    return jsonify(coloriage.public())


@app.get("/api/univers")
def api_univers():
    import univers
    return jsonify(univers.public())


@app.post("/api/livres")
def create():
    """Création directe, SANS paiement : réservée au mode démo (gratuit) et à tes essais (code ACCESS_CODE)."""
    cleanup()
    data = request.get_json(force=True, silent=True) or {}
    form, err = parse_book(data)
    if err:
        return jsonify(erreur=err), 400
    if not form.get("demo") and not (ACCESS_CODE and form.get("code") == ACCESS_CODE):
        return jsonify(erreur="Le livre est fabriqué après le paiement de la commande."), 402
    job_id = uuid.uuid4().hex[:12]
    folder = OUT / job_id; folder.mkdir()
    refs = browser_refs(save_avatar_pngs(data.get("avatar_png") or {}, folder), save_previews(data.get("apercus") or {}, folder))
    start_job(job_id, form, refs)
    return jsonify(id=job_id)


@app.get("/api/livres/<job_id>")
def status(job_id):
    job = JOBS.get(job_id) or abort(404)
    return jsonify(public(job))


@app.post("/api/livres/<job_id>/decision")
def decision(job_id):
    job = JOBS.get(job_id) or abort(404)
    if job.get("etat") != "validation":
        abort(409)
    body = request.get_json(force=True, silent=True) or {}
    job["_decision"] = {"action": "redessiner" if body.get("action") == "redessiner" else "valider",
                        "ids": [x for x in body.get("ids") or [] if isinstance(x, str)][:8]}
    job["_ev"].set()
    return jsonify(ok=True)


def _manifeste(job_id):
    """Livre finalisé : manifeste enregistré (fichiers et empreintes). Servir ce livre n'appelle jamais un modèle."""
    if not re.fullmatch(r"[\w-]{6,40}", job_id):
        return None
    f = OUT / job_id / "final.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


@app.get("/api/livres/<job_id>/fichier/<name>")
def fichier(job_id, name):
    if (job_id not in JOBS and not _manifeste(job_id)) or not PUBLIC.match(name):
        abort(404)
    p = OUT / job_id / name
    if not p.exists():
        abort(404)
    return send_file(p)


@app.get("/api/livres/<job_id>/apercu/<name>")
def apercu_livre(job_id, name):
    """Aperçus du livre finalisé (couverture, couverture à plat, dos, doubles pages, étagère) : fichiers enregistrés."""
    man = _manifeste(job_id) or abort(404)
    if f"apercus/{name}" not in man["fichiers"]:
        abort(404)
    return send_file(OUT / job_id / "apercus" / name, max_age=86400)


@app.get("/api/livres/<job_id>/pdf")
def download(job_id):
    man = _manifeste(job_id)
    if man:                                       # livre finalisé : le PDF enregistré, rien n'est refait
        return send_file(OUT / job_id / man["pdf_lecture"], as_attachment=True, download_name=man["pdf_lecture"])
    job = JOBS.get(job_id) or abort(404)
    if job.get("etat") != "termine":
        abort(409)
    return send_file(OUT / job_id / job["pdf"], as_attachment=True, download_name=job["pdf"])


import boutique  # noqa: E402  commande, paiement, impression, abonnements, administration
boutique.setup(sys.modules[__name__])
app.register_blueprint(boutique.bp)

if __name__ == "__main__":
    print("Ouvre http://localhost:8000 dans ton navigateur" + ("" if os.getenv("OPENAI_API_KEY") else "  (pas de clé OpenAI : mode démo)"))
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), threaded=True)
