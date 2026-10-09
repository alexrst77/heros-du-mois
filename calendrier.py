# -*- coding: utf-8 -*-
"""Calendrier mural personnalisé « Mon Héros du Mois » (Lulu, paysage 11 x 8,5 po, spirale, 12 mois, 26 pages).

Même chaîne que les livres, mêmes garde-fous :
- seules les données enregistrées à la commande servent (instantané + empreinte) ; mêmes avatars, mêmes portraits de référence
  (déjà payés si la famille a commandé des livres : ils sont repris du cache, sans nouvel appel) ;
- 13 illustrations SANS TEXTE (couverture + 12 mois), un appel chacune, un contrôle visuel chacune, aucune régénération
  automatique ; un écart -> « à relire » ; budget du calendrier borné AVANT tout appel (plafond BUDGET_CALENDRIER_USD, 4 $ max) ;
- tout le texte est composé par code : mois, jours (semaine du lundi), jours fériés du pays de livraison, fêtes des mères et
  des pères, fêtes choisies par la famille, anniversaire de l'enfant (avec son âge), dates de famille, couverture, quatrième.

Ordre des 26 pages (le calendrier ouvert montre l'image d'un mois au-dessus de la spirale et sa grille en dessous) :
1 couverture · 2 image du mois 1 · 3 grille du mois 1 · … · 24 image du mois 12 · 25 grille du mois 12 · 26 quatrième.
Zones laissées libres : reliure (haut des grilles et de la couverture, bas des images) et trou d'accroche (bas des grilles)."""
import os, io, re, json, time, shutil, calendar as CAL, datetime as DT, contextvars
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import generator as G
import budget as BU
import procede as P
import univers as U

ROOT = Path(__file__).parent
VERSION = "calendrier-2026-10-08-v1"
POD = os.getenv("LULU_CAL_POD", "1100X0850FCPRECO080CW444GXX")   # accepté par l'API Lulu (devis du 7/10/2026 : 26 pages)
PAGES = 26
TRIM = (792.0, 612.0)                       # 11 x 8,5 po
BLEED = 9.0                                 # 0,125 po
PAGE = (TRIM[0] + 2 * BLEED, TRIM[1] + 2 * BLEED)      # 810 x 630 pt
DPI = 300
K = DPI / 72
PX = (round(PAGE[0] * K), round(PAGE[1] * K))           # 3375 x 2625 px (cadre image du guide Lulu)
RELIURE = 44.0                               # pt depuis le bord du papier : spirale (trous à 0,25 po du bord fini)
ACCROCHE = 50.0                              # pt : trou d'accroche au milieu du bord bas des grilles
IMG_SIZE = os.getenv("OPENAI_CAL_SIZE", "1792x1392")   # rapport 1,287 ≈ cadre Lulu 1,286 ; multiples de 16
PROMPT_MAX = 4500                            # octets : borne de coût d'un prompt d'image du calendrier
PLAFOND = min(4.0, float(os.getenv("BUDGET_CALENDRIER_USD", "4")))   # 13 images : plafond propre au calendrier (4 $ max)

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
NAVY, NAVY_D = (31, 37, 87), (22, 27, 66)
GOLD, GOLD_D = (232, 194, 90), (196, 146, 44)
CREAM, PAPER = (255, 243, 214), (253, 250, 243)
MUTED, LINE = (112, 118, 154), (226, 219, 202)
ROSE, ANNIV_FOND = (240, 140, 150), (255, 236, 186)

FONT_TITRE = ROOT / "fonts" / "YoungSerif-Regular.ttf"
FONT_TEXTE = ROOT / "static" / "fonts" / "Nunito.woff"
_fonts = {}


def ft(kind, pt, poids=700):
    """Police à la taille donnée en points (rendu à 300 dpi). Nunito est variable : la graisse est réglée."""
    key = (kind, round(pt, 2), poids)
    if key not in _fonts:
        px = max(6, int(round(pt * K)))
        try:
            f = ImageFont.truetype(str(FONT_TITRE if kind == "titre" else FONT_TEXTE), px)
            if kind != "titre":
                try:
                    f.set_variation_by_axes([poids])
                except Exception:
                    pass
        except OSError:
            f = ImageFont.truetype(str(ROOT / "fonts" / ("DejaVuSerif.ttf" if kind == "titre" else "DejaVuSans-Bold.ttf")), px)
        _fonts[key] = f
    return _fonts[key]


# ====================================================================== 1. période et dates
def debut_par_defaut(today=None):
    """Janvier de l'année suivante dès septembre ; sinon le mois prochain."""
    d = today or DT.date.today()
    if d.month >= 9:
        return f"{d.year + 1}-01"
    return f"{d.year}-{d.month + 1:02d}"


def debuts_possibles(today=None, n=14):
    """Premiers mois proposés au parent : à partir du mois prochain (le calendrier doit arriver avant son 1er mois)."""
    d = today or DT.date.today()
    return [f"{d.year + (d.month - 1 + i) // 12}-{(d.month - 1 + i) % 12 + 1:02d}" for i in range(1, n + 1)]


def mois_du_calendrier(debut):
    y, m = (int(x) for x in debut.split("-"))
    return [(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1) for i in range(12)]


def libelle_annee(debut):
    ms = mois_du_calendrier(debut)
    return str(ms[0][0]) if ms[0][1] == 1 else f"{ms[0][0]}-{ms[-1][0]}"


def paques(y):
    """Dimanche de Pâques (calendrier grégorien, algorithme de Meeus)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return DT.date(y, mois, jour)


def dimanche(y, m, n):
    """n-ième dimanche du mois (n = -1 : le dernier)."""
    jours = [DT.date(y, m, d) for d in range(1, CAL.monthrange(y, m)[1] + 1) if DT.date(y, m, d).weekday() == 6]
    return jours[n if n < 0 else n - 1]


def jours_officiels(y, pays="FR"):
    """{date: [(texte, sorte)]} : jours fériés du pays de livraison, fêtes des mères et des pères, changements d'heure."""
    out = {}
    add = lambda d, t, k="ferie": out.setdefault(d, []).append((t, k))
    D, td, e = DT.date, DT.timedelta, paques(y)
    pays = (pays or "FR").upper()
    add(D(y, 1, 1), "Jour de l'an"); add(e + td(1), "Lundi de Pâques"); add(e + td(39), "Ascension")
    add(e + td(50), "Lundi de Pentecôte"); add(D(y, 12, 25), "Noël")
    if pays in ("FR", "MC"):
        add(D(y, 5, 1), "Fête du travail"); add(D(y, 8, 15), "Assomption"); add(D(y, 11, 1), "Toussaint")
    if pays == "FR":
        add(D(y, 5, 8), "Victoire 1945"); add(D(y, 7, 14), "Fête nationale"); add(D(y, 11, 11), "Armistice")
    if pays == "MC":
        add(D(y, 1, 27), "Sainte-Dévote"); add(D(y, 11, 19), "Fête du Prince"); add(D(y, 12, 8), "Immaculée Conception")
    if pays == "BE":
        add(D(y, 5, 1), "Fête du travail"); add(D(y, 7, 21), "Fête nationale"); add(D(y, 8, 15), "Assomption")
        add(D(y, 11, 1), "Toussaint"); add(D(y, 11, 11), "Armistice")
    if pays == "LU":
        add(D(y, 5, 1), "Fête du travail"); add(D(y, 5, 9), "Journée de l'Europe"); add(D(y, 6, 23), "Fête nationale")
        add(D(y, 8, 15), "Assomption"); add(D(y, 11, 1), "Toussaint"); add(D(y, 12, 26), "Saint-Étienne")
    if pays == "CH":
        add(e - td(2), "Vendredi saint"); add(D(y, 8, 1), "Fête nationale"); add(D(y, 12, 26), "Saint-Étienne")
    # fêtes des mères et des pères (non fériées)
    if pays in ("FR", "MC"):
        meres = dimanche(y, 5, -1)
        if meres == e + td(49):                     # le dernier dimanche de mai tombe à la Pentecôte : 1er dimanche de juin
            meres = dimanche(y, 6, 1)
        peres = dimanche(y, 6, 3)
    elif pays == "LU":
        meres, peres = dimanche(y, 5, 2), dimanche(y, 10, 1)
    elif pays == "CH":
        meres, peres = dimanche(y, 5, 2), dimanche(y, 6, 1)
    else:
        meres, peres = dimanche(y, 5, 2), dimanche(y, 6, 2)
    add(meres, "Fête des mères", "fete"); add(peres, "Fête des pères", "fete")
    add(dimanche(y, 3, -1), "Heure d'été", "info"); add(dimanche(y, 10, -1), "Heure d'hiver", "info")
    return out


LIBELLES_FETES = {"noel": "Noël", "halloween": "Halloween", "paques": "Pâques", "galette": "Galette des rois", "carnaval": "Mardi gras",
                  "ramadan": "Début du Ramadan", "aid": "Aïd el-Fitr", "nouvelan_chinois": "Nouvel An chinois",
                  "hanoukka": "Hanoukka", "diwali": "Diwali"}


def age_au(anniv_date, age, commande):
    """Âge fêté ce jour-là : l'âge donné à la commande + les anniversaires passés depuis."""
    n = 0
    for y in range(commande.year, anniv_date.year + 1):
        try:
            d = DT.date(y, anniv_date.month, anniv_date.day)
        except ValueError:
            d = DT.date(y, 2, 28)
        if commande < d <= anniv_date:
            n += 1
    return int(age) + n


def evenements(y, m, snap):
    """{jour: [(texte, sorte)]} du mois : sorte = anniv | perso | ferie | fete | info, dans cet ordre de priorité."""
    out = {}
    add = lambda d, t, k: out.setdefault(d, []).append((t, k)) if (d.year, d.month) == (y, m) else None
    for d, l in jours_officiels(y, snap.get("pays")).items():
        for t, k in l:
            add(d, t, k)
    deja = {(d, t) for d, l in out.items() for t, _ in l}
    for cle in [c for c in (snap.get("fetes") or "").split(",") if c in LIBELLES_FETES]:
        for d in U.dates_fete(cle, annees=[y]):
            if d.month == m and (d, LIBELLES_FETES[cle]) not in deja:
                add(d, LIBELLES_FETES[cle], "fete")
    commande = DT.date.fromisoformat(snap.get("commande_le") or DT.date.today().isoformat())
    a = snap.get("anniversaire") or ""
    if re.match(r"^\d\d-\d\d$", a) and int(a[:2]) == m:
        jour = min(int(a[3:]), CAL.monthrange(y, m)[1])
        d = DT.date(y, m, jour)
        try:
            age = (d.year - int(snap["naissance"])) if str(snap.get("naissance") or "").isdigit() else age_au(d, snap.get("age") or 5, commande)
            add(d, f"{snap['prenom']} a {age} ans !", "anniv")
        except (ValueError, TypeError):
            add(d, f"Anniversaire de {snap['prenom']}", "anniv")
    for x in snap.get("dates") or []:
        try:
            mm, jj = (int(v) for v in x["date"].split("-"))
            if mm == m:
                add(DT.date(y, m, min(jj, CAL.monthrange(y, m)[1])), x["texte"], "perso")
        except (ValueError, KeyError, AttributeError):
            pass
    rang = {"anniv": 0, "perso": 1, "ferie": 2, "fete": 3, "info": 4}
    return {d.day: sorted(l, key=lambda t: rang.get(t[1], 9)) for d, l in out.items()}


def nettoyer_dates(dates):
    """Dates de famille saisies par le parent : jour et mois valides, texte court, 15 au plus."""
    out = []
    for x in (dates or [])[:15]:
        if not isinstance(x, dict):
            continue
        t = re.sub(r"\s+", " ", str(x.get("texte") or "")).strip()[:26]
        d = str(x.get("date") or "").strip()
        m = re.match(r"^(\d{1,2})-(\d{1,2})$", d)
        if not t or not m:
            continue
        mm, jj = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= jj <= CAL.monthrange(2028, mm)[1]:
            out.append({"date": f"{mm:02d}-{jj:02d}", "texte": t})
    return out


# ====================================================================== 2. scènes des mois (sans texte, mêmes personnages)
SCENES = {
    1: ("La neige", "a snowy winter morning in a village garden: building a big snowman with a scarf and a carrot nose, snowflakes falling, frosted pine trees, a wooden sledge", "jour"),
    2: ("Mardi gras", "a joyful carnival day in a little town square: colourful costumes and paper masks, confetti and streamers, a plate of golden crêpes on a café table", "jour"),
    3: ("Le jardin se réveille", "early spring in a vegetable garden: planting seedlings in fresh earth, first daffodils and crocuses, a small watering can, a ladybird, blossoming fruit tree", "jour"),
    4: ("Les flaques d'avril", "a spring shower in the countryside: jumping in puddles in red rain boots under a red umbrella, cherry trees in blossom, a rainbow over the hills", "jour"),
    5: ("Le cerf-volant", "a windy May afternoon flying a colourful kite over a meadow full of poppies and wildflowers, butterflies, small white clouds", "jour"),
    6: ("Le pique-nique", "a picnic in a sunny meadow by a little river: a red gingham blanket, a basket of strawberries and cherries, curious wild bunnies, warm golden light", "soir"),
    7: ("La plage", "a sunny beach day: building a big sandcastle decorated with shells and starfish, gentle turquoise waves, sailboats, a friendly little crab, a striped parasol", "jour"),
    8: ("Une nuit d'été", "a summer night camping in a meadow: a small tent glowing with a lantern, fireflies, a sky full of stars and the Milky Way, a hot chocolate mug", "nuit"),
    9: ("Le verger", "a late summer apple orchard: picking red apples into a wicker basket, a ladder against a tree, a red school bag hanging on a branch, warm light", "soir"),
    10: ("Les feuilles d'automne", "autumn in the forest: jumping into a big pile of red and golden leaves, pumpkins, mushrooms, a curious squirrel, soft misty light", "soir"),
    11: ("Le nid douillet", "a cosy rainy afternoon at home: a blanket fort with fairy lights, reading a big picture book together, mugs of hot chocolate, rain drops on the window", "intérieur"),
    12: ("L'hiver illuminé", "a snowy village at dusk with warm string lights: ice skating on a little frozen pond, snowflakes, glowing windows", "soir"),
}
SCENES_FETES = {          # (mois, fête choisie) -> scène de la fête, si la famille l'a cochée
    (4, "paques"): ("La chasse aux œufs", "an Easter egg hunt in a blooming garden: colourful painted eggs hidden in the grass and flowers, a wicker basket, spring blossoms, a curious rabbit", "jour"),
    (10, "halloween"): ("Halloween", "a gentle, not scary Halloween at dusk: fun costumes, smiling carved pumpkins with candles, a basket of sweets, autumn leaves, a friendly cat", "soir"),
    (11, "diwali"): ("Diwali", "a Diwali evening on a terrace: rows of glowing diyas, a colourful rangoli pattern, marigold garlands, sweets on a plate", "nuit"),
    (12, "noel"): ("La magie de Noël", "Christmas morning in a cosy living room: a decorated Christmas tree with warm lights, wrapped presents, stockings, snow falling outside the window", "intérieur"),
    (12, "hanoukka"): ("Les lumières de Hanoukka", "a cosy Hanukkah evening: a menorah with glowing candles in the window, a spinning dreidel, blue and silver decorations, snowy night outside", "intérieur"),
    (2, "nouvelan_chinois"): ("Le Nouvel An chinois", "a Lunar New Year celebration: red lanterns, a friendly dancing paper dragon in the street, red envelopes, plum blossoms", "soir"),
}
ANNIV = ("Son anniversaire", "a birthday party in a garden decorated with balloons and paper garlands: a big cake with lit candles on the table, wrapped presents, confetti", "jour")
COUVERTURE = ("a magical garden where the four seasons meet: spring blossoms on the left, summer sunflowers, autumn red leaves and a snowy winter village on the right, "
              "golden fireflies, a little stone fountain; the companions gathered around the child")


def scenes_du_calendrier(mois, fetes, anniversaire):
    """Une scène par mois. Le mois de l'anniversaire de l'enfant devient une fête d'anniversaire ; une fête cochée par la
    famille remplace la scène de saison de son mois (Pâques, Halloween, Diwali, Noël ou Hanoukka, Nouvel An chinois)."""
    cles = [c for c in (fetes or "").split(",") if c]
    am = int(anniversaire[:2]) if re.match(r"^\d\d-\d\d$", anniversaire or "") else None
    out = []
    for i, (y, m) in enumerate(mois):
        fr, en, light = SCENES[m]
        for (mm, cle), sc in SCENES_FETES.items():
            if mm == m and cle in cles:
                fr, en, light = sc
                break
        if am == m:
            fr, en, light = ANNIV
        out.append({"rang": i + 1, "annee": y, "mois": m, "titre": fr, "scene": en, "light": light})
    return out


# ====================================================================== 3. pages (300 dpi)
def _cover_fit(im, size):
    im = im.convert("RGB")
    w, h = im.size; W, H = size
    r = W / H
    if w / h > r:
        nw = int(h * r); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / r); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize(size, Image.LANCZOS)


def page_image(path):
    """Illustration du mois, à fond perdu, agrandie au cadre Lulu (3375 x 2625 px)."""
    im = _cover_fit(Image.open(path), PX)
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))


def _p(v):
    return int(round(v * K))


def _txt(d, xy, t, f, fill, anchor="la"):
    d.text((_p(xy[0]), _p(xy[1])), t, font=f, fill=fill, anchor=anchor)


def _wrap(d, t, f, w):
    words, lines, cur = t.split(), [], ""
    for wd in words:
        x = (cur + " " + wd).strip()
        if d.textlength(x, font=f) <= w or not cur:
            cur = x
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines


def _mini(d, x, y, an, mois):
    _txt(d, (x, y), MOIS[mois - 1].capitalize(), ft("texte", 8.5, 800), NAVY)
    fl = ft("texte", 6.2, 800); fd = ft("texte", 6.4, 600)
    for i, j in enumerate("LMMJVSD"):
        _txt(d, (x + i * 13 + 3, y + 15), j, fl, MUTED, "ma")
    for w, week in enumerate(CAL.Calendar(0).monthdayscalendar(an, mois)):
        for i, jour in enumerate(week):
            if jour:
                _txt(d, (x + i * 13 + 3, y + 26 + w * 9.5), str(jour), fd, GOLD_D if i >= 5 else NAVY, "ma")


def page_grille(an, mois, evts, prenom):
    """Grille du mois : titre, sous-titre au prénom, mini-mois voisins, semaine du lundi, jours spéciaux.
    Reliure en haut (rien au-dessus de RELIURE), trou d'accroche au milieu du bas (zone laissée vide)."""
    im = Image.new("RGB", PX, PAPER); d = ImageDraw.Draw(im)
    x0, x1 = BLEED + 40, PAGE[0] - BLEED - 40
    top = BLEED + RELIURE + 4
    titre = MOIS[mois - 1].capitalize()
    ftit = ft("titre", 50)
    _txt(d, (x0, top), titre, ftit, NAVY)
    lw = d.textlength(titre, font=ftit) / K
    _txt(d, (x0 + lw + 14, top + 26), str(an), ft("titre", 24), GOLD_D)
    _txt(d, (x0 + 2, top + 66), f"MON HÉROS DU MOIS  ·  LE CALENDRIER DE {prenom.upper()}", ft("texte", 9.5, 800), MUTED)
    pm, py = (mois - 1, an) if mois > 1 else (12, an - 1)
    nm, ny = (mois + 1, an) if mois < 12 else (1, an + 1)
    _mini(d, x1 - 218, top + 4, py, pm); _mini(d, x1 - 100, top + 4, ny, nm)
    gy0 = top + 92
    cw = (x1 - x0) / 7
    fj = ft("texte", 8.5, 800)
    for i, j in enumerate(JOURS):
        _txt(d, (x0 + i * cw + cw / 2, gy0), j.upper(), fj, GOLD_D if i >= 5 else MUTED, "ma")
    ry0 = gy0 + 17
    d.line((_p(x0), _p(ry0 - 3), _p(x1), _p(ry0 - 3)), fill=NAVY, width=_p(1.1))
    weeks = CAL.Calendar(0).monthdayscalendar(an, mois)
    bas = PAGE[1] - BLEED - ACCROCHE + 8
    rh = (bas - ry0) / len(weeks)
    fn, fnb = ft("texte", 17, 800), ft("texte", 16, 900)
    fl = ft("texte", 7.8, 800)
    for w, week in enumerate(weeks):
        y = ry0 + w * rh
        if w:
            d.line((_p(x0), _p(y), _p(x1), _p(y)), fill=LINE, width=_p(.7))
        for i, jour in enumerate(week):
            x = x0 + i * cw
            if i:
                d.line((_p(x), _p(y + 4), _p(x), _p(y + rh - 4)), fill=LINE, width=_p(.7))
            if not jour:
                continue
            ev = evts.get(jour, [])
            anniv = any(k == "anniv" for _, k in ev)
            ferie = any(k == "ferie" for _, k in ev)
            if anniv:
                d.rounded_rectangle((_p(x + 3), _p(y + 3), _p(x + cw - 3), _p(y + rh - 3)), radius=_p(7), fill=ANNIV_FOND)
                d.ellipse((_p(x + 6), _p(y + 5), _p(x + 30), _p(y + 29)), fill=GOLD)
                _txt(d, (x + 18, y + 17.5), str(jour), fnb, NAVY, "mm")
                cx, cy = x + cw - 18, y + 14                     # petit gâteau dessiné
                d.rounded_rectangle((_p(cx - 8), _p(cy), _p(cx + 8), _p(cy + 9)), radius=_p(2), fill=ROSE)
                d.rectangle((_p(cx - 8), _p(cy + 3), _p(cx + 8), _p(cy + 4.4)), fill=PAPER)
                d.rectangle((_p(cx - .7), _p(cy - 5), _p(cx + .7), _p(cy)), fill=NAVY)
                d.ellipse((_p(cx - 1.8), _p(cy - 8.6), _p(cx + 1.8), _p(cy - 4.4)), fill=(255, 170, 40))
            else:
                col = GOLD_D if (i >= 5 or ferie) else NAVY
                _txt(d, (x + 8, y + 5), str(jour), fn, col)
            # libellés : 2 au plus, 2 lignes chacun, au bas de la case
            lignes = []
            for t, k in ev[:2]:
                for l in _wrap(d, t, fl, _p(cw - 12))[:2]:
                    lignes.append((l, k))
            if len(ev) > 2:
                lignes[-1] = (lignes[-1][0] + f"  +{len(ev) - 2}", lignes[-1][1])
            lignes = lignes[-4:]
            ly = y + rh - 5 - 9.4 * len(lignes)
            for l, k in lignes:
                _txt(d, (x + 7, ly), l, fl, NAVY if k in ("anniv", "perso") else (GOLD_D if k == "ferie" else MUTED))
                ly += 9.4
    return im


def page_couverture(cover, prenom, annee):
    """1re de couverture : l'illustration et le titre composé par code (PRÉNOM, « Une année de merveilles », l'année),
    en capitales dorées comme sur la maquette de la marque. « Mon Héros du Mois » en bas. Reliure en haut."""
    im = _cover_fit(Image.open(cover), PX).convert("RGBA")
    voile = Image.new("L", PX, 0); dv = ImageDraw.Draw(voile)
    for yy in range(0, int(PX[1] * .5)):
        dv.line((0, yy, PX[0], yy), fill=int(175 * max(0.0, 1 - yy / (PX[1] * .48)) ** 1.5))
    for yy in range(int(PX[1] * .9), PX[1]):
        dv.line((0, yy, PX[0], yy), fill=int(120 * (yy - PX[1] * .9) / (PX[1] * .1)))
    im = Image.composite(Image.new("RGBA", PX, (14, 18, 48, 255)), im, voile)
    nom = prenom.upper()
    taille = 70
    while taille > 34 and ImageDraw.Draw(im).textlength(nom, font=ft("titre", taille)) / K > 520:
        taille -= 2
    y0 = BLEED + RELIURE + 10
    lignes = [(y0, nom, ft("titre", taille)), (y0 + taille * 1.08, "Une année de merveilles", ft("titre", 25)),
              (y0 + taille * 1.08 + 34, str(annee), ft("titre", 30))]
    ombre = Image.new("RGBA", PX, (0, 0, 0, 0)); do = ImageDraw.Draw(ombre)
    for y, t, f in lignes:
        do.text((_p(PAGE[0] / 2), _p(y + 2)), t, font=f, fill=(8, 10, 30, 210), anchor="ma")
    im = Image.alpha_composite(im, ombre.filter(ImageFilter.GaussianBlur(_p(2.4))))
    # dorure : dégradé crème -> or appliqué au texte
    masque = Image.new("L", PX, 0); dm = ImageDraw.Draw(masque)
    for y, t, f in lignes:
        dm.text((_p(PAGE[0] / 2), _p(y)), t, font=f, fill=255, anchor="ma")
    grad = Image.new("RGBA", PX); dg = ImageDraw.Draw(grad)
    for yy in range(PX[1] // 2):
        k = (yy % _p(taille * 1.1)) / _p(taille * 1.1)
        c = tuple(int(a + (b - a) * k) for a, b in zip((255, 246, 214), (226, 182, 86)))
        dg.line((0, yy, PX[0], yy), fill=c + (255,))
    im.paste(grad, (0, 0), masque)
    d = ImageDraw.Draw(im)
    yl = y0 + taille * 1.08 + 30
    for sens in (-1, 1):                                    # deux filets dorés autour de l'année
        x = PAGE[0] / 2 + sens * 48
        d.line((_p(x), _p(yl + 16), _p(x + sens * 70), _p(yl + 16)), fill=GOLD, width=_p(.9))
    _txt(d, (PAGE[0] / 2, PAGE[1] - BLEED - 34), "M O N   H É R O S   D U   M O I S", ft("texte", 8.5, 800), CREAM, "ma")
    return im.convert("RGB")


def page_quatrieme(mois_imgs, mois, prenom, annee, cadeau=None):
    """4e de couverture : les 12 illustrations en vignettes, le titre, le petit mot si c'est un cadeau."""
    im = Image.new("RGB", PX, NAVY_D); d = ImageDraw.Draw(im)
    y = BLEED + RELIURE + 12
    _txt(d, (PAGE[0] / 2, y), f"Le calendrier de {prenom}", ft("titre", 26), CREAM, "ma")
    _txt(d, (PAGE[0] / 2, y + 36), annee, ft("titre", 15), GOLD, "ma")
    if cadeau and cadeau.get("de"):
        t = (f"« {cadeau['message']} » " if cadeau.get("message") else "") + f"Offert par {cadeau['de']}"
        for i, l in enumerate(_wrap(d, t, ft("texte", 9, 600), _p(560))[:2]):
            _txt(d, (PAGE[0] / 2, y + 60 + i * 12), l, ft("texte", 9, 600), (220, 224, 245), "ma")
    gx0, gy0, cols, gap = 120.0, y + 92, 4, 10.0
    tw = (PAGE[0] - 2 * gx0 - (cols - 1) * gap) / cols; th = tw / (PAGE[0] / PAGE[1])
    for k, (src, (an, m)) in enumerate(zip(mois_imgs, mois)):
        cx, cy = gx0 + (k % cols) * (tw + gap), gy0 + (k // cols) * (th + 22)
        t = _cover_fit(Image.open(src), (_p(tw), _p(th)))
        im.paste(t, (_p(cx), _p(cy)))
        d.rectangle((_p(cx), _p(cy), _p(cx + tw), _p(cy + th)), outline=(70, 78, 140), width=_p(.6))
        _txt(d, (cx + tw / 2, cy + th + 4), f"{MOIS[m - 1].capitalize()} {an}", ft("texte", 7.5, 800), (200, 205, 235), "ma")
    _txt(d, (PAGE[0] / 2, PAGE[1] - BLEED - ACCROCHE - 6), "Mon Héros du Mois  ·  un calendrier illustré rien que pour lui", ft("texte", 8, 700), GOLD, "ma")
    return im


# ====================================================================== 4. PDF : impression (26 pages) et lecture
def _jpeg(im, q=90):
    b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=q, optimize=True); b.seek(0)
    return b


def pdf_impression(pages, out):
    """Intérieur Lulu : 26 pages de 810 x 630 pt (11 x 8,5 po + fond perdu 0,125 po), images à 300 dpi."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(str(out), pagesize=PAGE, pageCompression=1)
    c.setTitle("Calendrier – intérieur"); c.setAuthor("Mon Héros du Mois")
    for p in pages:
        c.drawImage(ImageReader(_jpeg(p)), 0, 0, PAGE[0], PAGE[1]); c.showPage()
    c.save()
    return {"pages": len(pages), "format_pt": list(PAGE), "fini_pt": list(TRIM), "fond_perdu_pt": BLEED}


def _rogne(p):
    b = _p(BLEED)
    return p.crop((b, b, p.width - b, p.height - b))


def pdf_lecture(couv, mois_pages, dos, out):
    """PDF de relecture : la couverture, puis chaque mois comme accroché au mur (image au-dessus de la spirale, grille dessous)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    W, H = TRIM
    c = canvas.Canvas(str(out), pagesize=(W, H))
    c.setTitle("Calendrier"); c.setAuthor("Mon Héros du Mois")
    def plein(im, w, h, y=0):
        t = _rogne(im); t.thumbnail((int(w * 2.2), int(h * 2.2)))
        c.drawImage(ImageReader(_jpeg(t, 86)), 0, y, w, h)
    plein(couv, W, H); c.showPage()
    for img, grille in mois_pages:
        c.setPageSize((W, 2 * H + 16))
        plein(img, W, H, H + 16); plein(grille, W, H, 0)
        c.setFillColorRGB(.36, .37, .42)
        for k in range(44):
            x = 20 + k * (W - 40) / 43
            c.roundRect(x - 2.2, H + 2, 1.6, 12, .8, fill=1, stroke=0); c.roundRect(x + 1, H + 2, 1.6, 12, .8, fill=1, stroke=0)
        c.showPage()
    c.setPageSize((W, H)); plein(dos, W, H); c.showPage()
    c.save()


def dimensions_couverture():
    """Gabarit du fichier couverture du calendrier donné par l'API Lulu (None sans clés : jamais d'épaisseur inventée)."""
    import lulu
    if lulu.configured():
        w, h = lulu.cover_dimensions(PAGES, pod=POD)
        return {"largeur": w, "hauteur": h, "source": "API Lulu cover-dimensions (calendrier)", "confirme": True}
    return None


def fichiers_valides():
    """Les fichiers du calendrier ont-ils été acceptés par l'outil de validation de Lulu ? (une fois pour toutes, par code produit)"""
    f = BU.DATA / "lulu_calendrier_valide.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("pod") == POD
    except (OSError, ValueError):
        return os.getenv("CALENDRIER_FICHIERS_VALIDES") == "1"


def couverture_impression(folder, dims=None):
    """Fichier couverture Lulu : aux dimensions données par Lulu. Une planche deux fois plus large qu'une page = 4e | 1re ;
    sinon la 1re seule. Sans gabarit confirmé : maquette marquée non prête."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    folder = Path(folder)
    couv, dos = Image.open(folder / "page_couverture.jpg"), Image.open(folder / "page_quatrieme.jpg")
    if dims is None:
        dims = {"largeur": PAGE[0], "hauteur": PAGE[1], "source": "maquette : une page 11 x 8,5 po + fond perdu", "confirme": False}
    W, H = dims["largeur"], dims["hauteur"]
    c = canvas.Canvas(str(folder / "impression_couverture.pdf"), pagesize=(W, H)); c.setTitle("Calendrier – couverture")
    planche = W >= 1.5 * PAGE[0]
    if planche:
        c.drawImage(ImageReader(_jpeg(_cover_fit(dos, (_p(W / 2), _p(H))))), 0, 0, W / 2, H)
        c.drawImage(ImageReader(_jpeg(_cover_fit(couv, (_p(W / 2), _p(H))))), W / 2, 0, W / 2, H)
    else:
        c.drawImage(ImageReader(_jpeg(_cover_fit(couv, (_p(W), _p(H))))), 0, 0, W, H)
    c.showPage(); c.save()
    probs = []
    if not dims.get("confirme"):
        probs.append("Dimensions de la couverture non confirmées : clés Lulu absentes (maquette, pas prête à imprimer).")
    if not fichiers_valides():
        probs.append("Fichiers du calendrier pas encore validés par Lulu : dans l'admin, « Vérifier les fichiers chez Lulu » "
                     "(une fois suffit pour tous les calendriers).")
    return {"largeur": round(W, 2), "hauteur": round(H, 2), "planche": planche, "source": dims["source"], "dos": 0.0,
            "marge": BLEED, "numero": None, "pret_a_imprimer": not probs, "problemes": probs}


# ====================================================================== 5. aperçus (maquettes déterministes, aucun appel IA)
def _mur(w, h):
    wall = Image.new("RGB", (w, h), (236, 229, 216))
    light = Image.new("L", (w, h), 0); ImageDraw.Draw(light).ellipse((-w * .4, -h * .45, w * .9, h * .6), fill=255)
    wall = Image.composite(Image.new("RGB", (w, h), (247, 242, 232)), wall, light.filter(ImageFilter.GaussianBlur(w // 5)))
    return Image.blend(wall, Image.effect_noise((w, h), 9).convert("RGB"), 0.035)


def _accroche(wall, cal, ox, oy):
    a = cal.split()[3]
    for off, blur, val, col in ((30, 34, 150, (120, 105, 85)), (7, 6, 95, (90, 80, 65))):
        m = Image.new("L", wall.size, 0); m.paste(a.point(lambda v: val if v > 0 else 0), (ox + int(off * .7), oy + off))
        wall = Image.composite(Image.new("RGB", wall.size, col), wall, m.filter(ImageFilter.GaussianBlur(blur)))
    wall.paste(cal, (ox, oy), cal)
    return wall


def _spirale(d, x0, x1, y, n=46, trou_milieu=False):
    for k in range(n):
        x = x0 + 30 + k * (x1 - x0 - 60) / (n - 1)
        if trou_milieu and abs(x - (x0 + x1) / 2) < 34:
            continue
        for dx in (-4, 4):
            d.rounded_rectangle((x + dx - 2.5, y - 22, x + dx + 2.5, y + 22), radius=3, fill=(88, 92, 104, 255))
            d.line((x + dx - 1, y - 20, x + dx - 1, y + 18), fill=(205, 208, 215, 255), width=2)


def maquette_ouverte(img_page, grille_page, dst, W=1240):
    """Le calendrier ouvert, accroché au mur : l'image du mois au-dessus de la spirale, la grille dessous."""
    t = _rogne(img_page); g = _rogne(grille_page)
    H = int(W * t.height / t.width); gap = 26
    t = t.resize((W, H), Image.LANCZOS); g = g.resize((W, H), Image.LANCZOS)
    sheet = Image.new("RGBA", (W, 2 * H + gap), (0, 0, 0, 0))
    sheet.paste(t, (0, 0)); sheet.paste(g, (0, H + gap))
    d = ImageDraw.Draw(sheet)
    d.ellipse((W // 2 - 9, 12, W // 2 + 9, 30), fill=(245, 240, 230, 255), outline=(200, 190, 170, 255), width=2)
    _spirale(d, 0, W, H + gap // 2)
    cal = sheet.rotate(-0.7, resample=Image.BICUBIC, expand=True)
    SW, SH = int(W * 1.45), int(sheet.height + 360)
    wall = _accroche(_mur(SW, SH), cal, (SW - cal.width) // 2, 190)
    d = ImageDraw.Draw(wall); nx = SW // 2
    d.line((nx, 120, nx, 200), fill=(150, 140, 120), width=2); d.ellipse((nx - 8, 112, nx + 8, 128), fill=(110, 100, 85))
    wall.convert("RGB").save(dst, quality=88)
    return Path(dst)


def maquette_fermee(couv_page, dst, W=1400):
    """Le calendrier fermé au mur : la couverture, la spirale en haut, l'épaisseur des pages dessous."""
    c = _rogne(couv_page); H = int(W * c.height / c.width); c = c.resize((W, H), Image.LANCZOS)
    top = 60
    sheet = Image.new("RGBA", (W + 4, H + top + 24), (0, 0, 0, 0)); d = ImageDraw.Draw(sheet)
    for k in range(6, 0, -1):
        v = 248 - k * 3
        d.rectangle((2, top + k * 3, W + 1, top + H + k * 3), fill=(v, v - 3, v - 10, 255), outline=(215, 208, 195, 255))
    sheet.paste(c, (2, top))
    _spirale(d, 2, W + 2, top, trou_milieu=True)
    cx = W / 2 + 2
    d.line((cx - 40, top - 6, cx + 40, top - 6), fill=(88, 92, 104, 255), width=5)
    d.line((cx - 40, top - 6, cx, top - 52), fill=(88, 92, 104, 255), width=5); d.line((cx + 40, top - 6, cx, top - 52), fill=(88, 92, 104, 255), width=5)
    cal = sheet.rotate(-0.5, resample=Image.BICUBIC, expand=True)
    SW, SH = int(W * 1.36), int(sheet.height + 300)
    wall = _accroche(_mur(SW, SH), cal, (SW - cal.width) // 2, 170)
    d = ImageDraw.Draw(wall); nx = SW // 2
    d.ellipse((nx - 9, 170 + top - 72, nx + 9, 170 + top - 54), fill=(105, 95, 80))
    wall.convert("RGB").save(dst, quality=88)
    return Path(dst)


def planche(mois_imgs, mois, dst):
    """Les 12 illustrations d'un coup d'œil (relecture, mail)."""
    cw, ch, cols = 420, 327, 4
    im = Image.new("RGB", (cols * cw + 50, 3 * (ch + 40) + 30), (251, 245, 234)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONT_TEXTE), 22)
    for k, (src, (an, m)) in enumerate(zip(mois_imgs, mois)):
        x, y = 25 + (k % cols) * cw, 15 + (k // cols) * (ch + 40)
        im.paste(_cover_fit(Image.open(src), (cw - 14, ch - 10)), (x, y))
        d.text((x + (cw - 14) // 2, y + ch - 4), f"{MOIS[m - 1].capitalize()} {an}", font=f, fill=NAVY, anchor="ma")
    im.save(dst, quality=86)
    return Path(dst)


# ====================================================================== 6. assemblage
def composer(folder, snap, cover, mois_imgs, couv_dims="auto"):
    """Toutes les pages et tous les fichiers à partir des 13 illustrations : rien n'est généré ici."""
    folder = Path(folder)
    mois = [(s["annee"], s["mois"]) for s in snap["scenes"]]
    couv = page_couverture(cover, snap["prenom"], snap["annee"])
    dos = page_quatrieme(mois_imgs, mois, snap["prenom"], snap["annee"], snap.get("cadeau"))
    couv.save(folder / "page_couverture.jpg", quality=92); dos.save(folder / "page_quatrieme.jpg", quality=92)
    pages, paires = [couv], []
    for src, (an, m) in zip(mois_imgs, mois):
        im, gr = page_image(src), page_grille(an, m, evenements(an, m, snap), snap["prenom"])
        pages += [im, gr]; paires.append((im, gr))
    pages.append(dos)
    titre = f"Le calendrier de {snap['prenom']} {snap['annee']}"
    nom = re.sub(r"[^\w\-]+", "-", titre, flags=re.U).strip("-")[:80]
    lecture = folder / f"{nom}.pdf"
    pdf_lecture(couv, paires, dos, lecture)
    it = pdf_impression(pages, folder / "impression_interieur.pdf")
    if couv_dims == "auto":
        try:
            couv_dims = dimensions_couverture()
        except Exception as e:                               # gabarit indisponible : maquette marquée non confirmée
            print("gabarit couverture calendrier indisponible :", e); couv_dims = None
    cv = couverture_impression(folder, couv_dims)
    ap = folder / "apercus"; ap.mkdir(exist_ok=True)
    apercus = {"couverture": maquette_fermee(couv, ap / "couverture.jpg").name}
    choix = [0] + [i for i, s in enumerate(snap["scenes"]) if s["titre"] == ANNIV[0]][:1]
    for i in dict.fromkeys(choix + [6]):
        apercus[f"mois_{i + 1:02d}"] = maquette_ouverte(*paires[i], ap / f"mois_{i + 1:02d}.jpg").name
    apercus["planche"] = planche(mois_imgs, mois, ap / "planche.jpg").name
    # aperçu carré de la couverture (mail, admin) : même nom que pour les livres
    c = _rogne(couv); c.thumbnail((1100, 1100)); c.save(ap / "couverture.png")
    apercus["couverture_png"] = "couverture.png"
    for i, (im, gr) in enumerate(paires):                    # pages de contrôle visibles depuis l'admin
        if i in (0, 6):
            s = Image.new("RGB", (1100, 1720), (240, 236, 228)); a = _rogne(im); b = _rogne(gr)
            a.thumbnail((1100, 850)); b.thumbnail((1100, 850)); s.paste(a, (0, 0)); s.paste(b, (0, 870))
            s.save(folder / f"planche_contact_{i + 1}.jpg", quality=84)
    return {"titre": titre, "pdf": lecture.name, "interieur": it, "couverture": cv, "apercus": apercus}


# ====================================================================== 7. fabrication (IA) dans le budget du calendrier
SYSTEM_MOIS = """Tu contrôles une illustration de calendrier mural pour enfant (une page paysage, un mois).
Compare l'image à la fiche. BLOQUANTS (uniquement) :
- un personnage attendu absent ou méconnaissable, ou un personnage récurrent en double ;
- un humain en trop (aucun parent ni grand-parent ; aucun enfant absent des personnages attendus) ; un chien, un chat ou un lapin domestique en trop ; deux animaux fusionnés ;
- espèce ou couleur principale fausse ; accessoire manquant ou présent alors que la fiche dit « aucun » ;
- la peluche dessinée comme un animal vivant ; des lunettes sur un animal ou sur la peluche ;
- un visage dans les 8 % du haut ou les 10 % du bas de l'image (zone percée et reliée) ;
- du texte, des lettres, des chiffres, un cadre ou un filigrane dans l'image ; une anatomie très fausse.
MINEURS : nuances, détails de vêtements, lumière, décor un peu chargé.
CE N'EST PAS UN ÉCART : de petits animaux sauvages du décor (oiseaux, papillons, écureuil, lapins de prairie, coccinelle) ; un accessoire de saison porté par la peluche (masque de carnaval, bonnet, écharpe, patins) tant qu'elle reste une peluche.
Une teinte due à la lumière de la scène n'est PAS une couleur fausse. En cas de doute, ce n'est pas bloquant.
Réponds UNIQUEMENT en JSON : {"bloquants": ["consigne en anglais"], "mineurs": ["en français"], "personnages_vus": ["noms"]}"""


def snapshot(form, cfg, today=None):
    """Instantané immuable de la commande du calendrier : il commande seul les images et les pages."""
    if cfg.get("problemes"):
        raise P.ProcedeError("Configuration incomplète, rien n'est généré : " + " ; ".join(cfg["problemes"]))
    c = form.get("calendrier") or {}
    debut = c.get("debut") if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(c.get("debut") or "")) else debut_par_defaut(today)
    mois = mois_du_calendrier(debut)
    data = {"version": VERSION, "produit": "calendrier", "prenom": cfg["personnages"][0]["nom"], "age": str(form.get("age")), "naissance": form.get("naissance") or "",
            "personnages": [P.fiche(x) for x in cfg["personnages"]], "protagoniste": "heros",
            "debut": debut, "annee": libelle_annee(debut), "pays": (c.get("pays") or "FR").upper(),
            "scenes": scenes_du_calendrier(mois, form.get("fetes"), form.get("anniversaire")),
            "fetes": form.get("fetes") or "", "anniversaire": form.get("anniversaire") or "",
            "dates": nettoyer_dates(c.get("dates")), "commande_le": c.get("commande_le") or (today or DT.date.today()).isoformat(),
            "cadeau": {"de": form["cadeau_de"], "message": form.get("cadeau_message", "")} if form.get("cadeau_de") else None}
    data["empreinte"] = P.sha(data)
    data["empreinte_images"] = P.sha([VERSION, data["personnages"]])      # les dates ne changent pas les images
    return data


def _ids(snap):
    return [p["id"] for p in snap["personnages"]]


def image_prompt(scene, snap, refs, couverture=False):
    ids = _ids(snap)
    noms = ", ".join(p["nom"].upper() for p in snap["personnages"])
    head = ("Use case: illustration-story. Create ONE landscape full-bleed illustration for the COVER of a premium personalised "
            "children's WALL CALENDAR." if couverture else
            f"Use case: illustration-story. Create ONE landscape full-bleed illustration for CALENDAR MONTH {scene['mois']:02d} "
            f"of a premium personalised children's WALL CALENDAR (one picture per month, same characters all year).")
    style = P.PROMPT_IMAGE.split("CHARACTER BIBLE")[0].split("\n", 2)[2].strip()
    lines = [head, style, "CHARACTER BIBLE", P._bible_lines(ids, snap, {}), P.refs_text(refs, snap),
             f"SCENE: {COUVERTURE if couverture else scene['scene']}.",
             f"CHARACTERS: exactly these recurring characters ({noms}), each shown once, close together and clearly visible; "
             f"{snap['personnages'][0]['nom'].upper()} is the focal point. No other human at all (no parent, no grandparent, no child who is not listed); "
             "small background wildlife only if the scene asks for it.",
             "COMPOSITION: landscape, warm and joyful, readable from across a room. Keep every face and the main action inside the "
             "central 80 % of the picture: the top 8 % and the bottom 10 % are punched and bound (only sky, ground or foliage there).",
             ("Keep the upper third calm (sky, soft light) for a title that will be typeset separately." if couverture else
              f"Light: {scene['light']}."),
             "No writing, letters, numbers, calendar grid, title, captions, watermark, typography or frame."]
    p = "\n".join(lines)
    if len(p.encode()) > PROMPT_MAX:                            # trop long : la bible des personnages est résumée
        lines[1] = style[:600]
        p = "\n".join(lines)
    return p


def _key(snap, quoi, refs, size, quality):
    return P.sha([VERSION, P.model(), snap["empreinte_images"], quoi, [P.fsha(f) for _, f in refs], size, quality])[:12]


def cibles(snap, portraits, folder):
    """Fichiers attendus (couverture + 12 mois) et leurs références : la clé dit si l'image existe déjà (rien n'est refait)."""
    folder = Path(folder)
    qc, qm = G._m("q_main", G.IMAGE_QUALITY), G._m("q_scene", G.SCENE_QUALITY)
    ids = _ids(snap)
    crefs = P.refs_for(ids, portraits, None, folder, "couverture")
    cover = folder / f"cal-couverture-{_key(snap, 'couverture', crefs, IMG_SIZE, qc)}.png"
    out = [("couverture", None, crefs, cover, qc)]
    for s in snap["scenes"]:
        refs = P.refs_for(ids, portraits, cover if cover.exists() else P.STYLE["couverture"], folder, s["light"])
        out.append((f"mois {s['rang']}", s, refs, folder / f"cal-mois-{s['rang']:02d}-{_key(snap, [s['mois'], s['scene']], refs, IMG_SIZE, qm)}.png", qm))
    return out


def plan(cfg, folder, snap=None, portraits=None):
    """Appels qui RESTENT à faire, chacun à son maximum (borne haute avant tout appel)."""
    folder = Path(folder)
    qc, qm = G._m("q_main", G.IMAGE_QUALITY), G._m("q_scene", G.SCENE_QUALITY)
    qp = G._m("q_scene", G.PORTRAIT_QUALITY)
    img = lambda e, n, q: {"type": "image", "etape": e, "modele": P.model(), "prompt_max": "x" * PROMPT_MAX, "refs": n, "size": IMG_SIZE, "quality": q}
    ctl = lambda e: {"type": "chat", "etape": e, "modele": G.REVIEW_MODEL, "textes": [SYSTEM_MOIS, "x" * P.FICHE_MAX],
                     "max_tokens": P.REVIEW_MAX_TOKENS, "images": [P._vision_dims(IMG_SIZE)]}
    out = []
    for c in cfg["personnages"]:
        if not G.portrait_en_cache(c):
            out.append(P._p_image(f"portrait {c['id']}", 3, "1024x1024", qp))
        if not G.portrait_en_cache(c) or not Path(str(G.portrait_path(c)) + ".controle.json").exists():
            out.append(P._p_controle(f"contrôle portrait {c['id']}", P.SYSTEM_REF, "1024x1024"))
    if snap is None or portraits is None:
        out += [img("couverture", 3, qc), ctl("contrôle couverture")]
        for k in range(12):
            out += [img(f"mois {k + 1}", 3, qm), ctl(f"contrôle mois {k + 1}")]
        return out
    for etape, _, refs, path, q in cibles(snap, portraits, folder):
        if not path.exists():
            out.append(img(etape, len(refs), q))
        if not path.with_suffix(".json").exists():
            out.append(ctl("contrôle " + etape))
    return out


def _dessiner(etape, scene, refs, path, q, snap, folder):
    """UNE image (si elle n'existe pas déjà) et UN contrôle (mémorisé). Jamais de seconde tentative."""
    P.image_ok(path)                                # image tronquée (coupure, disque plein) : mise de côté et refaite
    rapport_p = path.with_suffix(".json")
    if path.exists() and rapport_p.exists():
        return json.loads(rapport_p.read_text(encoding="utf-8"))
    if not path.exists():
        prompt = image_prompt(scene, snap, refs, couverture=scene is None)
        (Path(folder) / "prompts").mkdir(exist_ok=True)
        (Path(folder) / "prompts" / f"{path.stem}.txt").write_text(prompt, encoding="utf-8")
        P.image(prompt, refs, path, IMG_SIZE, q, f"prompts/{path.stem}.txt", etape=etape)
    fiche = {"page": etape, "personnages_attendus": snap["personnages"], "scene": COUVERTURE if scene is None else scene["scene"]}
    v = P._vision(SYSTEM_MOIS, fiche, path)
    r = {"retenu": path.name, "bloquants": v["bloquants"], "bloquants_fr": v.get("bloquants_fr", []), "mineurs": v.get("mineurs", []), "controle_impossible": v.get("controle_impossible")}
    rapport_p.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def run(form, cfg, refs, folder, job, progress):
    """Fabrication complète du calendrier dans son budget. Renvoie le résumé pour le suivi de la commande."""
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

    etat("queued", "Instantané du calendrier", 2)
    m = P.model()
    if IMG_SIZE not in {"1024x1024", "1536x1024", "1024x1536"} and not P.custom_sizes_ok(m):
        raise P.ProcedeError(f"Le modèle image « {m} » ne produit pas le format {IMG_SIZE} du calendrier (gpt-image-2 requis).")
    P.disque_ok(folder)
    dep = BU.depense(livre)
    if dep["incertain"] > 0 or dep["reserve"] > 0:
        raise P.ProcedeError("Appel(s) au résultat incertain pour ce calendrier : règle-les dans l'admin avant toute reprise.")
    snap = snapshot(form, cfg)
    ecarts = P.check_snapshot(snap, form)
    if ecarts:
        raise P.ProcedeError("Les fiches ne correspondent pas à la commande : " + " ; ".join(ecarts))
    save("calendrier_instantane.json", snap)
    lignes, borne = BU.verifier_lancement(plan(cfg, folder), livre)
    save("budget.json", {"livre": livre, "plafond_usd": PLAFOND, "marge": BU.MARGE, "borne_lancement_usd": borne, "detail_lancement": lignes,
                         "deja_engage_usd": round(dep["total"], 4), "tarifs": BU.etat_tarifs()})

    etat("references", "Références des personnages", 6)
    portraits, rapport_refs = P.references(snap, cfg, refs, folder, lambda s: progress(s))
    save("references.json", rapport_refs)
    lignes2, borne2 = BU.verifier_lancement(plan(cfg, folder, snap, portraits), livre)

    etat("illustrating", "Couverture du calendrier", 14)
    t = cibles(snap, portraits, folder)
    rapports = {"couverture": _dessiner(*t[0][:4], t[0][4], snap, folder)}
    t = cibles(snap, portraits, folder)                     # la couverture existe : elle sert de référence aux 12 mois
    etat("illustrating", f"{MOIS[snap['scenes'][0]['mois'] - 1].capitalize()} (mois pilote)", 22)
    rapports["mois 1"] = _dessiner(*t[1][:4], t[1][4], snap, folder)
    if rapports["mois 1"]["bloquants"]:
        save("controle.json", {"etat": "needs_review", "pilote": rapports["mois 1"], "references": rapport_refs})
        raise P.ProcedeError("Mois pilote non conforme : " + " ; ".join(P.fr(rapports["mois 1"])) +
                             " (relecture humaine : aucune régénération automatique)")
    fait = [1]
    def un(c):
        r = _dessiner(*c[:4], c[4], snap, folder)
        fait[0] += 1; progress(f"Mois {fait[0]}/12", 22 + 6 * fait[0])
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

    etat("assembling", "Grilles, couverture et PDF", 94)
    cover = t[0][3]; mois_imgs = [c[3] for c in t[1:]]
    fab = composer(folder, snap, cover, mois_imgs)
    return conclure(folder, snap, fab, rapports, rapport_refs, livre, job)


def conclure(folder, snap, fab, rapports, rapport_refs, livre, job):
    folder = Path(folder)
    bloquants = [f"{k} : {x}" for k, r in rapports.items() for x in P.fr(r)]
    bloquants += [f"référence {k} : {x}" for k, v in rapport_refs.items() for x in P.fr(v)]
    impossibles = [f"{k} : contrôle visuel impossible ({r['controle_impossible']})" for k, r in rapports.items() if r.get("controle_impossible")]
    mineurs = [f"{k} : {x}" for k, r in rapports.items() for x in r.get("mineurs", [])]
    phase = "needs_review" if (bloquants or impossibles) else "ready"
    dep = BU.depense(livre) if livre else {"regle": 0}
    cout = round(dep["regle"], 4)
    cal = {"produit": "calendrier", "titre": fab["titre"], "prenom": snap["prenom"], "annee": snap["annee"], "debut": snap["debut"],
           "pdf_lecture": fab["pdf"], "images": sorted(p.name for p in folder.glob("cal-*.png")), "apercus": fab["apercus"]}
    (folder / "calendrier.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    controle = {"etat": phase, "produit": "calendrier", "instantane": snap["empreinte"], "modele_image": P.model(), "taille_image": IMG_SIZE,
                "references": rapport_refs, "images": rapports, "bloquants": bloquants, "mineurs": mineurs, "controles_impossibles": impossibles,
                "fabrication": {"interieur": fab["interieur"], "couverture": fab["couverture"]}, "impression_bloquee": fab["couverture"]["problemes"],
                "cout_api_usd": cout, "budget": dep}
    (folder / "controle.json").write_text(json.dumps(controle, ensure_ascii=False, indent=1), encoding="utf-8")
    job["phase"] = phase
    res = {"pdf": fab["pdf"], "titre": fab["titre"], "controle": bloquants + impossibles, "mineurs": mineurs + fab["couverture"]["problemes"],
           "pages": PAGES, "phase": phase, "cout": cout}
    if phase == "ready" and livre:
        finaliser(folder, res)
    return res


def finaliser(folder, res):
    """Fige le calendrier (manifeste + empreintes, sauvegarde) : ensuite, plus aucun appel de génération."""
    import fabrication as F
    folder = Path(folder)
    cal = json.loads((folder / "calendrier.json").read_text(encoding="utf-8"))
    fichiers = ([cal["pdf_lecture"], "calendrier.json", "calendrier_instantane.json", "references.json", "controle.json", "budget.json",
                 "impression_interieur.pdf", "impression_couverture.pdf", "page_couverture.jpg", "page_quatrieme.jpg"]
                + cal["images"] + [p.name for p in folder.glob("portrait_*.png")] + [f"apercus/{v}" for v in cal["apercus"].values()])
    man = F.finaliser(folder, fichiers, {"produit": "calendrier", "titre": res["titre"], "pdf_lecture": cal["pdf_lecture"], "pages": PAGES,
                                         "mineurs": res["mineurs"], "cout_api_usd": res["cout"], "appels_api": BU.appels(P.livre_id(folder)),
                                         "apercus": cal["apercus"], "volumeNumber": None})
    try:
        F.sauvegarder(folder, Path(os.getenv("SAUVEGARDE_DIR") or BU.DATA / "sauvegardes"))
    except Exception as e:
        print("sauvegarde du calendrier impossible :", e)
    res["finalise"] = True
    return man


def finaliser_apres_relecture(folder):
    """Admin, après relecture d'un calendrier « à relire » : fige les fichiers produits. Aucun appel IA."""
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        return json.loads((folder / "final.json").read_text(encoding="utf-8"))
    cal = json.loads((folder / "calendrier.json").read_text(encoding="utf-8"))
    ctl = json.loads((folder / "controle.json").read_text(encoding="utf-8"))
    if len([x for x in cal["images"] if x.startswith("cal-mois-")]) < 12 or not (folder / "impression_interieur.pdf").exists():
        raise P.ProcedeError("Calendrier incomplet : rien à finaliser")
    res = {"titre": cal["titre"], "mineurs": ctl.get("mineurs", []) + ctl.get("bloquants", []), "cout": ctl.get("cout_api_usd")}
    return finaliser(folder, res)


def recomposer(folder, form):
    """Admin : recompose les pages (dates, couverture Lulu) à partir des 13 images enregistrées. Aucun appel IA.
    Refusé pour un calendrier finalisé (ses fichiers sont figés)."""
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        raise P.ProcedeError("Calendrier finalisé : ses fichiers sont figés")
    snap = json.loads((folder / "calendrier_instantane.json").read_text(encoding="utf-8"))
    imgs = sorted(folder.glob("cal-mois-*.png")); cov = sorted(folder.glob("cal-couverture-*.png"))
    if len(imgs) < 12 or not cov:
        raise P.ProcedeError("Images du calendrier incomplètes")
    return composer(folder, snap, cov[-1], [sorted(folder.glob(f"cal-mois-{k:02d}-*.png"))[-1] for k in range(1, 13)])


DEMO = ROOT / "kit" / "calendrier_demo"


def demo(form, cfg, folder, job, progress, today=None):
    """Sans clé OpenAI (ou mode démo) : un calendrier complet à partir des illustrations d'exemple, aucun appel payant."""
    folder = Path(folder)
    progress("Mode démo : calendrier d'exemple, sans appel API", 30)
    snap = snapshot(form, cfg, today)
    (folder / "calendrier_instantane.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    kit = sorted((ROOT / "kit" / "noe_demo").glob("spread-*.jpg"))
    imgs = []
    for k, s in enumerate(snap["scenes"]):
        p = DEMO / f"mois-{s['mois']:02d}.jpg"
        dst = folder / f"cal-mois-{s['rang']:02d}-demo.png"
        Image.open(p if p.exists() else kit[k % len(kit)]).convert("RGB").save(dst)
        imgs.append(dst)
    cov = folder / "cal-couverture-demo.png"
    Image.open(ROOT / "kit" / "noe_demo" / "spread-2.jpg").convert("RGB").save(cov)
    fab = composer(folder, snap, cov, imgs)
    rapports = {"couverture": {"bloquants": [], "mineurs": []}}
    return conclure(folder, snap, fab, rapports, {}, None, job)
