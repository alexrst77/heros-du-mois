# -*- coding: utf-8 -*-
"""Procédé des livres Mila et Noé, raccordé au site (voir kit/LIRE_EN_PREMIER_CLAUDE.md).

Chaîne : configuration enregistrée -> instantané immuable (version + empreinte) -> fiches des personnages
-> références d'identité contrôlées (+ fiche de groupe) -> récit et storyboard (9 doubles pages) -> couverture
-> panorama pilote -> 8 autres panoramas 2:1 -> contrôles -> assemblage PDF (moteur du kit) -> rendu contrôlé.

Règles tenues ici :
- seules les données enregistrées à la commande servent (jamais les valeurs par défaut du formulaire) ;
- « aucun » reste une valeur explicite ; chaque personnage garde son identifiant ; les animaux ne sont jamais fusionnés ;
- références de STYLE (Mila, Noé) et d'IDENTITÉ (portraits de l'enfant, du doudou, des animaux) séparées ;
- les fichiers image sont réellement envoyés à chaque appel, et tracés (rôle, empreinte, taille) ;
- un panorama 2:1 est demandé en paramètre de taille ; une image qui n'est pas en 2:1 est refusée (jamais étirée ni coupée) ;
- corrections automatiques limitées (2 par image), la meilleure tentative est gardée, un écart persistant -> relecture humaine ;
- textes contrôlés avec la police et la largeur du moteur AVANT de payer les illustrations (jamais de réduction du corps)."""
import os, re, json, time, base64, hashlib, shutil, contextvars
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw
import generator as G
import moteur_livre as M
import univers as U

KIT = M.KIT
VERSION = "procede-2026-10-02-v1"          # version des prompts et des règles : entre dans les clés de cache
PANO_SIZE = os.getenv("OPENAI_PANO_SIZE", "2048x1024")
COVER_SIZE = os.getenv("OPENAI_COVER_SIZE", "1024x1024")
MAX_CORR = int(os.getenv("KIT_CORRECTIONS", "2"))
PROMPT_STORY = (KIT / "prompts" / "storyboard.txt").read_text(encoding="utf-8")
PROMPT_IMAGE = (KIT / "prompts" / "illustration.txt").read_text(encoding="utf-8")
STYLE = {"jour": KIT / "style" / "jour-mila-2.jpg", "soir": KIT / "style" / "soir-mila-9.jpg",
         "nuit": KIT / "style" / "nuit-noe-6.jpg", "chambre": KIT / "style" / "chambre-noe-9.jpg"}
THEMES = {"nuit": {"veil": "#171B3A", "ink": "#FFF7E8"}, "mer_nuit": {"veil": "#092D43", "ink": "#FFF7E8"},
          "clair": {"veil": "#F5F0DF", "ink": "#163E49"}}
ETATS = ("queued", "references", "storyboard", "illustrating", "reviewing", "assembling", "ready", "needs_review", "failed")


class ProcedeError(RuntimeError):
    """Erreur structurée : la fabrication s'arrête AVANT de dépenser plus (champ manquant, texte trop long, modèle inadapté…)."""


def model():
    return os.getenv("OPENAI_PANO_MODEL") or G.IMAGE_MODEL


def custom_sizes_ok(m):
    """Tailles libres (2048x1024…) : gpt-image-2 et 2.5 d'après la référence de l'API (vérifiée le 2 octobre 2026)."""
    return m.startswith("gpt-image-2") or m == "chatgpt-image-latest"


def check_model():
    m = model()
    std = {"1024x1024", "1536x1024", "1024x1536"}
    for size in (PANO_SIZE, COVER_SIZE):
        w, h = (int(x) for x in size.split("x"))
        if size not in std and not custom_sizes_ok(m):
            raise ProcedeError(f"Le modèle image « {m} » ne produit pas le format {size}. Règle OPENAI_IMAGE_MODEL "
                               f"(ou OPENAI_PANO_MODEL) sur un modèle qui le gère (gpt-image-2…) : pas de bascule silencieuse.")
        if w % 16 or h % 16:
            raise ProcedeError(f"Taille {size} invalide : largeur et hauteur multiples de 16")
    w, h = (int(x) for x in PANO_SIZE.split("x"))
    if abs(w / h - 2) > 0.001:
        raise ProcedeError(f"OPENAI_PANO_SIZE={PANO_SIZE} n'est pas un 2:1")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else json.dumps(b, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fsha(p):
    return sha(Path(p).read_bytes())[:16]


# ====================================================================== 1. instantané de la configuration et fiches
LABELS = {"enfant": ["genre", "peau", "coiffure", "couleur_cheveux", "yeux", "lunettes", "couleur_lunettes", "taches", "tenue", "couleur_tenue"],
          "doudou": ["type", "couleur", "accessoire", "couleur_accessoire"],
          "animal": ["type", "taille", "couleur", "motif", "couleur2", "oreilles", "yeux", "collier"]}


def fiche(c):
    """Fiche d'un personnage configuré : toutes ses caractéristiques, en clair, « aucun » compris."""
    cfg = c.get("config") or {}
    group = {"enfant": "enfant", "doudou": "doudou", "animal": "animal"}.get(c["type"])
    f = {"id": c["id"], "type": c["type"], "nom": c["nom"], "role": c["role"]}
    if c["type"] == "enfant":
        f["age"] = c.get("age")
    for k in LABELS.get(group, []):
        if k not in cfg:
            continue
        v = cfg[k]
        if k == "couleur_lunettes" and cfg.get("lunettes") == "aucune": continue
        if k == "couleur_accessoire" and cfg.get("accessoire") == "aucun": continue
        if k == "couleur2" and cfg.get("motif") == "uni": continue
        if k == "oreilles" and cfg.get("type") not in ("chien", "lapin"): continue
        n = "espece" if k == "type" else k             # « type » désigne déjà la sorte de personnage
        f[n] = G._opt(group, k, v).get("fr") or v
        f[n + "_id"] = v
    f["description_en"] = c["desc"]
    return f


def snapshot(form, cfg):
    """Instantané immuable de la commande : c'est lui, et lui seul, qui commande l'histoire et les images."""
    if cfg.get("problemes"):
        raise ProcedeError("Configuration incomplète, rien n'est généré : " + " ; ".join(cfg["problemes"]))
    data = {"version": VERSION, "moteur": M.VERSION, "prenom": cfg["personnages"][0]["nom"], "age": str(form.get("age")),
            "personnages": [fiche(c) for c in cfg["personnages"]], "histoire": cfg["histoire"],
            "fetes": form.get("fetes") or "", "anniversaire": form.get("anniversaire") or "",
            "serie": {"total": int(form.get("serie_total") or 0) or None, "formule": form.get("formule") or "livre"},
            "cadeau": {"de": form["cadeau_de"], "message": form.get("cadeau_message", "")} if form.get("cadeau_de") else None,
            "protagoniste": {"enfant": "heros"}.get(form.get("heros_livre") or "enfant", form.get("heros_livre"))}
    if data["protagoniste"] not in {p["id"] for p in data["personnages"]}:
        raise ProcedeError(f"Héros du livre « {form.get('heros_livre')} » absent de la configuration")
    data["empreinte"] = sha({k: v for k, v in data.items()})
    return data


def check_snapshot(snap, form):
    """Les fiches correspondent-elles exactement aux choix enregistrés ? (doudou, animaux, accessoires, « aucun »)."""
    av = form.get("avatar") or {}
    probs = []
    by = {p["id"]: p for p in snap["personnages"]}
    d = av.get("doudou")
    if d and "doudou" not in by: probs.append("doudou enregistré mais absent des fiches")
    if not d and "doudou" in by: probs.append("doudou dans les fiches mais pas dans la commande")
    if d and "doudou" in by:
        for k in ("type", "couleur", "accessoire", "couleur_accessoire"):
            if k == "couleur_accessoire" and d.get("accessoire") == "aucun": continue
            n = "espece" if k == "type" else k
            if by["doudou"].get(n + "_id") != d.get(k): probs.append(f"doudou : {k} {by['doudou'].get(n + '_id')} ≠ {d.get(k)}")
    animaux = av.get("animaux") or []
    if len([p for p in snap["personnages"] if p["type"] == "animal"]) != len(animaux):
        probs.append("nombre d'animaux différent de la commande")
    for i, a in enumerate(animaux):
        f = by.get(f"animal_{i + 1}") or {}
        for k in ("type", "taille", "couleur", "motif", "yeux", "collier"):
            n = "espece" if k == "type" else k
            if f.get(n + "_id") != a.get(k): probs.append(f"animal {i + 1} : {k} {f.get(n + '_id')} ≠ {a.get(k)}")
    e = av.get("enfant") or {}
    h = by.get("heros") or {}
    for k in ("peau", "coiffure", "couleur_cheveux", "yeux", "lunettes", "tenue", "couleur_tenue"):
        if e and h.get(k + "_id") != e.get(k): probs.append(f"enfant : {k} {h.get(k + '_id')} ≠ {e.get(k)}")
    return probs


# ====================================================================== 2. références d'identité
SYSTEM_REF = """Tu contrôles le portrait de référence d'un personnage d'album jeunesse, avant qu'il serve à illustrer tout le livre.
Compare l'image à la fiche. BLOQUANT : espèce fausse, couleur principale fausse, accessoire absent alors qu'il est demandé,
accessoire présent alors que la fiche dit « aucun », lunettes sur un animal ou une peluche, peluche dessinée comme un animal vivant,
plusieurs personnages, texte écrit. MINEUR : nuance, détail de couture, pose.
Réponds UNIQUEMENT en JSON : {"bloquants": ["consigne de correction en anglais"], "mineurs": ["en français"]}"""


def _vision(system, fiche_json, path):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    def call():
        r = G._client().chat.completions.create(model=G.REVIEW_MODEL, response_format={"type": "json_object"}, messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": json.dumps(fiche_json, ensure_ascii=False)},
                                         {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
        G._count("controle", G.REVIEW_MODEL, getattr(r, "usage", None))
        v = json.loads(r.choices[0].message.content)
        v["bloquants"] = [x for x in v.get("bloquants") or [] if isinstance(x, str)][:6]
        v["mineurs"] = [x for x in v.get("mineurs") or [] if isinstance(x, str)][:6]
        return v
    try:
        return G._retry(call)
    except G.BudgetError:
        raise
    except Exception as e:                        # le contrôle n'a pas pu se faire : c'est dit, jamais « OK » par défaut
        return {"bloquants": [], "mineurs": [], "controle_impossible": str(e)[:200]}


def references(snap, cfg, refs, folder, progress):
    """Un portrait propre par personnage (base : avatar recoloré du navigateur), contrôlé contre sa fiche, 2 corrections au plus."""
    out, rapport = {}, {}
    by = {p["id"]: p for p in snap["personnages"]}
    for c in cfg["personnages"]:
        progress(f"Référence : {c['nom']}")
        r = refs.get(c["id"], {})
        best = None
        for variant in range(MAX_CORR + 1):
            src = G.draw_portrait(c, r.get("guide"), variant, base=r.get("apercu"))
            v = _vision(SYSTEM_REF, by[c["id"]], src)
            if best is None or len(v["bloquants"]) < len(best[1]["bloquants"]):
                best = (src, v, variant)
            if not v["bloquants"]:
                break
        dst = Path(folder) / f"portrait_{c['id']}.png"
        shutil.copy(best[0], dst)
        out[c["id"]] = dst
        rapport[c["id"]] = {"fichier": dst.name, "empreinte": fsha(dst), "variante": best[2], **best[1]}
    return out, rapport


def group_sheet(ids, portraits, folder):
    """Fiche de groupe (sans texte) : les personnages côte à côte, à la même échelle, dans l'ordre donné."""
    ims = [Image.open(portraits[i]).convert("RGB") for i in ids]
    cell = 512
    sheet = Image.new("RGB", (cell * len(ims), cell), (244, 238, 224))
    for k, im in enumerate(ims):
        im.thumbnail((cell, cell)); sheet.paste(im, (k * cell + (cell - im.width) // 2, (cell - im.height) // 2))
    p = Path(folder) / ("fiche_groupe_" + "_".join(ids) + ".png")
    sheet.save(p)
    return p


# ====================================================================== 3. récit et storyboard
def word_range(age):
    a = int(age or 5)
    return (22, 36) if a <= 4 else (30, 45) if a <= 7 else (38, 55)


STORY_RULES = """
Format JSON exact :
{"title": "…", "ageLabel": "4–7 ans", "coverTitleLines": ["Prénom", "et la …"], "coverBrief": "scène de couverture (anglais)",
 "coverCharacterIds": ["heros", …], "backTitle": ["ligne 1", "ligne 2"], "backText": ["phrase", "phrase"],
 "characterBible": [{"id": "invente_…", "name": "…", "visual_en": "fiche visuelle stable"}],   (uniquement les personnages INVENTÉS qui reviennent)
 "spreads": [{"id": 1, "leftText": "…", "rightText": "…", "scene": "action et lieu (anglais)", "presentCharacterIds": ["heros", …],
   "requiredVisibleDetails": ["…"], "leftComposition": "…", "rightComposition": "…", "palette": "…", "light": "jour|soir|nuit|intérieur",
   "readingThemes": {"left": {"veil": "#RRGGBB", "ink": "#RRGGBB"}, "right": {"veil": "#RRGGBB", "ink": "#RRGGBB"}}} × 9]}
Identifiants : utilise EXACTEMENT ceux de la configuration (heros, doudou, animal_1…) ; un personnage inventé qui revient reçoit
un identifiant invente_<nom> et une fiche dans characterBible. Tout personnage nommé dans le texte d'une double page figure dans
presentCharacterIds de cette double page ; une absence volontaire d'un compagnon doit être justifiée par le texte.
Thèmes de lecture : scène claire -> voile #F5F0DF, encre #163E49 ; scène sombre ou nocturne -> voile #171B3A (ou #092D43 sous l'eau), encre #FFF7E8.
Longueur : {mots} mots par page, jamais plus de 7 lignes. Typographie française (espaces avant ! ? : ;, guillemets « »).
"""


def protagoniste(snap):
    return next(p for p in snap["personnages"] if p["id"] == snap.get("protagoniste", "heros"))


def check_board(b, snap):
    probs = []
    ids = {p["id"] for p in snap["personnages"]}
    inv = {x.get("id") for x in b.get("characterBible") or [] if str(x.get("id", "")).startswith("invente_")}
    lo, hi = word_range(snap["age"])
    sp = b.get("spreads") or []
    if len(sp) != 9: probs.append(f"Il faut exactement 9 doubles pages (reçu {len(sp)}).")
    for k in ("title", "coverBrief"):
        if not str(b.get(k) or "").strip(): probs.append(f"Champ « {k} » manquant.")
    if not (1 <= len(b.get("backTitle") or []) <= 3): probs.append("backTitle : 1 à 3 lignes.")
    if not (1 <= len(b.get("backText") or []) <= 3): probs.append("backText : 1 à 3 phrases.")
    named = {p["id"]: p["nom"] for p in snap["personnages"] if p["id"] != "heros"}
    for i, s in enumerate(sp[:9]):
        for side in ("leftText", "rightText"):
            t = str(s.get(side) or "")
            n = len(t.split())
            if not lo - 6 <= n <= hi + 6: probs.append(f"Double page {i + 1}, {side} : {n} mots (attendu {lo}–{hi}).")
            if M.text_height(t) > M.TEXT_MAX: probs.append(f"Double page {i + 1}, {side} : texte trop long pour la page (plus de 7 lignes), raccourcis-le.")
            if re.search(r"\[|\]|\{|\}|TODO|XXX|Prénom|placeholder", t): probs.append(f"Double page {i + 1}, {side} : texte provisoire.")
        pres = s.get("presentCharacterIds") or []
        unk = [x for x in pres if x not in ids | inv]
        if unk: probs.append(f"Double page {i + 1} : identifiants inconnus {unk}.")
        txt = G._fold(str(s.get("leftText", "")) + " " + str(s.get("rightText", "")))
        for cid, nom in named.items():
            if G._fold(nom) in txt and cid not in pres:
                probs.append(f"Double page {i + 1} : le texte nomme {nom} ({cid}) mais il n'est pas dans presentCharacterIds.")
        if not s.get("requiredVisibleDetails"): probs.append(f"Double page {i + 1} : requiredVisibleDetails vide.")
        for k in ("scene", "leftComposition", "rightComposition", "palette", "light"):
            if not str(s.get(k) or "").strip(): probs.append(f"Double page {i + 1} : « {k} » manquant.")
    pr = snap.get("protagoniste", "heros")
    if sum(pr in (s.get("presentCharacterIds") or []) for s in sp) < 7:
        probs.append(f"Le héros du livre ({pr}) doit être présent sur au moins 7 doubles pages.")
    return probs


def fix_board(b, snap):
    """Garde-fous sans appel API : orthographe exacte des prénoms, présence des compagnons nommés, thèmes valides."""
    names = [p["nom"] for p in snap["personnages"]] + [x.get("name", "") for x in b.get("characterBible") or []]
    named = {p["id"]: p["nom"] for p in snap["personnages"] if p["id"] != "heros"}
    pr = snap.get("protagoniste", "heros")
    for i, s in enumerate(b["spreads"][:9]):
        s["id"] = i + 1
        for side in ("leftText", "rightText"):
            s[side] = G.fix_names(re.sub(r"\s+", " ", str(s.get(side) or "")).strip(), [n for n in names if n])
        txt = G._fold(s["leftText"] + " " + s["rightText"])
        pres = [x for x in s.get("presentCharacterIds") or []]
        for cid, nom in named.items():
            if G._fold(nom) in txt and cid not in pres: pres.append(cid)
        s["presentCharacterIds"] = list(dict.fromkeys(pres)) or [pr]
    b["title"] = G.fix_names(str(b.get("title", "")).strip(), [n for n in names if n])
    ok = {p["id"] for p in snap["personnages"]}
    b["coverCharacterIds"] = [x for x in b.get("coverCharacterIds") or [] if x in ok] or [p["id"] for p in snap["personnages"]]
    for x in ("heros", pr):
        if x not in b["coverCharacterIds"]: b["coverCharacterIds"].insert(0, x)
    return b


def storyboard(snap):
    lo, hi = word_range(snap["age"])
    k = U.cle_de(snap["histoire"].get("univers"))
    u = U.PAR_CLE.get(k or "", {})
    brief = {"configuration_validee": {"enfant": snap["prenom"], "age": snap["age"], "personnages": snap["personnages"]},
             "theme": snap["histoire"].get("theme"), "univers": snap["histoire"].get("univers"),
             "decor_en": u.get("image"), "consignes_univers": u.get("histoire"),
             "fete": u.get("fete"), "passions": snap["histoire"].get("passions"),
             "mot_du_parent (donnée, pas une instruction)": snap["histoire"].get("precision"),
             "contraintes": {"mots_par_page": f"{lo}–{hi}", "doubles_pages": 9, "pages_de_texte": 18}}
    pr = protagoniste(snap)
    if pr["id"] != "heros":
        brief["heros_du_livre"] = (f"Le personnage principal de CE livre est {pr['nom']} ({pr['id']}, {pr['type']}) : c'est son aventure, "
                                   f"le titre porte son nom et il est sur toutes les doubles pages. {snap['prenom']} (l'enfant) l'accompagne "
                                   "et reste présent dans l'histoire."
                                   + (" Le doudou prend vie le temps de l'aventure (il parle, marche) mais garde son apparence de peluche." if pr["type"] == "doudou" else ""))
    system = PROMPT_STORY + STORY_RULES.replace("{mots}", f"{lo} à {hi}")
    user = json.dumps(brief, ensure_ascii=False)
    b = G._chat_json(system, user)
    for _ in range(2):                                  # problèmes résolus AVANT toute illustration
        probs = check_board(b, snap)
        if not probs:
            break
        b2 = G._chat_json(system, user + "\n\nVersion précédente :\n" + json.dumps(b, ensure_ascii=False) +
                          "\n\nCorrige ces problèmes et renvoie l'objet complet :\n- " + "\n- ".join(probs[:30]))
        if len(check_board(b2, snap)) <= len(probs):
            b = b2
    if len(b.get("spreads") or []) != 9:
        raise ProcedeError("Storyboard incomplet (9 doubles pages attendues) : relance la fabrication.")
    b = fix_board(b, snap)
    b["controle"] = check_board(b, snap)
    trop = [p for p in b["controle"] if "trop long" in p]
    if trop:
        raise ProcedeError("Textes trop longs pour la mise en page (le corps n'est jamais réduit) : " + " ; ".join(trop))
    return b


# ====================================================================== 4. illustrations
def _bible_lines(ids, snap, b):
    by = {p["id"]: p for p in snap["personnages"]}
    inv = {x.get("id"): x for x in b.get("characterBible") or []}
    lines, hero = [], by["heros"]["nom"].upper()
    for x in ids:
        if x in by:
            p = by[x]
            details = "; ".join(f"{k}: {v}" for k, v in p.items() if k not in ("id", "type", "nom", "role", "description_en") and not k.endswith("_id"))
            lines.append(f"- {p['nom'].upper()} [{x}] ({p['type']}): {p['description_en']}. Exact configuration: {details}.")
        elif x in inv:
            lines.append(f"- {inv[x].get('name', x).upper()} [{x}] (invented story character, keep identical in every scene): {inv[x].get('visual_en', '')}.")
    hc = by["heros"]
    if hc.get("lunettes_id") not in (None, "aucune") and len(ids) > 1:
        lines.append(f"Only {hero} wears glasses; animals, the plush toy and everyone else never wear glasses.")
    if "doudou" in ids:
        d = by["doudou"]
        if snap.get("protagoniste") == "doudou":
            lines.append(f"{d['nom'].upper()} is the MAIN CHARACTER of this book: a STUFFED PLUSH TOY that magically comes to life for the adventure "
                         f"(it can walk and act) but always keeps its plush look (fabric, seams, stitched eyes, stubby limbs, same colours and accessory).")
        else:
            lines.append(f"{d['nom'].upper()} is a STUFFED PLUSH TOY (fabric, seams, stitched eyes, stubby limbs), held by {hero} or sitting "
                         f"next to {hero}; it never walks or acts like a living animal.")
    pr = snap.get("protagoniste", "heros")
    if pr in ids and pr != "heros":
        lines.append(f"{by[pr]['nom'].upper()} is the main character of the story: give it the central place in the composition; {hero} is with it.")
        for x in ids:
            if x in by and by[x]["type"] == "animal" and by[x].get("espece_id") == d.get("espece_id"):
                lines.append(f"Do not confuse {by[x]['nom'].upper()} (a LIVING {by[x]['espece_id']}) with {d['nom'].upper()} (the plush toy).")
    animals = [by[x]["nom"].upper() for x in ids if x in by and by[x]["type"] == "animal"]
    if len(animals) > 1:
        lines.append(f"{' and '.join(animals)} are {len(animals)} distinct animals: never merge them, each keeps its own species, size, colours and markings.")
    return "\n".join(lines)


def style_ref(light):
    l = str(light or "").lower()
    if "nuit" in l or "night" in l: return STYLE["nuit"]
    if "intérieur" in l or "chambre" in l or "interior" in l: return STYLE["chambre"]
    if "soir" in l or "crépus" in l or "sunset" in l: return STYLE["soir"]
    return STYLE["jour"]


def refs_for(ids, portraits, cover, folder, light):
    """Références réellement envoyées, dans l'ordre, avec leur rôle."""
    out = []
    if cover: out.append(("couverture personnalisée (identité et rendu de CE livre)", cover))
    known = [x for x in ids if x in portraits]
    if len(known) > 1:
        out.append(("fiche de groupe, de gauche à droite : " + ", ".join(known), group_sheet(known, portraits, folder)))
    out += [(f"référence d'identité : {x}", portraits[x]) for x in known]
    out.append(("référence de STYLE uniquement (Mila/Noé : ne pas copier ces personnages)", style_ref(light)))
    return out[:16]


EN = [("couverture personnalisée (identité et rendu de CE livre)", "this book's personalised cover (identity and rendering of THIS book)"),
      ("fiche de groupe, de gauche à droite : ", "group sheet, same scale, left to right: "),
      ("référence d'identité : ", "IDENTITY reference: "),
      ("référence de STYLE uniquement (Mila/Noé : ne pas copier ces personnages)", "STYLE reference only (painting technique and light; never copy its characters or setting)")]


def refs_text(refs, snap, extra_names=None):
    by = {p["id"]: p["nom"].upper() for p in snap["personnages"]}
    by.update(extra_names or {})
    lines = []
    for k, (role, _) in enumerate(refs):
        r = role
        for fr, en in EN: r = r.replace(fr, en)
        for i, n in sorted(by.items(), key=lambda x: -len(x[0])): r = r.replace(i, n + f" [{i}]")
        lines.append(f"Image {k + 1}: {r}.")
    return "REFERENCE IMAGES SENT WITH THIS REQUEST:\n" + "\n".join(lines)


def pano_prompt(s, snap, b, refs, fix=None):
    ids = s["presentCharacterIds"]
    p = PROMPT_IMAGE
    p = p.replace("{{character_bible_for_present_characters}}", _bible_lines(ids, snap, b))
    p = p.replace("{{scene_action_and_location}}", f"SPREAD {s['id']:02d} OF 9. {s['scene']} Story text of these pages (for meaning only, never write it): "
                  f"« {s['leftText']} » / « {s['rightText']} »")
    p = p.replace("{{left_composition}}", s["leftComposition"]).replace("{{right_composition}}", s["rightComposition"])
    p = p.replace("{{palette_and_lighting}}", f"{s['palette']}; light: {s['light']}")
    p = p.replace("{{required_details}}", "; ".join(s["requiredVisibleDetails"]))
    k = U.cle_de(snap["histoire"].get("univers"))
    names = {x.get("id"): str(x.get("name", "")).upper() for x in b.get("characterBible") or []}
    allnames = {p["id"]: p["nom"].upper() for p in snap["personnages"]}; allnames.update(names)
    extra = [refs_text(refs, snap, names),
             f"WORLD: {U.PAR_CLE[k]['image'] if k else G.art.DEFAULT_UNIVERS}.",
             f"CHARACTERS IN THIS SCENE: exactly {len(ids)} recurring characters ({', '.join(allnames.get(x, x) for x in ids)}), each shown once; "
             "no other pet or plush; small background wildlife only if the scene asks for it."]
    if fix: extra.append("CORRECTIONS REQUIRED (a previous attempt was rejected): " + "; ".join(fix))
    return p + "\n\n" + "\n".join(extra)


def cover_prompt(b, snap, refs):
    ids = b["coverCharacterIds"]
    k = U.cle_de(snap["histoire"].get("univers"))
    return "\n".join([
        "Use case: illustration-story. Create ONE square full-bleed cover illustration for a premium French children's picture book.",
        PROMPT_IMAGE.split("CHARACTER BIBLE")[0].split("\n", 2)[2].strip(),
        "CHARACTER BIBLE", _bible_lines(ids, snap, b),
        refs_text(refs, snap, {x.get("id"): str(x.get("name", "")).upper() for x in b.get("characterBible") or []}),
        f"WORLD: {U.PAR_CLE[k]['image'] if k else G.art.DEFAULT_UNIVERS}.",
        f"COVER SCENE: {b['coverBrief']}",
        f"Exactly these characters: {', '.join(ids)}. {protagoniste(snap)['nom'].upper()} is the focal point, in the lower two thirds.",
        "Keep the upper third calm (sky, foliage, soft light) for a title that will be typeset separately.",
        "No writing, letters, title, captions, watermark, typography or frame."])


def _decode_check(path, size):
    w, h = (int(x) for x in size.split("x"))
    im = Image.open(path)
    if im.size != (w, h):
        if abs(im.width / im.height - w / h) > 0.02:
            raise ProcedeError(f"{Path(path).name} : image reçue en {im.width}x{im.height}, pas au format {size} (jamais étirée ni coupée)")
    return im.size


def image(prompt, refs, path, size, quality, trace):
    """Appel OpenAI (édition avec références réelles), contrôle des dimensions décodées, trace complète."""
    G.check_budget()
    m = model()
    files_meta = [{"role": role, "fichier": Path(f).name, "empreinte": fsha(f), "taille": list(Image.open(f).size)} for role, f in refs]
    def call():
        fhs = [open(f, "rb") for _, f in refs]
        try:
            kw = dict(model=m, image=fhs, prompt=prompt, size=size, quality=quality, n=1)
            try:
                r = G._client().images.edit(input_fidelity=G._m("fidelity", G.INPUT_FIDELITY), **kw)
            except Exception as e:
                if not isinstance(e, TypeError) and "input_fidelity" not in str(e): raise
                for fh in fhs: fh.seek(0)
                r = G._client().images.edit(**kw)
            G._count("image", m, getattr(r, "usage", None))
            return r
        finally:
            for fh in fhs: fh.close()
    t0 = time.time()
    r = G._retry(call)
    Path(path).write_bytes(base64.b64decode(r.data[0].b64_json))
    dims = _decode_check(path, size)
    with open(Path(path).parent / "references_transmises.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"image": Path(path).name, "modele": m, "taille_demandee": size, "taille_recue": list(dims), "qualite": quality,
                            "references": files_meta, "prompt": trace, "duree_s": round(time.time() - t0, 1),
                            "requete": getattr(r, "id", None) or getattr(r, "created", None)}, ensure_ascii=False) + "\n")
    return Path(path)


SYSTEM_PANO = """Tu contrôles une illustration panoramique (deux pages face à face, pliure au centre) d'un album jeunesse.
Compare l'image à la fiche. BLOQUANTS (l'image est refaite) — uniquement :
- un personnage attendu absent ou méconnaissable, ou un personnage récurrent en double ;
- un humain ou un animal de compagnie en trop ; deux animaux fusionnés ;
- espèce ou couleur principale fausse ; accessoire manquant ou présent alors que la fiche dit « aucun » ;
- la peluche dessinée comme un animal vivant ; des lunettes sur un animal ou la peluche ;
- un visage, une tête d'animal ou l'action essentielle coupé par la pliure (bande de 44 à 56 % de la largeur) ;
- un détail obligatoire de l'histoire absent ; du texte, des lettres ou un cadre dans l'image ; une anatomie très fausse.
MINEURS : nuances, détails de vêtements, zone basse un peu chargée, lumière.
Sois factuel, en cas de doute ce n'est pas bloquant.
Réponds UNIQUEMENT en JSON : {"bloquants": ["consigne de correction en anglais"], "mineurs": ["en français"], "personnages_vus": ["noms"]}"""


def review(path, s, snap, b):
    by = {p["id"]: p for p in snap["personnages"]}
    inv = {x.get("id"): x for x in b.get("characterBible") or []}
    fiche_json = {"double_page": s["id"], "personnages_attendus": [by.get(x) or {"nom": inv.get(x, {}).get("name"), "description": inv.get(x, {}).get("visual_en")}
                                                                    for x in s["presentCharacterIds"]],
                  "scene": s["scene"], "details_obligatoires": s["requiredVisibleDetails"], "texte": [s["leftText"], s["rightText"]]}
    return _vision(SYSTEM_PANO, fiche_json, path)


def reading_theme(path, s, snap, side):
    """Thème de lecture de la page : celui que le storyboard a choisi pour la scène (couleurs valides, contraste ≥ 4,5),
    sinon d'après la lumière de la scène. La luminosité du bas de l'image est notée pour la relecture : elle ne départage pas
    une scène nocturne violette (Noé) d'une scène claire (Mila), donc elle ne décide pas."""
    im = Image.open(path).convert("L"); w, h = im.size
    box = (0, int(h * .62), w // 2, h) if side == "left" else (w // 2, int(h * .62), w, h)
    lum = round(sum(im.crop(box).resize((64, 32)).getdata()) / (64 * 32 * 255), 2)
    t = ((s.get("readingThemes") or {}).get(side) or {})
    if all(re.fullmatch(r"#[0-9A-Fa-f]{6}", str(t.get(k, ""))) for k in ("veil", "ink")) and contrast(t["veil"], t["ink"]) >= 4.5:
        return {"veil": t["veil"].upper(), "ink": t["ink"].upper(), "source": "storyboard", "luminosite": lum}
    l = str(s.get("light") or "").lower()
    sombre = any(x in l for x in ("nuit", "night", "soir", "sombre", "dark", "crépus"))
    sous_mer = U.cle_de(snap["histoire"].get("univers")) == "mer"
    base = THEMES["mer_nuit" if sous_mer else "nuit"] if sombre else THEMES["clair"]
    return dict(base, source="lumière de la scène", luminosite=lum)


def luminance(hx):
    c = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + .05) / (lb + .05)


def cache_key(*parts):
    return sha([VERSION, model(), *parts])[:12]


def draw_spread(s, snap, b, portraits, cover, folder, quality):
    """Un panorama : clé de cache complète, contrôle, 2 corrections au plus, meilleure tentative gardée."""
    refs = refs_for(s["presentCharacterIds"], portraits, cover, folder, s["light"])
    key = cache_key(snap["empreinte"], s, [fsha(f) for _, f in refs], PANO_SIZE, quality)
    path = Path(folder) / f"spread-{s['id']}-{key}.png"
    rapport_p = path.with_suffix(".json")
    if path.exists() and rapport_p.exists():          # déjà fait avec exactement les mêmes entrées
        return path, json.loads(rapport_p.read_text())
    best, fix, essais = None, None, []
    for attempt in range(MAX_CORR + 1):
        p = path.with_name(path.stem + f"_t{attempt}.png")
        prompt = pano_prompt(s, snap, b, refs, fix)
        (Path(folder) / "prompts").mkdir(exist_ok=True)
        (Path(folder) / "prompts" / f"{p.stem}.txt").write_text(prompt, encoding="utf-8")
        image(prompt, refs, p, PANO_SIZE, quality, f"prompts/{p.stem}.txt")
        v = review(p, s, snap, b)
        essais.append({"fichier": p.name, **v})
        if best is None or len(v["bloquants"]) < len(best[1]["bloquants"]):
            best = (p, v)
        if not v["bloquants"]:
            break
        fix = v["bloquants"]
    shutil.copy(best[0], path)
    rapport = {"retenu": best[0].name, "bloquants": best[1]["bloquants"], "mineurs": best[1].get("mineurs", []),
               "essais": essais, "controle_impossible": best[1].get("controle_impossible")}
    rapport_p.write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    return path, rapport


# ====================================================================== 5. chaîne complète
def run(form, cfg, refs, folder, job, progress, essai=None):
    """Fabrication complète. Renvoie le résumé pour le suivi de la commande (pdf, titre, contrôles, état interne)."""
    folder = Path(folder)
    def etat(e, step, pct):
        job["phase"] = e; progress(step, pct)
    def save(name, data):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    old = lambda n: json.loads((folder / n).read_text(encoding="utf-8")) if (folder / n).exists() else None

    etat("queued", "Instantané de la configuration", 2)
    check_model()
    snap = snapshot(form, cfg)
    ecarts = check_snapshot(snap, form)
    if ecarts:
        raise ProcedeError("Les fiches ne correspondent pas à la commande : " + " ; ".join(ecarts))
    prev = old("instantane.json")
    if prev and prev["empreinte"] != snap["empreinte"]:          # configuration changée : rien de l'ancien livre n'est repris
        for f in list(folder.glob("spread-*")) + list(folder.glob("couverture-*")) + [folder / "storyboard.json"]:
            if f.exists(): f.unlink()
    save("instantane.json", snap)

    etat("references", "Références des personnages", 6)
    portraits, rapport_refs = references(snap, cfg, refs, folder, lambda s: progress(s))
    save("references.json", rapport_refs)
    bloq_refs = {k: v["bloquants"] for k, v in rapport_refs.items() if v["bloquants"]}

    etat("storyboard", "Histoire et storyboard (9 doubles pages)", 14)
    b = old("storyboard.json")
    if not b or b.get("_empreinte") != snap["empreinte"]:
        b = storyboard(snap); b["_empreinte"] = snap["empreinte"]; save("storyboard.json", b)

    for x in b.get("characterBible") or []:              # personnage inventé récurrent : une référence fixe, elle aussi
        cid = str(x.get("id", ""))
        n = sum(cid in s["presentCharacterIds"] for s in b["spreads"])
        if cid.startswith("invente_") and n >= 2 and x.get("visual_en"):
            progress(f"Référence : {x.get('name', cid)}")
            src = G.draw_invented({"id": cid, "type": "invente", "role": "personnage inventé", "nom": str(x.get("name") or cid),
                                   "desc": x["visual_en"]})
            portraits[cid] = Path(folder) / f"portrait_{cid}.png"; shutil.copy(src, portraits[cid])
            rapport_refs[cid] = {"fichier": portraits[cid].name, "empreinte": fsha(portraits[cid]), "invente": True, "bloquants": [], "mineurs": []}
    save("references.json", rapport_refs)
    quality_cover = G._m("q_main", G.IMAGE_QUALITY); quality = G._m("q_scene", G.SCENE_QUALITY)
    etat("illustrating", "Couverture", 22)
    crefs = refs_for(b["coverCharacterIds"], portraits, None, folder, "jour")
    ckey = cache_key(snap["empreinte"], b["coverBrief"], b["coverCharacterIds"], [fsha(f) for _, f in crefs], COVER_SIZE, quality_cover)
    cover = folder / f"couverture-{ckey}.png"
    if not cover.exists():
        prompt = cover_prompt(b, snap, crefs)
        (folder / "prompts").mkdir(exist_ok=True); (folder / "prompts" / f"{cover.stem}.txt").write_text(prompt, encoding="utf-8")
        image(prompt, crefs, cover, COVER_SIZE, quality_cover, f"prompts/{cover.stem}.txt")

    spreads = b["spreads"]
    etat("illustrating", "Panorama pilote (double page 1)", 28)
    results = {1: draw_spread(spreads[0], snap, b, portraits, cover, folder, quality)}
    if results[1][1]["bloquants"]:                    # le pilote ne passe pas : on n'engage pas les 8 autres
        save("controle.json", {"etat": "needs_review", "pilote": results[1][1], "references": rapport_refs})
        raise ProcedeError("Panorama pilote refusé après corrections : " + " ; ".join(results[1][1]["bloquants"]) +
                           " (relecture nécessaire avant de dépenser plus)")
    todo = [s for s in spreads[1:]] if essai != "apercu" else []
    done = [1]
    def one(s):
        r = draw_spread(s, snap, b, portraits, cover, folder, quality)
        done[0] += 1; progress(f"Panoramas {done[0]}/9", 28 + 7 * done[0])
        return s["id"], r
    with ThreadPoolExecutor(max_workers=G.WORKERS) as ex:
        for sid, r in [f.result() for f in [ex.submit(contextvars.copy_context().run, one, s) for s in todo]]:
            results[sid] = r

    etat("reviewing", "Contrôles", 92)
    pages = []
    for s in spreads:
        if s["id"] not in results:
            pages += [None, None]; continue
        path = results[s["id"]][0]
        for side, key in (("left", "leftText"), ("right", "rightText")):
            t = reading_theme(path, s, snap, side)
            pages.append({"text": s[key], "veil": t["veil"], "ink": t["ink"], "theme": t})
    titre = b["title"]
    lines = [x for x in b.get("coverTitleLines") or [] if str(x).strip()] or [titre]
    book = {"title": titre, "collection": "Mon Héros du Mois", "ageLabel": b.get("ageLabel") or "4–7 ans",
            "cover": cover.name, "coverTitle": {"lines": lines, "numero": int(snap["histoire"].get("numero") or 1), "serie": snap["serie"]},
            "cadeau": snap.get("cadeau"),
            "spreads": [results[s["id"]][0].name if s["id"] in results else None for s in spreads],
            "pages": pages, "backTitle": b["backTitle"], "backText": b["backText"],
            "backColor": "#171B3A" if (pages[14] or {}).get("veil", "#171B3A") != THEMES["clair"]["veil"] else "#163E49"}
    save("livre.json", book)

    etat("assembling", "Assemblage du PDF", 95)
    name = re.sub(r"[^\w\-]+", "-", titre, flags=re.U).strip("-")[:80] or "livre"
    if essai == "apercu":
        pdf = folder / "apercu.pdf"
        rep = M.render(book, pdf, base=folder, work=folder / "rendu", pages=[0, 1])
    else:
        pdf = folder / f"{name}.pdf"
        rep = M.render(book, pdf, base=folder, work=folder / "rendu")
    for i, sheet in enumerate(rep.get("planches", [])):          # planches contact visibles depuis l'admin
        shutil.copy(folder / "rendu" / sheet, folder / f"planche_contact_{i + 1}.jpg")
    bloquants = [f"double page {k} : {x}" for k, (_, r) in sorted(results.items()) for x in r["bloquants"]]
    bloquants += [f"référence {k} : {x}" for k, v in bloq_refs.items() for x in v]
    bloquants += rep.get("problemes_rendu", [])
    mineurs = [f"double page {k} : {x}" for k, (_, r) in sorted(results.items()) for x in r.get("mineurs", [])]
    impossibles = [f"double page {k} : contrôle visuel impossible ({r['controle_impossible']})" for k, (_, r) in results.items() if r.get("controle_impossible")]
    phase = "needs_review" if (bloquants or impossibles) else "ready"
    controle = {"etat": phase, "instantane": snap["empreinte"], "modele_image": model(), "tailles": {"panorama": PANO_SIZE, "couverture": COVER_SIZE},
                "references": rapport_refs, "storyboard": b.get("controle", []), "panoramas": {k: r for k, (_, r) in results.items()},
                "rendu": rep, "bloquants": bloquants, "mineurs": mineurs, "controles_impossibles": impossibles,
                "format": "lecture 210 × 210 mm (kit) : fichiers d'impression Lulu non générés"}
    save("controle.json", controle)
    job["phase"] = phase
    return {"pdf": pdf.name, "titre": titre, "controle": bloquants + impossibles, "mineurs": mineurs, "pages": rep.get("pages"), "phase": phase}


def demo(folder, progress):
    """Sans clé OpenAI : le livre de Noé du kit, assemblé par le même moteur (aucun appel payant)."""
    folder = Path(folder)
    progress("Mode démo : livre de Noé (kit), sans appel API", 30)
    book = json.loads((KIT / "noe-demo.json").read_text(encoding="utf-8"))
    rep = M.render(book, folder / "Noe-et-la-poussiere-d-etoiles.pdf", base=KIT, work=folder / "rendu")
    for i, sheet in enumerate(rep.get("planches", [])):
        shutil.copy(folder / "rendu" / sheet, folder / f"planche_contact_{i + 1}.jpg")
    return {"pdf": "Noe-et-la-poussiere-d-etoiles.pdf", "titre": book["title"], "controle": rep["problemes_rendu"],
            "mineurs": [], "pages": rep["pages"], "phase": "ready"}
