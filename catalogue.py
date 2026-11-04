# -*- coding: utf-8 -*-
"""Catalogue du configurateur « Créer son livre » : une seule source pour le parcours, la génération, la mise en page et l'admin.

Chaque rubrique est une liste d'options {cle, nom, …, actif}. L'admin peut renommer, masquer ou compléter une option : ses
réglages sont gardés dans DATA_DIR/catalogue.json et fusionnés ici (clé par clé). Les clés ne changent jamais (elles sont
enregistrées dans les projets et les commandes).

Règles tenues :
- aucun paramètre décoratif : chaque champ « pour_histoire » / « style_en » / « police » est réellement lu par la génération
  (procede.py) ou la mise en page (moteur_livre.py) ;
- seuls les styles ayant un aperçu validé et les langues réellement prises en charge sont proposés à la vente ;
- aucune promesse chiffrée (délai, nombre de clients) n'est écrite ici."""
import os, json, copy, threading
from pathlib import Path

DATA = Path(os.getenv("DATA_DIR") or Path(__file__).parent / "data")
FICHIER = DATA / "catalogue.json"
FONTS = Path(__file__).parent / "fonts" / "livre"
_lock = threading.Lock()

# ------------------------------------------------------------------ A. tranche d'âge du LECTEUR (pas celle des personnages)
AGES = [
    {"cle": "0-2", "nom": "0 à 2 ans", "emoji": "🍼", "mots": [8, 16], "phrases": "2 phrases très courtes (3 à 7 mots), sons et répétitions",
     "pour_histoire": "Livre pour un tout-petit (0 à 2 ans) lu par un adulte : une seule action très simple par page, mots du quotidien "
                      "(maman, dodo, câlin, ballon), répétitions et onomatopées, aucune intrigue complexe, aucun suspense ni danger.",
     "age_label": "0–2 ans"},
    {"cle": "3-5", "nom": "3 à 5 ans", "emoji": "🧸", "mots": [20, 32], "phrases": "3 ou 4 phrases courtes (6 à 12 mots)",
     "pour_histoire": "Livre pour un enfant de 3 à 5 ans : une aventure simple et rassurante, un seul problème, un vocabulaire de maternelle, "
                      "dialogues courts, émotions nommées simplement.", "age_label": "3–5 ans"},
    {"cle": "6-9", "nom": "6 à 9 ans", "emoji": "📘", "mots": [30, 44], "phrases": "4 ou 5 phrases (8 à 14 mots)",
     "pour_histoire": "Livre pour un enfant de 6 à 9 ans qui commence à lire seul : intrigue avec deux rebondissements, un peu d'humour, "
                      "vocabulaire riche mais accessible, dialogues vivants.", "age_label": "6–9 ans"},
    {"cle": "10+", "nom": "10 ans et plus", "emoji": "🎧", "mots": [38, 52], "phrases": "5 phrases (jusqu'à 18 mots)",
     "pour_histoire": "Livre pour un lecteur de 10 ans et plus : récit plus construit avec du suspense doux, des personnages nuancés, "
                      "un vocabulaire plus riche, de l'humour et une vraie progression ; ton jamais infantilisant.", "age_label": "10 ans et +"},
]

# ------------------------------------------------------------------ B / C. thèmes et sujets (dépendants du thème)
# sujet : univers = clé d'univers.py (décor des illustrations déjà calibré) OU decor_en (décor propre au sujet) ; theme = consigne de récit.
THEMES = [
    {"cle": "contes", "nom": "Contes de fées", "emoji": "🏰", "sujets": [
        {"cle": "chateau", "nom": "Château et chevaliers", "univers": "chateau", "theme": "Une quête de chevalier, toute en gentillesse"},
        {"cle": "fees", "nom": "Fées et licornes", "univers": "fees", "theme": "Aider le royaume des fées"},
        {"cle": "dragon", "nom": "Le dragon timide", "univers": "chateau", "theme": "Devenir ami avec un dragon timide qui ne crache que des bulles"},
        {"cle": "princesse", "nom": "Princesse ou prince du royaume", "univers": "chateau", "theme": "Une journée de princesse ou de prince où rien ne se passe comme prévu"},
        {"cle": "foret", "nom": "La forêt enchantée", "univers": "foret", "theme": "Retrouver le chemin de la forêt enchantée"},
    ]},
    {"cle": "aventure", "nom": "Aventure", "emoji": "🧭", "sujets": [
        {"cle": "pirates", "nom": "Pirates", "univers": "pirates", "theme": "Une aventure de pirates gentils"},
        {"cle": "espace", "nom": "Voyage dans l'espace", "univers": "espace", "theme": "Un voyage dans les étoiles"},
        {"cle": "tresor", "nom": "Chasse au trésor", "univers": "pirates", "theme": "Une chasse au trésor avec une carte et des devinettes"},
        {"cle": "exploration", "nom": "Exploration", "univers": "montagne", "theme": "Une grande exploration en montagne"},
        {"cle": "superheros", "nom": "Super-héros", "univers": "superheros", "theme": "Découvrir son super-pouvoir de gentillesse"},
        {"cle": "cirque", "nom": "Le cirque", "univers": "cirque", "theme": "Le grand spectacle du cirque des étoiles"},
    ]},
    {"cle": "mondes", "nom": "Mondes à découvrir", "emoji": "🌍", "sujets": [
        {"cle": "dinosaures", "nom": "Dinosaures", "univers": "dinosaure", "theme": "Une journée chez les dinosaures"},
        {"cle": "vikings", "nom": "Les Vikings", "decor_en": "a friendly Viking village by a fjord: wooden longhouses, a dragon-headed longship, "
                                                            "northern pines, wool and furs; palette of slate blue, pine green, warm wood and torch light",
         "theme": "Une aventure chez les Vikings (gentils explorateurs, jamais de combat)"},
        {"cle": "ocean", "nom": "L'océan", "univers": "mer", "theme": "Une plongée au fond de l'océan"},
        {"cle": "jungle", "nom": "La jungle", "univers": "jungle", "theme": "Une expédition dans la jungle"},
        {"cle": "savane", "nom": "La savane", "univers": "savane", "theme": "Un safari dans la grande savane"},
        {"cle": "pole", "nom": "Le pôle Nord", "univers": "pole", "theme": "Une aventure sur la banquise"},
        {"cle": "desert", "nom": "Le désert et l'oasis", "univers": "desert", "theme": "La traversée du désert jusqu'à l'oasis"},
        {"cle": "ferme", "nom": "La ferme", "univers": "ferme", "theme": "Une journée à la ferme"},
    ]},
    {"cle": "fetes", "nom": "Fêtes", "emoji": "🎉", "sujets": [
        {"cle": "noel", "nom": "Noël", "univers": "noel", "theme": "La magie de Noël"},
        {"cle": "anniversaire", "nom": "Anniversaire", "univers": "anniversaire", "theme": "Le jour de son anniversaire"},
        {"cle": "paques", "nom": "Pâques", "univers": "paques", "theme": "La chasse aux œufs de Pâques"},
        {"cle": "halloween", "nom": "Halloween", "univers": "halloween", "theme": "Une nuit d'Halloween drôle et jamais effrayante"},
        {"cle": "galette", "nom": "Galette des rois", "univers": "galette", "theme": "La galette des rois"},
        {"cle": "carnaval", "nom": "Carnaval", "univers": "carnaval", "theme": "Le défilé du carnaval"},
    ]},
    {"cle": "famille", "nom": "Famille", "emoji": "🏡", "sujets": [
        {"cle": "bebe", "nom": "L'arrivée d'un bébé", "decor_en": "a warm family home and a sunny park nearby: cosy rooms, a cradle, soft toys, garden flowers; palette of cream, sage, apricot and soft blue",
         "theme": "L'arrivée d'un bébé dans la famille : trouver sa place de grand"},
        {"cle": "petite_soeur", "nom": "Une petite sœur arrive", "decor_en": "a warm family home and a sunny park nearby: cosy rooms, a cradle, soft toys, garden flowers; palette of cream, sage, apricot and soft blue",
         "theme": "Bientôt une petite sœur : se préparer à devenir grand frère ou grande sœur"},
        {"cle": "petit_frere", "nom": "Un petit frère arrive", "decor_en": "a warm family home and a sunny park nearby: cosy rooms, a cradle, soft toys, garden flowers; palette of cream, sage, apricot and soft blue",
         "theme": "Bientôt un petit frère : se préparer à devenir grand frère ou grande sœur"},
        {"cle": "animal", "nom": "Un nouvel animal", "decor_en": "a cheerful family home with a garden: a new pet basket, toys, a lawn and flower beds; palette of fresh green, warm wood, sky blue",
         "theme": "Un nouvel animal à la maison : apprendre à s'en occuper"},
        {"cle": "demenagement", "nom": "Déménagement", "decor_en": "moving day: cardboard boxes, a small moving van, a new house with an empty bedroom, a new street with trees; palette of kraft brown, sky blue, leafy green",
         "theme": "Déménager et apprivoiser sa nouvelle maison"},
        {"cle": "vacances", "nom": "Vacances", "decor_en": "a sunny holiday seaside: beach, sandcastles, a striped parasol, a small harbour, ice cream stand; palette of turquoise, sand, coral and white",
         "theme": "Les plus belles vacances"},
        {"cle": "dormir_ailleurs", "nom": "Dormir chez quelqu'un", "decor_en": "a cosy bedroom in someone else's home at night: a nightlight, a different bed, photos on the wall, a window with stars; palette of navy, warm lamp light and soft pink",
         "theme": "Dormir pour la première fois chez quelqu'un d'autre"},
        {"cle": "mariage", "nom": "Un mariage", "decor_en": "a joyful outdoor wedding party: a garden with garlands, flower arches, a big cake, music; palette of ivory, blush pink, sage green and gold",
         "theme": "Le grand jour d'un mariage dans la famille"},
        {"cle": "rentree", "nom": "La rentrée", "decor_en": "a friendly primary school: a colourful classroom, a playground with a big tree, school bags; palette of primary colours softened, warm morning light",
         "theme": "Le premier jour d'école"},
    ]},
    {"cle": "educatif", "nom": "Éducatif", "emoji": "🔢", "sujets": [
        {"cle": "nombres", "nom": "Les nombres", "univers": "foret", "theme": "Apprendre à compter de 1 à 10 au fil de l'aventure (un nombre par page, à compter dans l'image)"},
        {"cle": "couleurs", "nom": "Les couleurs", "univers": "fees", "theme": "Retrouver les couleurs disparues, une couleur par page"},
        {"cle": "nature", "nom": "La nature et les saisons", "univers": "foret", "theme": "Découvrir la nature au fil des quatre saisons"},
        {"cle": "propre", "nom": "Devenir propre", "decor_en": "a cosy bright home: bathroom with a little potty, bedroom, garden; palette of mint, cream and sunny yellow",
         "theme": "Apprendre à aller sur le pot, sans honte et avec fierté"},
        {"cle": "dents", "nom": "Se brosser les dents", "decor_en": "a cheerful bathroom that turns into a tiny magical world of sparkling teeth and bubbles; palette of aqua, white and soft pink",
         "theme": "Le grand combat contre les miettes : se brosser les dents"},
        {"cle": "politesse", "nom": "Les mots magiques", "univers": "chateau", "theme": "Les mots magiques : bonjour, merci, s'il te plaît"},
    ]},
    {"cle": "emotions", "nom": "Émotions et sentiments", "emoji": "💛", "sujets": [
        {"cle": "peur_noir", "nom": "La peur du noir", "univers": "espace", "theme": "La peur du noir"},
        {"cle": "colere", "nom": "La colère", "univers": "montagne", "theme": "Apprivoiser sa colère"},
        {"cle": "confiance", "nom": "La confiance en soi", "univers": "superheros", "theme": "Avoir confiance en soi"},
        {"cle": "separation", "nom": "La séparation", "decor_en": "a gentle everyday world: home, school gate, a park, a window with a view of the sky; palette of soft blue, warm cream and rose",
         "theme": "Être séparé de quelqu'un qu'on aime, et savoir qu'on se retrouvera"},
        {"cle": "timidite", "nom": "La timidité", "univers": "cirque", "theme": "Oser malgré la timidité"},
        {"cle": "jalousie", "nom": "La jalousie", "univers": "foret", "theme": "Quand on est jaloux"},
    ]},
    {"cle": "activites", "nom": "Activités", "emoji": "⚽", "sujets": [
        {"cle": "football", "nom": "Le football", "decor_en": "a friendly village football pitch: green grass, small goals, cheering friends, a sunny sky; palette of grass green, white and warm sun",
         "theme": "Le grand match de football"},
        {"cle": "danse", "nom": "La danse", "decor_en": "a small dance studio and a stage with soft spotlights, ribbons and mirrors; palette of rose, lilac and warm gold",
         "theme": "Le premier spectacle de danse"},
        {"cle": "musique", "nom": "La musique", "univers": "cirque", "theme": "Monter un petit orchestre"},
        {"cle": "cuisine", "nom": "La cuisine", "decor_en": "a cosy family kitchen full of bowls, flour clouds, fruits and a warm oven glow; palette of cream, cherry red, butter yellow",
         "theme": "Préparer un gâteau extraordinaire"},
        {"cle": "jardin", "nom": "Le jardinage", "univers": "ferme", "theme": "Faire pousser son premier potager"},
        {"cle": "velo", "nom": "Le vélo", "decor_en": "a sunny park with paths, a little hill, trees and a pond; palette of fresh green, sky blue and warm sunlight",
         "theme": "Apprendre à faire du vélo sans les petites roues"},
    ]},
]

# ------------------------------------------------------------------ D. message central (guide le récit, sans morale lourde)
MESSAGES = [
    {"cle": "amitie", "nom": "Amitié", "emoji": "🤝"}, {"cle": "courage", "nom": "Courage", "emoji": "🛡️"},
    {"cle": "nature", "nom": "Prendre soin de la nature", "emoji": "🌱"}, {"cle": "amour", "nom": "Amour", "emoji": "💞"},
    {"cle": "perseverance", "nom": "Persévérance", "emoji": "✊"}, {"cle": "partage", "nom": "Partage", "emoji": "🍪"},
    {"cle": "honnetete", "nom": "Honnêteté", "emoji": "🌟"}, {"cle": "respect", "nom": "Respect", "emoji": "🙏"},
    {"cle": "inspire", "nom": "Laissez-vous inspirer", "emoji": "✨", "inspire": True},
]
CONSIGNE_MESSAGE = ("Valeur qui guide le récit : « {nom} ». Elle se lit dans les choix et les actions des personnages, "
                    "jamais dans une leçon : aucune morale énoncée, aucune phrase du type « il a compris que… ».")

# ------------------------------------------------------------------ E. styles d'illustration (même scène de démonstration pour tous)
SCENE_DEMO = ("A five-year-old girl with curly auburn hair, a yellow raincoat and red boots, and her small grey dog, discover a glowing "
              "lantern at the foot of an old oak tree that has a tiny round door in its trunk; golden autumn afternoon, falling leaves.")
STYLES = [
    {"cle": "gouache", "nom": "Gouache", "maison": True, "actif": True,
     "style_en": "premium richly textured hand-painted gouache with fine coloured-pencil craft, nuanced facial expressions, dimensional magical light, "
                 "detailed layered scenery, tactile surfaces and depth"},
    {"cle": "aquarelle", "nom": "Aquarelle", "actif": False,
     "style_en": "delicate transparent watercolour on textured paper, soft wet-on-wet blooms, light pencil underdrawing, airy pastel washes, white paper glowing through"},
    {"cle": "anim3d", "nom": "Animation 3D", "actif": False,
     "style_en": "polished 3D animated feature-film look, soft subsurface skin, rounded appealing shapes, cinematic warm lighting, gentle depth of field (original characters, no studio imitation)"},
    {"cle": "geometrique", "nom": "Géométrique", "actif": False,
     "style_en": "modern geometric picture-book illustration: simple bold shapes, flat colour planes with subtle grain, clean edges, graphic composition, soft mid-century palette"},
    {"cle": "pate", "nom": "Pâte à modeler", "actif": False,
     "style_en": "handmade clay stop-motion look: modelling-clay characters and sets with fingerprints and soft bevels, miniature handcrafted props, warm studio lighting"},
    {"cle": "autocollant", "nom": "Art autocollant", "actif": False,
     "style_en": "cheerful sticker art: bold clean outlines, white die-cut sticker borders around characters, glossy flat colours, playful layered sticker composition"},
    {"cle": "bd", "nom": "Bande dessinée", "actif": False,
     "style_en": "classic Franco-Belgian comic style: clear ink line, flat bright colours, expressive faces, dynamic poses (no speech bubbles, no text)"},
    {"cle": "anime", "nom": "Anime doux", "actif": False,
     "style_en": "soft hand-drawn Japanese animation style: gentle line art, painted pastoral backgrounds, big expressive eyes, soft cel shading, airy skies (original characters only)"},
    {"cle": "blocs", "nom": "Monde de blocs", "actif": False,
     "style_en": "voxel block-world style: everything built from small cubes, chunky pixel textures, bright playful colours, soft global lighting (no game branding)"},
    {"cle": "collage", "nom": "Collage", "actif": False,
     "style_en": "textured paper collage: cut and torn papers, fabric and newsprint textures, layered shapes with soft shadows, handmade craft feeling"},
]
DOSSIER_STYLES = DATA / "styles"          # aperçus générés depuis l'admin (même scène de démonstration pour chaque style)

# ------------------------------------------------------------------ F. polices (OFL, incorporables au PDF : fonts/livre/OFL-*.txt)
POLICES = [
    {"cle": "conte", "nom": "Conte classique", "fichier": "Lora", "taille": 14.8, "interligne": 21},
    {"cle": "douce", "nom": "Arrondie et douce", "fichier": "Nunito", "taille": 14.8, "interligne": 21},
    {"cle": "bulles", "nom": "Bulles amusantes", "fichier": "Fredoka", "taille": 14.8, "interligne": 21},
    {"cle": "poetique", "nom": "Fine et poétique", "fichier": "Quicksand", "taille": 15, "interligne": 21},
    {"cle": "geometrique", "nom": "Géométrique et aventure", "fichier": "Lexend", "taille": 14, "interligne": 21},
    {"cle": "manuscrite", "nom": "Manuscrite joyeuse", "fichier": "PatrickHand", "gras": "PatrickHand-Regular", "taille": 16.5, "interligne": 21},
    {"cle": "ecole", "nom": "Cahier d'école", "fichier": "Andika", "taille": 14.8, "interligne": 21},
    {"cle": "aventure", "nom": "Livre d'aventure", "fichier": "ZillaSlab", "taille": 15.5, "interligne": 21},
]
PHRASE_POLICE = "« Où es-tu, petit lutin ? » chuchota Zoé en éclairant la forêt. Ça y est : l'aventure commence déjà !"

# ------------------------------------------------------------------ G. cherche et trouve
CHERCHE = [
    {"cle": "coccinelle", "nom": "Une petite coccinelle", "emoji": "🐞", "en": "a tiny red ladybird with black spots"},
    {"cle": "souris", "nom": "Une petite souris", "emoji": "🐭", "en": "a tiny grey mouse with pink ears"},
    {"cle": "etoile", "nom": "Une étoile dorée", "emoji": "⭐", "en": "a small golden five-pointed star"},
    {"cle": "escargot", "nom": "Un escargot", "emoji": "🐌", "en": "a small snail with a spiral orange shell"},
    {"cle": "plume", "nom": "Une plume bleue", "emoji": "🪶", "en": "a small bright blue feather"},
    {"cle": "papillon", "nom": "Un papillon", "emoji": "🦋", "en": "a small yellow butterfly"},
]

# ------------------------------------------------------------------ H. langues (seulement celles réellement prises en charge)
LANGUES = [
    {"cle": "fr", "nom": "Français", "actif": True},
    # Prompts, relecture, contrôles et quatrième de couverture sont écrits pour le français : aucune autre langue n'est vendue tant
    # que la chaîne n'a pas été adaptée et testée (activer ici ne suffit pas).
]

# ------------------------------------------------------------------ I. personnages secondaires
TYPES_PERSONNAGES = {
    "personne": {"nom": "Personne", "relations": ["frère", "sœur", "maman", "papa", "grand-mère", "grand-père", "ami", "amie", "tante", "oncle", "cousin", "cousine", "autre proche"]},
    "animal": {"nom": "Animal", "relations": ["animal de compagnie"]},
    "objet": {"nom": "Objet", "relations": ["doudou", "jouet", "objet fétiche"]},
}
EVENEMENTS = ["Anniversaire", "Vacances", "Rencontre", "Souvenir familial", "Situation vécue", "Autre demande"]

# ------------------------------------------------------------------ limites (coûts et qualité des illustrations)
LIMITES = {
    "personnages_max": int(os.getenv("PERSONNAGES_MAX", "4")),            # personnages secondaires (en plus du héros)
    "proches_max": int(os.getenv("PROCHES_MAX", "2")),                    # personnes (adultes, amis) en plus des frères et sœurs
    "corrections_texte": int(os.getenv("CORRECTIONS_TEXTE", "5")),        # versions du texte après génération (sans IA, gratuites)
    "corrections_image": int(os.getenv("CORRECTIONS_IMAGE", "2")),        # demandes de retouche d'illustration incluses
    "photo_jours": int(os.getenv("PHOTO_JOURS", "30")),                   # conservation des photos après le livre prêt
    "brouillon_jours": int(os.getenv("BROUILLON_JOURS", "60")),
}


# ------------------------------------------------------------------ fusion avec les réglages de l'admin
def _surcharges():
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def enregistrer(rubrique, cle, champs):
    """Admin : modifie une option (nom, actif, texte…). Les clés et les listes internes ne sont jamais remplacées."""
    permis = {"nom", "actif", "emoji", "theme", "pour_histoire", "style_en", "en", "decor_en"}
    champs = {k: v for k, v in (champs or {}).items() if k in permis and isinstance(v, (str, bool))}
    with _lock:
        d = _surcharges()
        d.setdefault(rubrique, {}).setdefault(cle, {}).update({k: (v.strip()[:600] if isinstance(v, str) else v) for k, v in champs.items()})
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = FICHIER.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, FICHIER)


def _fusion(rubrique, liste):
    s = _surcharges().get(rubrique, {})
    out = []
    for x in copy.deepcopy(liste):
        x.update(s.get(x["cle"], {}))
        x.setdefault("actif", True)
        out.append(x)
    return out


def ages(): return _fusion("ages", AGES)
def messages(): return _fusion("messages", MESSAGES)
def cherche(): return _fusion("cherche", CHERCHE)
def polices(): return _fusion("polices", POLICES)
def langues(): return _fusion("langues", LANGUES)


def themes():
    out = _fusion("themes", THEMES)
    s = _surcharges().get("sujets", {})
    for t in out:
        for x in t["sujets"]:
            x.update(s.get(f"{t['cle']}/{x['cle']}", {}))
            x.setdefault("actif", True)
    return out


def apercu_style(cle):
    p = DOSSIER_STYLES / f"{cle}.webp"
    return p if p.exists() else None


def styles():
    out = _fusion("styles", STYLES)
    for x in out:
        x["apercu"] = bool(apercu_style(x["cle"]))
        x["vendable"] = bool(x.get("actif")) and (x["apercu"] or bool(x.get("maison")))
    return out


def par_cle(liste, cle):
    return next((x for x in liste if x["cle"] == cle), None)


def sujet(theme, sujet_cle):
    t = par_cle(themes(), theme)
    return (t, par_cle(t["sujets"], sujet_cle)) if t else (None, None)


def public():
    """Ce que voit le configurateur : seulement les options actives (styles : avec aperçu)."""
    return {"ages": [a for a in ages() if a["actif"]],
            "themes": [dict(t, sujets=[x for x in t["sujets"] if x["actif"]]) for t in themes() if t["actif"]],
            "messages": [m for m in messages() if m["actif"]],
            "styles": [{k: v for k, v in s.items() if k != "style_en"} for s in styles() if s["vendable"]],
            "polices": [{k: p[k] for k in ("cle", "nom", "fichier")} for p in polices() if p["actif"]],
            "phrase_police": PHRASE_POLICE,
            "cherche": [c for c in cherche() if c["actif"]],
            "langues": [l for l in langues() if l["actif"]],
            "types": TYPES_PERSONNAGES, "evenements": EVENEMENTS,
            "limites": {k: LIMITES[k] for k in ("personnages_max", "proches_max", "corrections_texte", "corrections_image", "photo_jours")}}


# ------------------------------------------------------------------ validation d'un projet (côté serveur)
def valider(o):
    """Vérifie les choix d'un projet contre le catalogue. Renvoie la liste des rubriques à revoir (dépendances comprises)."""
    a_revoir = []
    o = o or {}
    if not par_cle([a for a in ages() if a["actif"]], o.get("age_lecteur")): a_revoir.append("age")
    t, s = sujet(o.get("theme"), o.get("sujet"))
    if not t or not t["actif"]: a_revoir.append("theme")
    elif not s or not s["actif"]: a_revoir.append("sujet")
    if not par_cle([m for m in messages() if m["actif"]], o.get("message")): a_revoir.append("message")
    st = par_cle(styles(), o.get("style"))
    if not st or not st["vendable"]: a_revoir.append("style")
    if not par_cle([p for p in polices() if p["actif"]], o.get("police")): a_revoir.append("police")
    if o.get("cherche") not in (None, "", "non"):
        if o["cherche"] != "auto" and not par_cle([c for c in cherche() if c["actif"]], o["cherche"]): a_revoir.append("cherche")
    if not par_cle([l for l in langues() if l["actif"]], o.get("langue") or "fr"): a_revoir.append("langue")
    return a_revoir


def police_fichiers(cle):
    """(regular.ttf, bold.ttf) d'une police du catalogue, ou None (ancienne police du moteur)."""
    p = par_cle(POLICES, cle)
    if not p:
        return None
    r = FONTS / f"{p['fichier']}-Regular.ttf"
    b = FONTS / f"{p.get('gras') or p['fichier'] + '-Bold'}.ttf"
    return (r, b if b.exists() else r, p.get("taille", 14.8), p.get("interligne", 21)) if r.exists() else None
