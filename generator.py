# -*- coding: utf-8 -*-
"""Chaîne de génération « Mon Héros du Mois » (API OpenAI).
1. Histoire (texte)            -> write_story
2. Storyboard contrôlé          -> make_storyboard (action, personnages, gestes, décor, cadrage, zone de texte)
3. Planche personnages          -> character_sheet (à partir des avatars du formulaire + planche de style), validée par le parent
4. Couverture, 9 scènes, décors -> draw_* (la planche validée et la planche de style sont passées en images de référence)
Les règles graphiques viennent de art.py."""
import os, json, time, base64, re, shutil
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import art
import couleur

TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "high")   # portraits et couverture : low | medium | high
SCENE_QUALITY = os.getenv("OPENAI_SCENE_QUALITY", "medium")  # 18 pages intérieures (le poste de coût principal)
INPUT_FIDELITY = os.getenv("OPENAI_INPUT_FIDELITY", "high")  # high = personnages plus fidèles, mais références plus chères

# ---------------------------------------------------------------- compteur de coût OpenAI (par livre)
import contextvars, threading as _th
METER = contextvars.ContextVar("meter", default=None)
_mlock = _th.Lock()
PRICES = {   # dollars par million de jetons : (texte entrée, image entrée, sortie)
    "gpt-image-1.5": (5, 8, 32), "gpt-image-1-mini": (2, 2.5, 8), "gpt-image-1": (5, 10, 40), "gpt-image-2.5": (5, 8, 30),
    "gpt-4.1-mini": (0.4, 0.4, 1.6), "gpt-4.1": (2, 2, 8), "gpt-4o-mini": (0.15, 0.15, 0.6), "gpt-4o": (2.5, 2.5, 10)}


def _price(model):
    return next((v for k, v in sorted(PRICES.items(), key=lambda kv: -len(kv[0])) if model.startswith(k)), (5, 10, 40))


def start_meter():
    m = {"appels": 0, "dollars": 0.0, "detail": {}}
    METER.set(m)
    return m


def _count(kind, model, usage):
    m = METER.get()
    if m is None or usage is None:
        return
    g = lambda o, k: (o.get(k) if isinstance(o, dict) else getattr(o, k, None)) or 0
    if kind == "image":
        det = g(usage, "input_tokens_details") or {}
        txt, img = g(det, "text_tokens"), g(det, "image_tokens")
        if not (txt or img): txt = g(usage, "input_tokens")
        tin, iin, out = _price(model)
        cost = (txt * tin + img * iin + g(usage, "output_tokens") * out) / 1e6
    else:
        tin, _, out = _price(model)
        cost = (g(usage, "prompt_tokens") * tin + g(usage, "completion_tokens") * out) / 1e6
    with _mlock:
        m["appels"] += 1; m["dollars"] += cost
        d = m["detail"].setdefault(kind, [0, 0.0]); d[0] += 1; d[1] += cost
WORKERS = int(os.getenv("IMAGE_WORKERS", "3"))


def _client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _retry(fn, tries=3):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # erreurs réseau / limites de débit
            msg = str(e)
            if i == tries - 1 or "invalid_api_key" in msg or "Incorrect API key" in msg or "insufficient_quota" in msg:
                raise
            time.sleep(4 * (i + 1))


def _chat_json(system, user):
    def call():
        r = _client().chat.completions.create(model=TEXT_MODEL, response_format={"type": "json_object"},
                                              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        _count("texte", TEXT_MODEL, getattr(r, "usage", None))
        return json.loads(r.choices[0].message.content)
    return _retry(call)


OPTIONS = json.loads((Path(__file__).parent / "static" / "options.json").read_text(encoding="utf-8"))


def _opt(group, key, val):
    lst = OPTIONS[group].get(key, [])
    return next((o for o in lst if o["id"] == val), lst[0] if lst else {"en": "", "fr": ""})


def _name(s):
    """Prénom nettoyé, avec majuscule (« hatchi » -> « Hatchi », « jean-paul » -> « Jean-Paul »)."""
    s = "".join(ch for ch in str(s or "") if ch.isalpha() or ch in " -'’").strip()[:20]
    return "-".join(" ".join(w[:1].upper() + w[1:] for w in part.split(" ")) for part in s.split("-"))


def _pick(group, src, where, problems):
    """Valeurs de l'éditeur -> identifiants connus. Une valeur absente ou inconnue est SIGNALÉE (jamais remplacée en silence)."""
    out = {}
    for k, lst in OPTIONS[group].items():
        v = (src or {}).get(k)
        ids = [o["id"] for o in lst]
        if v in ids:
            out[k] = v
        else:
            out[k] = ids[0]
            problems.append(f"{where} : « {k} » {'absent' if v in (None, '') else 'inconnu (' + str(v) + ')'} -> valeur par défaut « {ids[0]} »")
    return out


def sanitize_avatar(av, prenom, age, problems=None):
    """Ne garde que des identifiants connus (options.json) : aucun texte libre n'atteint les prompts, sauf les prénoms."""
    problems = [] if problems is None else problems
    if not isinstance(av, dict):
        problems.append("configuration des avatars absente")
        return None
    out = {"enfant": _pick("enfant", av.get("enfant"), "enfant", problems), "doudou": None, "animaux": [], "problemes": problems}
    d = av.get("doudou") or {}
    if d.get("actif"):
        out["doudou"] = _pick("doudou", d, "doudou", problems)
        out["doudou"]["nom"] = _name(d.get("nom"))
        if not out["doudou"]["nom"]:
            problems.append("doudou : nom non renseigné")
    for i, a in enumerate((av.get("animaux") or [])[:3]):
        if isinstance(a, dict):
            x = _pick("animal", a, f"animal {i + 1}", problems)
            x["nom"] = _name(a.get("nom"))
            if not x["nom"]:
                problems.append(f"animal {i + 1} : nom non renseigné")
            out["animaux"].append(x)
    out["prenom"], out["age"] = prenom, age
    return out


def avatar_descriptions(av):
    """Descriptions visuelles (anglais) construites uniquement à partir des choix de l'éditeur."""
    e = av["enfant"]; g = lambda k: _opt("enfant", k, e[k])
    hero = (f"{av['prenom']}, a {av['age']}-year-old {g('genre')['en']} with {g('peau')['en']}, "
            f"{g('couleur_cheveux')['en']} {g('coiffure')['en']}, {g('yeux')['en']}")
    if e["lunettes"] != "aucune":
        hero += f", {g('lunettes')['en'].replace('glasses', g('couleur_lunettes')['en'] + ' glasses')}"
    if e["taches"] == "oui":
        hero += f", {g('taches')['en']}"
    hero += f"; always wearing {g('couleur_tenue')['en']} {g('tenue')['en']}"
    if e["tenue"] == "pyjama":
        hero += " and slippers"
    res = {"hero": hero, "doudou": None, "animaux": []}
    d = av.get("doudou")
    if d:
        h = lambda k: _opt("doudou", k, d[k])
        txt = f"{d['nom'] or 'the plush toy'}, {av['prenom']}'s soft plush {h('couleur')['en']} {h('type')['en']} (a cuddly toy, not a living animal, with button eyes and visible stitching)"
        if d["accessoire"] != "aucun":
            txt += f", {h('accessoire')['en'].replace('little', h('couleur_accessoire')['en']).replace('small', h('couleur_accessoire')['en'])}"
        res["doudou"] = txt
    for a in av.get("animaux", []):
        h = lambda k: _opt("animal", k, a[k])
        size = {"petit": "small (reaching the child's knee)", "moyen": "medium-sized (reaching the child's hip)",
                "grand": "large (its back reaches the child's waist)"}.get(a["taille"], h("taille")["en"]) if a["type"] in ("chien", "chat") else h("taille")["en"]
        txt = f"{a['nom'] or 'the pet'}, {av['prenom']}'s {size} {h('couleur')['en']} {h('type')['en']} (a living animal)"
        if a["type"] in ("chien", "lapin"):
            txt += f" with {h('oreilles')['en']}"
        if a["motif"] != "uni" and a["type"] != "oiseau":
            txt += f", {h('motif')['en'].replace('a second colour', h('couleur2')['en']).replace('white muzzle and white belly', h('couleur2')['en'] + ' muzzle and ' + h('couleur2')['en'] + ' belly')}"
        txt += f", {h('yeux')['en']}"
        if a["collier"] != "aucun" and a["type"] != "oiseau":
            txt += f", {h('collier')['en']}"
        res["animaux"].append(txt)
    return res


def fixed_characters(f):
    """Bloc personnages imposé à chaque illustration."""
    av = f.get("avatar")
    if not av:
        return hero_description(f)
    d = avatar_descriptions(av)
    parts = [f"HERO: {d['hero']}."]
    if d["doudou"]:
        parts.append(f"PLUSH TOY (held by the hero in most scenes): {d['doudou']}.")
    for t in d["animaux"]:
        parts.append(f"PET: {t}.")
    return " ".join(parts)


def hero_description(f):
    genre = {"garçon": "boy", "garcon": "boy", "fille": "girl"}.get(f.get("genre"), "child")
    parts = [f"{f['prenom']}, a {f['age']}-year-old {genre}"]
    if f.get("cheveux"): parts.append(f"hair: {f['cheveux']}")
    if f.get("yeux"): parts.append(f"eyes: {f['yeux']}")
    if f.get("peau"): parts.append(f"skin tone: {f['peau']}")
    if f.get("lunettes") == "oui": parts.append("wears round glasses")
    parts.append(f"always wearing: {f.get('tenue') or 'yellow pyjamas with small white stars and red slippers'}")
    desc = "; ".join(parts)
    if f.get("doudou_nom"):
        desc += (f". Always carries {f['doudou_nom']}, a soft plush {f.get('doudou_type') or 'toy'}"
                 + (f" ({f['doudou_desc']})" if f.get("doudou_desc") else ""))
    if f.get("animal"):
        desc += f". Pet companion: {f['animal']}"
    return desc



def univers_key(u):
    u = (u or "").lower()
    for k in art.UNIVERS:
        if k in u or (k == "espace" and "étoile" in u) or (k == "pôle" and "nord" in u) or (k == "dinosaure" and "dino" in u):
            return k
    return None


def _fold(s):
    """Comparaison de prénoms insensible aux accents et à la casse (Aboudèh = aboudeh)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn").strip()


# ====================================================================== 0. configuration unique de la commande
def build_config(form):
    """Configuration complète et figée de la commande : SEULE source utilisée ensuite (histoire, images, PDF).
    Chaque personnage a un identifiant stable (heros, doudou, animal_1, animal_2…)."""
    av = form.get("avatar")
    probs = list((av or {}).get("problemes", []))
    chars = []
    if av:
        d = avatar_descriptions(av)
        chars.append({"id": "heros", "type": "enfant", "role": "héros", "nom": av["prenom"], "age": av["age"],
                      "config": dict(av["enfant"]), "desc": d["hero"]})
        if av.get("doudou"):
            dd = av["doudou"]
            chars.append({"id": "doudou", "type": "doudou", "role": "doudou (jouet en peluche, pas un animal vivant)",
                          "nom": dd["nom"] or f"le doudou {_opt('doudou', 'type', dd['type'])['fr'].lower()}",
                          "config": {k: v for k, v in dd.items() if k != "nom"}, "desc": d["doudou"]})
        for i, (a, t) in enumerate(zip(av["animaux"], d["animaux"])):
            chars.append({"id": f"animal_{i + 1}", "type": "animal", "role": "animal de compagnie (vivant)",
                          "nom": a["nom"] or f"le {_opt('animal', 'type', a['type'])['fr'].lower()}",
                          "config": {k: v for k, v in a.items() if k != "nom"}, "desc": t})
    else:
        probs.append("aucun avatar configuré : description textuelle minimale utilisée")
        chars.append({"id": "heros", "type": "enfant", "role": "héros", "nom": form["prenom"], "age": form["age"],
                      "config": {}, "desc": hero_description(form)})
    for c in chars:
        c["cle"] = portrait_key(c)
    return {"version": art.STYLE_VERSION, "personnages": chars, "problemes": probs,
            "histoire": {k: form.get(k) for k in ("theme", "univers", "passions", "precision", "numero")}}


def portrait_key(c):
    """Clé de cache d'un portrait : configuration complète + version du style + modèle. Tout changement l'invalide."""
    import hashlib
    blob = json.dumps({"t": c["type"], "cfg": c.get("config"), "age": c.get("age"), "desc": c.get("desc"),
                       "v": art.STYLE_VERSION, "m": IMAGE_MODEL}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()[:20]


# ====================================================================== 1. portraits de référence (après paiement)
REF_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).parent) / "cache_references"; REF_DIR.mkdir(parents=True, exist_ok=True)


def portrait_prompt(c, has_model, has_guide, diffs=None):
    refs = []
    if has_model: refs.append("image 1 is a painted base model from this book's collection: keep its painting style, rendering quality and general anatomy")
    if has_guide: refs.append(f"image {2 if has_model else 1} is the parent's colour guide (flat drawing): follow its colours, glasses, freckles, outfit, markings and accessories, never its flat style")
    refs.append("the LAST image is the style swatch board: technique, texture and light only, never its content")
    kind = {"enfant": "the hero child", "doudou": "the plush toy", "animal": "the pet"}.get(c["type"], "the character")
    return "\n".join([art.STYLE_BIBLE, "REFERENCE IMAGES: " + "; ".join(refs) + ".",
        f"Create the official REFERENCE PORTRAIT of {kind} {c['nom'].upper()} for this picture book: {c['desc']}.",
        "Full body, three-quarter view, relaxed natural pose, gentle expression, centred, on a plain soft cream paper background, "
        "even soft daylight with true neutral colours (no yellow or orange colour cast). Every attribute listed above must be clearly visible "
        + ("(hair, skin, eyes, glasses if listed, clothing). " if c["type"] == "enfant" else
           "(species, fur colours, markings, ears, collar if listed). It wears NO glasses and NO clothes. ")
        + "One single character only. No scenery, no text."]
        + ([f"IMPORTANT, the base model differs from this character: " + "; ".join(diffs) + "."] if diffs else [])
        + (["This is a STUFFED PLUSH TOY made of soft fabric: visible seams, small stitched or button eyes, stubby limbs without claws, "
            "sitting like a toy. It must never look like a living animal."] if c["type"] == "doudou" else [])
        + [art.AVOID])


def draw_portrait(c, guide=None, variant=0, base=None):
    """Portrait peint personnalisé. Mis en cache par clé (config + version) : réutilisé d'un livre à l'autre (abonnement)."""
    out = REF_DIR / f"{c['cle']}_{variant}.png"
    if out.exists():
        return out
    model = base if base and Path(base).exists() else None     # aperçu recoloré du navigateur (couleurs, lunettes, yeux…)
    diffs = []
    if c["type"] in ("enfant", "doudou", "animal") and c.get("config"):
        if model is None:                                        # sinon : même recoloration, faite ici (jamais les couleurs du modèle)
            model = recolor_model(c["type"], c["config"])
        if model is None:
            try:
                model = model_file(c["type"], c["config"])
            except Exception:
                model = None
        diffs = base_differences(c["type"], c["config"])
    refs = [r for r in (model, guide) if r and Path(r).exists()] + [art.STYLE_BOARD]
    return _edit(portrait_prompt(c, bool(model and Path(model).exists()), bool(guide and Path(guide).exists()), diffs), refs, out)


def draw_invented(c, variant=0):
    """Personnage inventé par l'histoire (ex. une dinosaure) : portrait à partir de sa description, pour rester identique."""
    import hashlib
    key = hashlib.sha1((c["nom"] + c["desc"] + art.STYLE_VERSION).encode()).hexdigest()[:20]
    out = REF_DIR / f"{key}_{variant}.png"
    if out.exists():
        return out
    return _edit(portrait_prompt(c, False, False), [art.STYLE_BOARD], out)


# ====================================================================== 2. histoire (18 pages illustrées) + relecture
N_PAGES = 18

SYSTEM_STORY = """Tu es un·e auteur·rice reconnu·e d'albums jeunesse (3-8 ans), en français, pour la collection « Mon Héros du Mois ».
Tu écris une histoire ORIGINALE lue à voix haute le soir. L'enfant est le personnage principal, présent et actif sur presque
toutes les pages ; c'est lui qui résout le problème. Ton chaleureux, drôle par moments, rassurant. Aucun personnage ou marque existants.

Le livre compte 18 pages ILLUSTRÉES : chaque page = un moment précis, montrable en une image, avec son propre texte.
Chaque page fait avancer le récit (jamais de redite de la page précédente). Arc : 1-2 situation de départ concrète ;
3-4 élément déclencheur ; 5-13 péripéties dans des lieux variés, un obstacle précis et une tentative de l'enfant ;
14-15 moment clé où l'enfant réussit grâce au thème ; 16-17 célébration ; 18 retour au calme.
Le thème du parent est au cœur de l'histoire et se résout de façon réaliste et bienveillante.

Écriture : 30 à 55 mots par page, phrases simples et vivantes, verbes d'action, détails concrets (sons, textures, couleurs),
dialogues naturels en « guillemets français ». Chaque personnage imposé garde EXACTEMENT son prénom (même orthographe,
majuscule). Le doudou est une peluche : il peut « répondre » dans l'imaginaire de l'enfant mais reste un jouet ; quand il est
avec l'enfant, dis-le. Tous les compagnons imposés participent, chacun avec au moins une action utile, mais PAS tous sur chaque page :
seulement ceux utiles au moment raconté. Ne redécris jamais l'apparence des personnages imposés (elle est fixée).
Si tu inventes un personnage récurrent (une créature, un ami), donne-lui un nom et une description visuelle précise et stable.
Réponds UNIQUEMENT en JSON :
{"titre": ["ligne 1 ≤ 18 car.", "ligne 2 ≤ 24 car."], "titre_court": "≤ 34 caractères, majuscules",
 "personnages_inventes": [{"nom": "UNIQUEMENT les nouveaux personnages, jamais un personnage imposé", "description_visuelle": "EN ANGLAIS, espèce, couleurs, taille, signes distinctifs"}],
 "pages": [{"texte": ["paragraphe", "…"]}],
 "questions": ["3 questions courtes à poser à l'enfant sur l'histoire"],
 "teaser": "une phrase qui donne envie de la prochaine aventure",
 "quatrieme": {"accroche": ["≤ 22 car.", "≤ 28 car."], "paragraphes": ["≤ 12 mots", "≤ 22 mots"], "question": "≤ 42 caractères"}}"""

SYSTEM_RELECTURE = """Tu es correcteur·rice professionnel·le d'albums jeunesse. Relis et corrige le texte des pages SANS changer l'histoire :
orthographe, accords, pronoms cohérents avec le genre de chaque personnage, majuscules des prénoms (orthographe exacte fournie),
ponctuation française, fluidité et continuité d'une page à l'autre. Garde 30 à 55 mots par page : raccourcis si besoin, ne rallonge pas.
Réponds UNIQUEMENT en JSON : {"pages": [{"texte": ["…"]}], "corrections": ["liste courte des corrections faites"]}"""


def fix_names(text, names):
    """Rétablit l'orthographe exacte des prénoms (majuscule, accents) partout dans le texte."""
    import re, unicodedata
    for n in names:
        if not n or " " in n.strip():
            continue
        pat = "".join(f"[{c}{unicodedata.normalize('NFD', c)[0]}]" if unicodedata.normalize("NFD", c)[0] != c else re.escape(c) for c in n.lower())
        text = re.sub(rf"(?<![\w]){pat}(?![\w])", n, text, flags=re.IGNORECASE)
    return text


def add_invented(story, nom, desc):
    """Ajoute un personnage inventé (identifiant stable invente_N) s'il n'existe pas déjà."""
    if any(_fold(c["nom"]) == _fold(nom) for c in story["personnages"]):
        return None
    k = sum(c["type"] == "invente" for c in story["personnages"]) + 1
    c = {"id": f"invente_{k}", "type": "invente", "role": "personnage inventé", "nom": nom, "desc": desc}
    story["personnages"].append(c)
    return c


def check_story(s, cfg):
    probs = []
    pages = s.get("pages") or []
    if len(pages) != N_PAGES:
        probs.append(f"Il faut exactement {N_PAGES} pages (reçu {len(pages)}).")
    text = " ".join(" ".join(p.get("texte", [])) for p in pages)
    for c in cfg["personnages"]:
        n = _fold(text).count(_fold(c["nom"]))
        if n < (8 if c["id"] == "heros" else 2):
            probs.append(f"« {c['nom']} » ({c['role']}) doit apparaître plus souvent, prénom écrit exactement ainsi (actuellement {n} fois).")
    for i, p in enumerate(pages[:N_PAGES]):
        w = len(" ".join(p.get("texte", [])).split())
        if w > 60 or w < 20:
            probs.append(f"Page {i + 1} : {w} mots (attendu 30 à 55).")
    return probs


def write_story(cfg, form):
    brief = {"heros": {"prenom": cfg["personnages"][0]["nom"], "age": form["age"],
                       "genre": (cfg["personnages"][0].get("config") or {}).get("genre") or form.get("genre")},
             "personnages_imposes": [{"prenom": c["nom"], "role": c["role"]} for c in cfg["personnages"]],
             **{k: v for k, v in cfg["histoire"].items() if k != "numero"}}
    user = "Brief du parent :\n" + json.dumps(brief, ensure_ascii=False)
    s = _chat_json(SYSTEM_STORY, user)
    probs = check_story(s, cfg)
    if probs:
        s = _chat_json(SYSTEM_STORY, user + "\n\nVersion précédente :\n" + json.dumps(s, ensure_ascii=False) +
                       "\n\nCorrige ces problèmes et renvoie l'histoire complète :\n- " + "\n- ".join(probs))
    if len(s.get("pages", [])) < N_PAGES:
        raise ValueError("L'histoire générée est incomplète, relance la génération.")
    s["pages"] = s["pages"][:N_PAGES]
    # relecture professionnelle
    names = []
    for n in [c["nom"] for c in cfg["personnages"]] + [_name(p.get("nom", "")) for p in s.get("personnages_inventes") or []]:
        if n and _fold(n) not in {_fold(x) for x in names}:      # l'orthographe configurée prime toujours
            names.append(n)
    try:
        r = _chat_json(SYSTEM_RELECTURE, json.dumps({"prenoms_exacts": names, "genre_heros": brief["heros"]["genre"],
                                                     "pages": s["pages"]}, ensure_ascii=False))
        if len(r.get("pages", [])) == N_PAGES:
            s["pages"] = r["pages"]; s["relecture"] = r.get("corrections", [])
    except Exception as e:
        s["relecture"] = [f"relecture impossible : {e}"]
    for p in s["pages"]:
        p["texte"] = [fix_names(t, names) for t in p.get("texte", [])]
    s["prenom"] = cfg["personnages"][0]["nom"]; s["numero"] = cfg["histoire"].get("numero") or "01"
    s["univers"] = cfg["histoire"].get("univers"); s["accroche_couverture"] = "UNE AVENTURE À LIRE ENSEMBLE"
    # personnages inventés : jamais un doublon d'un personnage imposé (sinon sa description écraserait la configuration)
    imposes = {_fold(c["nom"]) for c in cfg["personnages"]}
    s["personnages"] = [dict(c) for c in cfg["personnages"]]
    s["doublons_supprimes"] = []
    for p in (s.get("personnages_inventes") or []):
        n = _name(p.get("nom", ""))
        if not n: continue
        if _fold(n) in imposes or any(_fold(n) in _fold(x) or _fold(x) in _fold(n) for x in imposes):
            s["doublons_supprimes"].append(n); continue
        add_invented(s, n, p.get("description_visuelle", ""))
    age = int(form["age"])
    s.setdefault("quatrieme", {})["age"] = "3–5 ans" if age <= 4 else "4–6 ans" if age <= 6 else "6–8 ans"
    s["controle_histoire"] = check_story(s, cfg)
    return s


# ====================================================================== 3. storyboard (par identifiants)
SYSTEM_BOARD = """Tu es directeur·rice artistique d'albums jeunesse. Tu construis le STORYBOARD des 18 pages illustrées + la couverture.
Chaque illustration RACONTE exactement le passage de sa page : on voit l'action, le lieu, les objets et TOUS les personnages cités
(si le texte parle d'un ruisseau, le ruisseau est visible ; si le doudou est contre l'enfant, on voit le doudou contre l'enfant).
Jamais un simple portrait de groupe face au lecteur. L'enfant est le personnage principal, présent sur presque toutes les pages.

Personnages : utilise UNIQUEMENT leurs identifiants (champ "id" fourni). N'ajoute aucun animal ni personnage qui n'est pas listé.
Pour chaque page :
- personnages : ids présents à l'image (tous ceux que le texte met en scène à ce moment, pas plus) ;
- action : l'action visible, précise ; expressions_gestes : gestes et émotions de chaque personnage présent ;
- decor et objets ; elements_en : liste EN ANGLAIS des éléments concrets du texte qui doivent être visibles ;
- cadrage parmi : plan_large, action, intime, detail, decouverte, plongee (au moins 5 différents sur le livre, jamais 2 fois le même d'affilée) ;
- zone_texte (bas, haut, gauche, droite) : zone naturellement calme (ciel, brume, mur, eau, feuillage peu détaillé), jamais sur un visage ;
  gauche/droite seulement si le texte fait moins de 35 mots ; varie-la ;
- lumiere : matin, jour, crépuscule, nuit ou intérieur ; palette_en : palette propre à la scène EN ANGLAIS
  (ex. "moonlit blues with golden lantern accents", "deep greens and turquoise water with pink flowers") : varie les palettes,
  évite une dominante jaune-orange uniforme sur tout le livre ;
- prompt_en : 3 à 5 phrases EN ANGLAIS pour l'illustrateur : plans (premier plan, milieu, fond), positions, action exacte,
  source de lumière, où se trouve la zone calme pour le texte. Désigne chaque personnage par son NOM en majuscules. Pas de style graphique.
Si le texte met en scène un personnage absent de la liste (une créature, un ami…), déclare-le dans "personnages_supplementaires"
avec un nom et une description visuelle précise EN ANGLAIS, puis utilise son identifiant "invente_<nom en minuscules sans accent>".
Réponds UNIQUEMENT en JSON :
{"personnages_supplementaires": [{"nom": "", "description_en": ""}],
 "couverture": {"personnages": [], "cadrage": "", "lumiere": "", "palette_en": "", "prompt_en": ""},
 "pages": [{"page": 1, "personnages": [], "action": "", "expressions_gestes": "", "decor": "", "objets": [], "elements_en": [],
            "cadrage": "", "zone_texte": "", "lumiere": "", "palette_en": "", "prompt_en": ""}]}"""


def _ids(story):
    return {c["id"]: c for c in story["personnages"]}


def mentioned(text, story):
    """Personnages cités dans un texte (prénom, insensible aux accents), par identifiant."""
    t = _fold(text)
    return [c["id"] for c in story["personnages"] if c.get("nom") and _fold(c["nom"]) in t]


def check_board(b, story):
    probs = []
    pg = b.get("pages") or []
    ids = _ids(story)
    if len(pg) != N_PAGES:
        probs.append(f"Il faut exactement {N_PAGES} pages (reçu {len(pg)}).")
    cads = [p.get("cadrage") for p in pg]
    if any(c not in art.CADRAGES for c in cads): probs.append("Cadrage inconnu.")
    if len(set(cads)) < 5: probs.append("Pas assez de cadrages différents (minimum 5).")
    for i in range(1, len(cads)):
        if cads[i] == cads[i - 1]: probs.append(f"Pages {i} et {i + 1} : même cadrage d'affilée.")
    for i, p in enumerate(pg):
        unk = [x for x in p.get("personnages") or [] if x not in ids]
        if unk: probs.append(f"Page {i + 1} : identifiants inconnus {unk} (utilise : {sorted(ids)}).")
        miss = [x for x in mentioned(" ".join(story["pages"][i]["texte"]), story) if x not in (p.get("personnages") or [])]
        if miss: probs.append(f"Page {i + 1} : le texte cite {[ids[x]['nom'] for x in miss]} mais ils ne sont pas à l'image.")
    if sum("heros" in (p.get("personnages") or []) for p in pg) < 15:
        probs.append("L'enfant doit être présent sur au moins 15 pages.")
    pals = [p.get("palette_en", "") for p in pg]
    if len(set(pals)) < 6: probs.append("Palettes trop peu variées.")
    return probs


def fix_board(b, story):
    """Garde-fous appliqués quoi qu'il arrive (sans appel API)."""
    ids = _ids(story)
    seq = ["plan_large", "action", "intime", "decouverte", "detail", "plongee"]
    pg = (b.get("pages") or [])[:N_PAGES]
    while len(pg) < N_PAGES:
        pg.append({"prompt_en": "", "personnages": ["heros"]})
    for i, p in enumerate(pg):
        p["page"] = i + 1
        texte = " ".join(story["pages"][i]["texte"])
        chars = [x for x in (p.get("personnages") or []) if x in ids]
        for x in mentioned(texte, story):              # tout personnage cité par le texte est à l'image
            if x not in chars: chars.append(x)
        if "doudou" in ids and "heros" in chars and "doudou" not in chars and re.search(r"doudou|peluche|serre|câlin|bras", texte, re.I):
            chars.append("doudou")
        p["personnages"] = chars or ["heros"]
        c = p.get("cadrage")
        if c not in art.CADRAGES or (i and c == pg[i - 1]["cadrage"]):
            p["cadrage"] = next(x for x in seq[i % 6:] + seq if not i or x != pg[i - 1]["cadrage"])
        words = len(texte.split())
        if p.get("zone_texte") not in art.ZONES or (words > 35 and p["zone_texte"] in ("gauche", "droite")):
            p["zone_texte"] = "bas"
        if p.get("lumiere") not in art.MOMENTS:
            p["lumiere"] = next((m for m in art.MOMENTS if m in str(p.get("lumiere", "")).lower()), "jour")
        p["a_montrer"] = list(dict.fromkeys([e for e in (p.get("elements_en") or []) if e]))
    zones = [p["zone_texte"] for p in pg]
    for i, p in enumerate(pg):                          # au plus 8 fois la même zone
        if zones.count(p["zone_texte"]) > 8:
            alt = [z for z in ("haut", "bas") if zones.count(z) < 8 and z != p["zone_texte"]]
            if alt: zones[i] = p["zone_texte"] = alt[0]
    b["pages"] = pg
    cov = b.get("couverture") or {}
    cov["personnages"] = [x for x in (cov.get("personnages") or []) if x in ids] or [c["id"] for c in story["personnages"] if c["id"] != "invente_1"][:4]
    if "heros" not in cov["personnages"]: cov["personnages"].insert(0, "heros")
    if cov.get("lumiere") not in art.MOMENTS: cov["lumiere"] = "crépuscule"
    b["couverture"] = cov
    return b


def register_extra(b, story):
    """Personnages récurrents déclarés par le storyboard -> ajoutés avec un identifiant, identifiants du storyboard remappés."""
    import unicodedata
    for x in b.get("personnages_supplementaires") or []:
        n = _name(x.get("nom", ""))
        if not n: continue
        c = add_invented(story, n, x.get("description_en", "")) or next(c for c in story["personnages"] if _fold(c["nom"]) == _fold(n))
        alias = "invente_" + re.sub(r"[^a-z0-9]", "", _fold(n))
        for p in (b.get("pages") or []) + [b.get("couverture") or {}]:
            p["personnages"] = [c["id"] if y in (alias, n, _fold(n)) else y for y in (p.get("personnages") or [])]


def make_storyboard(story):
    user = json.dumps({"univers": story.get("univers"), "titre": story["titre"],
                       "personnages": [{"id": c["id"], "nom": c["nom"], "role": c["role"]} for c in story["personnages"]],
                       "pages": [{"page": i + 1, "texte": p["texte"]} for i, p in enumerate(story["pages"])]}, ensure_ascii=False)
    b = _chat_json(SYSTEM_BOARD, user)
    register_extra(b, story)
    probs = check_board(b, story)
    if probs:
        b2 = _chat_json(SYSTEM_BOARD, user + "\n\nStoryboard précédent :\n" + json.dumps(b, ensure_ascii=False) +
                        "\n\nCorrige ces problèmes et renvoie le storyboard complet :\n- " + "\n- ".join(probs[:25]))
        register_extra(b2, story)
        if len(check_board(b2, story)) <= len(probs):
            b = b2
    b = fix_board(b, story)
    b["controle"] = check_board(b, story)
    return b


# ====================================================================== 4. prompts d'images
def _world(story, lumiere, palette=None):
    k = univers_key(story.get("univers"))
    return (f"WORLD: {art.UNIVERS.get(k, art.DEFAULT_UNIVERS)}. LIGHT: {art.MOMENTS.get(lumiere, art.MOMENTS['jour'])}. "
            f"COLOUR PALETTE OF THIS PAGE: {palette or 'rich and varied'}. " + art.COLOUR_RULE)


def refs_block(ids, story, first_index=1, style=True):
    """Liste explicite des images de référence transmises (une par personnage présent), dans l'ordre d'envoi."""
    by = _ids(story)
    lines = [f"Image {first_index + k}: {by[x]['nom'].upper()} ({by[x]['role']}) - {by[x]['desc']}." for k, x in enumerate(ids)]
    notes = []
    h = by.get("heros")
    if h and "heros" in ids and ((h.get("config") or {}).get("lunettes") not in (None, "aucune")) and len(ids) > 1:
        notes.append(f"Only {h['nom'].upper()} wears glasses: the animals, the plush toy and every other character NEVER wear glasses.")
    if "doudou" in ids:
        d = by["doudou"]; hero = by.get("heros", {}).get("nom", "the hero").upper()
        notes.append(f"{d['nom'].upper()} is a STUFFED PLUSH TOY (fabric, seams, stitched eyes, stubby limbs), about the size of {hero}'s torso: "
                     f"it is held in {hero}'s arms, tucked under an arm or sitting next to {hero}; it never walks, runs or acts like a living animal.")
        dt = (d.get("config") or {}).get("type")
        for x in ids:
            if by[x]["type"] == "animal" and (by[x].get("config") or {}).get("type") == dt:
                notes.append(f"Do not confuse them: {by[x]['nom'].upper()} is a LIVING {dt and _opt('animal', 'type', dt).get('en', dt)} (real fur, natural pose), "
                             f"{d['nom'].upper()} is the plush toy (fabric, smaller, held by {hero}). They must look clearly different.")
    return ("REFERENCE IMAGES (one per character, sent in this order): " + " ".join(lines + notes) +
            (f" Image {first_index + len(ids)}: style swatch board (painting technique, texture and light only; never copy its content). " if style else " ") +
            "Each character must match its reference portrait exactly: same species, face, hair, colours, markings, clothes, "
            "accessories and relative size. Poses and expressions change with the scene.")


def scene_prompt(p, story):
    ids = p.get("personnages", [])
    by = _ids(story)
    names = ", ".join(by[x]["nom"].upper() for x in ids)
    parts = [art.STYLE_BIBLE, refs_block(ids, story, style=False), _world(story, p.get("lumiere"), p.get("palette_en")),
             f"CHARACTERS IN THIS SCENE: exactly {len(ids)} ({names}). Do not add any other person or animal (no extra pet, "
             "no rabbit, no bird, no background creature unless it is listed in the story elements below), do not merge characters. "
             "Every listed character must be clearly visible, whole and recognisable (not hidden or cropped out).",
             f"SCENE: {p.get('prompt_en', '')}"]
    if p.get("expressions_gestes"): parts.append(f"Expressions and gestures: {p['expressions_gestes']}.")
    if p.get("a_montrer"): parts.append("These story elements must be clearly visible: " + ", ".join(p["a_montrer"]) + ".")
    if p.get("fix"): parts.append("CORRECTIONS FROM THE REVIEW OF A PREVIOUS ATTEMPT (must be fixed): " + p["fix"])
    zone = p.get("zone_texte", "bas")
    parts += [f"CAMERA: {art.CADRAGES.get(p.get('cadrage'), art.CADRAGES['plan_large'])}",
              art.ZONE_RULE.format(zone=art.ZONES[zone], calm=art.CALM[zone]),
              "Square format, full-bleed painting that fills the whole canvas. No text in the image.", art.AVOID]
    return "\n".join(parts)


def cover_prompt(b, story):
    c = b["couverture"]; ids = c["personnages"]
    return "\n".join([art.STYLE_BIBLE, refs_block(ids, story), _world(story, c.get("lumiere"), c.get("palette_en")),
        f"CHARACTERS: exactly these {len(ids)}. Do not add any other person or animal.",
        f"BOOK COVER SCENE: {c.get('prompt_en', '')} The hero is the clear focal point, engaged in the adventure, full of wonder.",
        f"CAMERA: {art.CADRAGES.get(c.get('cadrage'), art.CADRAGES['decouverte'])}",
        art.ZONE_RULE.format(zone=art.ZONES['haut'], calm=art.CALM['haut']) + " A large title will be placed there.", art.AVOID])


# ====================================================================== 5. appels images
def _save(resp, path):
    Path(path).write_bytes(base64.b64decode(resp.data[0].b64_json))
    return Path(path)


def _edit(prompt, refs, path, size="1024x1024", quality=None):
    refs = [Path(r) for r in refs]
    missing = [str(r) for r in refs if not r.exists()]
    if missing:
        raise FileNotFoundError(f"Référence introuvable : {missing}")
    def call():
        files = [open(r, "rb") for r in refs]
        try:
            kw = dict(model=IMAGE_MODEL, image=files, prompt=prompt, size=size, quality=quality or IMAGE_QUALITY, n=1)
            try:
                r = _client().images.edit(input_fidelity=INPUT_FIDELITY, **kw)
                _count("image", IMAGE_MODEL, getattr(r, "usage", None))
                return r
            except Exception as e:   # option non gérée par le SDK ou le modèle : on réessaie sans
                if not isinstance(e, TypeError) and "input_fidelity" not in str(e):
                    raise
                for fh in files: fh.seek(0)
                r = _client().images.edit(**kw)
                _count("image", IMAGE_MODEL, getattr(r, "usage", None))
                return r
        finally:
            for fh in files: fh.close()
    out = _retry(lambda: _save(call(), path))
    corr = couleur.fix_file(out)          # dominante jaune-orangée corrigée (l'original reste en *_brut.png)
    # trace : quelles références ont réellement été transmises pour cette image
    with open(Path(path).parent / "references_transmises.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"image": Path(path).name, "references": [r.name for r in refs], "couleur": corr}, ensure_ascii=False) + "\n")
    return out


def ref_files(ids, portraits, style=True):
    """Portraits des personnages présents (+ planche de style pour la couverture ; les pages s'en passent : moins de coût)."""
    return [portraits[x] for x in ids if x in portraits] + ([art.STYLE_BOARD] if style else [])


def draw_cover(board, story, portraits, folder):
    ids = [x for x in board["couverture"]["personnages"] if x in portraits]
    board["couverture"]["personnages"] = ids
    return _edit(cover_prompt(board, story), ref_files(ids, portraits), Path(folder) / "image_00.png")


def draw_scenes(board, story, portraits, folder, pages, progress, check=True):
    """Dessine les pages demandées ; chaque image est contrôlée (vision) et redessinée une fois au plus si elle s'écarte."""
    done = [0]
    def one(i):
        p = board["pages"][i]
        p["personnages"] = [x for x in p["personnages"] if x in portraits]
        path = Path(folder) / f"image_{i + 1:02d}.png"
        _edit(scene_prompt(p, story), ref_files(p["personnages"], portraits, style=False), path, quality=SCENE_QUALITY)
        verdict = review_scene(path, p, story) if check else {"ok": True}
        tries = 0
        while not verdict.get("ok", True) and tries < MAX_RETRIES:   # nouvel essai UNIQUEMENT pour un écart bloquant
            tries += 1
            keep = path.with_name(path.stem + f"_essai{tries}.png"); shutil.copy(path, keep)
            p["fix"] = "; ".join(verdict.get("problemes", []))
            _edit(scene_prompt(p, story), ref_files(p["personnages"], portraits, style=False), path, quality=SCENE_QUALITY)
            new = review_scene(path, p, story)
            if len(new.get("bloquants", [])) > len(verdict.get("bloquants", [])):   # le nouvel essai est pire : on garde l'ancien
                shutil.copy(keep, path); new = dict(verdict, garde_essai=tries)
            verdict = new
        p.pop("fix", None)
        verdict["tentatives"] = tries + 1
        p["controle_visuel"] = verdict
        done[0] += 1; progress(f"Illustrations {done[0]}/{len(pages)}")
        return path
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:   # le compteur de coût suit chaque tâche
        futs = [ex.submit(contextvars.copy_context().run, one, i) for i in pages]
        return dict(zip(pages, [f.result() for f in futs]))


# ====================================================================== 6. contrôle visuel automatique
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "1"))
SYSTEM_REVIEW = """Tu contrôles une illustration d'album jeunesse avant impression. Compare l'image à la fiche de la page.
Classe chaque écart en deux catégories.
BLOQUANTS (l'image doit être refaite) — uniquement :
- un personnage attendu est absent ou méconnaissable ;
- un personnage ou un animal en trop (humain, animal de compagnie, créature) ; les petits éléments de décor (papillons, lucioles) ne comptent pas ;
- mauvaise espèce ou couleur principale nettement fausse (ex. chien marron au lieu de noir, peluche bleue au lieu de grise) ;
- la peluche (doudou) dessinée comme un animal vivant, ou deux personnages confondus ;
- un accessoire porté par le mauvais personnage (ex. des lunettes sur un animal ou sur la peluche) ;
- l'action principale du texte est absente (ex. le texte parle d'un dinosaure et il n'y en a pas) ;
- du texte écrit dans l'image.
MINEURS (signalés, l'image est gardée) : détails de vêtements (col, motifs), couleur des yeux, coutures, gestes secondaires,
calme de la zone de texte, lumière ou teinte générale.
Sois factuel : ne signale que ce qui est réellement visible. En cas de doute, ce n'est pas bloquant.
Réponds UNIQUEMENT en JSON : {"bloquants": ["écart précis, formulé comme une consigne de correction en anglais"],
 "mineurs": ["écart court en français"], "personnages_vus": ["noms"], "score": 0-10}"""


def review_scene(path, p, story):
    by = _ids(story)
    fiche = {"personnages_attendus": [{"nom": by[x]["nom"], "description": by[x]["desc"]} for x in p.get("personnages", [])],
             "action": p.get("action") or p.get("prompt_en"), "elements": p.get("a_montrer", []), "zone_texte": p.get("zone_texte")}
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    try:
        def call():
            r = _client().chat.completions.create(model=REVIEW_MODEL, response_format={"type": "json_object"}, messages=[
                {"role": "system", "content": SYSTEM_REVIEW},
                {"role": "user", "content": [{"type": "text", "text": json.dumps(fiche, ensure_ascii=False)},
                                             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
            _count("controle", REVIEW_MODEL, getattr(r, "usage", None))
            v = json.loads(r.choices[0].message.content)
            v["bloquants"] = [x for x in v.get("bloquants") or [] if isinstance(x, str)][:6]
            v["mineurs"] = [x for x in v.get("mineurs") or [] if isinstance(x, str)][:6]
            v["ok"] = not v["bloquants"]
            v["problemes"] = v["bloquants"]
            return v
        return _retry(call)
    except Exception as e:
        return {"ok": True, "problemes": [], "bloquants": [], "mineurs": [], "erreur_controle": str(e)[:200]}


REVIEW_MODEL = os.getenv("OPENAI_REVIEW_MODEL", TEXT_MODEL)


# ====================================================================== 5. avatars peints (éditeur)
PACK = Path(__file__).parent / "style" / "avatars"          # modèles peints du pack (1024 px, transparents)
CACHE = Path(os.getenv("DATA_DIR") or Path(__file__).parent) / "cache_avatars"; CACHE.mkdir(parents=True, exist_ok=True)
AV_KEYS = {"enfant": ["genre", "peau", "coiffure", "couleur_cheveux", "yeux", "lunettes", "couleur_lunettes", "taches", "tenue", "couleur_tenue"],
           "doudou": ["type", "couleur", "accessoire", "couleur_accessoire"],
           "animal": ["type", "oreilles", "couleur", "motif", "couleur2", "yeux", "collier"]}
_GROUP = {"enfant": "enfant", "doudou": "doudou", "animal": "animal"}


def normalize_cfg(kind, cfg, age=None):
    """Garde uniquement ce qui change l'apparence (identifiants connus seulement)."""
    cfg = cfg or {}
    out = {k: _opt(_GROUP[kind], k, cfg.get(k))["id"] for k in AV_KEYS[kind] if k in OPTIONS[_GROUP[kind]]}
    if kind == "enfant":
        if out["lunettes"] == "aucune": out.pop("couleur_lunettes")
        out["age"] = str(age) if str(age or "").isdigit() else "5"
    if kind == "doudou" and out["accessoire"] == "aucun": out.pop("couleur_accessoire")
    if kind == "animal":
        if out["type"] not in ("chien", "lapin"): out.pop("oreilles")
        if out["motif"] == "uni" or out["type"] == "oiseau" and out["motif"] != "ventre": out.pop("couleur2", None)
        if out["type"] == "oiseau": out.pop("collier")
    return out


def model_file(kind, cfg):
    g = "coiffure" if kind == "enfant" else "type"
    return PACK / (_opt(_GROUP[kind], g, cfg.get(g))["img"] + ".png")


def is_model(kind, cfg):
    """Vrai si la configuration correspond exactement au modèle peint du pack (aucune génération nécessaire)."""
    base = OPTIONS["modeles"][kind] if kind != "animal" else OPTIONS["modeles"]["animal"].get(cfg.get("type"), {})
    if kind == "enfant" and cfg.get("age", "5") not in ("4", "5", "6"):
        return False
    return all(cfg.get(k, v) == v for k, v in base.items() if k in cfg or k in AV_KEYS[kind])


def avatar_key(kind, cfg):
    import hashlib
    return hashlib.sha1(json.dumps({"k": kind, **cfg}, sort_keys=True).encode()).hexdigest()[:20]


# ====================================================================== 7. modèle peint recoloré côté serveur
# Même calcul que l'aperçu du navigateur (static/avatar.js) : sert de base au portrait quand l'aperçu du navigateur
# n'est pas disponible (livre test, renouvellement d'abonnement), pour ne jamais partir des couleurs du modèle
# (ex. doudou chat bleu à nœud rouge alors que le parent a choisi gris sans accessoire).
AV_STATIC = Path(__file__).parent / "static" / "avatars"


def _rgb2hsl(r, g, b):
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    l = (mx + mn) / 2; d = mx - mn
    s = np.where(d == 0, 0, d / np.maximum(1e-6, 1 - np.abs(2 * l - 1)))
    h = np.where(d == 0, 0, np.where(mx == r, ((g - b) / np.maximum(d, 1e-6)) % 6,
                 np.where(mx == g, (b - r) / np.maximum(d, 1e-6) + 2, (r - g) / np.maximum(d, 1e-6) + 4))) / 6
    return h % 1, np.clip(s, 0, 1), l


def _hsl2rgb(h, s, l):
    c = (1 - np.abs(2 * l - 1)) * s; hp = h * 6; x = c * (1 - np.abs(hp % 2 - 1)); m = l - c / 2
    z = np.zeros_like(h); i = np.floor(hp).astype(int) % 6
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [c, x, z, z, x, c])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [x, c, c, x, z, z])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [z, z, x, c, c, x])
    return r + m, g + m, b + m


def _hex(c):
    c = c.lstrip("#"); return [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _shade(c, k):
    h, s, l = _rgb2hsl(*[np.array(v) for v in _hex(c)])
    l = np.clip(l + k * (1 - l if k > 0 else l), 0, 1)
    return "#" + "".join(f"{int(round(float(v) * 255)):02x}" for v in _hsl2rgb(h, s, l))


def recolor_targets(kind, cfg):
    m = OPTIONS["modeles"]
    base = m["animal"].get(cfg.get("type"), {}) if kind == "animal" else m[kind]
    col = lambda g, k: _opt(g, k, cfg.get(k)).get("c")
    t = {}
    if kind == "enfant":
        if cfg.get("couleur_cheveux") != base["couleur_cheveux"]: t["R"] = col("enfant", "couleur_cheveux")
        if cfg.get("peau") != base["peau"]: t["G"] = col("enfant", "peau")
        if cfg.get("couleur_tenue") != base["couleur_tenue"]: t["B"] = col("enfant", "couleur_tenue")
    elif kind == "doudou":
        if cfg.get("couleur") != base["couleur"]: t["R"] = col("doudou", "couleur")
        if cfg.get("accessoire") != "aucun" and cfg.get("couleur_accessoire") != base["couleur_accessoire"]:
            t["B"] = col("doudou", "couleur_accessoire")
    else:
        main = col("animal", "couleur")
        if cfg.get("couleur") != base.get("couleur"): t["R"] = main
        if cfg.get("motif") == "uni" and cfg.get("type") != "oiseau": t["G"] = _shade(main, .2)
        elif cfg.get("couleur2") and cfg.get("couleur2") != base.get("couleur2"): t["G"] = col("animal", "couleur2")
    return {k: v for k, v in t.items() if v}


def recolor_model(kind, cfg):
    """Modèle peint du pack recoloré selon la configuration (fond crème), mis en cache. None si impossible."""
    import hashlib
    try:
        name = model_file(kind, cfg).stem
        t = recolor_targets(kind, cfg)
        out = CACHE / f"base_{hashlib.sha1(json.dumps([name, t], sort_keys=True).encode()).hexdigest()[:16]}.png"
        if out.exists():
            return out
        im = Image.open(AV_STATIC / f"{name}.webp").convert("RGBA")
        px = np.asarray(im).astype(np.float32) / 255
        mask = np.asarray(Image.open(AV_STATIC / f"{name}.mask.png").convert("RGB").resize(im.size)).astype(np.float32) / 255
        st = json.loads((AV_STATIC / "masks.json").read_text()).get(name, {})
        r, g, b = px[..., 0], px[..., 1], px[..., 2]
        for i, k in enumerate("RGB"):
            if k not in t or k not in st: continue
            hb, sb, lb = [float(v) for v in _rgb2hsl(*[np.array(v / 255) for v in st[k]])]
            ht, stt, lt = [float(v) for v in _rgb2hsl(*[np.array(v) for v in _hex(t[k])])]
            h, s, l = _rgb2hsl(r, g, b)
            h = (h + ht - hb + 1) % 1; s = np.minimum(1, s * stt / max(sb, .05))
            l = l * lt / max(lb, 1e-3) if lt <= lb else 1 - (1 - l) * (1 - lt) / max(1 - lb, 1e-3)
            r2, g2, b2 = _hsl2rgb(h, s, np.clip(l, 0, 1))
            w = mask[..., i]
            r, g, b = r * (1 - w) + r2 * w, g * (1 - w) + g2 * w, b * (1 - w) + b2 * w
        rgba = np.dstack([r, g, b, px[..., 3]])
        fg = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
        bg = Image.new("RGB", im.size, (246, 238, 222)); bg.paste(fg, (0, 0), fg)
        bg.save(out)
        return out
    except Exception:
        return None


def base_differences(kind, cfg):
    """Ce que le modèle peint montre et que le parent n'a PAS choisi : consignes explicites pour le portrait."""
    m = OPTIONS["modeles"]
    base = m["animal"].get(cfg.get("type"), {}) if kind == "animal" else m[kind]
    en = lambda g, k, v: _opt(g, k, v).get("en", v)
    out = []
    if kind == "doudou":
        if cfg.get("accessoire") == "aucun" and base.get("accessoire") != "aucun":
            out.append("REMOVE the bow / accessory worn by the base model: this plush toy has NO accessory at all, bare neck")
        elif cfg.get("accessoire") != base.get("accessoire"):
            out.append(f"replace the base model's {en('doudou', 'accessoire', base['accessoire'])} with {en('doudou', 'accessoire', cfg['accessoire'])}")
        if cfg.get("couleur") != base.get("couleur"):
            out.append(f"its fabric is {en('doudou', 'couleur', cfg['couleur'])}, NOT {en('doudou', 'couleur', base['couleur'])} like the base model")
    elif kind == "animal":
        if cfg.get("couleur") != base.get("couleur"):
            out.append(f"main fur colour is {en('animal', 'couleur', cfg['couleur'])}, NOT {en('animal', 'couleur', base['couleur'])} like the base model")
        for k in ("motif", "yeux", "collier", "oreilles"):
            if cfg.get(k) and base.get(k) and cfg[k] != base[k]:
                out.append(f"{en('animal', k, cfg[k])} (different from the base model)")
    else:
        if cfg.get("tenue") != base.get("tenue"):
            out.append(f"outfit is {en('enfant', 'tenue', cfg['tenue'])} in {en('enfant', 'couleur_tenue', cfg.get('couleur_tenue'))}, NOT the base model's {en('enfant', 'tenue', base['tenue'])}")
        if cfg.get("couleur_cheveux") != base.get("couleur_cheveux"):
            out.append(f"hair is {en('enfant', 'couleur_cheveux', cfg['couleur_cheveux'])}")
        if cfg.get("yeux") != base.get("yeux"):
            out.append(f"eyes are {en('enfant', 'yeux', cfg['yeux'])}")
    return out
