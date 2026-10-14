# -*- coding: utf-8 -*-
"""Grand livre A4 portrait (21 x 29,7 cm, couverture rigide) : 3 à 5 histoires, chacune dans son monde, réunies en un seul livre.

Chaque histoire est d'abord fabriquée et validée comme un livre normal (mêmes illustrations, même relecture). Ce module ne fait
AUCUN appel IA : il recompose les fichiers enregistrés des histoires validées en un intérieur A4 et une couverture A4.

Mise en page d'une histoire (20 pages) : page d'ouverture (recto) avec sa couverture et son titre, puis 18 pages (illustration
carrée pleine largeur en haut, texte sur fond crème dessous ; chaque double page garde son panorama d'un seul tenant), puis une
page « Fin » (verso). Début du livre : page de titre (« Ce livre appartient à ») et sommaire."""
import io, json, re, tempfile
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFilter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
import moteur_livre as M

VERSION = "recueil-2026-10-14-v1"
POD = __import__("os").getenv("LULU_GRAND_POD", "0827X1169FCSTDCW080CW444GXX")     # A4 portrait, couleur standard, rigide, papier épais brillant
TRIM = (595.28, 841.89)                      # A4 (8,27 x 11,69 po)
BLEED = 9.0                                  # 0,125 po
SAFE = 36.0                                  # 0,5 po
PAGE = (TRIM[0] + 2 * BLEED, TRIM[1] + 2 * BLEED)
CREME, ENCRE, OR, NUIT = "#FBF5EA", "#24184D", "#C99A2E", "#1B1442"
PAGES_PAR_HISTOIRE = 20


def nb_pages(n):
    return 2 + PAGES_PAR_HISTOIRE * n


# ---------------------------------------------------------------- pages
def _fond(c, couleur=CREME):
    c.setFillColor(HexColor(couleur)); c.rect(0, 0, PAGE[0], PAGE[1], fill=1, stroke=0)


def _etoiles(c, n=40, seed=3, zone=None):
    import random
    r = random.Random(seed); x0, y0, x1, y1 = zone or (0, 0, PAGE[0], PAGE[1])
    for _ in range(n):
        c.setFillColor(HexColor("#FFE7A3")); c.setFillAlpha(r.uniform(.25, .8))
        c.circle(r.uniform(x0, x1), r.uniform(y0, y1), r.uniform(.6, 1.8), fill=1, stroke=0)
    c.setFillAlpha(1)


def _centre(c, y, txt, font, size, couleur=ENCRE, largeur=None):
    largeur = largeur or (TRIM[0] - 2 * SAFE)
    while size > 9 and pdfmetrics.stringWidth(txt, font, size) > largeur:
        size -= 1
    c.setFillColor(HexColor(couleur)); c.setFont(font, size); c.drawCentredString(PAGE[0] / 2, y, txt)
    return size


def _folio(c, n, couleur="#8A7F9E"):
    c.setFillColor(HexColor(couleur)); c.setFont("Story", 9); c.drawCentredString(PAGE[0] / 2, BLEED + SAFE - 14, str(n))


def page_titre(c, prenom, titre, histoires):
    _fond(c, NUIT); _etoiles(c, 70, 1)
    _centre(c, PAGE[1] - 250, "Ce livre appartient à", "Story", 20, "#EAD49D")
    _centre(c, PAGE[1] - 320, prenom, "StoryBold", 54, "#FFF4DC")
    c.setStrokeColor(HexColor("#DCC38C")); c.setLineWidth(.8); c.line(PAGE[0] / 2 - 60, PAGE[1] - 360, PAGE[0] / 2 + 60, PAGE[1] - 360)
    st = ParagraphStyle("t", fontName="StoryBold", fontSize=26, leading=34, textColor=HexColor("#FFF4DC"), alignment=1)
    q = Paragraph(escape(titre), st); _, h = q.wrap(TRIM[0] - 2 * SAFE - 40, 200); q.drawOn(c, BLEED + SAFE + 20, PAGE[1] - 400 - h)
    _centre(c, PAGE[1] - 430 - h, f"{len(histoires)} histoires, {len(histoires)} mondes", "Story", 15, "#EAD49D")
    _centre(c, BLEED + SAFE + 30, "Mon Héros du Mois", "StoryBold", 13, "#EAD49D")


def page_sommaire(c, entrees):
    _fond(c)
    _centre(c, PAGE[1] - BLEED - SAFE - 70, "Sommaire", "StoryBold", 32)
    y = PAGE[1] - BLEED - SAFE - 150
    x0, x1 = BLEED + SAFE + 20, PAGE[0] - BLEED - SAFE - 20
    for i, (titre, monde, page) in enumerate(entrees, start=1):
        c.setFillColor(HexColor(OR)); c.setFont("StoryBold", 13); c.drawString(x0, y + 22, f"HISTOIRE {i}  ·  {monde.upper()}"[:70])
        size = 19
        while size > 12 and pdfmetrics.stringWidth(titre, "StoryBold", size) > (x1 - x0 - 50):
            size -= 1
        c.setFillColor(HexColor(ENCRE)); c.setFont("StoryBold", size); c.drawString(x0, y, titre)
        c.setFont("Story", 15); c.drawRightString(x1, y, str(page))
        c.setStrokeColor(HexColor("#E3D7C3")); c.setLineWidth(.6); c.setDash(1, 3)
        c.line(x0 + pdfmetrics.stringWidth(titre, "StoryBold", size) + 8, y + 3, x1 - pdfmetrics.stringWidth(str(page), "Story", 15) - 8, y + 3)
        c.setDash()
        y -= 92
    _folio(c, 2)


def page_ouverture(c, i, livre, base, monde, num):
    """Recto : « Histoire i », le monde, la couverture de l'histoire (avec son titre composé), en grand."""
    _fond(c)
    _centre(c, PAGE[1] - BLEED - SAFE - 40, f"HISTOIRE {i}", "StoryBold", 15, OR)
    _centre(c, PAGE[1] - BLEED - SAFE - 66, monde, "Story", 15, "#6A5F86")
    cote = TRIM[0] - 2 * SAFE - 10
    x, y = (PAGE[0] - cote) / 2, (PAGE[1] - cote) / 2 - 40
    c.setFillColor(HexColor("#000000")); c.setFillAlpha(.12); c.roundRect(x + 5, y - 7, cote, cote, 14, fill=1, stroke=0); c.setFillAlpha(1)
    k = cote / M.S
    c.saveState()
    p = c.beginPath(); p.roundRect(x, y, cote, cote, 14); c.clipPath(p, stroke=0, fill=0)
    c.translate(x, y); c.scale(k, k); M.page_couverture(c, str(base / livre["cover"]), livre)
    c.restoreState()
    _folio(c, num)


def page_histoire(c, idx, livre, base, num):
    """Illustration carrée pleine largeur en haut (moitié du panorama), texte sur fond crème en dessous."""
    _fond(c)
    p = str(base / livre["spreads"][idx // 2]); half = idx % 2
    im = Image.open(p); w, h = im.size
    cote = PAGE[0]                                   # largeur de la page, fond perdu compris
    scale = max(2 * cote / w, cote / h); dw, dh = w * scale, h * scale
    y0 = PAGE[1] - cote
    c.saveState(); pth = c.beginPath(); pth.rect(0, y0, cote, cote); c.clipPath(pth, stroke=0, fill=0)
    c.drawImage(p, (2 * cote - dw) / 2 - half * cote, y0 + (cote - dh) / 2, dw, dh)
    c.restoreState()
    # fondu de l'image vers le crème : aucune ligne dure entre l'illustration et le texte
    g = Image.new("RGBA", (2, 200))
    rgb = tuple(int(CREME[k:k + 2], 16) for k in (1, 3, 5))
    for row in range(200):
        t = row / 199; g.putpixel((0, row), rgb + (round(255 * (t ** 1.6)),)); g.putpixel((1, row), rgb + (round(255 * (t ** 1.6)),))
    c.drawImage(ImageReader(g), 0, y0, PAGE[0], 40, mask="auto")
    # texte : le plus grand corps qui tient dans la zone (lisible à voix haute), jamais coupé
    x0, larg = BLEED + SAFE + 4, TRIM[0] - 2 * SAFE - 8
    haut_dispo = y0 - (BLEED + SAFE + 8) - 8
    txt = livre["pages"][idx]["text"]
    for size in (17, 16, 15, 14, 13, 12, 11):
        st = ParagraphStyle("b", fontName="Story", fontSize=size, leading=size * 1.42, textColor=HexColor(ENCRE))
        para = Paragraph(escape(txt), st); _, ph = para.wrap(larg, 1000)
        if ph <= haut_dispo:
            break
    probleme = None if ph <= haut_dispo else f"texte trop long (page {num})"
    para.drawOn(c, x0, y0 - 10 - ph - max(0, (haut_dispo - ph) / 2 - 10))
    _folio(c, num)
    return probleme


def page_fin(c, i, livre, base, num, prenom):
    _fond(c)
    p = base / livre["spreads"][-1]
    try:                                              # petit médaillon : la dernière illustration de l'histoire
        im = Image.open(p).convert("RGB"); w, h = im.size
        im = im.crop(((w - h) // 2, 0, (w + h) // 2, h)).resize((700, 700))
        m = Image.new("L", im.size, 0); ImageDraw.Draw(m).ellipse((0, 0, 699, 699), fill=255)
        im.putalpha(m)
        b = io.BytesIO(); im.save(b, "PNG"); b.seek(0)
        d = 230; c.drawImage(ImageReader(b), (PAGE[0] - d) / 2, PAGE[1] / 2 - 20, d, d, mask="auto")
    except Exception:
        pass
    _centre(c, PAGE[1] / 2 - 70, "Fin", "StoryBold", 40)
    _centre(c, PAGE[1] / 2 - 104, f"de « {livre['title']} »", "Story", 15, "#6A5F86")
    _folio(c, num)


def page_derniere(c, prenom, n):
    _fond(c, NUIT); _etoiles(c, 50, 9)
    _centre(c, PAGE[1] / 2 + 20, f"{prenom} a vécu {n} aventures.", "StoryBold", 24, "#FFF4DC")
    _centre(c, PAGE[1] / 2 - 16, "La prochaine commence ce soir…", "Story", 16, "#EAD49D")


# ---------------------------------------------------------------- composition
def charger(dossiers):
    out = []
    for d in dossiers:
        d = Path(d)
        livre = json.loads((d / "livre.json").read_text(encoding="utf-8"))
        snap = {}
        try:
            snap = json.loads((d / "instantane.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        out.append((livre, d, snap.get("univers") or (snap.get("histoire") or {}).get("univers") or ""))
    return out


def titre_recueil(prenom):
    return f"Les grandes aventures de {prenom}"


def composer(dossiers, out_dir, prenom, mondes=None, cadeau=None):
    """dossiers : dossiers des histoires VALIDÉES, dans l'ordre. Écrit impression_interieur.pdf, le PDF de lecture et un aperçu."""
    M._register()
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    hs = charger(dossiers)
    mondes = list(mondes or []) + [""] * len(hs)
    mondes = [mondes[i] or hs[i][2] or "" for i in range(len(hs))]
    titre = titre_recueil(prenom)
    probs = []
    entrees = [(l["title"], mondes[i] or f"Histoire {i + 1}", 3 + PAGES_PAR_HISTOIRE * i) for i, (l, d, _) in enumerate(hs)]

    def dessiner(c):
        page_titre(c, prenom, titre, hs); c.showPage()                               # p1 (recto)
        page_sommaire(c, entrees); c.showPage()                                       # p2
        num = 3
        for i, (l, d, _) in enumerate(hs, start=1):
            page_ouverture(c, i, l, d, mondes[i - 1], num); c.showPage(); num += 1    # recto
            for idx in range(18):                                                     # verso + recto : chaque panorama d'un seul tenant
                pb = page_histoire(c, idx, l, d, num); c.showPage(); num += 1
                if pb:
                    probs.append(f"histoire {i} : {pb}")
            if i < len(hs):
                page_fin(c, i, l, d, num, prenom)
            else:
                page_derniere(c, prenom, len(hs))
            c.showPage(); num += 1
        return num - 1

    interieur = out_dir / "impression_interieur.pdf"
    c = canvas.Canvas(str(interieur), pagesize=PAGE, pageCompression=1); c.setTitle(titre + " – intérieur"); c.setAuthor("Mon Héros du Mois")
    n = dessiner(c); c.save()
    if n != nb_pages(len(hs)):
        probs.append(f"{n} pages au lieu de {nb_pages(len(hs))}")
    nom = re.sub(r"[^\w\-]+", "-", titre, flags=re.U).strip("-")[:80] + ".pdf"
    c = canvas.Canvas(str(out_dir / nom), pagesize=PAGE, pageCompression=1); c.setTitle(titre); c.setAuthor("Mon Héros du Mois")
    premiere(c, hs, prenom, titre, mondes); c.showPage()
    dessiner(c)
    quatrieme(c, hs, prenom, mondes, cadeau); c.showPage(); c.save()
    info = {"version": VERSION, "titre": titre, "pdf": nom, "pages": n, "pod": POD, "histoires": [l["title"] for l, _, _ in hs],
            "mondes": mondes, "problemes": probs}
    (out_dir / "recueil.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


# ---------------------------------------------------------------- couverture (1re | dos | 4e)
def _collage(hs):
    """Les couvertures des histoires, posées en éventail sur le ciel du livre (image RGBA)."""
    W, H = 1600, 1250
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    n = len(hs); cote = 760 if n <= 3 else 640
    pos = {3: [(-430, 120, -9), (430, 120, 9), (0, -40, 0)], 4: [(-480, 140, -10), (480, 140, 10), (-170, -20, -3), (170, -20, 3)],
           5: [(-520, 170, -12), (520, 170, 12), (-260, 40, -5), (260, 40, 5), (0, -60, 0)]}[max(3, min(5, n))]
    for (l, d, _), (dx, dy, a) in zip(hs, pos):
        c = Image.open(d / l["cover"]).convert("RGB").resize((cote, cote))
        m = Image.new("L", c.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, cote - 1, cote - 1), 34, fill=255)
        c.putalpha(m)
        ombre = Image.new("RGBA", (cote + 80, cote + 80), (0, 0, 0, 0))
        ImageDraw.Draw(ombre).rounded_rectangle((40, 52, cote + 40, cote + 52), 34, fill=(0, 0, 0, 120))
        ombre = ombre.filter(ImageFilter.GaussianBlur(18))
        bloc = Image.new("RGBA", ombre.size, (0, 0, 0, 0)); bloc.alpha_composite(ombre); bloc.alpha_composite(c, (40, 40))
        bloc = bloc.rotate(a, resample=Image.BICUBIC, expand=True)
        im.alpha_composite(bloc, (W // 2 + dx - bloc.width // 2, H // 2 + dy - bloc.height // 2))
    return im


def premiere(c, hs, prenom, titre, mondes, x=0, y=0, w=None, h=None):
    """1re de couverture (dans la boîte x, y, w, h ; par défaut : une page avec fond perdu)."""
    w, h = w or PAGE[0], h or PAGE[1]
    c.saveState(); c.translate(x, y)
    c.setFillColor(HexColor(NUIT)); c.rect(0, 0, w, h, fill=1, stroke=0)
    try:                                              # ciel : la couverture de la 1re histoire, très adoucie
        fond = Image.open(hs[0][1] / hs[0][0]["cover"]).convert("RGB").resize((int(w), int(h))).filter(ImageFilter.GaussianBlur(28))
        b = io.BytesIO(); fond.save(b, "JPEG", quality=85); b.seek(0)
        c.drawImage(ImageReader(b), 0, 0, w, h); c.setFillColor(HexColor(NUIT)); c.setFillAlpha(.55); c.rect(0, 0, w, h, fill=1, stroke=0); c.setFillAlpha(1)
    except Exception:
        pass
    import random
    r = random.Random(4)
    for _ in range(60):
        c.setFillColor(HexColor("#FFE7A3")); c.setFillAlpha(r.uniform(.3, .9)); c.circle(r.uniform(0, w), r.uniform(h * .45, h), r.uniform(.6, 2), fill=1, stroke=0)
    c.setFillAlpha(1)
    cx = w / 2
    c.setFillColor(HexColor("#EAD49D")); c.setFont("StoryBold", 13); c.drawCentredString(cx, h - 78, "MON HÉROS DU MOIS")
    size = 64
    while size > 34 and pdfmetrics.stringWidth(prenom.upper(), "StoryBold", size) > w - 120:
        size -= 2
    c.setFillColor(HexColor("#F6D27A")); c.setFont("StoryBold", size); c.drawCentredString(cx, h - 78 - 18 - size, prenom.upper())
    c.setFillColor(HexColor("#FFF4DC")); c.setFont("Story", 24); c.drawCentredString(cx, h - 78 - 18 - size - 40, "et ses grandes aventures")
    col = _collage(hs); b = io.BytesIO(); col.save(b, "PNG"); b.seek(0)
    cw = w - 40; ch = cw * col.height / col.width
    c.drawImage(ImageReader(b), (w - cw) / 2, 120, cw, ch, mask="auto")
    c.setFillColor(HexColor("#F2C14E")); lab = f"{len(hs)} HISTOIRES · {len(hs)} MONDES"
    c.setFont("StoryBold", 12); lw = pdfmetrics.stringWidth(lab, "StoryBold", 12) + 30
    c.roundRect(cx - lw / 2, 70, lw, 26, 13, fill=1, stroke=0); c.setFillColor(HexColor(NUIT)); c.drawCentredString(cx, 79, lab)
    c.restoreState()


def quatrieme(c, hs, prenom, mondes, cadeau=None, x=0, y=0, w=None, h=None):
    w, h = w or PAGE[0], h or PAGE[1]
    c.saveState(); c.translate(x, y)
    c.setFillColor(HexColor(NUIT)); c.rect(0, 0, w, h, fill=1, stroke=0)
    import random
    r = random.Random(8)
    for _ in range(50):
        c.setFillColor(HexColor("#FFE7A3")); c.setFillAlpha(r.uniform(.25, .8)); c.circle(r.uniform(0, w), r.uniform(0, h), r.uniform(.6, 1.8), fill=1, stroke=0)
    c.setFillAlpha(1)
    cx = w / 2
    c.setFillColor(HexColor("#FFF4DC")); c.setFont("StoryBold", 26); c.drawCentredString(cx, h - 140, f"Les {len(hs)} aventures de {prenom}")
    yy = h - 210
    for i, (l, _, _) in enumerate(hs):
        c.setFillColor(HexColor("#EAD49D")); c.setFont("Story", 12); c.drawCentredString(cx, yy + 20, (mondes[i] or f"Histoire {i + 1}").upper()[:60])
        c.setFillColor(HexColor("#FFF4DC")); c.setFont("StoryBold", 17); c.drawCentredString(cx, yy, l["title"][:60])
        yy -= 64
    if cadeau and cadeau.get("de"):
        st = ParagraphStyle("k", fontName="Story", fontSize=13, leading=19, textColor=HexColor("#EAD49D"), alignment=1)
        body = f"<font name='StoryBold'>Offert par {escape(cadeau['de'])}</font>" + (f"<br/>« {escape(cadeau['message'])} »" if cadeau.get("message") else "")
        q = Paragraph(body, st); _, hk = q.wrap(w - 160, 120); q.drawOn(c, 80, 170)
    c.setStrokeColor(HexColor("#DCC38C")); c.setLineWidth(.7); c.line(cx - 50, 130, cx + 50, 130)
    c.setFillColor(HexColor("#FFF4DC")); c.setFont("Story", 12); c.drawCentredString(cx, 100, "Des histoires à lire ensemble, un monde par soir")
    c.restoreState()


def couverture(dossiers, out, prenom, mondes=None, cadeau=None, dims=None, pages=None):
    """Couverture à plat 4e | dos | 1re aux dimensions Lulu (API cover-dimensions). Sans gabarit : maquette marquée non confirmée."""
    M._register()
    hs = charger(dossiers)
    mondes = list(mondes or []) + [""] * len(hs)
    mondes = [mondes[i] or hs[i][2] or "" for i in range(len(hs))]
    if dims is None:
        dims = {"largeur": 2 * (TRIM[0] + 54) + 30, "hauteur": TRIM[1] + 108, "source": "maquette (dimensions non confirmées)", "confirme": False}
    W, H = dims["largeur"], dims["hauteur"]
    m = (H - TRIM[1]) / 2
    dos = max(0.0, W - 2 * (TRIM[0] + m))
    c = canvas.Canvas(str(out), pagesize=(W, H)); c.setTitle("Couverture – " + titre_recueil(prenom))
    quatrieme(c, hs, prenom, mondes, cadeau, 0, 0, TRIM[0] + m, H)
    premiere(c, hs, prenom, titre_recueil(prenom), mondes, W - TRIM[0] - m, 0, TRIM[0] + m, H)
    if dos > .5:
        c.setFillColor(HexColor(NUIT)); c.rect(TRIM[0] + m, 0, dos, H, fill=1, stroke=0)
        if (pages or 0) >= 81 and dos >= 18:          # Lulu : texte sur le dos à partir de 81 pages seulement
            c.saveState(); c.translate(TRIM[0] + m + dos / 2 + 4, H / 2); c.rotate(90)
            c.setFillColor(HexColor("#F6D27A")); c.setFont("StoryBold", min(13, dos * .5)); c.drawCentredString(0, 0, titre_recueil(prenom)); c.restoreState()
    c.showPage(); c.save()
    probs = [] if dims.get("confirme") else ["Dimensions de la couverture non confirmées : clés Lulu absentes (maquette)."]
    return {"largeur": round(W, 2), "hauteur": round(H, 2), "dos": round(dos, 2), "source": dims["source"], "pret_a_imprimer": not probs, "problemes": probs}


def dimensions(pages):
    import lulu
    if lulu.configured():
        w, h = lulu.cover_dimensions(pages, pod=POD)
        return {"largeur": w, "hauteur": h, "source": "API Lulu cover-dimensions (grand livre A4)", "confirme": True}
    return None


def apercu_png(pdf, out, page=0, zoom=.6):
    """Image d'une page du PDF (aperçu admin)."""
    try:
        import fitz
        d = fitz.open(str(pdf)); pix = d[page].get_pixmap(matrix=fitz.Matrix(zoom, zoom)); pix.save(str(out)); return Path(out)
    except Exception:
        return None
