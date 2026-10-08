# -*- coding: utf-8 -*-
"""Cahier de coloriage personnalisé « Mon Héros du Mois » (Lulu, Lettre US 8,5 x 11 po, spirale, intérieur noir et blanc).

Même principe que les livres et le calendrier : mêmes avatars, mêmes portraits de référence (repris du cache s'ils sont déjà
payés), instantané immuable de la commande, budget borné AVANT tout appel (plafond BUDGET_COLORIAGE_USD, 5 $ max), un appel
par image, un contrôle visuel par image, aucune régénération automatique, « à relire » en cas d'écart.

Contenu : 30 pages à colorier choisies par le parent dans le catalogue (THEMES) + 4 pages « Dessine… » + une page
« Ce cahier appartient à » (prénom en lettres creuses, à colorier). Impression recto seul (le verso de chaque dessin reste
blanc : les feutres ne traversent pas sur le dessin suivant). Couverture en couleur, titre composé par code.
Les traits générés sont binarisés (noir pur sur blanc) : aucun gris à l'impression."""
import os, io, re, json, random, contextvars
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFilter, ImageOps

import generator as G
import budget as BU
import procede as P
import calendrier as C

ROOT = Path(__file__).parent
VERSION = "coloriage-2026-10-08-v1"
POD = os.getenv("LULU_COLO_POD", "0850X1100BWSTDCO060UW444MXX")    # Lettre US, N&B standard, spirale, papier 60# non couché
NB_PAGES = 30                                   # pages à colorier choisies par le parent
TRIM = (612.0, 792.0)                           # 8,5 x 11 po, portrait
BLEED = 9.0
PAGE = (TRIM[0] + 2 * BLEED, TRIM[1] + 2 * BLEED)            # 630 x 810 pt
K = C.K
PX = (round(PAGE[0] * K), round(PAGE[1] * K))                # 2625 x 3375 px
RELIURE = 50.0                                  # pt : spirale sur le bord gauche (marge intérieure)
IMG_SIZE = os.getenv("OPENAI_COLO_SIZE", "1024x1536")        # portrait 2:3 (taille standard du modèle)
COVER_SIZE = os.getenv("OPENAI_COLO_COVER_SIZE", "1024x1536")
PROMPT_MAX = 3600
PLAFOND = min(5.0, float(os.getenv("BUDGET_COLORIAGE_USD", "5")))    # 31 images : plafond propre au cahier (5 $ max)
NAVY, GOLD, CREAM = C.NAVY, C.GOLD, C.CREAM
STYLE_TRAIT = ROOT / "kit" / "style" / "coloriage-trait.jpg"      # rendu « page de coloriage » attendu (trait seul, aucun personnage à copier)
NOIR = (0, 0, 0)

CATEGORIES = [("aventures", "Aventures"), ("vie", "Ma vie"), ("fetes", "Fêtes et saisons"), ("metiers", "Métiers"),
              ("sports", "Sports et jeux"), ("animaux", "Animaux")]
# (clé, catégorie, emoji, titre — {p} = prénom, scène en anglais pour l'illustrateur)
_T = [
    ("chateau_sable", "aventures", "🏖️", "{p} construit son château de sable", "building a big sandcastle on the beach with a bucket and spade, shells, a friendly crab, waves and a sailboat"),
    ("astronaute", "aventures", "🚀", "{p}, astronaute", "floating in space in an astronaut suit next to a rocket, planets with rings, stars and a smiling moon"),
    ("pirates", "aventures", "🏴‍☠️", "{p} et le trésor des pirates", "a pirate adventure: opening a treasure chest full of coins on an island, a pirate ship, a parrot, palm trees"),
    ("dinosaures", "aventures", "🦕", "{p} chez les dinosaures", "meeting a friendly baby triceratops and a long-neck dinosaur among giant ferns and a small volcano"),
    ("chevalier", "aventures", "🏰", "{p} au château fort", "a knight adventure in front of a castle with towers and flags, a friendly little dragon"),
    ("sous_marin", "aventures", "🐠", "{p} au fond de la mer", "diving under the sea with a mask: fish, a turtle, an octopus, coral, seaweed and bubbles"),
    ("jungle", "aventures", "🌴", "{p} dans la jungle", "exploring the jungle: a monkey on a vine, a toucan, big leaves, a waterfall"),
    ("pole_nord", "aventures", "🐧", "{p} au pôle Nord", "at the North Pole with penguins, a polar bear cub, an igloo and snowflakes"),
    ("fees", "aventures", "🧚", "{p} au royaume des fées", "in a fairy garden with a unicorn, fairies with wings, giant mushrooms and flowers"),
    ("cirque", "aventures", "🎪", "{p} au cirque", "under a circus tent: juggling balls, a seal with a ball, a little clown car, bunting"),
    ("superheros", "aventures", "🦸", "{p}, super-héros", "flying above the city rooftops as a superhero with a cape, waving, buildings and clouds"),
    ("safari", "aventures", "🦒", "{p} en safari", "on a safari jeep ride with a giraffe, an elephant, a zebra and acacia trees"),
    ("montgolfiere", "aventures", "🎈", "{p} en montgolfière", "flying in a hot-air balloon basket over hills, a village and birds"),
    ("train", "aventures", "🚂", "{p} et le petit train", "driving a little steam train on a track through hills, tunnel and trees"),
    ("ferme", "vie", "🚜", "{p} à la ferme", "on a farm with a tractor, a cow, a pig, chickens and a barn"),
    ("ecole", "vie", "🎒", "{p} à l'école", "at school in the classroom with a schoolbag, a desk, books, pencils and a blackboard (blank)"),
    ("cuisine", "vie", "🧁", "{p} fait un gâteau", "baking a cake in the kitchen: a mixing bowl, whisk, eggs, flour, cupcakes"),
    ("bain", "vie", "🛁", "L'heure du bain de {p}", "bath time in a bathtub full of bubbles with a rubber duck and toys"),
    ("dodo", "vie", "🌙", "Bonne nuit, {p}", "going to bed under a duvet with the plush toy, a night light, a moon and stars through the window"),
    ("jardin", "vie", "🌻", "{p} au jardin", "gardening: watering sunflowers and vegetables with a watering can, a snail and a butterfly"),
    ("parc", "vie", "🛝", "{p} au parc", "playing at the playground: a slide, a swing, a sandbox and trees"),
    ("pique_nique", "vie", "🧺", "Le pique-nique de {p}", "a picnic on a checked blanket in a meadow with a basket, fruit and sandwiches"),
    ("lecture", "vie", "📚", "{p} lit une histoire", "reading a big picture book in a cosy armchair with cushions and a bookshelf"),
    ("musique", "vie", "🎸", "{p} fait de la musique", "playing music: a little guitar, a drum, a xylophone and musical notes"),
    ("peinture", "vie", "🎨", "{p}, petit artiste", "painting on an easel with a palette and brushes, paint pots"),
    ("deguisement", "vie", "🎭", "{p} se déguise", "dressing up with a crown, a cape and a magic wand in front of a mirror"),
    ("cabane", "vie", "🏕️", "La cabane de {p}", "a wooden treehouse with a rope ladder, a little flag and leaves"),
    ("voiture", "vie", "🚗", "{p} part en vacances", "driving a little car full of suitcases on a country road towards the sea"),
    ("anniversaire", "fetes", "🎂", "Joyeux anniversaire, {p} !", "a birthday party: a big cake with candles, balloons, garlands and presents"),
    ("noel", "fetes", "🎄", "Le Noël de {p}", "Christmas: decorating a Christmas tree with baubles and a star, presents underneath"),
    ("bonhomme_neige", "fetes", "⛄", "{p} et le bonhomme de neige", "building a snowman with a scarf and a carrot nose, snowflakes, a sledge"),
    ("halloween", "fetes", "🎃", "L'Halloween de {p}", "a gentle Halloween: costume, smiling carved pumpkins, a basket of sweets, a friendly bat"),
    ("paques", "fetes", "🐣", "{p} cherche les œufs de Pâques", "an Easter egg hunt in a garden with decorated eggs, a basket and a bunny"),
    ("automne", "fetes", "🍂", "{p} et les feuilles d'automne", "jumping in a pile of autumn leaves, a squirrel, acorns and mushrooms"),
    ("printemps", "fetes", "🌷", "Le printemps de {p}", "spring in a flowery meadow: tulips, butterflies, a bird nest with eggs"),
    ("pluie", "fetes", "☔", "{p} sous la pluie", "jumping in puddles with rain boots and an umbrella, raindrops and a rainbow"),
    ("galette", "fetes", "👑", "{p} tire les rois", "wearing a paper crown and sharing a galette des rois cake on a table"),
    ("aid", "fetes", "🌙", "La fête de l'Aïd de {p}", "an Eid celebration with lanterns, a table of pastries, garlands and a crescent moon"),
    ("diwali", "fetes", "🪔", "Le Diwali de {p}", "Diwali: lighting little oil lamps (diyas) and drawing a rangoli pattern"),
    ("hanoukka", "fetes", "🕎", "Le Hanoukka de {p}", "Hanukkah: a menorah with candles, a spinning dreidel and doughnuts"),
    ("nouvel_an_chinois", "fetes", "🐉", "{p} et le dragon du Nouvel An", "Lunar New Year: a friendly paper dragon dance, lanterns and red envelopes"),
    ("pompier", "metiers", "🚒", "{p}, pompier", "a firefighter with a helmet and hose next to a fire truck with a ladder"),
    ("docteur", "metiers", "🩺", "{p}, docteur", "playing doctor with a stethoscope, taking care of the plush toy, a medical kit"),
    ("veterinaire", "metiers", "🐾", "{p}, vétérinaire", "a vet looking after a puppy and a kitten with a bandage and a medical kit"),
    ("boulanger", "metiers", "🥖", "{p}, boulanger", "a baker with a chef hat in a bakery: baguettes, croissants and an oven"),
    ("pilote", "metiers", "✈️", "{p}, pilote d'avion", "a pilot waving from a small propeller plane above the clouds"),
    ("policier", "metiers", "🚓", "{p}, policier", "a police officer with a cap next to a little police car, directing traffic"),
    ("jardinier", "metiers", "🧑‍🌾", "{p}, jardinier", "a gardener pushing a wheelbarrow full of vegetables and flowers"),
    ("chef", "metiers", "👨‍🍳", "{p}, grand chef", "a chef with a tall hat cooking pancakes in a pan in a big kitchen"),
    ("archeologue", "metiers", "🦴", "{p}, chercheur de fossiles", "digging up dinosaur bones with a brush and a little shovel"),
    ("football", "sports", "⚽", "{p} marque un but", "kicking a football into a goal on a grass pitch"),
    ("danse", "sports", "🩰", "{p} danse", "dancing ballet in a tutu on a little stage with music notes"),
    ("velo", "sports", "🚲", "{p} fait du vélo", "riding a bicycle with a helmet on a path through the park"),
    ("piscine", "sports", "🏊", "{p} à la piscine", "swimming in a pool with armbands, a float and splashes"),
    ("ski", "sports", "⛷️", "{p} fait du ski", "skiing down a snowy slope with fir trees and mountains"),
    ("judo", "sports", "🥋", "{p} au judo", "doing judo in a kimono with a belt on a tatami mat"),
    ("basket", "sports", "🏀", "{p} joue au basket", "throwing a basketball into a hoop"),
    ("equitation", "sports", "🐴", "{p} à poney", "riding a pony in a meadow with a fence"),
    ("cerf_volant", "sports", "🪁", "{p} et son cerf-volant", "flying a kite on a windy hill with clouds"),
    ("trottinette", "sports", "🛴", "{p} en trottinette", "riding a scooter on the pavement past houses and trees"),
    ("chiots", "animaux", "🐶", "{p} et les chiots", "playing with a basket of puppies"),
    ("chatons", "animaux", "🐱", "{p} et les chatons", "playing with kittens and a ball of wool"),
    ("aquarium", "animaux", "🐟", "{p} et l'aquarium", "looking at an aquarium with fish, a little castle and bubbles"),
    ("papillons", "animaux", "🦋", "{p} et les papillons", "watching butterflies in a garden of flowers with a butterfly net"),
    ("zoo", "animaux", "🦁", "{p} au zoo", "at the zoo with a lion cub, a panda and a flamingo"),
    ("foret", "animaux", "🦊", "{p} dans la forêt", "in a forest with a fox, a hedgehog, an owl on a branch and mushrooms"),
    ("mare", "animaux", "🐸", "{p} au bord de la mare", "by a pond with frogs on lily pads, ducks and dragonflies"),
    ("abeilles", "animaux", "🐝", "{p} et les abeilles", "watching friendly bees around a beehive and flowers"),
]
THEMES = [{"cle": k, "cat": c, "emoji": e, "titre": t, "scene": s} for k, c, e, t, s in _T]
PAR_CLE = {t["cle"]: t for t in THEMES}
# sélection proposée d'office (variée : un peu de chaque catégorie)
PAR_DEFAUT = ["chateau_sable", "astronaute", "dinosaures", "pirates", "sous_marin", "fees", "superheros", "pole_nord", "safari", "montgolfiere",
              "ferme", "cuisine", "jardin", "parc", "dodo", "cabane", "anniversaire", "noel", "bonhomme_neige", "automne", "pluie",
              "pompier", "docteur", "pilote", "football", "velo", "piscine", "chiots", "foret", "papillons"]


def public():
    """Catalogue pour la page de création (titres avec « {p} » à remplacer par le prénom)."""
    return {"categories": [{"cle": k, "nom": n} for k, n in CATEGORIES], "themes": [{k: t[k] for k in ("cle", "cat", "emoji", "titre")} for t in THEMES],
            "par_defaut": PAR_DEFAUT, "nombre": NB_PAGES}


def choisir(cles, fetes=None):
    """30 pages : celles du parent (clés connues, sans doublon), complétées par la sélection par défaut."""
    out = [c for c in dict.fromkeys(cles or []) if c in PAR_CLE][:NB_PAGES]
    for c in PAR_DEFAUT + [t["cle"] for t in THEMES]:
        if len(out) >= NB_PAGES:
            break
        if c not in out:
            out.append(c)
    return out


def dessine_pages(snap):
    """Pages « Dessine… » (aucun appel IA) : elles personnalisent le cahier avec ses vrais compagnons."""
    d = next((p for p in snap["personnages"] if p["type"] == "doudou"), None)
    a = next((p for p in snap["personnages"] if p["type"] == "animal"), None)
    return [f"Dessine {d['nom']}, ton doudou !" if d else "Dessine ton jouet préféré !",
            "Dessine ta maison !",
            f"Dessine {a['nom']} !" if a else "Dessine l'animal de tes rêves !",
            "Dessine-toi en super-héros !"]


# ====================================================================== pages composées (300 dpi)
_p = C._p
_txt = C._txt


def _ft(kind, pt, poids=700):
    return C.ft(kind, pt, poids)


def binariser(path):
    """Trait noir pur sur blanc : niveaux de gris -> seuil (adouci) ; rapport sur la part de gris et d'aplats noirs."""
    im = Image.open(path).convert("L")
    im = ImageOps.autocontrast(im, cutoff=1)
    hist = im.histogram(); n = sum(hist)
    gris = sum(hist[60:200]) / n
    bw = im.filter(ImageFilter.GaussianBlur(0.8)).point(lambda v: 0 if v < 150 else 255)
    noir = bw.histogram()[0] / n
    return bw, {"gris": round(gris, 3), "noir": round(noir, 3)}


def _cadre_page(titre, num):
    """Page blanche titrée (marge de reliure à gauche), numéro en bas."""
    im = Image.new("L", PX, 255); d = ImageDraw.Draw(im)
    x0, x1 = BLEED + RELIURE, PAGE[0] - BLEED - 30
    taille = 24
    while taille > 15 and d.textlength(titre, font=_ft("titre", taille)) / K > (x1 - x0):
        taille -= 1
    _txt(d, ((x0 + x1) / 2, BLEED + 36), titre, _ft("titre", taille), 0, "ma")
    if num:
        _txt(d, ((x0 + x1) / 2, PAGE[1] - BLEED - 30), f"Mon Héros du Mois  ·  {num}", _ft("texte", 8, 700), 110, "ma")
    return im, d, x0, x1


def page_coloriage(trait, titre, num):
    im, d, x0, x1 = _cadre_page(titre, num)
    top, bas = BLEED + 80, PAGE[1] - BLEED - 52
    w, h = x1 - x0, bas - top
    t = trait.copy()
    t.thumbnail((_p(w), _p(h)), Image.LANCZOS)
    t = t.point(lambda v: 0 if v < 128 else 255)
    im.paste(t, (_p(x0 + (w - t.width / K) / 2), _p(top + (h - t.height / K) / 2)))
    return im


def _etoile(d, cx, cy, r):
    import math
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5; rr = r if k % 2 == 0 else r * .45
        pts.append((_p(cx + rr * math.cos(a)), _p(cy - rr * math.sin(a))))
    d.polygon(pts, outline=0, fill=255, width=_p(1.6))


def page_dessine(titre, num):
    im, d, x0, x1 = _cadre_page(titre, num)
    top, bas = BLEED + 80, PAGE[1] - BLEED - 52
    d.rounded_rectangle((_p(x0), _p(top), _p(x1), _p(bas)), radius=_p(16), outline=0, width=_p(2.2))
    for cx, cy in ((x0 + 22, top + 22), (x1 - 22, top + 22), (x0 + 22, bas - 22), (x1 - 22, bas - 22)):
        _etoile(d, cx, cy, 10)
    return im


def page_appartient(prenom):
    """« Ce cahier appartient à » + le prénom en lettres creuses, à colorier."""
    im = Image.new("L", PX, 255); d = ImageDraw.Draw(im)
    cx = (BLEED + RELIURE + PAGE[0] - BLEED - 30) / 2
    _txt(d, (cx, 250), "Ce cahier de coloriage appartient à", _ft("titre", 22), 0, "ma")
    taille = 96
    while taille > 40 and d.textlength(prenom, font=_ft("titre", taille)) / K > 470:
        taille -= 4
    d.text((_p(cx), _p(300)), prenom, font=_ft("titre", taille), fill=255, stroke_width=_p(2.4), stroke_fill=0, anchor="ma")
    for i, (x, y) in enumerate(((cx - 210, 520), (cx + 210, 540), (cx - 120, 610), (cx + 130, 620), (cx, 570))):
        _etoile(d, x, y, 16 if i < 4 else 24)
    _txt(d, (cx, PAGE[1] - BLEED - 60), "Mon Héros du Mois", _ft("texte", 9, 800), 110, "ma")
    return im


def page_couverture(cover, prenom):
    """1re de couverture (couleur) : illustration, PRÉNOM doré, « Mon cahier de coloriage », pastille « À colorier »."""
    im = C._cover_fit(Image.open(cover), PX).convert("RGBA")
    voile = Image.new("L", PX, 0); dv = ImageDraw.Draw(voile)
    for yy in range(int(PX[1] * .42)):
        dv.line((0, yy, PX[0], yy), fill=int(200 * (1 - yy / (PX[1] * .42)) ** 1.3))
    im = Image.composite(Image.new("RGBA", PX, (14, 18, 48, 255)), im, voile)
    nom = prenom.upper(); taille = 84
    while taille > 40 and ImageDraw.Draw(im).textlength(nom, font=_ft("titre", taille)) / K > 470:
        taille -= 2
    cx = (BLEED + RELIURE + PAGE[0] - BLEED) / 2
    L = [(BLEED + 52, nom, _ft("titre", taille), GOLD), (BLEED + 60 + taille * 1.1, "Mon cahier de coloriage", _ft("titre", 28), CREAM),
         (BLEED + 100 + taille * 1.1, "30 dessins à colorier, rien qu'à toi", _ft("texte", 13, 700), CREAM)]
    om = Image.new("RGBA", PX, (0, 0, 0, 0)); do = ImageDraw.Draw(om)
    for y, t, f, c in L:
        do.text((_p(cx), _p(y + 2)), t, font=f, fill=(0, 0, 0, 200), anchor="ma")
    im = Image.alpha_composite(im, om.filter(ImageFilter.GaussianBlur(_p(2.2))))
    d = ImageDraw.Draw(im)
    for y, t, f, c in L:
        _txt(d, (cx, y), t, f, c, "ma")
    r, bx, by = 60, PAGE[0] - BLEED - 90, PAGE[1] - BLEED - 90
    d.ellipse((_p(bx - r), _p(by - r), _p(bx + r), _p(by + r)), fill=(255, 255, 255, 240), outline=NAVY, width=_p(2.4))
    _txt(d, (bx, by - 30), "À", _ft("titre", 20), NAVY, "ma"); _txt(d, (bx, by - 6), "COLORIER", _ft("texte", 14, 900), NAVY, "ma")
    _txt(d, (PAGE[0] / 2, PAGE[1] - BLEED - 26), "M O N   H É R O S   D U   M O I S", _ft("texte", 9, 800), CREAM, "ma")
    return im.convert("RGB")


def page_quatrieme(traits, prenom, cadeau=None):
    """4e de couverture : quelques pages du cahier en vignettes, le titre, le petit mot si c'est un cadeau."""
    im = Image.new("RGB", PX, (251, 245, 234)); d = ImageDraw.Draw(im)
    cx = PAGE[0] / 2
    _txt(d, (cx, BLEED + 60), f"Le cahier de coloriage de {prenom}", _ft("titre", 24), NAVY, "ma")
    if cadeau and cadeau.get("de"):
        t = (f"« {cadeau['message']} » " if cadeau.get("message") else "") + f"Offert par {cadeau['de']}"
        for i, l in enumerate(C._wrap(d, t, _ft("texte", 10, 600), _p(460))[:2]):
            _txt(d, (cx, BLEED + 98 + i * 14), l, _ft("texte", 10, 600), (90, 95, 130), "ma")
    cols, tw, gap = 3, 140.0, 14.0
    th = tw * 1.5; gx = cx - (cols * tw + (cols - 1) * gap) / 2; gy = BLEED + 150
    for k, t in enumerate(traits[:6]):
        x, y = gx + (k % cols) * (tw + gap), gy + (k // cols) * (th + gap)
        v = t.convert("RGB").copy(); v.thumbnail((_p(tw), _p(th)))
        fond = Image.new("RGB", (_p(tw), _p(th)), "white"); fond.paste(v, ((fond.width - v.width) // 2, (fond.height - v.height) // 2))
        im.paste(fond, (_p(x), _p(y)))
        d.rectangle((_p(x), _p(y), _p(x + tw), _p(y + th)), outline=(200, 190, 170), width=_p(.8))
    _txt(d, (cx, PAGE[1] - BLEED - 60), "Mon Héros du Mois  ·  des pages à colorier rien que pour lui", _ft("texte", 9, 700), C.GOLD_D, "ma")
    return im


def pdf(pages, out, size):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(str(out), pagesize=size, pageCompression=1)
    c.setTitle("Cahier de coloriage"); c.setAuthor("Mon Héros du Mois")
    for p in pages:
        if p.mode == "L":
            b = io.BytesIO(); p.convert("1").save(b, "PNG"); b.seek(0)          # noir et blanc pur : léger et net
        else:
            b = C._jpeg(p)
        c.drawImage(ImageReader(b), 0, 0, size[0], size[1]); c.showPage()
    c.save()


def dimensions_couverture(pages):
    import lulu
    if lulu.configured():
        w, h = lulu.cover_dimensions(pages, pod=POD)
        return {"largeur": w, "hauteur": h, "source": "API Lulu cover-dimensions (coloriage)", "confirme": True}
    return None


def fichiers_valides():
    f = BU.DATA / "lulu_coloriage_valide.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("pod") == POD
    except (OSError, ValueError):
        return os.getenv("COLORIAGE_FICHIERS_VALIDES") == "1"


def couverture_impression(folder, dims=None):
    """Fichier couverture Lulu aux dimensions données par Lulu : planche 4e | 1re si elle est deux fois plus large qu'une page."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    folder = Path(folder)
    couv, dos = Image.open(folder / "page_couverture.jpg"), Image.open(folder / "page_quatrieme.jpg")
    if dims is None:
        dims = {"largeur": PAGE[0], "hauteur": PAGE[1], "source": "maquette : une page 8,5 x 11 po + fond perdu", "confirme": False}
    W, H = dims["largeur"], dims["hauteur"]
    c = canvas.Canvas(str(folder / "impression_couverture.pdf"), pagesize=(W, H)); c.setTitle("Cahier de coloriage – couverture")
    planche = W >= 1.5 * PAGE[0]
    if planche:
        c.drawImage(ImageReader(C._jpeg(C._cover_fit(dos, (_p(W / 2), _p(H))))), 0, 0, W / 2, H)
        c.drawImage(ImageReader(C._jpeg(C._cover_fit(couv, (_p(W / 2), _p(H))))), W / 2, 0, W / 2, H)
    else:
        c.drawImage(ImageReader(C._jpeg(C._cover_fit(couv, (_p(W), _p(H))))), 0, 0, W, H)
    c.showPage(); c.save()
    probs = []
    if not dims.get("confirme"):
        probs.append("Dimensions de la couverture non confirmées : clés Lulu absentes (maquette, pas prête à imprimer).")
    if not fichiers_valides():
        probs.append("Fichiers du cahier de coloriage pas encore validés par Lulu : dans l'admin, « Vérifier les fichiers chez Lulu » "
                     "(une fois suffit pour tous les cahiers).")
    return {"largeur": round(W, 2), "hauteur": round(H, 2), "planche": planche, "source": dims["source"], "dos": 0.0,
            "marge": BLEED, "numero": None, "pret_a_imprimer": not probs, "problemes": probs}


# ====================================================================== aperçus (maquettes, aucun appel IA)
def _beton(w, h):
    b = Image.effect_noise((w, h), 40).convert("RGB")
    b = Image.blend(Image.new("RGB", (w, h), (166, 166, 164)), b, .22).filter(ImageFilter.GaussianBlur(1.2))
    n2 = Image.effect_noise((max(1, w // 8), max(1, h // 8)), 60).convert("L").resize((w, h), Image.BICUBIC)
    return Image.blend(b, Image.merge("RGB", (n2, n2, n2)), .10)


def _pose(fond, obj, x, y, o=24, bl=26):
    m = Image.new("L", fond.size, 0); m.paste(150, (x + o, y + o, x + o + obj.width, y + o + obj.height))
    fond = Image.composite(Image.new("RGB", fond.size, (60, 60, 60)), fond, m.filter(ImageFilter.GaussianBlur(bl)))
    fond.paste(obj, (x, y)); return fond


def _spirale(d, x, y0, y1, n=34):
    for k in range(n):
        y = y0 + 20 + k * (y1 - y0 - 40) / (n - 1)
        d.ellipse((x - 2, y - 4, x + 22, y + 4), fill=(30, 30, 30))
        d.rounded_rectangle((x - 20, y - 7, x + 20, y + 1), radius=4, fill=(70, 70, 75)); d.line((x - 16, y - 4, x + 16, y - 4), fill=(190, 190, 195), width=2)


def maquette_fermee(couv, dst):
    c = C._rogne(couv); c = c.resize((900, int(900 * c.height / c.width)), Image.LANCZOS)
    B = _pose(_beton(1500, 1500), c, 320, (1500 - c.height) // 2)
    _spirale(ImageDraw.Draw(B), 320, (1500 - c.height) // 2, (1500 + c.height) // 2)
    B.save(dst, quality=88); return Path(dst)


def maquette_ouverte(gauche, droite, dst):
    W = 850
    g = C._rogne(gauche).convert("RGB").resize((W, int(W * 810 / 630)), Image.LANCZOS)
    r = C._rogne(droite).convert("RGB").resize(g.size, Image.LANCZOS)
    B = _beton(2000, g.height + 300)
    B = _pose(B, g, 140, 150, 18, 22); B = _pose(B, r, 1010, 150, 18, 22)
    d = ImageDraw.Draw(B)
    for k in range(34):
        y = 170 + k * (g.height - 40) / 33
        d.ellipse((985, y - 5, 1035, y + 5), outline=(60, 60, 65), width=6)
    B.save(dst, quality=88); return Path(dst)


# ====================================================================== assemblage
def composer(folder, snap, cover, traits_src):
    """Toutes les pages et tous les fichiers à partir des images enregistrées : rien n'est généré ici."""
    folder = Path(folder)
    prenom = snap["prenom"]
    traits, mesures = [], {}
    for k, src in enumerate(traits_src):
        bw, m = binariser(src); traits.append(bw); mesures[k + 1] = m
    couv = page_couverture(cover, prenom); dos = page_quatrieme(traits, prenom, snap.get("cadeau"))
    couv.save(folder / "page_couverture.jpg", quality=92); dos.save(folder / "page_quatrieme.jpg", quality=92)
    blanc = Image.new("L", PX, 255)
    lecture, impression = [page_appartient(prenom)], [page_appartient(prenom), blanc]
    dess = dessine_pages(snap); num = 0
    pos_dessine = {7: 0, 15: 1, 23: 2, 30: 3}                  # une page « Dessine… » après les dessins 7, 15, 23 et 30
    for k, (t, pg) in enumerate(zip(traits, snap["pages"]), start=1):
        num += 1; p = page_coloriage(t, pg["titre"], num)
        lecture.append(p); impression += [p, blanc]                # recto seul : le verso reste blanc
        if k in pos_dessine:
            num += 1; q = page_dessine(dess[pos_dessine[k]], num)
            lecture.append(q); impression += [q, blanc]
    titre = f"Le cahier de coloriage de {prenom}"
    nom = re.sub(r"[^\w\-]+", "-", titre, flags=re.U).strip("-")[:80]
    pdf([couv] + lecture + [dos], folder / f"{nom}.pdf", PAGE)
    pdf(impression, folder / "impression_interieur.pdf", PAGE)
    pages = len(impression)
    try:
        dims = dimensions_couverture(pages)
    except Exception as e:
        print("gabarit couverture coloriage indisponible :", e); dims = None
    cv = couverture_impression(folder, dims)
    ap = folder / "apercus"; ap.mkdir(exist_ok=True)
    apercus = {"couverture": maquette_fermee(couv, ap / "couverture.jpg").name,
               "ouvert": maquette_ouverte(lecture[1], lecture[8] if len(lecture) > 8 else lecture[2], ap / "ouvert.jpg").name}
    c = C._rogne(couv); c.thumbnail((1100, 1100)); c.save(ap / "couverture.png"); apercus["couverture_png"] = "couverture.png"
    pl = Image.new("RGB", (6 * 300 + 70, 5 * 420 + 60), (251, 245, 234))
    for k, t in enumerate(traits[:30]):
        v = t.convert("RGB").copy(); v.thumbnail((290, 410)); pl.paste(v, (35 + (k % 6) * 300, 30 + (k // 6) * 420))
    pl.save(ap / "planche.jpg", quality=84); apercus["planche"] = "planche.jpg"
    pl.save(folder / "planche_contact_1.jpg", quality=84)
    return {"titre": titre, "pdf": f"{nom}.pdf", "interieur": {"pages": pages, "format_pt": list(PAGE)}, "couverture": cv,
            "apercus": apercus, "mesures": mesures, "pages": pages}


# ====================================================================== fabrication (IA)
SYSTEM_PAGE = """Tu contrôles une page de cahier de coloriage pour enfant (dessin au trait noir sur fond blanc).
Compare l'image à la fiche. BLOQUANTS (uniquement) :
- l'enfant attendu absent ou méconnaissable (coiffure, lunettes, vêtements très différents) ; un personnage récurrent en double ;
- un humain ou un animal de compagnie en trop (aucun parent, frère, sœur) ; la peluche dessinée comme un animal vivant ;
- de la couleur, des aplats gris ou des ombrages (ce doit être un dessin au trait à colorier) ;
- du texte, des lettres, des chiffres, un cadre, une signature ; une anatomie très fausse.
MINEURS : détails trop petits, traits un peu fins, décor chargé.
En cas de doute, ce n'est pas bloquant.
Réponds UNIQUEMENT en JSON : {"bloquants": ["consigne en anglais"], "mineurs": ["en français"]}"""


def snapshot(form, cfg):
    if cfg.get("problemes"):
        raise P.ProcedeError("Configuration incomplète, rien n'est généré : " + " ; ".join(cfg["problemes"]))
    c = form.get("coloriage") or {}
    prenom = cfg["personnages"][0]["nom"]
    pages = [{"rang": i + 1, "cle": k, "titre": PAR_CLE[k]["titre"].replace("{p}", prenom), "scene": PAR_CLE[k]["scene"]}
             for i, k in enumerate(choisir(c.get("pages")))]
    data = {"version": VERSION, "produit": "coloriage", "prenom": prenom, "age": str(form.get("age")),
            "personnages": [P.fiche(x) for x in cfg["personnages"]], "protagoniste": "heros", "pages": pages,
            "cadeau": {"de": form["cadeau_de"], "message": form.get("cadeau_message", "")} if form.get("cadeau_de") else None}
    data["empreinte"] = P.sha(data)
    data["empreinte_images"] = P.sha([VERSION, data["personnages"]])
    return data


def _ids(snap):
    return [p["id"] for p in snap["personnages"]]


def prompt_page(pg, snap, refs):
    ids = _ids(snap)
    noms = ", ".join(p["nom"].upper() for p in snap["personnages"])
    lines = ["Use case: coloring-book page. Create ONE portrait COLORING PAGE for children aged 3 to 8 (personalised colouring book).",
             "STYLE: pure black line art on a pure white background, like a printed colouring book. Thick, clean, uniform outlines "
             "(marker-like), every shape closed, large areas to colour, few tiny details. NO colour, NO grey, NO shading, NO hatching, "
             "NO gradients, no solid black areas except small pupils.",
             "CHARACTER BIBLE (identity only — draw them as uncoloured outlines):", P._bible_lines(ids, snap, {}),
             P.refs_text(refs, snap) + " Copy only the identity (face, hairstyle, glasses, clothes shapes, proportions); never the colours "
             "or the painting style.",
             f"SCENE: {pg['scene']}.",
             f"CHARACTERS: exactly these recurring characters ({noms}), each shown once; {snap['personnages'][0]['nom'].upper()} is the "
             "main subject, large, near the centre. No other human (no parent, sibling, grandparent); small animals or objects of the "
             "scene are fine.",
             "COMPOSITION: portrait page, the drawing fills the page but keeps a clean white margin: no line touches the edges.",
             "No writing, letters, numbers, title, signature, frame or border."]
    p = "\n".join(lines)
    if len(p.encode()) > PROMPT_MAX:
        lines[3] = lines[3][:900]; p = "\n".join(lines)
    return p


def prompt_couverture(snap, refs):
    ids = _ids(snap)
    style = P.PROMPT_IMAGE.split("CHARACTER BIBLE")[0].split("\n", 2)[2].strip()
    lines = ["Use case: illustration-story. Create ONE portrait full-bleed COVER illustration for a premium personalised children's "
             "COLOURING BOOK.", style[:1200], "CHARACTER BIBLE", P._bible_lines(ids, snap, {}), P.refs_text(refs, snap),
             "SCENE: the child happily colouring a big page with coloured pencils at a little table, the companions around; around them a "
             "playful scene where some elements are fully painted and others are still simple black outlines waiting to be coloured "
             "(stars, flowers, a rocket, a sun).",
             "Keep the upper third calm (soft sky, light background) for a title typeset separately, and the bottom-right corner simple.",
             "No writing, letters, numbers, title, captions, watermark or frame."]
    p = "\n".join(lines)
    return p if len(p.encode()) <= PROMPT_MAX + 1500 else p[:PROMPT_MAX + 1500]


def _key(snap, quoi, refs, size, quality):
    return P.sha([VERSION, P.model(), snap["empreinte_images"], quoi, [P.fsha(f) for _, f in refs], size, quality])[:12]


def cibles(snap, portraits, folder):
    folder = Path(folder)
    qc, qm = G._m("q_main", G.IMAGE_QUALITY), G._m("q_scene", G.SCENE_QUALITY)
    ids = _ids(snap)
    known = [x for x in ids if x in portraits]
    groupe = (("fiche de groupe, de gauche à droite : " + ", ".join(known), P.group_sheet(known, portraits, folder)) if len(known) > 1
              else (f"référence d'identité : {known[0]}", portraits[known[0]]))
    crefs = [groupe, ("référence de STYLE uniquement (Mila/Noé : ne pas copier ces personnages)", P.STYLE["couverture"])]
    out = [("couverture", None, crefs, folder / f"colo-couverture-{_key(snap, 'couverture', crefs, COVER_SIZE, qc)}.png", qc, COVER_SIZE)]
    style = ("STYLE reference only for the colouring-page look (line weight, clean outlines, level of detail): never copy its "
             "characters, outfits, crown or scene", STYLE_TRAIT)
    for pg in snap["pages"]:
        refs = [groupe, style]
        out.append((f"page {pg['rang']}", pg, refs, folder / f"colo-page-{pg['rang']:02d}-{_key(snap, [pg['cle'], pg['scene']], refs, IMG_SIZE, qm)}.png",
                    qm, IMG_SIZE))
    return out


def plan(cfg, folder, snap=None, portraits=None):
    folder = Path(folder)
    qc, qm, qp = G._m("q_main", G.IMAGE_QUALITY), G._m("q_scene", G.SCENE_QUALITY), G._m("q_scene", G.PORTRAIT_QUALITY)
    img = lambda e, n, q, size: {"type": "image", "etape": e, "modele": P.model(), "prompt_max": "x" * (PROMPT_MAX + (1500 if e == "couverture" else 0)),
                                 "refs": n, "size": size, "quality": q}
    ctl = lambda e, size: {"type": "chat", "etape": e, "modele": G.REVIEW_MODEL, "textes": [SYSTEM_PAGE, "x" * P.FICHE_MAX],
                           "max_tokens": P.REVIEW_MAX_TOKENS, "images": [P._vision_dims(size)]}
    out = []
    for c in cfg["personnages"]:
        if not G.portrait_en_cache(c):
            out.append(P._p_image(f"portrait {c['id']}", 3, "1024x1024", qp))
        if not G.portrait_en_cache(c) or not Path(str(G.portrait_path(c)) + ".controle.json").exists():
            out.append(P._p_controle(f"contrôle portrait {c['id']}", P.SYSTEM_REF, "1024x1024"))
    if snap is None or portraits is None:
        out += [img("couverture", 2, qc, COVER_SIZE), ctl("contrôle couverture", COVER_SIZE)]
        for k in range(NB_PAGES):
            out += [img(f"page {k + 1}", 2, qm, IMG_SIZE), ctl(f"contrôle page {k + 1}", IMG_SIZE)]
        return out
    for etape, _, refs, path, q, size in cibles(snap, portraits, folder):
        if not path.exists():
            out.append(img(etape, len(refs), q, size))
        if not path.with_suffix(".json").exists():
            out.append(ctl("contrôle " + etape, size))
    return out


def _dessiner(etape, pg, refs, path, q, size, snap, folder):
    rapport_p = path.with_suffix(".json")
    if path.exists() and rapport_p.exists():
        return json.loads(rapport_p.read_text(encoding="utf-8"))
    if not path.exists():
        prompt = prompt_couverture(snap, refs) if pg is None else prompt_page(pg, snap, refs)
        (Path(folder) / "prompts").mkdir(exist_ok=True)
        (Path(folder) / "prompts" / f"{path.stem}.txt").write_text(prompt, encoding="utf-8")
        P.image(prompt, refs, path, size, q, f"prompts/{path.stem}.txt", etape=etape)
    fiche = {"page": etape, "personnages_attendus": snap["personnages"], "scene": "couverture en couleur" if pg is None else pg["scene"]}
    v = P._vision(SYSTEM_PAGE if pg is not None else C.SYSTEM_MOIS, fiche, path)
    r = {"retenu": path.name, "bloquants": v["bloquants"], "mineurs": v.get("mineurs", []), "controle_impossible": v.get("controle_impossible")}
    if pg is not None:
        _, m = binariser(path)
        r["mesures"] = m
        if m["noir"] > 0.30:
            r["mineurs"].append(f"beaucoup d'aplats noirs ({int(m['noir'] * 100)} % de la page)")
    rapport_p.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def run(form, cfg, refs, folder, job, progress):
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        return P.resume_finalise(folder)
    with P._Verrou(folder):
        livre = P.livre_id(folder)
        BU.PLAFONDS[livre] = PLAFOND
        jeton = BU.LIVRE.set(livre)
        try:
            return _run(form, cfg, refs, folder, job, progress, livre)
        finally:
            BU.LIVRE.reset(jeton)


def _run(form, cfg, refs, folder, job, progress, livre):
    def etat(e, step, pct):
        job["phase"] = e; progress(step, pct)
    def save(name, data):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    etat("queued", "Instantané du cahier de coloriage", 2)
    dep = BU.depense(livre)
    if dep["incertain"] > 0 or dep["reserve"] > 0:
        raise P.ProcedeError("Appel(s) au résultat incertain pour ce cahier : règle-les dans l'admin avant toute reprise.")
    snap = snapshot(form, cfg)
    ecarts = P.check_snapshot(snap, form)
    if ecarts:
        raise P.ProcedeError("Les fiches ne correspondent pas à la commande : " + " ; ".join(ecarts))
    save("coloriage_instantane.json", snap)
    lignes, borne = BU.verifier_lancement(plan(cfg, folder), livre)
    save("budget.json", {"livre": livre, "plafond_usd": PLAFOND, "marge": BU.MARGE, "borne_lancement_usd": borne, "detail_lancement": lignes,
                         "deja_engage_usd": round(dep["total"], 4), "tarifs": BU.etat_tarifs()})
    etat("references", "Références des personnages", 5)
    portraits, rapport_refs = P.references(snap, cfg, refs, folder, lambda s: progress(s))
    save("references.json", rapport_refs)
    BU.verifier_lancement(plan(cfg, folder, snap, portraits), livre)
    t = cibles(snap, portraits, folder)
    etat("illustrating", "Couverture", 10)
    rapports = {"couverture": _dessiner(*t[0], snap, folder)}
    etat("illustrating", "Page pilote", 14)
    rapports["page 1"] = _dessiner(*t[1], snap, folder)
    if rapports["page 1"]["bloquants"]:
        save("controle.json", {"etat": "needs_review", "pilote": rapports["page 1"], "references": rapport_refs})
        raise P.ProcedeError("Page pilote non conforme : " + " ; ".join(rapports["page 1"]["bloquants"]) +
                             " (relecture humaine : aucune régénération automatique)")
    fait = [1]
    def un(c):
        r = _dessiner(*c, snap, folder)
        fait[0] += 1; progress(f"Pages {fait[0]}/{NB_PAGES}", 14 + int(78 * fait[0] / NB_PAGES))
        return c[0], r
    with ThreadPoolExecutor(max_workers=G.WORKERS) as ex:
        futs = [ex.submit(contextvars.copy_context().run, un, c) for c in t[2:]]
        errs = []
        for f in futs:
            try:
                k, r = f.result(); rapports[k] = r
            except Exception as e:
                errs.append(e)
        if errs:
            raise errs[0]
    etat("assembling", "Mise en page et PDF", 94)
    fab = composer(folder, snap, t[0][3], [c[3] for c in t[1:]])
    return conclure(folder, snap, fab, rapports, rapport_refs, livre, job)


def conclure(folder, snap, fab, rapports, rapport_refs, livre, job):
    folder = Path(folder)
    bloquants = [f"{k} : {x}" for k, r in rapports.items() for x in r["bloquants"]]
    bloquants += [f"référence {k} : {x}" for k, v in rapport_refs.items() for x in v.get("bloquants", [])]
    impossibles = [f"{k} : contrôle visuel impossible ({r['controle_impossible']})" for k, r in rapports.items() if r.get("controle_impossible")]
    mineurs = [f"{k} : {x}" for k, r in rapports.items() for x in r.get("mineurs", [])]
    phase = "needs_review" if (bloquants or impossibles) else "ready"
    dep = BU.depense(livre) if livre else {"regle": 0}
    cout = round(dep["regle"], 4)
    info = {"produit": "coloriage", "titre": fab["titre"], "prenom": snap["prenom"], "pdf_lecture": fab["pdf"], "pages_impression": fab["pages"],
            "images": sorted(p.name for p in folder.glob("colo-*.png")), "apercus": fab["apercus"]}
    (folder / "coloriage.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    controle = {"etat": phase, "produit": "coloriage", "instantane": snap["empreinte"], "modele_image": P.model(), "references": rapport_refs,
                "images": rapports, "mesures": fab["mesures"], "bloquants": bloquants, "mineurs": mineurs, "controles_impossibles": impossibles,
                "fabrication": {"interieur": fab["interieur"], "couverture": fab["couverture"]}, "impression_bloquee": fab["couverture"]["problemes"],
                "cout_api_usd": cout, "budget": dep}
    (folder / "controle.json").write_text(json.dumps(controle, ensure_ascii=False, indent=1), encoding="utf-8")
    job["phase"] = phase
    res = {"pdf": fab["pdf"], "titre": fab["titre"], "controle": bloquants + impossibles, "mineurs": mineurs + fab["couverture"]["problemes"],
           "pages": fab["pages"], "phase": phase, "cout": cout}
    if phase == "ready" and livre:
        finaliser(folder, res)
    return res


def pages_impression(folder):
    try:
        return int(json.loads((Path(folder) / "coloriage.json").read_text(encoding="utf-8"))["pages_impression"])
    except (OSError, ValueError, KeyError):
        return 2 + 2 * (NB_PAGES + 4)


def finaliser(folder, res):
    import fabrication as F
    folder = Path(folder)
    info = json.loads((folder / "coloriage.json").read_text(encoding="utf-8"))
    fichiers = ([info["pdf_lecture"], "coloriage.json", "coloriage_instantane.json", "references.json", "controle.json", "budget.json",
                 "impression_interieur.pdf", "impression_couverture.pdf", "page_couverture.jpg", "page_quatrieme.jpg"]
                + info["images"] + [p.name for p in folder.glob("portrait_*.png")] + [f"apercus/{v}" for v in info["apercus"].values()])
    man = F.finaliser(folder, fichiers, {"produit": "coloriage", "titre": res["titre"], "pdf_lecture": info["pdf_lecture"], "pages": res["pages"],
                                         "mineurs": res["mineurs"], "cout_api_usd": res["cout"], "appels_api": BU.appels(P.livre_id(folder)),
                                         "apercus": info["apercus"], "volumeNumber": None})
    try:
        F.sauvegarder(folder, Path(os.getenv("SAUVEGARDE_DIR") or BU.DATA / "sauvegardes"))
    except Exception as e:
        print("sauvegarde du cahier impossible :", e)
    res["finalise"] = True
    return man


def finaliser_apres_relecture(folder):
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        return json.loads((folder / "final.json").read_text(encoding="utf-8"))
    info = json.loads((folder / "coloriage.json").read_text(encoding="utf-8"))
    ctl = json.loads((folder / "controle.json").read_text(encoding="utf-8"))
    if len([x for x in info["images"] if x.startswith("colo-page-")]) < NB_PAGES or not (folder / "impression_interieur.pdf").exists():
        raise P.ProcedeError("Cahier incomplet : rien à finaliser")
    res = {"titre": info["titre"], "mineurs": ctl.get("mineurs", []) + ctl.get("bloquants", []), "cout": ctl.get("cout_api_usd"),
           "pages": info["pages_impression"]}
    return finaliser(folder, res)


def recomposer(folder, form=None):
    """Admin : recompose les pages à partir des images enregistrées (aucun appel IA). Refusé pour un cahier finalisé."""
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        raise P.ProcedeError("Cahier finalisé : ses fichiers sont figés")
    snap = json.loads((folder / "coloriage_instantane.json").read_text(encoding="utf-8"))
    cov = sorted(folder.glob("colo-couverture-*.png"))
    pages = [sorted(folder.glob(f"colo-page-{k:02d}-*.png")) for k in range(1, NB_PAGES + 1)]
    if not cov or not all(pages):
        raise P.ProcedeError("Images du cahier incomplètes")
    return composer(folder, snap, cov[-1], [p[-1] for p in pages])


DEMO_PAGE = ROOT / "kit" / "coloriage_demo"


def demo(form, cfg, folder, job, progress):
    """Sans clé OpenAI : un cahier complet avec la page d'exemple, aucun appel payant."""
    folder = Path(folder)
    progress("Mode démo : cahier d'exemple, sans appel API", 30)
    snap = snapshot(form, cfg)
    (folder / "coloriage_instantane.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    src = sorted(DEMO_PAGE.glob("*.png"))
    traits = []
    for pg in snap["pages"]:
        dst = folder / f"colo-page-{pg['rang']:02d}-demo.png"
        Image.open(src[(pg["rang"] - 1) % len(src)]).save(dst); traits.append(dst)
    cov = folder / "colo-couverture-demo.png"
    Image.open(ROOT / "kit" / "calendrier_demo" / "mois-07.jpg").convert("RGB").save(cov)
    fab = composer(folder, snap, cov, traits)
    return conclure(folder, snap, fab, {"couverture": {"bloquants": [], "mineurs": []}}, {}, None, job)
