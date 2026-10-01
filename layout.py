# -*- coding: utf-8 -*-
"""Moteur de mise en page « Mon Héros du Mois ».
- Illustrations pleine page ; le texte se pose dans la zone la plus calme (indice du storyboard + analyse de l'image).
- Fondu continu (distance douce, courbe « smootherstep »), teinte prélevée dans le décor, opacité calculée pour la lisibilité,
  tramage anti-stries, halo doux sous les lettres au lieu d'un bandeau.
- Pages chapitre : décor d'ambiance (images générées) ou ambiance procédurale tirée de la palette de la scène.
- Typographie adaptative (taille, retours à la ligne, espaces insécables) + contrôle qualité chiffré."""
from pathlib import Path
import io, math, random, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

import art

ROOT = Path(__file__).parent
FONTS = {"Serif": "DejaVuSerif.ttf", "Serif-Bold": "DejaVuSerif-Bold.ttf", "Sans": "DejaVuSans.ttf"}
for n, f in FONTS.items():
    pdfmetrics.registerFont(TTFont(n, str(ROOT / "fonts" / f)))

PAGE, PX, M = art.PAGE, art.PX, art.MARGIN
K = PX / PAGE                                   # pixels par point
B = 0.0                                         # fond perdu de la page en cours (0 à l'écran, 9 pt à l'impression)


def set_mode(mode):
    """'ecran' : 8,5 pouces sans fond perdu ; 'impression' : fond perdu 0,125 pouce et 300 dpi."""
    global PX, K, B
    PX = art.PX_PRINT if mode == "impression" else art.PX
    K = PX / PAGE
    B = art.BLEED if mode == "impression" else 0.0
NBSP = " "


# ============================================================ texte
def frenchify(s):
    s = re.sub(r"\s+([!?;:»%])", NBSP + r"\1", s)
    s = re.sub(r"«\s+", "«" + NBSP, s)
    s = re.sub(r"\s+—", NBSP + "—", s)
    return s


def _w(t, font, size):
    return pdfmetrics.stringWidth(t, font, size)


def wrap(text, font, size, width):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = w if not cur else cur + " " + w
        if _w(t, font, size) <= width or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def wrap_para(text, font, size, width):
    """Retour à la ligne avec contrôle des veuves (dernier mot seul)."""
    out = []
    for part in text.split("\n"):
        lines = wrap(part, font, size, width)
        wd = width
        for _ in range(4):
            if len(lines) > 1 and len(lines[-1].split(" ")) == 1:
                wd *= 0.94; lines = wrap(part, font, size, wd)
            else:
                break
        out += lines
    return out


def layout_block(paras, spec, width, size=None):
    size = size or spec["size"]
    lead = size * spec["leading"]
    gap = lead * 0.55
    lines, y = [], 0.0
    for i, p in enumerate(paras):
        if i:
            y += gap
        for ln in wrap_para(frenchify(p), spec["font"], size, width):
            lines.append((ln, y)); y += lead
    return dict(lines=lines, height=y - (lead - size * 1.18), size=size, lead=lead, font=spec["font"], width=width)


def fit_block(paras, spec, width, max_h, prefer=None):
    size = prefer or spec["size"]
    b = layout_block(paras, spec, width, size)
    while b["height"] > max_h and size > spec["min"]:
        size = round(size - 0.25, 2); b = layout_block(paras, spec, width, size)
    while b["height"] < max_h * 0.5 and size < spec["max"]:
        nb = layout_block(paras, spec, width, size + 0.5)
        if nb["height"] > max_h * 0.62:
            break
        size += 0.5; b = nb
    b["overflow"] = b["height"] > max_h + 0.5
    return b


def ascent(font):
    return pdfmetrics.getFont(font).face.ascent / 1000.0


# ============================================================ image
def load(path):
    im = Image.open(path).convert("RGB")
    im.info.pop("icc_profile", None)
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    im = im.resize((PX, PX), Image.LANCZOS)
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=45, threshold=2))


def _lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rel_lum(arr):
    l = _lin(arr.astype(np.float32))
    return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]


class Analysis:
    def __init__(self, im):
        small = np.asarray(im.resize((256, 256), Image.BILINEAR)).astype(np.float32)
        self.small = small
        self.lum = rel_lum(small)
        g = small.mean(-1)
        gx = np.abs(np.diff(g, axis=1, append=g[:, -1:])); gy = np.abs(np.diff(g, axis=0, append=g[-1:, :]))
        det = Image.fromarray(np.clip((gx + gy) * 3, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4))
        self.detail = np.asarray(det).astype(np.float32) / 255.0
        # peau (visages, mains) : à protéger, jamais sous le texte
        hsv = np.asarray(Image.fromarray(small.astype(np.uint8)).convert("HSV")).astype(np.float32)
        h, sat, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
        skin = (h > 4) & (h < 36) & (sat > 0.18) & (sat < 0.68) & (v > 0.5)
        self.skin = np.asarray(Image.fromarray((skin * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))).astype(np.float32) / 255

    def _sl(self, r):
        x0, y0, x1, y1 = [int(max(0, min(256, v / PAGE * 256))) for v in r]
        return slice(y0, max(y0 + 1, y1)), slice(x0, max(x0 + 1, x1))

    def region(self, r):
        sy, sx = self._sl(r)
        return self.small[sy, sx], self.lum[sy, sx], self.detail[sy, sx]

    def skin_in(self, r):
        sy, sx = self._sl(r)
        return float(self.skin[sy, sx].mean())


def tint_from(pix, dark=True):
    med = np.median(pix.reshape(-1, 3), axis=0) / 255.0
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*med)
    if dark:
        s = min(0.62, s * 1.15 + 0.05); v = 0.13 + 0.05 * min(1, s)
    else:
        s = min(0.18, s * 0.5); v = 0.96
    return np.array(colorsys.hsv_to_rgb(h, s, v)) * 255.0


def smootherstep(t):
    t = np.clip(t, 0, 1)
    return t * t * t * (t * (t * 6 - 15) + 10)


def soft_rect_mask(rect, feather, extend=()):
    """Masque doux (0..1) autour d'un rectangle (pt) : distance euclidienne, transition smootherstep. Rien de rayé."""
    x0, y0, x1, y1 = rect
    if "left" in extend: x0 = -PAGE
    if "right" in extend: x1 = 2 * PAGE
    if "top" in extend: y0 = -PAGE
    if "bottom" in extend: y1 = 2 * PAGE
    ax = (np.arange(PX, dtype=np.float32) + 0.5) / K
    dx = np.maximum(np.maximum(x0 - ax, 0), ax - x1)
    dy = np.maximum(np.maximum(y0 - ax, 0), ax - y1)
    d = np.sqrt(dy[:, None] ** 2 + dx[None, :] ** 2)
    return 1.0 - smootherstep(d / max(feather, 1))


def compose(im, mask, alpha, tint):
    arr = np.asarray(im).astype(np.float32)
    a = (mask * alpha)[..., None]
    return arr * (1 - a) + tint[None, None, :] * a


def text_mask(blocks):
    """Masque des lettres (pour le halo), rendu avec les mêmes polices que le PDF."""
    m = Image.new("L", (PX, PX), 0)
    d = ImageDraw.Draw(m)
    for b in blocks:
        f = ImageFont.truetype(str(ROOT / "fonts" / FONTS[b["font"]]), int(round(b["size"] * K)))
        for ln, x, base in b["placed"]:
            d.text((x * K, base * K), ln, font=f, fill=255, anchor="ls")
    return m


def finish(arr):
    """Tramage triangulaire (±1 niveau) avant quantification : supprime les stries des dégradés."""
    n = (np.random.random(arr.shape[:2]) - np.random.random(arr.shape[:2]))[..., None]
    return Image.fromarray(np.clip(arr + n, 0, 255).astype(np.uint8))


def contrast(lum_bg, ink_lum):
    hi, lo = max(lum_bg, ink_lum), min(lum_bg, ink_lum)
    return (hi + 0.05) / (lo + 0.05)


INK_LUM = {"dark": 0.90, "light": 0.02}   # clé = mode du voile (voile sombre -> encre ivoire)


# ============================================================ composition d'une zone de texte
def place_block(b, x, top):
    a = ascent(b["font"])
    b["placed"] = [(ln, x, top + y + b["size"] * a) for ln, y in b["lines"]]
    b["rect"] = (x - 2, top - 2, x + b["width"] + 2, top + b["height"] + 4)
    return b


HALO_NEAR = 0.35      # assombrissement moyen apporté par le halo au contact des lettres
TARGET = {"dark": 0.14, "light": 0.32}   # luminance (linéaire) du fond pour un contraste >= 5:1


def needed_alpha(pix, tint, mode):
    """Plus petite opacité de voile qui rend le fond lisible (recherche exacte sur les pixels de la zone)."""
    p = pix.reshape(-1, 3)
    lo, hi = 0.0, 1.0
    for _ in range(14):
        a = (lo + hi) / 2
        eff = 1 - (1 - a) * (1 - HALO_NEAR)
        lum = rel_lum((p * (1 - eff) + tint * eff)[None])[0]
        ok = np.percentile(lum, 92) <= TARGET["dark"] if mode == "dark" else np.percentile(lum, 8) >= TARGET["light"]
        hi, lo = (a, lo) if ok else (hi, a)
    return hi


def treat_text_area(im, an, blocks, zone_rect, extend, feather, mode=None, strength=1.0):
    """Assombrit (ou éclaircit) juste ce qu'il faut autour du texte, avec une teinte du décor, puis ajoute un halo."""
    pix, lum, det = an.region(zone_rect)
    dark_tint, light_tint = tint_from(pix, True), tint_from(pix, False)
    nd, nl = needed_alpha(pix, dark_tint, "dark"), needed_alpha(pix, light_tint, "light")
    if mode is None:
        mode = "light" if nl + 0.15 < nd else "dark"
    need = nd if mode == "dark" else nl
    alpha = float(np.clip(need, art.FADE["min_alpha"], art.FADE["max_alpha"])) * strength
    tint = dark_tint if mode == "dark" else light_tint
    mask = soft_rect_mask(zone_rect, feather, extend)
    tm = text_mask(blocks)
    fs = max(b["size"] for b in blocks) * K
    halo = tm.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(fs * 0.55))
    h = (np.clip(np.asarray(halo).astype(np.float32) / 255.0 * 1.8, 0, 1) * art.FADE["halo_alpha"])[..., None]
    tmk = np.asarray(tm.filter(ImageFilter.MaxFilter(9)))[::4, ::4] > 0
    goal = art.MIN_CONTRAST + 0.3
    for _ in range(6):   # boucle fermée : on mesure le vrai contraste et on corrige juste ce qu'il faut
        arr = compose(im, mask, alpha, tint)
        arr = arr * (1 - h) + tint[None, None, :] * h
        lum_after = rel_lum(arr[::4, ::4])
        bgl = float(np.percentile(lum_after[tmk], 90)) if tmk.any() else 0.0
        cr = contrast(bgl, INK_LUM[mode])
        if cr >= goal or alpha >= art.FADE["max_alpha"]:
            break
        alpha = min(art.FADE["max_alpha"], alpha + max(0.06, 0.5 * (goal - cr) / goal))
    return finish(arr), mode, dict(voile=round(alpha, 2), contrast=round(cr, 2), mode=mode)


def draw_blocks(c, blocks, colors):
    for b, col in zip(blocks, colors):
        c.setFont(b["font"], b["size"]); c.setFillColorRGB(*col)
        for ln, x, base in b["placed"]:
            c.drawString(x, PAGE - base, ln)


def bg(c, im):
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=93, subsampling=0); buf.seek(0)
    c.drawImage(ImageReader(buf), -B, -B, PAGE + 2 * B, PAGE + 2 * B)


def folio(c, n, mode):
    c.setFont("Sans", 8)
    c.setFillColorRGB(*((0.86, 0.81, 0.68) if mode == "dark" else (0.35, 0.3, 0.26)))
    c.drawCentredString(PAGE / 2, art.SAFE, str(n))


# ============================================================ pages illustrées
def zone_geometry(zone, b_height, width):
    if zone == "bas":
        return (M, PAGE - 52 - b_height), ("left", "right", "bottom")
    if zone == "haut":
        return (M, 46), ("left", "right", "top")
    if zone == "gauche":
        return (M, (PAGE - b_height) / 2 - 10), ("left",)
    return (PAGE - M - width, (PAGE - b_height) / 2 - 10), ("right",)


def picture_page(c, im, paras, hint=None, num=None):
    an = Analysis(im)
    words = sum(len(p.split()) for p in paras)
    cands = ["bas", "haut"] + (["gauche", "droite"] if words <= 38 else [])
    best = None
    for z in cands:
        width = PAGE - 2 * M if z in ("bas", "haut") else PAGE * 0.38 - M * 0.5
        max_h = PAGE * (0.36 if z in ("bas", "haut") else 0.62)
        b = fit_block(paras, art.BODY, width, max_h)
        (x, top), ext = zone_geometry(z, b["height"], width)
        r = (x - 14, top - 12, x + width + 14, top + b["height"] + 12)
        pix, lum, det = an.region(r)
        need = needed_alpha(pix, tint_from(pix, True), "dark")
        score = float(det.mean()) + 2.0 * an.skin_in(r) + 0.45 * need + (0.04 if z in ("gauche", "droite") else 0)
        if z == hint:
            score *= 0.72                         # le storyboard a prévu cette zone à la composition
        if b["overflow"]:
            score += 1
        if best is None or score < best[0]:
            best = (score, z, b, (x, top), ext, r)
    _, z, b, (x, top), ext, r = best
    place_block(b, x, top)
    feather = max(art.FADE["feather_pt"], 0.85 * b["height"])
    if z in ("bas", "haut"):
        feather = min(feather, PAGE * 0.5 - b["height"])
    img, mode, q = treat_text_area(im, an, [b], r, ext, feather)
    bg(c, img)
    draw_blocks(c, [b], [art.INK_LIGHT if mode == "dark" else art.INK_DARK])
    if num:
        folio(c, num, mode if z == "bas" else "dark")
    q.update(zone=z, taille=b["size"], debordement=b["overflow"])
    return q


# ============================================================ ambiance des pages chapitre
def palette(im):
    a = np.asarray(im.resize((64, 64))).reshape(-1, 3).astype(np.float32)
    lum = a.mean(1)
    base = np.median(a, axis=0)
    hi = np.median(a[lum >= np.percentile(lum, 96)], axis=0)
    return base, hi


def ornaments(univers):
    u = (univers or "").lower()
    if "espace" in u or "étoile" in u: return "stars"
    if "mer" in u: return "bubbles"
    if "pôle" in u or "neige" in u: return "snow"
    if "château" in u: return "lights"
    return "leaves"


def _palette_colors(scene, n=6):
    q = scene.resize((48, 48)).quantize(n, method=Image.Quantize.MEDIANCUT).convert("RGB")
    cols = sorted({c for _, c in q.getcolors(48 * 48)}, key=lambda c: sum(c))
    return [np.array(c, dtype=np.float32) for c in cols]


def _leaf(d, cx, cy, L, W, ang, col, vein):
    pts = [(t * L, math.sin(t * math.pi) ** 0.8 * W / 2) for t in np.linspace(0, 1, 22)]
    pts += [(t * L, -math.sin(t * math.pi) ** 0.8 * W / 2) for t in np.linspace(1, 0, 22)]
    ca, sa = math.cos(ang), math.sin(ang)
    d.polygon([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts], fill=col)
    d.line([(cx, cy), (cx + L * 0.92 * ca, cy + L * 0.92 * sa)], fill=vein, width=4)


def procedural_ambiance(scene, univers, seed):
    """Décor d'ambiance SANS personnage : couleurs de la scène en nappes douces, feuillages/étoiles/bulles selon
    l'univers sur les bords, lumières dorées ; le centre reste calme pour le texte."""
    rnd = random.Random(seed)
    cols = _palette_colors(scene, 8)
    # couleur de fond : la teinte la plus saturée parmi les tons sombres de la scène (évite les bruns ternes)
    import colorsys
    darks = sorted(cols, key=lambda c: -colorsys.rgb_to_hsv(*(c / 255))[1] if sum(c) < 420 else 1)
    h0, s0, _ = colorsys.rgb_to_hsv(*(darks[0] / 255))
    base = np.array(colorsys.hsv_to_rgb(h0, min(0.75, s0 * 1.2 + 0.1), 0.2)) * 255
    arr = np.ones((PX // 8, PX // 8, 3), np.float32) * base
    yy, xx = np.mgrid[0:PX // 8, 0:PX // 8].astype(np.float32)
    for _ in range(7):                                   # nappes de couleur (aucune forme reconnaissable)
        c = cols[rnd.randrange(len(cols))] * rnd.uniform(0.55, 0.85)
        cx, cy = rnd.choice([rnd.uniform(0, 64), rnd.uniform(192, 256)]), rnd.uniform(0, 256)
        r = rnd.uniform(60, 140)
        w = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))[..., None] * rnd.uniform(0.35, 0.6)
        arr = arr * (1 - w) + c * w
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize((PX, PX), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30))
    a = np.asarray(img).astype(np.float32)
    vign = 1 - 0.32 * (((xx * 8 / PX - 0.5) ** 2 + (yy * 8 / PX - 0.46) ** 2) * 2)
    a *= np.asarray(Image.fromarray((np.clip(vign, 0, 1) * 255).astype(np.uint8)).resize((PX, PX), Image.BICUBIC)).astype(np.float32)[..., None] / 255
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
    hi = cols[-1]; hi_c = tuple(int(v) for v in np.clip(hi * 0.6 + np.array([255, 214, 140]) * 0.4, 0, 255))
    kind = ornaments(univers)
    if kind == "leaves":
        greens = [c for c in cols if c[1] >= c[0] * 0.9] or cols
        for depth, (n, blur, dim) in enumerate([(28, 9, 1.0), (24, 0, 0.62)]):   # plan lointain flou, puis premier plan
            layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
            for _ in range(n):
                side = rnd.choice(["tl", "tr", "bl", "br", "t", "l", "r", "b"])
                cx = {"tl": 0, "bl": 0, "l": 0, "tr": PX, "br": PX, "r": PX}.get(side, rnd.uniform(0, PX)) + rnd.uniform(-120, 120)
                cy = {"tl": 0, "tr": 0, "t": 0, "bl": PX, "br": PX, "b": PX}.get(side, rnd.uniform(0, PX)) + rnd.uniform(-120, 120)
                toward = math.atan2(PX / 2 - cy, PX / 2 - cx) + rnd.uniform(-0.9, 0.9)
                L = rnd.uniform(260, 620) * (1.2 if depth else 0.9); W = L * rnd.uniform(0.3, 0.46)
                g = greens[rnd.randrange(len(greens))] * dim * rnd.uniform(0.8, 1.15)
                col = tuple(int(min(255, v)) for v in g) + (int(rnd.uniform(200, 250)),)
                vein = tuple(int(min(255, v * 1.35)) for v in g) + (150,)
                _leaf(d, cx, cy, L, W, toward, col, vein)
            if blur:
                layer = layer.filter(ImageFilter.GaussianBlur(blur))
            img = Image.alpha_composite(img, layer)
    glow = Image.new("RGBA", (PX, PX), (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    dots = Image.new("RGBA", (PX, PX), (0, 0, 0, 0)); dd = ImageDraw.Draw(dots)
    n = {"stars": 150, "bubbles": 45, "snow": 130}.get(kind, 75)
    for _ in range(n):
        while True:                                      # plus dense sur les bords, rare au centre
            x, y = rnd.uniform(0, PX), rnd.uniform(0, PX)
            if rnd.random() < 1.25 - min(x, y, PX - x, PX - y) / PX * 3.4:
                break
        r = rnd.uniform(2, 7)
        if kind == "bubbles":
            dd.ellipse((x - r * 4, y - r * 4, x + r * 4, y + r * 4), outline=hi_c + (150,), width=3)
        elif kind == "snow":
            dd.ellipse((x - r, y - r, x + r, y + r), fill=(245, 248, 255, 210))
        else:
            g.ellipse((x - r * 7, y - r * 7, x + r * 7, y + r * 7), fill=hi_c + (70,))
            dd.ellipse((x - r * .6, y - r * .6, x + r * .6, y + r * .6), fill=(255, 240, 190, 240))
            if kind == "stars" and r > 5:
                dd.line((x - r * 3, y, x + r * 3, y), fill=(255, 245, 210, 160), width=2)
                dd.line((x, y - r * 3, x, y + r * 3), fill=(255, 245, 210, 160), width=2)
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(16)))
    img = Image.alpha_composite(img, dots)
    return img.convert("RGB")


def ambiance_from_frame(frame, scene, k):
    im = frame.transpose(Image.FLIP_LEFT_RIGHT) if k % 2 else frame
    z = 1.0 + 0.04 * (k % 3)
    if z > 1:
        w = int(PX / z); o = (PX - w) // 2
        im = im.crop((o, o, o + w, o + w)).resize((PX, PX), Image.LANCZOS)
    # harmonise légèrement avec la double page
    t = tint_from(np.asarray(scene.resize((32, 32))), True)
    arr = np.asarray(im).astype(np.float32) * 0.9 + t[None, None, :] * 0.1
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def paper_grain(img, seed=0, amt=3.0):
    rs = np.random.RandomState(seed)
    n = rs.normal(0, amt, (PX // 2, PX // 2)).astype(np.float32)
    n = np.asarray(Image.fromarray(n).resize((PX, PX), Image.BILINEAR))
    arr = np.asarray(img).astype(np.float32) + n[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def chapter_page(c, amb, title, paras, header, num):
    an = Analysis(amb)
    width = PAGE * 0.74
    tb = fit_block([title], dict(art.TITLE, leading=1.18, max=art.TITLE["size"]), width, 80)
    avail = PAGE - 2 * 64 - tb["height"] - 22
    b = fit_block(paras, art.CHAP_BODY, width, avail)
    total = tb["height"] + 22 + b["height"]
    top = max(64, (PAGE - total) / 2 - 8)
    x = (PAGE - width) / 2
    place_block(tb, x, top); place_block(b, x, top + tb["height"] + 22)
    r = (x - 22, top - 20, x + width + 22, top + total + 20)
    img, mode, q = treat_text_area(amb, an, [tb, b], r, (), 120, strength=0.9)
    bg(c, img)
    c.setFont("Sans", 7.5); c.setFillColorRGB(*((0.95, 0.84, 0.6) if mode == "dark" else (0.45, 0.3, 0.15)))
    c.drawCentredString(PAGE / 2, PAGE - art.SAFE - 7, header.upper())
    draw_blocks(c, [tb, b], [art.TITLE_WARM if mode == "dark" else art.TITLE_DARK, art.INK_LIGHT if mode == "dark" else art.INK_DARK])
    folio(c, num, mode)
    q.update(zone="centre", taille=b["size"], debordement=b["overflow"] or tb["overflow"])
    return q


# ============================================================ couverture et 4e
def cover_page(c, im, story):
    an = Analysis(im)
    t = story["titre"]
    width = PAGE - 2 * 42
    b1 = fit_block([t[0]], dict(font="Serif-Bold", size=36, min=26, max=38, leading=1.12), width, 46)
    b2 = fit_block([t[1]], dict(font="Serif-Bold", size=29, min=22, max=30, leading=1.12), width, 80) if len(t) > 1 else None
    kick = layout_block([f"MON HÉROS DU MOIS  •  AVENTURE {story.get('numero', '01')}"], dict(font="Sans", size=9, leading=1.2), width)
    place_block(kick, 42, art.SAFE + 2); place_block(b1, 42, 62)
    blocks = [kick, b1]
    if b2:
        place_block(b2, 42, 62 + b1["height"] + 8); blocks.append(b2)
    bottom = (b2 or b1)["rect"][3]
    r = (30, 18, PAGE - 30, bottom + 10)
    img, mode, q = treat_text_area(im, an, blocks, r, ("left", "right", "top"), 120)
    acc = layout_block([story.get("accroche_couverture", "UNE AVENTURE À LIRE ENSEMBLE").upper()], dict(font="Sans", size=9, leading=1.2), width)
    place_block(acc, 42, PAGE - art.SAFE - 12)
    an2 = Analysis(img)
    img, mode2, q2 = treat_text_area(img, an2, [acc], (30, PAGE - art.SAFE - 26, PAGE - 30, PAGE - art.SAFE + 4), ("left", "right", "bottom"), 70, mode="dark", strength=0.8)
    bg(c, img)
    gold = art.TITLE_WARM if mode == "dark" else art.TITLE_DARK
    draw_blocks(c, blocks, [gold, (1, 0.95, 0.82) if mode == "dark" else art.INK_DARK, gold][:len(blocks)])
    draw_blocks(c, [acc], [(0.96, 0.87, 0.68)])
    q.update(zone="haut", taille=b1["size"], debordement=b1["overflow"] or bool(b2 and b2["overflow"]))
    return q


def back_page(c, amb, story):
    q4 = story["quatrieme"]
    width = PAGE - 2 * 46
    head = layout_block([f"MON HÉROS DU MOIS  •  AVENTURE {story.get('numero', '01')}"], dict(font="Sans", size=9, leading=1.2), width)
    t = fit_block(["\n".join(q4["accroche"][:2])], dict(font="Serif-Bold", size=27, min=21, max=28, leading=1.3), width, 110)
    p = fit_block(q4["paragraphes"], dict(font="Serif", size=16, min=13, max=17, leading=1.5), width, 150)
    qn = layout_block([q4.get("question", "").upper()], dict(font="Sans", size=9.5, leading=1.4), width)
    meta = layout_block([f"À lire ensemble • {q4.get('age', '4–6 ans')}", f"Une histoire écrite pour {story.get('prenom', '')}"],
                        dict(font="Sans", size=9, leading=1.5), width)
    place_block(head, 46, art.SAFE + 4)
    top = 140
    place_block(t, 46, top); place_block(p, 46, top + t["height"] + 26); place_block(qn, 46, top + t["height"] + 26 + p["height"] + 30)
    place_block(meta, 46, PAGE - art.SAFE - 34)
    blocks = [head, t, p, qn, meta]
    r = (30, top - 20, PAGE - 30, qn["rect"][3] + 16)
    img, mode, q = treat_text_area(amb, Analysis(amb), blocks, r, ("left", "right"), 140, mode="dark")
    bg(c, img)
    draw_blocks(c, blocks, [(0.97, 0.86, 0.61), (1, 0.88, 0.63), art.INK_LIGHT, (1, 0.88, 0.63), (0.86, 0.84, 0.76)])
    q.update(zone="gauche", taille=p["size"], debordement=t["overflow"] or p["overflow"])
    return q


# ============================================================ pages ajoutées pour l'impression (24 pages intérieures)
def _names(story):
    ps = story.get("personnages") or [{"nom": story.get("prenom", ""), "role": "héros"}]
    hero = ps[0]["nom"]; others = [p["nom"] for p in ps[1:] if p.get("role", "") != "personnage inventé"]
    return hero, others


def _center_blocks(c, amb, blocks, colors, gap=18, strength=0.9, mode="dark", top=None):
    total = sum(b["height"] for b in blocks) + gap * (len(blocks) - 1)
    y = top if top is not None else (PAGE - total) / 2
    for b in blocks:
        place_block(b, (PAGE - b["width"]) / 2, y); y += b["height"] + gap
    r = (min(b["rect"][0] for b in blocks) - 26, blocks[0]["rect"][1] - 24, max(b["rect"][2] for b in blocks) + 26, blocks[-1]["rect"][3] + 24)
    img, mode, q = treat_text_area(amb, Analysis(amb), blocks, r, (), 130, mode=mode, strength=strength)
    bg(c, img)
    draw_blocks(c, blocks, colors)
    return q


def _centered(lines, font, size, width, leading=1.35):
    """Bloc dont chaque ligne est centrée (on mesure la ligne la plus large)."""
    b = layout_block(lines, dict(font=font, size=size, leading=leading), width)
    w = max(_w(ln, font, size) for ln, _ in b["lines"])
    b["lines"] = [(ln, y) for ln, y in b["lines"]]
    b["width"] = w
    b["center"] = True
    return b


def page_garde(c, amb, story):
    hero, _ = _names(story)
    b1 = _centered(["Ce livre appartient à"], "Serif", 17, 420)
    b2 = _centered([hero], "Serif-Bold", 44, 480)
    b3 = _centered([story.get("dedicace") or "Une aventure écrite rien que pour toi."], "Serif", 14, 400, 1.5)
    return _center_blocks(c, amb, [b1, b2, b3], [art.INK_LIGHT, art.TITLE_WARM, art.INK_LIGHT])


def page_titre(c, amb, story):
    hero, others = _names(story)
    t = story["titre"]
    b1 = _centered([t[0]], "Serif-Bold", 34, 500)
    b2 = _centered([t[1]] if len(t) > 1 else [""], "Serif-Bold", 26, 500)
    avec = f"Une aventure de {hero}" + (f", avec {', '.join(others[:-1]) + ' et ' + others[-1] if len(others) > 1 else others[0]}" if others else "")
    b3 = _centered(wrap(frenchify(avec), "Serif", 14, 420), "Serif", 14, 440, 1.5)
    b4 = _centered([f"MON HÉROS DU MOIS  •  AVENTURE {story.get('numero', '01')}"], "Sans", 8.5, 400)
    return _center_blocks(c, amb, [b1, b2, b3, b4], [art.TITLE_WARM, (0.97, 0.83, 0.53), art.INK_LIGHT, (0.9, 0.82, 0.62)], gap=14)


def page_fin(c, amb, story):
    b1 = _centered(["Fin"], "Serif-Bold", 64, 300)
    b2 = _centered(wrap(frenchify(story.get("teaser") or "À très vite pour une nouvelle aventure !"), "Serif", 16, 420), "Serif", 16, 440, 1.5)
    return _center_blocks(c, amb, [b1, b2], [art.TITLE_WARM, art.INK_LIGHT], gap=26)


def page_heros(c, amb, portraits, story):
    """Galerie des héros : les portraits de référence validés, chacun avec son prénom."""
    arr = np.asarray(amb).astype(np.float32) * 0.6
    base = Image.fromarray(arr.astype(np.uint8)).convert("RGB")
    items = [(pth, nom) for pth, nom in (portraits or []) if pth and Path(pth).exists()][:6]
    n = len(items)
    cols = 3 if n > 4 else max(1, min(n, 2 if n == 4 else n))
    rows = max(1, (n + cols - 1) // cols)
    tile = int(PX * (0.27 if cols == 3 else 0.34))
    gap = int(PX * 0.03)
    top = int(PX * 0.24)
    labels = []
    d = ImageDraw.Draw(base)
    for i, (pth, nom) in enumerate(items):
        r, cidx = divmod(i, cols)
        in_row = min(cols, n - r * cols)
        x0 = (PX - (in_row * tile + (in_row - 1) * gap)) // 2 + cidx * (tile + gap)
        y0 = top + r * (tile + gap + int(PX * 0.05))
        im = Image.open(pth).convert("RGB")
        s0 = min(im.size); im = im.crop(((im.width - s0) // 2, (im.height - s0) // 2, (im.width + s0) // 2, (im.height + s0) // 2)).resize((tile, tile), Image.LANCZOS)
        mask = Image.new("L", (tile, tile), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile, tile), radius=tile // 9, fill=255)
        d.rounded_rectangle((x0 + 8, y0 + 14, x0 + tile + 8, y0 + tile + 14), radius=tile // 9, fill=(8, 16, 20))
        base.paste(im, (x0, y0), mask)
        labels.append((nom, (x0 + tile / 2) / K, (y0 + tile) / K + 8))
    b1 = _centered(["Les héros de cette histoire"], "Serif-Bold", 24, 480)
    place_block(b1, (PAGE - b1["width"]) / 2, art.SAFE + 34)
    blocks = [b1]
    for nom, cx, ty in labels:
        bb = _centered([nom], "Serif-Bold", 13, 200)
        place_block(bb, cx - bb["width"] / 2, ty); blocks.append(bb)
    img, mode, q = treat_text_area(base, Analysis(base), blocks, (40, art.SAFE + 20, PAGE - 40, art.SAFE + 70), (), 80, mode="dark")
    bg(c, img)
    draw_blocks(c, blocks, [art.TITLE_WARM] + [art.INK_LIGHT] * (len(blocks) - 1))
    return q


def page_jeu(c, story, num):
    """Page d'activité claire : questions + cadre pour dessiner (imprimable, pensée pour le crayon)."""
    hero, _ = _names(story)
    im = Image.new("RGB", (PX, PX), (250, 243, 228))
    im = paper_grain(im, 5, 4.0)
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = [int(v * K) for v in (70, PAGE * 0.47, PAGE - 70, PAGE - 70)]
    for i in range(x0, x1, 28):
        d.line((i, y0, min(i + 14, x1), y0), fill=(214, 170, 90), width=5); d.line((i, y1, min(i + 14, x1), y1), fill=(214, 170, 90), width=5)
    for j in range(y0, y1, 28):
        d.line((x0, j, x0, min(j + 14, y1)), fill=(214, 170, 90), width=5); d.line((x1, j, x1, min(j + 14, y1)), fill=(214, 170, 90), width=5)
    bg(c, im)
    qs = story.get("questions") or ["Quel moment de l'aventure as-tu préféré ?",
                                    f"Et toi, qu'est-ce qui te donne du courage, comme {hero} ?",
                                    "Invente la prochaine aventure de l'équipe !"]
    t = _centered(["À toi de jouer !"], "Serif-Bold", 26, 480)
    place_block(t, (PAGE - t["width"]) / 2, art.SAFE + 22)
    body = fit_block([f"{i + 1}. {q}" for i, q in enumerate(qs[:3])], dict(art.CHAP_BODY, size=14.5), PAGE - 150, PAGE * 0.24)
    place_block(body, 75, art.SAFE + 22 + t["height"] + 18)
    lab = _centered(["Dessine ici ton moment préféré"], "Serif", 12, 400)
    place_block(lab, (PAGE - lab["width"]) / 2, PAGE * 0.47 + 14)
    draw_blocks(c, [t, body, lab], [art.TITLE_DARK, art.INK_DARK, (0.55, 0.42, 0.25)])
    folio(c, num, "light")
    return dict(voile=0, contrast=12.0, mode="light", taille=body["size"], debordement=body["overflow"])


def page_colophon(c, amb, story):
    import datetime
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    n = datetime.date.today()
    hero, _ = _names(story)
    b1 = _centered(["Mon Héros du Mois"], "Serif-Bold", 18, 400)
    b2 = _centered(wrap(frenchify(f"Cette histoire a été écrite et illustrée pour {hero}."), "Serif", 12.5, 380) +
                   [f"Aventure n°{story.get('numero', '01')} · {mois[n.month - 1]} {n.year}"], "Serif", 12.5, 400, 1.6)
    return _center_blocks(c, amb.filter(ImageFilter.GaussianBlur(6)), [b1, b2], [art.TITLE_WARM, art.INK_LIGHT], gap=12)


# ============================================================ assemblage
def warm_cast(im):
    """Teinte moyenne jaune (b* en Lab). Pages de Léo : 7 à 21. Au-delà de 22 : dominante jaune-orangée signalée."""
    import couleur
    return couleur.stats(im)[1]


def _build_pdf(story, images, out_path, progress=lambda *_: None, storyboard=None, pages=None,
              mode="ecran", portraits=None):
    """images : [couverture, page 1..18] ; storyboard : pages (zone_texte, contrôle visuel) ;
    pages : indices des pages d'histoire à inclure (aperçu). mode 'ecran' : 20 pages (couverture, 18 pages, 4e).
    mode 'impression' : intérieur Lulu de 24 pages avec fond perdu (la couverture est un fichier à part : build_cover).
    portraits : [(chemin, prénom)] pour la page des héros. Renvoie le contrôle qualité."""
    set_mode(mode)
    random.seed(7); np.random.seed(7)
    n_pages = len(story["pages"])
    pages = list(range(n_pages)) if pages is None else pages
    imgs = {i: load(p) for i, p in enumerate(images) if p}
    sb = {s.get("page"): s for s in (storyboard or []) if isinstance(s, dict)}
    c = canvas.Canvas(str(out_path), pagesize=(PAGE + 2 * B, PAGE + 2 * B))
    c.setTitle(" ".join(story["titre"])); c.setAuthor("Mon Héros du Mois")
    qa = []

    def page(fn, kind, *a, extra=None):
        c.translate(B, B)
        q = fn(c, *a)
        qa.append(dict(page=len(qa) + 1, type=kind, **q, **(extra or {}))); c.showPage()

    def amb(k):
        base = imgs.get(k) or imgs[0]
        return paper_grain(procedural_ambiance(base, story.get("univers"), k), k)

    full = len(pages) == n_pages
    if mode == "impression":
        progress("Pages d'ouverture")
        page(page_garde, "garde", amb(n_pages), story)
        page(page_titre, "titre", amb(1), story)
    else:
        progress("Couverture")
        page(cover_page, "couverture", imgs[0], story, extra=dict(dominante_chaude=round(warm_cast(imgs[0]), 1)))
    off = 2 if mode == "impression" else 1
    for k in pages:
        progress(f"Mise en page {k + 1}/{n_pages}")
        info = sb.get(k + 1) or {}
        extra = dict(page_histoire=k + 1, dominante_chaude=round(warm_cast(imgs[k + 1]), 1))
        if info.get("controle_visuel"):
            extra["controle_visuel"] = info["controle_visuel"]
        page(lambda c_, *a: picture_page(c_, *a), "illustration", imgs[k + 1], story["pages"][k]["texte"],
             info.get("zone_texte"), off + k + 1, extra=extra)
    if full:
        if mode == "impression":
            progress("Pages de fin")
            page(page_fin, "fin", amb(n_pages), story)
            page(page_heros, "heros", amb(1), portraits, story)
            page(lambda c_, s_: page_jeu(c_, s_, off + n_pages + 3), "activite", story)
            page(page_colophon, "colophon", amb(n_pages // 2), story)
        else:
            page(back_page, "quatrieme", paper_grain(procedural_ambiance(imgs[0], story.get("univers"), 99).filter(ImageFilter.GaussianBlur(3)), 99), story)
    c.save()
    expected = (2 + n_pages + 4 if mode == "impression" else n_pages + 2) if full else len(pages) + (2 if mode == "impression" else 1)
    set_mode("ecran")
    return qa_summary(qa, expected)


def _build_cover(story, cover_img, back_amb, out_path, width, height):
    """Fichier couverture Lulu en une pièce : 4e de couverture | tranche | 1re de couverture.
    width/height : dimensions données par l'API Lulu (cover-dimensions), en points, fond perdu compris."""
    set_mode("impression")
    global B
    trim = PAGE
    m = (height - trim) / 2                     # marge extérieure (fond perdu, ou rabat pour une couverture rigide)
    spine = max(0.0, width - 2 * (trim + m))
    c = canvas.Canvas(str(out_path), pagesize=(width, height))
    c.setTitle("Couverture - " + " ".join(story["titre"]))
    B = m
    cov = load(cover_img)
    back = paper_grain(back_amb.resize((PX, PX), Image.LANCZOS).filter(ImageFilter.GaussianBlur(3)), 99)
    c.saveState(); c.translate(m, m); q_back = back_page(c, back, story); c.restoreState()
    c.saveState(); c.translate(width - trim - m, m); q_front = cover_page(c, cov, story); c.restoreState()
    if spine > 0.5:
        col = np.median(np.asarray(cov.resize((32, 32))).reshape(-1, 3), axis=0) / 255 * 0.45
        c.setFillColorRGB(*col); c.rect(trim + m, 0, spine, height, stroke=0, fill=1)
        if spine >= 18:                          # titre sur la tranche si elle est assez large (≥ 0,25 pouce)
            c.saveState(); c.translate(trim + m + spine / 2 + 3, height / 2); c.rotate(-90)
            c.setFont("Serif-Bold", min(10, spine * 0.45)); c.setFillColorRGB(*art.TITLE_WARM)
            c.drawCentredString(0, 0, " ".join(story["titre"])); c.restoreState()
    c.showPage(); c.save()
    set_mode("ecran")
    return dict(largeur=round(width, 2), hauteur=round(height, 2), tranche=round(spine, 2), marge=round(m, 2),
                contrast=min(q_back["contrast"], q_front["contrast"]))


def qa_summary(qa, expected):
    probs = []
    for q in qa:
        if q["contrast"] < art.MIN_CONTRAST:
            probs.append(f"page {q['page']} : contraste {q['contrast']} < {art.MIN_CONTRAST}")
        if q.get("debordement"):
            probs.append(f"page {q['page']} : texte trop long pour la zone")
        if q.get("taille", 99) < 13:
            probs.append(f"page {q['page']} : texte petit ({q['taille']} pt)")
        cv = q.get("controle_visuel") or {}
        ref = f"page {q['page']}" + (f" (illustration {q['page_histoire']})" if q.get("page_histoire") else "")
        if cv and not cv.get("ok", True):
            probs.append(f"{ref} : écart bloquant après {cv.get('tentatives', 1)} essai(s) : " + "; ".join(cv.get("problemes", []))[:300])
        if q.get("dominante_chaude", 0) > 22:
            probs.append(f"{ref} : dominante jaune-orangée (b* {q['dominante_chaude']:.0f}, Léo : 7 à 21)")
    if len(qa) != expected:
        probs.append(f"{len(qa)} pages au lieu de {expected}")
    mineurs = [f"page {q['page']} : " + "; ".join((q.get("controle_visuel") or {}).get("mineurs", [])) for q in qa
               if (q.get("controle_visuel") or {}).get("mineurs")]
    return dict(pages=len(qa), attendu=expected, details=qa, problemes=probs, mineurs=mineurs, ok=not probs)


# La mise en page utilise des réglages globaux (écran / impression) : deux livres ne sont jamais mis en page en même temps.
import threading as _threading
_LOCK = _threading.RLock()


def build_pdf(*a, **k):
    with _LOCK:
        return _build_pdf(*a, **k)


def build_cover(*a, **k):
    with _LOCK:
        return _build_cover(*a, **k)
