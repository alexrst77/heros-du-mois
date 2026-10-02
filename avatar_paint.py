# -*- coding: utf-8 -*-
"""Avatar peint personnalisé, calculé côté serveur. C'est exactement le même calcul que l'aperçu du navigateur
(static/avatar.js, fonction paint) : cheveux, peau, yeux, tenue (type et couleur) et taches de rousseur.
Il sert de base aux portraits du livre, pour que le livre reprenne ce que le parent a vu à l'écran."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

AV = Path(__file__).parent / "static" / "avatars"
_MST = None
WHITE = "#F4F0E6"


def mst():
    global _MST
    if _MST is None:
        _MST = json.loads((AV / "masks.json").read_text())
    return _MST


def hexrgb(c):
    c = c.lstrip("#"); return np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def rgb2hsl(r, g, b):
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    l = (mx + mn) / 2; d = mx - mn
    s = np.where(d == 0, 0, d / np.maximum(1e-6, 1 - np.abs(2 * l - 1)))
    dd = np.maximum(d, 1e-6)
    h = np.where(d == 0, 0, np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4))) / 6
    return h % 1, np.clip(s, 0, 1), l


def hsl2rgb(h, s, l):
    c = (1 - np.abs(2 * l - 1)) * s; hp = (h % 1) * 6; x = c * (1 - np.abs(hp % 2 - 1)); m = l - c / 2
    z = np.zeros_like(hp); i = np.floor(hp).astype(int) % 6
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [c, x, z, z, x, c])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [x, c, c, x, z, z])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [z, z, x, c, c, x])
    return r + m, g + m, b + m


def light_map(l, lb, lt):
    """Luminosité : on garde le relief peint. Plus foncé : proportionnel ; plus clair : décalé, sans aplatir."""
    return np.where(lt <= lb, l * lt / max(lb, 1e-3), np.clip(min(lt, 0.72) + (l - lb) * 0.8, 0, 0.96)) if np.ndim(lt) == 0 \
        else np.where(lt <= lb, l * lt / max(lb, 1e-3), np.clip(np.minimum(lt, 0.72) + (l - lb) * 0.8, 0, 0.96))


def shift_zone(rgb, w, base, target):
    """Recolore une zone (cheveux, peau…) en gardant texture et lumière."""
    r, g, b = rgb
    hb, sb, lb = [float(v) for v in rgb2hsl(*[np.array(v / 255) for v in base])]
    ht, st, lt = [float(v) for v in rgb2hsl(*hexrgb(target))]
    h, s, l = rgb2hsl(r, g, b)
    ks = st / max(sb, .05)
    h = (h + ht - hb) % 1; s = np.minimum(1, s * (min(1, ks) if lt > lb else ks))
    r2, g2, b2 = hsl2rgb(h, s, light_map(l, lb, lt))
    return r * (1 - w) + r2 * w, g * (1 - w) + g2 * w, b * (1 - w) + b2 * w


def iris(rgb, w, target):
    r, g, b = rgb
    ht, st, lt = [float(v) for v in rgb2hsl(*hexrgb(target))]
    h, s, l = rgb2hsl(r, g, b)
    s2 = min(1, st * 1.2) * np.clip((l - 0.06) / 0.22, 0, 1)
    r2, g2, b2 = hsl2rgb(np.full_like(h, ht), s2, light_map(l, 0.33, min(lt, 0.55)))
    return r * (1 - w) + r2 * w, g * (1 - w) + g2 * w, b * (1 - w) + b2 * w


def tenue_fill(kind, color, geo, size):
    """Couleur de chaque point du vêtement selon le type de tenue (avant ombrage)."""
    hh, ww = size
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    k = ww / 480.0
    nx, ny = geo["neck"][0] * k, geo["neck"][1] * k; hw = geo["hw"] * k
    x0, y0, x1, y1 = [v * k for v in geo["box"]]
    main, white = hexrgb(color), hexrgb(WHITE)
    fill = np.broadcast_to(main, (hh, ww, 3)).copy()
    extra = np.zeros((hh, ww), np.float32)           # détails peints par-dessus (boutons, cordons) : -1 sombre, +1 clair
    if kind == "mariniere":
        band = (y1 - y0) / 9.5
        stripe = (((yy - y0) / band) % 2) < 1
        fill[stripe] = white
    elif kind == "salopette":
        fill[:] = white
        bib_top = ny + 38 * k
        strap = (np.abs(np.abs(xx - nx) - (hw + 30 * k)) < 12 * k) & (yy < bib_top + 4 * k)
        bib = (np.abs(xx - nx) < 62 * k) & (yy >= bib_top)
        fill[strap | bib] = main
        for sx in (-1, 1):
            bx, by = nx + sx * (hw + 30 * k), bib_top + 2 * k
            extra[((xx - bx) ** 2 + (yy - by) ** 2) < (6 * k) ** 2] = 1
    elif kind == "sweat":
        d = np.sqrt(((xx - nx) / (hw + 14 * k)) ** 2 + ((yy - ny + 18 * k) / (46 * k)) ** 2)
        extra[(d > 0.8) & (d < 1.08) & (yy < ny + 30 * k)] = -1                      # bord-côte de l'encolure
        for sx in (-1, 1):
            cx = nx + sx * 13 * k
            extra[(np.abs(xx - cx) < 2.6 * k) & (yy > ny + 4 * k) & (yy < ny + 52 * k)] = 1   # cordons
    elif kind == "robe":
        for sx in (-1, 1):                                   # col Claudine : deux pans arrondis autour du cou
            cx, cy = nx + sx * hw * 0.78, ny - 2 * k
            lobe = ((xx - cx) / (hw * 1.2)) ** 2 + ((yy - cy) / (30 * k)) ** 2 < 1
            fill[lobe] = white
    return fill, extra


def paint(name, t):
    """t : {'R': cheveux, 'G': peau, 'E': yeux, 'B': couleur tenue, 'tenue': type} -> image RGBA (Pillow)."""
    im = Image.open(AV / f"{name}.webp").convert("RGBA")
    px = np.asarray(im).astype(np.float32) / 255
    size = im.size[::-1]
    M = np.asarray(Image.open(AV / f"{name}.mask.png").convert("RGB").resize(im.size)).astype(np.float32) / 255
    st = mst().get(name, {})
    rgb = (px[..., 0], px[..., 1], px[..., 2])
    for i, k in enumerate("RG"):
        if t.get(k) and k in st:
            rgb = shift_zone(rgb, M[..., i], st[k], t[k])
    if t.get("E") and (AV / f"{name}.eyes.png").exists():
        E = np.asarray(Image.open(AV / f"{name}.eyes.png").convert("L").resize(im.size)).astype(np.float32) / 255
        rgb = iris(rgb, E, t["E"])
    kind = t.get("tenue") or "pyjama"
    if (t.get("B") or kind != "pyjama") and "B" in st:
        w = M[..., 2]
        if kind == "pyjama" or "tenue" not in st:     # pyjama étoilé : le modèle d'origine, recoloré
            if t.get("B"): rgb = shift_zone(rgb, w, st["B"], t["B"])
        else:
            sh = np.asarray(Image.open(AV / f"{name}.shirt.png").convert("RGB").resize(im.size)).astype(np.float32) / 255
            lum = sh[..., 0]; lb = st["tenue"]["lum"]
            fill, extra = tenue_fill(kind, t.get("B") or "#E9B840", st["tenue"], size)
            fh, fs, fl = rgb2hsl(fill[..., 0], fill[..., 1], fill[..., 2])
            l2 = light_map(lum, lb, fl)
            l2 = np.where(extra > 0, np.clip(l2 * 0.25 + 0.72, 0, 0.95), np.where(extra < 0, l2 * 0.78, l2))
            r2, g2, b2 = hsl2rgb(fh, fs, np.clip(l2, 0, 1))
            r, g, b = rgb
            rgb = (r * (1 - w) + r2 * w, g * (1 - w) + g2 * w, b * (1 - w) + b2 * w)
    out = np.dstack([*rgb, px[..., 3]])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")
