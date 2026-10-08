# -*- coding: utf-8 -*-
"""Moteur de mise en page des livres Mila et Noé (kit « Kit_Claude_Livres »), porté tel quel dans le site.

Les calculs sont ceux de kit/render_book_original.py, sans modification : pages carrées de 595,2756 pt (210 mm),
panoramas 2:1 coupés en deux à x = 50 %, DejaVu Serif 14,8 / 21 pt, marges 45 pt, texte à 43 pt du bas,
hauteur maximale 147 pt (au-delà : erreur, jamais de réduction du corps), fondu continu de 225 pt
(opacité 0,96 jusqu'à 135 pt puis décroissance douce jusqu'à zéro), folio en 8 pt, quatrième sur le panorama 8.

Ajouts du site (n'altèrent pas les pages du kit) :
- text_height() : contrôle des textes AVANT de payer les illustrations ;
- titre de couverture composé (book["coverTitle"]) pour les nouveaux livres, dont l'illustration n'a pas de texte ;
- aperçu partiel (pages=…) pour les livres d'essai ;
- rendu de contrôle avec PyMuPDF, ou poppler s'il est absent."""
from pathlib import Path
import json, shutil, subprocess, tempfile
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor

KIT = Path(__file__).parent / "kit"
S = 595.2756
TEXT_MAX = 147
VERSION = "kit-2026-10-02"

_fonts = []


def _register():
    if not _fonts:
        pdfmetrics.registerFont(TTFont('Story', str(KIT / 'fonts/DejaVuSerif.ttf')))
        pdfmetrics.registerFont(TTFont('StoryBold', str(KIT / 'fonts/DejaVuSerif-Bold.ttf')))
        _fonts.append(1)


def body_style(ink='#FFF7E8'):
    return ParagraphStyle('body', fontName='Story', fontSize=14.8, leading=21, textColor=HexColor(ink))


def text_height(txt):
    """Hauteur du texte d'une page, avec exactement le style et la largeur du moteur (limite : 147 pt)."""
    _register()
    _, ph = Paragraph(escape(txt), body_style()).wrap(S - 90, 160)
    return ph


def _veil(color):
    # Continuous, smoothly fading local veil; no rectangular text panel.  (code du kit)
    veil = Image.new('RGBA', (2, 900))
    rgb = tuple(int(color[k:k + 2], 16) for k in (1, 3, 5))
    for row in range(900):
        y = 225 * (1 - row / 899)
        t = max(0, min(1, (y - 135) / 90))
        alpha = .96 * (1 - t * t * (3 - 2 * t))
        for col in range(2):
            veil.putpixel((col, row), rgb + (round(alpha * 255),))
    return veil


def _cover_title(c, t):
    """Titre composé sur une couverture sans texte (orthographe maîtrisée). t = {"kicker", "lines": [prénom, suite…], "color"}.
    Lisibilité par un fondu doux en haut (même courbe que le voile du kit, inversée), jamais par un cadre ou un bandeau."""
    top = Image.new('RGBA', (2, 900))
    for row in range(900):
        y = 260 * (row / 899)
        u = max(0, min(1, (y - 110) / 150))
        a = .62 * (1 - u * u * (3 - 2 * u))
        for col in range(2): top.putpixel((col, row), (11, 21, 48, round(a * 255)))
    c.drawImage(ImageReader(top), 0, S - 260, S, 260, mask='auto')
    color = t.get("color") or '#FFF1CF'
    c.setFillColor(HexColor('#EAD49D')); c.setFont('Story', 11)
    kick = "   ".join((t.get("kicker") or "MON HÉROS DU MOIS").upper().split(" "))
    c.drawCentredString(S / 2, S - 40, kick)
    lines = [str(x) for x in t["lines"] if str(x).strip()]
    y = S - 58
    for i, line in enumerate(lines):
        size = 56 if i == 0 and len(lines) > 1 else 34
        st = ParagraphStyle('ct', fontName='StoryBold', fontSize=size, leading=size * 1.08, textColor=HexColor(color), alignment=1)
        sh = ParagraphStyle('cts', parent=st, textColor=HexColor('#0B1530'))
        p = Paragraph(escape(line), st); _, h = p.wrap(S - 80, 300)
        q = Paragraph(escape(line), sh); q.wrap(S - 80, 300)
        y -= h
        c.setFillAlpha(.5); q.drawOn(c, 41.5, y - 2); c.setFillAlpha(1); p.drawOn(c, 40, y)
        y -= 4


def _serie(c, t):
    """Bas de couverture : où en est la série (« Livre 1 sur 6 » + points + ce qui reste à recevoir). Utile pour un cadeau."""
    se = t.get("serie") or {}
    n, total, f = int(t.get("numero") or 1), se.get("total"), se.get("formule")
    if not total:                              # seulement quand la série a une fin connue (cadeau, livres de fête)
        return
    c.drawImage(ImageReader(_veil('#0B1530')), 0, 0, S, 150, mask='auto')
    pill = f"LIVRE {n} SUR {total}" if total else f"AVENTURE N° {n}"
    c.setFont('StoryBold', 11); w = pdfmetrics.stringWidth(pill, 'StoryBold', 11) + 28
    c.setFillColor(HexColor('#F2C14E')); c.roundRect(S / 2 - w / 2, 70, w, 22, 11, fill=1, stroke=0)
    c.setFillColor(HexColor('#1A1F4A')); c.drawCentredString(S / 2, 77, pill)
    if total:
        gap = min(16, 260 / max(total, 1)); x0 = S / 2 - gap * (total - 1) / 2
        for i in range(total):
            c.setFillColor(HexColor('#F2C14E') if i < n else HexColor('#FFF4DC')); c.setFillAlpha(1 if i < n else .35)
            c.circle(x0 + i * gap, 56, 3.2, fill=1, stroke=0)
        c.setFillAlpha(1)
        reste = total - n
        line = ("Le dernier livre de la série" if reste <= 0 else
                f"Encore {reste} aventure{'s' if reste > 1 else ''} à recevoir, " + ("une avant chaque fête" if f == "fetes" else "une chaque mois"))
    else:
        line = "Une nouvelle aventure arrive chaque mois"
    c.setFillColor(HexColor('#FFF4DC')); c.setFont('Story', 11.5); c.drawCentredString(S / 2, 32, line)


def page_couverture(c, cover, book):
    c.drawImage(cover, 0, 0, S, S)
    if book.get('coverTitle'):
        _cover_title(c, book['coverTitle'])
        _serie(c, book['coverTitle'])
        _pastille(c, book['coverTitle'])


def _pastille(c, t):
    """Numéro de collection sur la 1re de couverture (coin bas droit, dans la zone sûre de l'imprimeur) : Lulu refuse
    tout texte sur un dos de 0,25 po. Pas de pastille quand la série est déjà affichée (« Livre 1 sur 6 »)."""
    if (t.get('serie') or {}).get('total') or not t.get('numero'):
        return
    n, r, cx, cy = int(t['numero']), 17, S - 58, 58
    c.setFillColor(HexColor('#0B1530')); c.setFillAlpha(.35); c.circle(cx + 1.2, cy - 1.5, r + 1, fill=1, stroke=0); c.setFillAlpha(1)
    c.setFillColor(HexColor('#E8C25A')); c.circle(cx, cy, r, fill=1, stroke=0)
    c.setStrokeColor(HexColor('#9C7A2B')); c.setLineWidth(.8); c.circle(cx, cy, r, fill=0, stroke=1)
    c.setStrokeColor(HexColor('#FFF1CF')); c.setLineWidth(.6); c.circle(cx, cy, r - 3, fill=0, stroke=1)
    fs = 15 if n < 10 else 12
    c.setFillColor(HexColor('#1A1F4A')); c.setFont('StoryBold', fs); c.drawCentredString(cx, cy - fs * .36, str(n))


def page_histoire(c, idx, txt, p, book, folio_y=19):
    """Une page d'histoire (calculs du kit). Renvoie la hauteur du texte."""
    spread = idx // 2; half = idx % 2
    im = Image.open(p); w, h = im.size
    scale = max(2 * S / w, S / h); dw, dh = w * scale, h * scale
    c.drawImage(p, (2 * S - dw) / 2 - half * S, (S - dh) / 2, dw, dh)
    color = book['pages'][idx]['veil']; ink = book['pages'][idx]['ink']
    c.drawImage(ImageReader(_veil(color)), 0, 0, S, 225, mask='auto')
    c.setFillAlpha(1)
    para = Paragraph(escape(txt), body_style(ink)); pw, ph = para.wrap(S - 90, 160)
    if ph > TEXT_MAX: raise ValueError(f'Text overflow on page {idx + 2}; shorten text, do not shrink type')
    para.drawOn(c, 45, 43)
    c.setFillColor(HexColor(ink)); c.setFont('Story', 8); c.drawCentredString(S / 2, folio_y, str(idx + 2))
    return ph


def page_quatrieme(c, p, book):
    # Back cover, image and quiet integrated synopsis.  (code du kit)
    im = Image.open(p); w, h = im.size; scale = S / h
    c.drawImage(p, S - w * scale, 0, w * scale, S)
    c.setFillColor(HexColor(book['backColor'])); c.setFillAlpha(.84); c.rect(0, 0, S, S, fill=1, stroke=0); c.setFillAlpha(1)
    c.setFillColor(HexColor('#EAD49D')); c.setFont('Story', 12); c.drawCentredString(S / 2, 520, book['collection'].upper())
    style = ParagraphStyle('backtitle', fontName='StoryBold', fontSize=29, leading=38, textColor=HexColor('#FFF4DC'), alignment=1)
    up = 36 if book.get('cadeau') else 0       # livre offert : le texte remonte pour laisser la place au petit mot
    q = Paragraph('<br/>'.join(escape(t) for t in book['backTitle']), style); _, h = q.wrap(S - 100, 140); q.drawOn(c, 50, 370 + up)
    style = ParagraphStyle('back', fontName='Story', fontSize=16, leading=25, textColor=HexColor('#FFF4DC'), alignment=1)
    q = Paragraph('<br/><br/>'.join(escape(t) for t in book['backText']), style); _, h = q.wrap(S - 130, 240); q.drawOn(c, 65, 325 + up - h)
    if book.get('cadeau'):                     # livre offert : de la part de qui, et son petit mot
        k = book['cadeau']
        st = ParagraphStyle('kdo', fontName='Story', fontSize=11.5, leading=16, textColor=HexColor('#EAD49D'), alignment=1)
        body = f"<font name='StoryBold'>Offert par {escape(k['de'])}</font>" + (f"<br/>« {escape(k['message'])} »" if k.get('message') else '')
        q = Paragraph(body, st); _, hk = q.wrap(S - 150, 90); q.drawOn(c, 75, 126)
    c.setStrokeColor(HexColor('#DCC38C')); c.setLineWidth(.7); c.line(245, 112, 350, 112)
    c.setFont('Story', 11); c.drawCentredString(S / 2, 85, 'Une aventure à lire ensemble • ' + book['ageLabel'])
    num = (book.get('coverTitle') or {}).get('numero')
    c.setFont('Story', 9); c.drawCentredString(S / 2, 62, book['title'] + (f"  •  livre n° {int(num)} de la collection" if num else ''))


def render(book, out, base=None, work=None, pages=None, check=True):
    """book : manifeste au format du kit (title, collection, ageLabel, cover, spreads[9], pages[18] {text, veil, ink},
    backTitle, backText, backColor ; + coverTitle facultatif). Chemins relatifs à `base`.
    pages=None : livre complet (20 pages). pages=[0, 1] : aperçu (couverture + ces pages d'histoire)."""
    _register()
    base = Path(base or Path(out).parent).resolve()
    out = Path(out).resolve()
    work = Path(work or out.parent / 'render-work')
    (work / 'assets').mkdir(parents=True, exist_ok=True)

    def asset(rel):
        p = (base / rel).resolve()
        if not p.is_relative_to(base): raise ValueError('Asset outside manifest folder')
        if not p.is_file(): raise ValueError(f'Missing asset: {rel}')
        return str(p)
    full = pages is None
    if full and (len(book['spreads']) != 9 or len(book['pages']) != 18):
        raise ValueError('Expected 9 spreads and 18 story pages')
    texts = [p['text'] if p else '' for p in book['pages']]
    need = sorted({i // 2 for i in (range(18) if full else pages)} | ({7} if full else set()))
    paths = {}
    for i in need:
        p = asset(book['spreads'][i]); im = Image.open(p)
        if abs(im.width / im.height - 2) > 0.02: raise ValueError('Spread must be 2:1; do not silently crop characters')
        paths[i] = p

    def jpeg(source, name):
        dest = work / 'assets' / name
        if Image.open(source).format == 'JPEG': shutil.copyfile(source, dest)
        else: Image.open(source).convert('RGB').save(dest, quality=95, subsampling=0, optimize=True)
        return str(dest)
    paths = {i: jpeg(p, f'spread-{i + 1}.jpg') for i, p in paths.items()}
    cover = jpeg(asset(book['cover']), 'cover.jpg')
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(S, S), pageCompression=1)
    c.setTitle(book['title']); c.setAuthor(book['collection']); c.setSubject('Une aventure illustrée à lire ensemble • ' + book.get('ageLabel', '4–7 ans'))
    # Cover and final back cover are included in the 20-page count.
    page_couverture(c, cover, book)
    c.showPage()
    heights = {}
    for idx, txt in enumerate(texts):
        if not full and idx not in pages: continue
        heights[idx + 2] = page_histoire(c, idx, txt, paths[idx // 2], book)
        c.showPage()
    if full:
        page_quatrieme(c, paths[7], book)
        c.showPage()
    c.save()
    report = {"pdf": str(out), "bytes": out.stat().st_size, "hauteurs_texte": heights}
    if check:
        report.update(verify(out, 20 if full else 1 + len(pages), work, story_pages=full))
    return report


# ---------------------------------------------------------------- contrôle du rendu (pages en images + planches contact)
def _pages_png(pdf, work, zoom=.7):
    try:
        import fitz
        doc = fitz.open(pdf); n = len(doc); texts = []
        for i, p in enumerate(doc):
            texts.append(p.get_text())
            p.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(str(work / f'page-{i + 1:02}.png'))
        return n, texts
    except ImportError:                     # PyMuPDF absent : poppler
        info = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True).stdout
        n = int([l for l in info.splitlines() if l.startswith('Pages:')][0].split()[1])
        tmp = Path(tempfile.mkdtemp())
        subprocess.run(['pdftoppm', '-r', str(round(72 * zoom)), '-png', str(pdf), str(tmp / 'p')], check=True)
        for i, f in enumerate(sorted(tmp.glob('p-*.png'))):
            shutil.move(str(f), work / f'page-{i + 1:02}.png')
        texts = [subprocess.run(['pdftotext', '-f', str(i + 1), '-l', str(i + 1), str(pdf), '-'], capture_output=True, text=True).stdout
                 for i in range(n)]
        return n, texts


def verify(pdf, expected, work, story_pages=True):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    n, texts = _pages_png(pdf, work)
    probs = []
    if n != expected:
        probs.append(f"{n} pages au lieu de {expected}")
    if story_pages:
        for i in range(1, min(n, 19)):
            if len(texts[i]) <= 70:
                probs.append(f"page {i + 1} : texte absent ou trop court dans le PDF")
    for start in range(0, n, 10):
        sheet = Image.new('RGB', (1500, 640), '#c5c5c5'); d = ImageDraw.Draw(sheet)
        for j in range(min(10, n - start)):
            im = Image.open(work / f'page-{start + j + 1:02}.png').convert('RGB'); im.thumbnail((295, 295))
            x = (j % 5) * 300; y = (j // 5) * 320; sheet.paste(im, (x, y)); d.text((x + 8, y + 298), str(start + j + 1), fill='black')
        sheet.save(work / f'contact-{start}.jpg', quality=90)
    return {"pages": n, "problemes_rendu": probs, "planches": [f'contact-{s}.jpg' for s in range(0, n, 10)]}


if __name__ == "__main__":      # même usage que le kit : python moteur_livre.py kit/noe-demo.json --output test/Noe.pdf
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('manifest', type=Path); ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(render(json.loads(a.manifest.read_text(encoding='utf-8')), a.output, base=a.manifest.parent), ensure_ascii=False))
