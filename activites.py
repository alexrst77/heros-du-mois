# -*- coding: utf-8 -*-
"""Pages d'activités du cahier de coloriage V2, fabriquées et VÉRIFIÉES par le programme (l'IA ne fait que le dessin de base).

- labyrinthe : généré (parcours en profondeur), solution trouvée par un parcours en largeur, chemin unique ;
- points à relier : contour de la silhouette dessinée par l'IA, rééchantillonné en N points numérotés dans l'ordre ;
- coloriage magique : dessin IA en aplats, réduit à une palette de 6 couleurs nommées, une zone = un numéro posé au cœur de la zone ;
- « termine le dessin » : la moitié gauche d'un coloriage du cahier, l'autre moitié à dessiner.
Chaque fonction renvoie (image, rapport) ; rapport["problemes"] vide = page conforme."""
import math, random
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageOps

PALETTE = [("rouge", (220, 50, 50)), ("orange", (240, 140, 40)), ("jaune", (245, 210, 50)), ("vert", (70, 170, 70)),
           ("bleu", (60, 120, 210)), ("violet", (140, 80, 190)), ("rose", (240, 140, 180)), ("marron", (140, 90, 50))]


# ---------------------------------------------------------------- labyrinthe
def labyrinthe(cols, rows, seed):
    """Murs d'un labyrinthe parfait (un seul chemin entre deux cases) : murs[(x, y)] = {'N','S','E','O'} encore debout."""
    rnd = random.Random(seed)
    murs = {(x, y): {"N", "S", "E", "O"} for x in range(cols) for y in range(rows)}
    D = {"N": (0, -1, "S"), "S": (0, 1, "N"), "E": (1, 0, "O"), "O": (-1, 0, "E")}
    vu, pile = {(0, 0)}, [(0, 0)]
    while pile:
        x, y = pile[-1]
        vois = [(d, x + dx, y + dy, o) for d, (dx, dy, o) in D.items() if 0 <= x + dx < cols and 0 <= y + dy < rows and (x + dx, y + dy) not in vu]
        if not vois:
            pile.pop(); continue
        d, nx, ny, o = rnd.choice(vois)
        murs[(x, y)].discard(d); murs[(nx, ny)].discard(o)
        vu.add((nx, ny)); pile.append((nx, ny))
    return murs


def solution(murs, cols, rows, depart, arrivee):
    """Plus court chemin (parcours en largeur) ; None s'il n'existe pas."""
    from collections import deque
    D = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "O": (-1, 0)}
    prec, file = {depart: None}, deque([depart])
    while file:
        c = file.popleft()
        if c == arrivee:
            break
        for d, (dx, dy) in D.items():
            n = (c[0] + dx, c[1] + dy)
            if d not in murs[c] and 0 <= n[0] < cols and 0 <= n[1] < rows and n not in prec:
                prec[n] = c; file.append(n)
    if arrivee not in prec:
        return None
    ch, c = [], arrivee
    while c is not None:
        ch.append(c); c = prec[c]
    return ch[::-1]


def taille_labyrinthe(age):
    a = int(age or 5)
    return (7, 9) if a <= 4 else (9, 12) if a <= 6 else (12, 15)


def dessiner_labyrinthe(box_px, age, seed, avec_solution=False):
    """Labyrinthe dans la boîte (x0, y0, x1, y1) en pixels. Entrée en haut à gauche, sortie en bas à droite."""
    cols, rows = taille_labyrinthe(age)
    murs = labyrinthe(cols, rows, seed)
    ch = solution(murs, cols, rows, (0, 0), (cols - 1, rows - 1))
    x0, y0, x1, y1 = box_px
    c = min((x1 - x0) / cols, (y1 - y0) / rows)
    ox, oy = x0 + ((x1 - x0) - c * cols) / 2, y0 + ((y1 - y0) - c * rows) / 2
    im = Image.new("L", (int(x1), int(y1)), 255); d = ImageDraw.Draw(im)
    w = max(4, int(c * .09))
    if avec_solution and ch:
        pts = [(ox + (x + .5) * c, oy + (y + .5) * c) for x, y in ch]
        d.line(pts, fill=150, width=max(3, int(c * .22)), joint="curve")
    for (x, y), m in murs.items():
        X, Y = ox + x * c, oy + y * c
        if "N" in m and not (x == 0 and y == 0): d.line((X, Y, X + c, Y), fill=0, width=w)
        if "O" in m: d.line((X, Y, X, Y + c), fill=0, width=w)
        if "S" in m and not (x == cols - 1 and y == rows - 1): d.line((X, Y + c, X + c, Y + c), fill=0, width=w)
        if "E" in m: d.line((X + c, Y, X + c, Y + c), fill=0, width=w)
    probs = []
    if not ch:
        probs.append("labyrinthe sans solution")
    return im, {"cols": cols, "rows": rows, "solution": len(ch or []), "cellule_px": c, "origine": (ox, oy), "problemes": probs}


# ---------------------------------------------------------------- points à relier
def nb_points(age):
    a = int(age or 5)
    return 18 if a <= 4 else 28 if a <= 6 else 40


def points_silhouette(path, n):
    """Contour extérieur de la plus grande forme sombre de l'image, rééchantillonné en n points (sens horaire, départ en haut)."""
    g = np.asarray(Image.open(path).convert("L"))
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cs, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return [], {"problemes": ["aucune forme trouvée dans la silhouette"]}
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float)
    aire = cv2.contourArea(c.astype(np.float32)) / (g.shape[0] * g.shape[1])
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[c, c[:1]], axis=0).T))]
    L = seg[-1]
    pts = []
    for k in range(n):
        t = k * L / n
        i = np.searchsorted(seg, t) - 1
        i = max(0, min(i, len(c) - 1)); j = (i + 1) % len(c)
        f = (t - seg[i]) / max(1e-6, seg[i + 1] - seg[i])
        pts.append(tuple(c[i] + f * (c[j] - c[i])))
    k0 = min(range(n), key=lambda k: (pts[k][1], pts[k][0]))          # le 1 en haut
    pts = pts[k0:] + pts[:k0]
    probs = []
    if aire < .05:
        probs.append(f"silhouette trop petite ({aire:.0%} de l'image)")
    return pts, {"aire": round(aire, 3), "probs_src": probs, "problemes": probs}


def dessiner_points(path, box_px, age):
    """Page « relie les points » : points numérotés 1..n, sans le trait (l'enfant le trace), placés dans la boîte."""
    from calendrier import ft
    n = nb_points(age)
    pts, r = points_silhouette(path, n)
    x0, y0, x1, y1 = box_px
    im = Image.new("L", (int(x1), int(y1)), 255); d = ImageDraw.Draw(im)
    if not pts:
        return im, r
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    marge = 120                                                  # place pour les numéros autour des points
    k = min((x1 - x0 - 2 * marge) / max(1, bx1 - bx0), (y1 - y0 - 2 * marge) / max(1, by1 - by0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    P = [(cx + (x - (bx0 + bx1) / 2) * k, cy + (y - (by0 + by1) / 2) * k) for x, y in pts]
    gx, gy = sum(p[0] for p in P) / n, sum(p[1] for p in P) / n
    f = ft("texte", 11, 800)
    boites, probs = [], list(r["problemes"])
    rayon = 17
    for i, (x, y) in enumerate(P):
        d.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=0)
        vx, vy = x - gx, y - gy; nv = math.hypot(vx, vy) or 1
        for dist in (60, 80, 100):                               # numéro à l'extérieur, sans chevaucher les autres
            tx, ty = x + vx / nv * dist, y + vy / nv * dist
            t = str(i + 1); w = d.textlength(t, font=f)
            bb = (tx - w / 2 - 5, ty - 26, tx + w / 2 + 5, ty + 26)
            if not any(bb[0] < b[2] and bb[2] > b[0] and bb[1] < b[3] and bb[3] > b[1] for b in boites) and \
               not any(bb[0] - 14 < px < bb[2] + 14 and bb[1] - 14 < py < bb[3] + 14 for px, py in P):
                break
        else:
            probs.append(f"numéro {i + 1} serré contre un autre")
        if bb[0] < x0 or bb[2] > x1 or bb[1] < y0 or bb[3] > y1:
            probs.append(f"numéro {i + 1} hors de la page")
        boites.append(bb)
        d.text((tx, ty), t, font=f, fill=0, anchor="mm")
    ecarts = [math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]) for i in range(1, n)]
    if min(ecarts) < 55:
        probs.append("deux points consécutifs trop proches")
    d.ellipse((P[0][0] - rayon - 9, P[0][1] - rayon - 9, P[0][0] + rayon + 9, P[0][1] + rayon + 9), outline=0, width=5)   # le départ entouré
    r.update({"n": n, "problemes": probs})
    return im, r


# ---------------------------------------------------------------- coloriage magique (numéroté)
def _palette_proche(rgb):
    pal = np.array([c for _, c in PALETTE], float)
    return int(np.argmin(((pal - np.array(rgb, float)) ** 2).sum(1)))


def coloriage_magique(path, box_px, n_max=6, aire_min_px=2500):
    """Dessin IA en aplats -> page au trait avec un numéro par zone et la légende (numéro -> couleur, en toutes lettres).
    Les zones blanches (fond) restent sans numéro. Renvoie l'image, la légende et un rapport vérifié."""
    from calendrier import ft
    src = Image.open(path).convert("RGB")
    x0, y0, x1, y1 = [int(v) for v in box_px]
    W, H = x1 - x0, y1 - y0
    k = min(W / src.width, H / src.height)
    src = src.resize((int(src.width * k), int(src.height * k)), Image.LANCZOS)
    a = np.asarray(src).astype(np.int16)
    lum = a.mean(2)
    trait = (lum < 70).astype(np.uint8)
    trait = cv2.dilate(trait, np.ones((3, 3), np.uint8), 1)
    sat = a.max(2) - a.min(2)
    blanc = (lum > 215) & (sat < 40)
    zones = ((trait == 0) & ~blanc).astype(np.uint8)
    n_lab, lab, stats, _ = cv2.connectedComponentsWithStats(zones, 4)
    # couleur de chaque zone = couleur nommée la plus proche de sa médiane
    choix = {}
    for i in range(1, n_lab):
        if stats[i, cv2.CC_STAT_AREA] < aire_min_px:
            continue
        m = lab == i
        choix[i] = _palette_proche(np.median(a[m], axis=0))
    # au plus n_max couleurs : les plus utilisées
    from collections import Counter
    usage = Counter()
    for i, c in choix.items():
        usage[c] += int(stats[i, cv2.CC_STAT_AREA])
    garde = [c for c, _ in usage.most_common(n_max)]
    num = {c: k + 1 for k, c in enumerate(garde)}
    for i, c in list(choix.items()):
        if c not in num:                                   # couleur rare : ramenée à la plus proche des couleurs gardées
            pal = np.array([PALETTE[g][1] for g in garde], float)
            choix[i] = garde[int(np.argmin(((pal - np.array(PALETTE[c][1], float)) ** 2).sum(1)))]
    # page : trait noir + petites zones fermées par le trait, numéros au cœur des zones
    im = Image.new("L", (x1, y1), 255)
    t_img = Image.fromarray(np.where(trait > 0, 0, 255).astype(np.uint8))
    bords = cv2.Canny(((lab > 0) * 255).astype(np.uint8), 50, 150)          # contour de chaque zone, même là où l'IA n'a pas tracé
    contours_z = np.zeros_like(trait)
    for i in choix:
        e = cv2.morphologyEx((lab == i).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        contours_z |= e
    t_arr = np.minimum(np.asarray(t_img), np.where(contours_z > 0, 0, 255)).astype(np.uint8)
    t_img = Image.fromarray(t_arr)
    ox, oy = x0 + (W - t_img.width) // 2, y0 + (H - t_img.height) // 2
    im.paste(t_img, (ox, oy))
    d = ImageDraw.Draw(im)
    probs, poses = [], 0
    for i, c in choix.items():
        m = (lab == i).astype(np.uint8)
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
        yy, xx = np.unravel_index(int(np.argmax(dist)), dist.shape)
        r = float(dist[yy, xx])
        if r < 30:
            continue                                        # zone trop fine pour un numéro lisible : laissée libre
        taille = max(12.0, min(30.0, r * .55 / 4.17))           # en points (lisible par un enfant, tient dans la zone)
        d.text((ox + xx, oy + yy), str(num[c]), font=ft("texte", taille, 800), fill=0, anchor="mm")
        if lab[yy, xx] != i:
            probs.append("numéro hors de sa zone")
        poses += 1
    legende = [(num[c], PALETTE[c][0]) for c in garde]
    if poses < 4:
        probs.append(f"trop peu de zones numérotées ({poses})")
    if not legende:
        probs.append("aucune couleur reconnue")
    return im, {"zones": poses, "legende": legende, "problemes": probs}


# ---------------------------------------------------------------- termine le dessin
def moitie(trait):
    """La moitié gauche d'un dessin au trait ; la droite reste blanche, avec une ligne pointillée au milieu."""
    t = trait.convert("L").copy()
    w, h = t.size
    d = ImageDraw.Draw(t)
    d.rectangle((w // 2 + 2, 0, w, h), fill=255)
    for y in range(0, h, 36):
        d.line((w // 2, y, w // 2, y + 18), fill=120, width=4)
    return t
