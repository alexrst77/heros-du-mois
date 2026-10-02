# -*- coding: utf-8 -*-
"""Pré-calcule, pour chaque avatar peint du pack, des masques de zones recolorables (aperçu instantané dans l'éditeur).
Sortie : static/avatars/<nom>.mask.png (R, G, B = 3 zones, douces) + static/avatars/masks.json (couleur moyenne de chaque zone)."""
import json, glob, os
import numpy as np
from PIL import Image, ImageFilter

SIZE = 480


def hsv(im):
    h = np.asarray(im.convert("RGB").convert("HSV")).astype(np.float32)
    return h[..., 0] * 360 / 255, h[..., 1] / 255, h[..., 2] / 255


def blur(m, r=1.2):
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255


def local_mean(m, r):
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(r))).astype(np.float32) / 255


def fill_holes(m):
    """Remplit les trous d'un masque (tout ce qui n'est pas relié au bord)."""
    from collections import deque
    h, w = m.shape; seen = np.zeros_like(m, bool); q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not m[y, x] and not seen[y, x]: seen[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not m[y, x] and not seen[y, x]: seen[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not m[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True; q.append((ny, nx))
    return ~seen


def largest(m):
    """Plus grande composante connexe d'un masque."""
    from collections import deque
    h, w = m.shape; lab = np.zeros((h, w), np.int32); best, bestn, n = 0, 0, 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1; lab[y0, x0] = n; q = deque([(y0, x0)]); cnt = 0
        while q:
            y, x = q.popleft(); cnt += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; q.append((ny, nx))
        if cnt > bestn:
            best, bestn = n, cnt
    return lab == best


def close(m, r):
    im = Image.fromarray((m * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.MaxFilter(r)).filter(ImageFilter.MinFilter(r))) > 127


def child(im):
    A = np.asarray(im)[..., 3] > 30
    H, S, V = hsv(im)
    yy = np.mgrid[0:SIZE, 0:SIZE][0] / SIZE
    warm = (H < 34) | (H > 335)
    core = A & (H > 32) & (H < 60) & (S > 0.45) & (V > 0.38) & (yy > 0.52)
    zone = np.zeros_like(A)                                            # tout le vêtement, y compris les morceaux séparés par les cheveux
    for c in components(close(core, 15)):
        if c[0] > 400 and c[2] > 0.66 * SIZE:                          # sous le cou seulement (pas les élastiques des couettes)
            m = np.zeros_like(A); m[c[3][:, 0], c[3][:, 1]] = True; zone |= fill_holes(m)
    peau = ((H < 34) | (H > 335)) & (V > 0.55) & (S > 0.12) & (S < 0.8)        # le cou ne doit jamais prendre la couleur du vêtement
    zone |= (np.asarray(Image.fromarray((zone * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))) > 127) & ~peau
    zone |= A & (yy > 0.84)                                            # le bas de l'image n'est que vêtement (et mèches, traitées ensuite)
    zone &= A
    strand = zone & (H > 4) & (H < 31) & (S > 0.35) & (V < 0.72)
    # une mèche posée sur le vêtement est reliée aux cheveux ; un pli ou une couture du vêtement ne l'est pas
    hair_out = A & ~zone & (((H > 4) & (H < 46)) | (V < 0.35)) & (S > 0.2) & (yy < 0.75)
    hair_out = np.asarray(Image.fromarray((hair_out * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 127
    meche = np.zeros_like(A)
    for c in components(strand):
        if hair_out[c[3][:, 0], c[3][:, 1]].any() or c[0] > 900:
            meche[c[3][:, 0], c[3][:, 1]] = True
    shirt = zone & ~meche
    # visage : peau claire franche, refermée avec un petit rayon (pour ne pas engloutir les mèches voisines)
    strict = A & ~shirt & warm & (S > 0.1) & (S < 0.62) & (V > 0.86)
    core = fill_holes(largest(close(strict, 5))) & A & ~shirt
    near = Image.fromarray((core * 255).astype(np.uint8))
    for _ in range(3): near = near.filter(ImageFilter.MaxFilter(9))
    near = np.asarray(near) > 127
    cand = A & ~shirt & warm & (V > 0.74) & (S < 0.82)                # peau dans l'ombre (joues, oreilles, cou)
    skinreg = (core | (near & cand)) & A & ~shirt
    xx = np.mgrid[0:SIZE, 0:SIZE][1] / SIZE
    neck = cand & (yy > 0.55) & (xx > 0.35) & (xx < 0.68)
    for c in components(neck):
        if c[0] > 300: skinreg[c[3][:, 0], c[3][:, 1]] = True
    # oreilles : zones de peau (même ombrées) reliées au visage, refermées pour inclure le creux de l'oreille
    far = Image.fromarray((core * 255).astype(np.uint8))
    for _ in range(12): far = far.filter(ImageFilter.MaxFilter(9))
    far = np.asarray(far) > 127
    earc = A & ~shirt & ~core & far & ((H < 30) | (H > 330)) & (V > 0.5) & (S > 0.22) & (S < 0.98)
    # les oreilles sont sur les côtés du visage, à hauteur des yeux et de la bouche : on ne cherche que là
    ys, xs = np.nonzero(core)
    y0, y1 = np.percentile(ys, 30), np.percentile(ys, 85)
    xx = np.mgrid[0:SIZE, 0:SIZE][1]; yy2 = np.mgrid[0:SIZE, 0:SIZE][0]
    rows = (yy2 > y0) & (yy2 < y1)
    left, right = np.percentile(xs, 2), np.percentile(xs, 98)
    for side in ((xx < left + 26) & rows, (xx > right - 26) & rows):
        cs = [c for c in components(earc & side) if c[0] > 60]
        if cs:
            c = max(cs, key=lambda c: c[0])
            m = np.zeros_like(A); m[c[3][:, 0], c[3][:, 1]] = True
            skinreg |= fill_holes(close(m, 7)) & A & ~shirt
    face = fill_holes(skinreg) & A & ~shirt
    feat = face & ~skinreg & (V < 0.6)                                 # yeux, sourcils, bouche : on n'y touche pas
    skin = skinreg & warm & (S > 0.08) & (V > 0.6)
    hairlike = (((H > 4) & (H < 46)) | (V < 0.35)) & (S > 0.2) & (V < 0.9)
    hair = A & ~shirt & ~skin & ~feat & hairlike
    grow = np.asarray(Image.fromarray((hair * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 127
    hair = grow & A & ~shirt & ~skin & ~feat                         # attrape les petites mèches sombres isolées
    return {"R": hair, "G": skin, "B": shirt, "_feat": feat, "_face": face}


def components(m):
    from collections import deque
    h, w = m.shape; lab = np.zeros((h, w), np.int32); out = []; n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]: continue
        n += 1; lab[y0, x0] = n; q = deque([(y0, x0)]); pts = []
        while q:
            y, x = q.popleft(); pts.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; q.append((ny, nx))
        a = np.array(pts); out.append((len(pts), a[:, 1].mean(), a[:, 0].mean(), a))
    return out


def find_eyes(z, im):
    """Les deux yeux : paire de grandes taches sombres à même hauteur dans le visage."""
    H, S, V = hsv(im)
    dark = z["_face"] & (V < 0.42)
    comps = [c for c in components(dark) if c[0] > 60]
    best = None
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            a, b = comps[i], comps[j]
            dx, dy = abs(a[1] - b[1]), abs(a[2] - b[2])
            if 0.1 * SIZE < dx < 0.32 * SIZE and dy < 0.06 * SIZE:
                sc = a[0] + b[0]
                if best is None or sc > best[0]:
                    best = (sc, sorted([a, b], key=lambda c: c[1]))
    if not best: return None, None
    eyes = []; iris = np.zeros((SIZE, SIZE), bool)
    for c in best[1]:
        pts = c[3]; r = max(pts[:, 1].max() - pts[:, 1].min(), pts[:, 0].max() - pts[:, 0].min()) / 2 + 2
        eyes.append([round(float(c[1]), 1), round(float(c[2]), 1), round(float(r), 1)])
        yy, xx = np.mgrid[0:SIZE, 0:SIZE]
        disk = (xx - c[1]) ** 2 + (yy - c[2]) ** 2 <= (r * 1.0) ** 2
        # iris = tout ce qui est brun-orangé dans l'œil (y compris ses reflets clairs) ; ni le blanc, ni la peau, ni la pupille noire
        brun = (H > 5) & (H < 45) & (S > 0.3) & (V > 0.12) & ((V < 0.8) | (S > 0.6))
        iris |= disk & brun & ~z["G"]
    return eyes, iris


def shirt_layers(shirt, im, name):
    """Pour changer la tenue en direct : luminosité du vêtement SANS les étoiles (ombres et plis gardés),
    masque des étoiles, et géométrie de l'encolure. Fichier <nom>.shirt.png : R = luminosité, G = étoiles."""
    H, S, V = hsv(im)
    L = np.asarray(im.convert("L")).astype(np.float32) / 255
    from scipy.ndimage import median_filter
    Lm = median_filter(np.asarray(im.convert("L")).astype(np.float32) / 255, size=15)
    stars = shirt & (((S < 0.5) & (V > 0.66)) | (np.asarray(im.convert("L")).astype(np.float32) / 255 > Lm + 0.07))
    stars = np.asarray(Image.fromarray((stars * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 127
    keep = (shirt & ~stars).astype(np.float32)
    num, den = L * keep, keep.copy()
    for r in (4, 8, 16):                                   # on bouche les étoiles avec la luminosité voisine
        from scipy.ndimage import gaussian_filter
        bn, bd = gaussian_filter(num, r), gaussian_filter(den, r)
        fill = bn / np.maximum(bd, 1e-4)
        num = np.where(den > 0, num, fill * (bd > 0.02)); den = np.where(den > 0, den, (bd > 0.02).astype(np.float32))
    plain = np.where(shirt, np.where(stars, num, L), 0)
    out = np.stack([plain * 255, stars * 255, np.zeros_like(plain)], -1).astype(np.uint8)
    Image.fromarray(out).save(f"static/avatars/{name}.shirt.png", optimize=True)
    ys, xs = np.nonzero(shirt)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    top = np.array([ys[xs == x].min() if (xs == x).any() else SIZE for x in range(SIZE)])
    mid = np.arange(int(x0 + (x1 - x0) * 0.3), int(x0 + (x1 - x0) * 0.7))
    ref = np.median(top[mid])
    hole = mid[top[mid] > ref + 0.4 * (top[mid].max() - ref)] if top[mid].max() > ref + 8 else mid[top[mid] >= top[mid].max() - 4]
    nx = float(hole.mean()); hw = float((hole.max() - hole.min()) / 2 + 6); ny = float(top[hole].max())
    if ny > 370 or hw < 22 or x1 - x0 < 240:            # cheveux longs sur les épaules : même buste que les autres modèles
        nx, ny, hw, (x0, y0, x1, y1) = 248.0, 360.0, 30.0, (104, 304, 392, 464)
    return {"neck": [round(nx, 1), round(ny, 1)], "hw": round(hw, 1), "box": [x0, y0, x1, y1],
            "lum": round(float(np.median(plain[shirt & ~stars])), 3)}


def animal(im):
    A = np.asarray(im)[..., 3] > 30
    H, S, V = hsv(im)
    feat = V < 0.28                                           # yeux, truffe, contours
    main = A & ~feat & (S > 0.42)
    light = A & ~feat & ~main & (V > 0.6) & (S < 0.42)
    return {"R": main, "G": light, "B": np.zeros_like(A)}


def doudou(im):
    A = np.asarray(im)[..., 3] > 30
    H, S, V = hsv(im)
    bow = largest(A & ((H < 14) | (H > 345)) & (S > 0.55) & (V > 0.3))   # le nœud seulement (pas le nez ni l'intérieur des oreilles)
    bow = fill_holes(close(bow, 5)) & A
    blue = A & ~bow & (H > 140) & (H < 290) & (S > 0.012)
    grey_hl = A & ~bow & ~blue & (S < 0.22) & (V > 0.35) & (local_mean(blue.astype(np.float32), 8) > 0.2)
    cream = (H > 22) & (H < 65) & (S > 0.1)
    pinkish = ((H < 20) | (H > 330)) & (S > 0.12)
    body = close(blue | grey_hl, 7) & A & ~bow & ~(cream & (S > 0.16)) & ~(pinkish & (S > 0.2)) & (V > 0.2)
    return {"R": body, "G": np.zeros_like(A), "B": bow}


def main():
    stats = {}
    for f in sorted(glob.glob("style/avatars/*.png")):
        name = os.path.basename(f)[:-4]
        im = Image.open(f).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
        zones = child(im) if name.startswith("enfant") else animal(im) if name.startswith("animal") else doudou(im)
        extra = {}
        if name.startswith("enfant"):
            eyes, iris = find_eyes(zones, im)
            if eyes:
                extra["eyes"] = eyes
                yy, xx = np.mgrid[0:SIZE, 0:SIZE]
                for ex, ey, er in eyes:                    # jamais de couleur de cheveux sur les yeux, cils et sourcils proches
                    zones["R"] &= ~((xx - ex) ** 2 + (yy - ey) ** 2 <= (er * 1.9) ** 2)
                Image.fromarray((blur(iris.astype(np.float32), 0.8) * 255).astype(np.uint8)).save(f"static/avatars/{name}.eyes.png", optimize=True)
                zones["E"] = iris
        if name.startswith("enfant"):
            extra["tenue"] = shirt_layers(zones["B"], im, name)
        rgb = np.asarray(im.convert("RGB")).astype(np.float32)
        st = {}
        for k, m in zones.items():
            if k.startswith("_"): continue
            if m.any():
                hs = np.asarray(im.convert("RGB").convert("HSV")).astype(np.float32)[m]
                # moyenne en HSL simplifiée : on stocke la couleur médiane RGB de la zone
                st[k] = [int(v) for v in np.median(rgb[m], axis=0)]
        stats[name] = dict(st, **extra)
        out = np.stack([blur(zones[k].astype(np.float32)) for k in "RGB"], -1)
        Image.fromarray((out * 255).astype(np.uint8)).save(f"static/avatars/{name}.mask.png", optimize=True)
    json.dump(stats, open("static/avatars/masks.json", "w"), indent=1)
    print(len(stats), "masques")


if __name__ == "__main__":
    main()
