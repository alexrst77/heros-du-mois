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
    zone = fill_holes(largest(close(core, 15))) & A                     # tout le vêtement (ombres et étoiles comprises)
    strand = (H > 4) & (H < 31) & (S > 0.35) & (V < 0.72)               # mèches de cheveux posées sur le vêtement
    shirt = zone & ~strand
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
    face = fill_holes(skinreg) & A & ~shirt
    feat = face & ~skinreg & (V < 0.6)                                 # yeux, sourcils, bouche : on n'y touche pas
    skin = skinreg & warm & (S > 0.08) & (V > 0.6)
    hairlike = (((H > 4) & (H < 46)) | (V < 0.35)) & (S > 0.2) & (V < 0.9)
    hair = A & ~shirt & ~skin & ~feat & hairlike
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
        disk = (xx - c[1]) ** 2 + (yy - c[2]) ** 2 <= (r * 0.82) ** 2
        # iris seulement : ni la pupille noire, ni les reflets, ni les cils et paupières (sombres et peu saturés)
        iris |= disk & (V > 0.08) & ~((V > 0.6) & (S < 0.3))       # ni la pupille, ni le blanc de l'œil, ni les reflets
    return eyes, iris


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
                Image.fromarray((blur(iris.astype(np.float32), 0.8) * 255).astype(np.uint8)).save(f"static/avatars/{name}.eyes.png", optimize=True)
                zones["E"] = iris
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
