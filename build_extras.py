# -*- coding: utf-8 -*-
"""Compléments des avatars peints (à lancer après build_masks.py) : tout ce que l'éditeur montre en direct en plus des couleurs.
- doudous sans nœud (<nom>-nu.webp) : base de « aucun accessoire » et de l'écharpe, nœud effacé (fourrure reconstituée) ;
- géométrie de l'écharpe des doudous (autour du cou, à la place du nœud) ;
- yeux des animaux (<nom>.eyes.png) : iris recolorable, pupille et reflets gardés ;
- géométrie du collier des animaux (courbe sous le menton) et position des yeux (motif « masque »).
Sortie : fichiers dans static/avatars/ et entrées ajoutées à static/avatars/masks.json."""
import json
import numpy as np
from PIL import Image
from scipy import ndimage as nd
import cv2

AV = "static/avatars/"
DOUDOUS = ["doudou-lapin", "doudou-ours", "doudou-chat", "doudou-chien", "doudou-elephant"]
EYES = {"animal-chat": [(204, 132), (255, 114)], "animal-chien": [(232, 119), (283, 94)], "animal-hamster": [(226, 142), (297, 120)],
        "animal-lapin": [(250, 178), (320, 160)], "animal-oiseau": [(264, 113), (327, 135)]}
# collier : courbe (début, contrôle, fin) dans l'espace 480 px, demi-épaisseur ; relevé sur chaque modèle peint
COLLIERS = {"animal-chat": {"p0": [150, 214], "c": [222, 238], "p1": [292, 196], "hw": 6.5},
            "animal-chien": {"p0": [204, 214], "c": [262, 236], "p1": [322, 204], "hw": 6.5},
            "animal-hamster": {"p0": [176, 214], "c": [252, 236], "p1": [326, 206], "hw": 6},
            "animal-lapin": {"p0": [268, 240], "c": [312, 258], "p1": [366, 234], "hw": 5.5}}


def nobow(n):
    im = np.array(Image.open(AV + f"{n}.webp").convert("RGBA"))
    m = np.array(Image.open(AV + f"{n}.mask.png").convert("RGB").resize(im.shape[1::-1]))
    mask = cv2.dilate((m[..., 2] > 40).astype(np.uint8) * 255, np.ones((5, 5), np.uint8), iterations=2)
    rgb = im[..., :3].astype(np.float32)
    low = cv2.cvtColor(cv2.inpaint(cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2BGR), mask, 15, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB).astype(np.float32)
    low = cv2.GaussianBlur(low, (0, 0), 3)
    ys, xs = np.where(mask > 0)
    src = np.roll(rgb, -(ys.max() - ys.min() + 8), axis=0)          # grain de la fourrure pris juste en dessous
    fill = np.clip(low + src - cv2.GaussianBlur(src, (0, 0), 3), 0, 255)
    w = cv2.GaussianBlur(mask.astype(np.float32) / 255, (0, 0), 2)[..., None]
    Image.fromarray(np.dstack([(rgb * (1 - w) + fill * w).astype(np.uint8), im[..., 3]])).save(AV + f"{n}-nu.webp", quality=92)
    m2 = m.copy(); m2[..., 2] = 0
    Image.fromarray(m2).save(AV + f"{n}-nu.mask.png")
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
    ech = {"p0": [round(cx - half * 1.05), round(cy - half * .32)], "c": [round(cx), round(cy + half * .42)],
           "p1": [round(cx + half * 1.05), round(cy - half * .32)], "hw": round(half * .26, 1),
           "tail": {"p0": [round(cx + half * .42), round(cy + half * .1)], "c": [round(cx + half * .62), round(cy + half * .7)],
                    "p1": [round(cx + half * .5), round(cy + half * 1.25)], "hw": round(half * .2, 1)}}
    return ech


def eye_mask(n):
    im = np.asarray(Image.open(AV + f"{n}.webp").convert("RGBA")).astype(float) / 255
    rgb = im[..., :3]; mx = rgb.max(-1); mn = rgb.min(-1); l = (mx + mn) / 2
    H, W = l.shape; yy, xx = np.mgrid[0:H, 0:W]
    out = np.zeros((H, W))
    lmax = 0.72 if n == "animal-chat" else 0.58          # iris vert clair du chat
    for (cx, cy) in EYES[n]:
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (d2 > 24 ** 2) & (d2 < 32 ** 2) & (im[..., 3] > .9)
        fur = np.median(rgb[ring], axis=0)
        cand = (np.sqrt(((rgb - fur) ** 2).sum(-1)) > .22) & (d2 < 24 ** 2)
        lab, _ = nd.label(cand)
        ys, xs = np.where((l < .2) & (d2 < 8 ** 2))
        eye = nd.binary_fill_holes(nd.binary_closing(np.isin(lab, list(set(lab[ys, xs]) - {0})), iterations=2))
        iris = nd.binary_opening(eye & (l > .07) & (l < lmax), iterations=1)
        lab2, _ = nd.label(iris)
        keep = (set(lab2[ys, xs]) | set(lab2[max(0, cy - 6):cy + 7, max(0, cx - 6):cx + 7].ravel())) - {0}
        out = np.maximum(out, np.isin(lab2, list(keep)))
    out = nd.gaussian_filter(out.astype(float), .7)
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(AV + f"{n}.eyes.png")


if __name__ == "__main__":
    st = json.load(open(AV + "masks.json"))
    for n in DOUDOUS:
        ech = nobow(n)
        st[n]["echarpe"] = ech
        st[n + "-nu"] = {k: v for k, v in st[n].items() if k != "B"}
    for n in EYES:
        eye_mask(n)
        st[n]["yeux"] = [list(p) for p in EYES[n]]
        st[n]["E"] = True
        if n in COLLIERS:
            st[n]["collier"] = COLLIERS[n]
    json.dump(st, open(AV + "masks.json", "w"), indent=1)
    print("ok")
