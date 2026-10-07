# -*- coding: utf-8 -*-
"""Fichiers de fabrication et aperçus d'un livre, à partir des fichiers RÉELS du livre (aucun appel IA).

- Intérieur d'impression : 24 pages (minimum Lulu pour une couverture rigide), format fini 8,5 x 8,5 po (21,6 cm) + fond perdu
  0,125 po. Les 18 pages d'histoire gardent la mise en page du kit (mise à l'échelle) ; chaque double page tombe sur une vraie
  double page imprimée (pages paires à gauche).
- Couverture à plat : 4e | dos numéroté | 1re, aux dimensions du gabarit Lulu (API cover-dimensions). Sans clés Lulu, une
  maquette est produite et marquée « dimensions non confirmées » : jamais annoncée prête à imprimer.
- Le numéro de collection (volumeNumber) est composé par code, avec une vraie police, toujours au même endroit du dos.
- Aperçus : rendus déterministes des PDF (couverture, couverture à plat, détail du dos, doubles pages, album fin sur l'étagère)."""
import json, hashlib, shutil, subprocess, tempfile, zipfile, time, os
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

VERSION = "fabrication-2026-10-07-v1"
TRIM = 612.0                     # 8,5 po
BLEED = 9.0                      # 0,125 po (guide Lulu)
SAFE = 36.0                      # 0,5 po de marge de sécurité (guide Lulu)
PAGE_IMP = TRIM + 2 * BLEED      # 630 pt
PAGES_IMPRESSION = 24            # minimum Lulu pour une couverture rigide
# Guide Lulu (Book Creation Guide) : dos de 0,25 po de 24 à 84 pages ; « 80 pages ou moins : pas de texte sur le dos ».
LULU_TEXTE_DOS_MIN_PAGES = 81
NUM_Y_DEPUIS_BAS = 54.0          # le numéro est toujours à 0,75 po du bas du dos (même place sur toute la collection)


# ---------------------------------------------------------------- intérieur d'impression (24 pages)
def _texte_page(c, lignes, couleur="#1F2557", fond="#FBF5EA"):
    c.setFillColor(HexColor(fond)); c.rect(0, 0, PAGE_IMP, PAGE_IMP, fill=1, stroke=0)
    y = PAGE_IMP / 2 + 20 * len(lignes) / 2
    for txt, taille, gras in lignes:
        c.setFillColor(HexColor(couleur)); c.setFont('StoryBold' if gras else 'Story', taille)
        c.drawCentredString(PAGE_IMP / 2, y, txt); y -= taille * 1.6


def interieur(book, out, base, numero, prenom):
    """PDF intérieur pour l'imprimeur : 24 pages de 630 pt (fini 612 pt + fond perdu)."""
    M._register()
    base = Path(base)
    paths = {i: str(base / book['spreads'][i]) for i in range(9)}
    k = PAGE_IMP / M.S                                   # mise à l'échelle des pages du kit vers le format imprimé
    c = canvas.Canvas(str(out), pagesize=(PAGE_IMP, PAGE_IMP), pageCompression=1)
    c.setTitle(book['title'] + " – intérieur"); c.setAuthor("Mon Héros du Mois")
    # p1 : ex-libris (page de droite)
    _texte_page(c, [("Ce livre appartient à", 16, False), (prenom, 34, True)]); c.showPage()
    # p2 : mentions (gauche)
    _texte_page(c, [("Mon Héros du Mois", 11, False), (f"Collection – livre n° {numero}", 11, False)]); c.showPage()
    # p3 : page de titre (droite)
    _texte_page(c, [(l, 30 if i == 0 else 22, i == 0) for i, l in enumerate(book.get('coverTitle', {}).get('lines') or [book['title']])]); c.showPage()
    # p4 à p21 : les 18 pages d'histoire ; p4 (paire, à gauche) + p5 (droite) = double page 1, etc.
    folio = (SAFE + BLEED + 2) / k                       # folio dans la zone de sécurité de l'imprimeur
    for idx, p in enumerate(book['pages']):
        c.saveState(); c.scale(k, k)
        M.page_histoire(c, idx, p['text'], paths[idx // 2], book, folio_y=folio)
        c.restoreState(); c.showPage()
    # p22 : texte de quatrième (gauche), p23 : collection (droite), p24 : blanche
    c.saveState(); c.scale(k, k); M.page_quatrieme(c, paths[7], book); c.restoreState(); c.showPage()
    _texte_page(c, [("Fin", 30, True), (f"Livre n° {numero} de la collection de {prenom}", 12, False)]); c.showPage()
    _texte_page(c, []); c.showPage()
    c.save()
    return {"pages": PAGES_IMPRESSION, "format_pt": PAGE_IMP, "fini_pt": TRIM, "fond_perdu_pt": BLEED}


# ---------------------------------------------------------------- couverture à plat (4e | dos | 1re)
def dimensions_couverture(pages=PAGES_IMPRESSION):
    """Dimensions du fichier couverture : API Lulu (gabarit réel). Sans clés : None (aucune épaisseur inventée)."""
    import lulu
    if lulu.configured():
        w, h = lulu.cover_dimensions(pages)
        return {"largeur": w, "hauteur": h, "source": "API Lulu cover-dimensions", "confirme": True}
    return None


def couverture_a_plat(book, out, base, numero, prenom, dims=None):
    """Couverture à plat. dims : {'largeur', 'hauteur', 'source', 'confirme'}. Sans gabarit Lulu, maquette marquée non confirmée :
    dos de 0,25 po (tableau du guide Lulu, 24 à 84 pages) et rabat de 0,75 po, à remplacer par les dimensions de l'API."""
    M._register()
    base = Path(base)
    if dims is None:
        dos = 18.0; rabat = 54.0
        dims = {"largeur": 2 * (TRIM + rabat) + dos, "hauteur": TRIM + 2 * rabat, "source": "maquette : dos 0,25 po (guide Lulu), rabat 0,75 po supposé",
                "confirme": False}
    W, H = dims["largeur"], dims["hauteur"]
    m = (H - TRIM) / 2                                   # marge extérieure (rabat / fond perdu) donnée par le gabarit
    dos = max(0.0, W - 2 * (TRIM + m))
    c = canvas.Canvas(str(out), pagesize=(W, H)); c.setTitle("Couverture – " + book['title'])
    k = TRIM / M.S                                       # les pages du kit sont composées pour la zone finie (titres dans la zone sûre)
    cov = Image.open(base / book['cover']).convert("RGB")
    tmpd = Path(tempfile.mkdtemp())
    def fond(img, x, w):                                 # rabat et fond perdu : l'illustration prolongée (agrandie, adoucie)
        e = img.resize((int(w * 2), int(H * 2))).filter(ImageFilter.GaussianBlur(6))
        c.drawImage(ImageReader(e), x, 0, w, H)
    # 4e de couverture (à gauche)
    back = Image.open(base / book['spreads'][7]).convert("RGB"); bw, bh = back.size
    fond(back.crop((bw - bh, 0, bw, bh)), 0, TRIM + m)
    c.setFillColor(HexColor(book['backColor'])); c.setFillAlpha(.84); c.rect(0, 0, TRIM + m, H, fill=1, stroke=0); c.setFillAlpha(1)
    c.saveState(); _clip(c, m, m, TRIM, TRIM); c.translate(m, m); c.scale(k, k); M.page_quatrieme(c, str(base / book['spreads'][7]), book); c.restoreState()
    # 1re de couverture (à droite)
    fond(cov, W - TRIM - m, TRIM + m)
    cov.save(tmpd / "c.jpg", quality=95)
    c.saveState(); _clip(c, W - TRIM - m, m, TRIM, TRIM); c.translate(W - TRIM - m, m); c.scale(k, k); M.page_couverture(c, str(tmpd / "c.jpg"), book); c.restoreState()
    # dos : décor en continuité avec la couverture (bande gauche de l'illustration, adoucie), motif, numéro
    x0 = TRIM + m
    if dos > 0.5:
        bande = cov.crop((0, 0, max(8, cov.width // 24), cov.height)).resize((max(8, int(dos * 4)), cov.height)).filter(ImageFilter.GaussianBlur(3))
        sombre = Image.new("RGB", bande.size, (16, 22, 52)); bande = Image.blend(bande, sombre, .45)
        c.drawImage(ImageReader(bande), x0, 0, dos, H)
        cx = x0 + dos / 2
        # filets dorés en haut et en bas du dos
        c.setStrokeColor(HexColor('#D9B45A')); c.setLineWidth(.6)
        for y in (m + 26, m + TRIM - 26): c.line(x0 + 2, y, x0 + dos - 2, y)
        # petit motif : étoile
        _etoile(c, cx, m + TRIM - 44, min(5.5, dos * .28))
        # prénom + titre dans le sens de lecture de la collection, seulement si le dos est assez large
        if dos >= 36:
            c.saveState(); c.translate(cx + 4, m + TRIM / 2); c.rotate(-90)
            c.setFillColor(HexColor('#FFF1CF')); c.setFont('StoryBold', min(14, dos * .38))
            c.drawCentredString(0, 0, f"{prenom} – {book['title']}"[:60]); c.restoreState()
        # numéro de collection : pastille dorée, toujours à la même hauteur
        r = min(7.5, dos * .42); cy = m + NUM_Y_DEPUIS_BAS
        c.setFillColor(HexColor('#E8C25A')); c.circle(cx, cy, r, stroke=0, fill=1)
        c.setStrokeColor(HexColor('#9C7A2B')); c.setLineWidth(.4); c.circle(cx, cy, r, stroke=1, fill=0)
        fs = r * (1.25 if numero < 10 else .95)
        c.setFillColor(HexColor('#1A1F4A')); c.setFont('StoryBold', fs)
        c.drawCentredString(cx, cy - fs * .36, str(numero))
    c.showPage(); c.save()
    probs = []
    if not dims.get("confirme"):
        probs.append("Dimensions non confirmées : clés Lulu absentes, maquette d'après le guide Lulu (pas prêt à imprimer).")
    if dims.get("confirme") and dos < 9:
        probs.append(f"Gabarit de l'imprimeur incohérent avec ce calcul (dos de {dos:.1f} pt) : vérifier le gabarit téléchargé chez Lulu.")
    if PAGES_IMPRESSION < LULU_TEXTE_DOS_MIN_PAGES and os.getenv("DOS_NUMERO_VALIDE_IMPRIMEUR") != "1":
        probs.append(f"Lulu (guide de création) : pas de texte sur le dos à {PAGES_IMPRESSION} pages (minimum {LULU_TEXTE_DOS_MIN_PAGES}). "
                     "Le numéro est composé sur le dos, mais Lulu ne garantit pas son placement sur un dos de 0,25 po : "
                     "fichier NON prêt à imprimer tant que l'imprimeur ne l'a pas validé par écrit "
                     "(alors seulement : variable DOS_NUMERO_VALIDE_IMPRIMEUR=1).")
    return {"largeur": round(W, 2), "hauteur": round(H, 2), "dos": round(dos, 2), "marge": round(m, 2), "source": dims["source"],
            "numero": numero, "numero_y": NUM_Y_DEPUIS_BAS, "pret_a_imprimer": not probs, "problemes": probs}


def _clip(c, x, y, w, h):
    """Chaque face reste dans son panneau : rien ne déborde sur le dos ni sur l'autre face."""
    pa = c.beginPath(); pa.rect(x, y, w, h); c.clipPath(pa, stroke=0, fill=0)


def _etoile(c, cx, cy, r):
    import math
    p = c.beginPath()
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5; rr = r if i % 2 == 0 else r * .45
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    p.close(); c.setFillColor(HexColor('#E8C25A')); c.drawPath(p, fill=1, stroke=0)


# ---------------------------------------------------------------- aperçus déterministes
def _pdf_png(pdf, page, dpi, dst):
    """Rendu d'une page en PNG : PyMuPDF (installé sur le serveur), sinon poppler (pdftoppm)."""
    try:
        import fitz
        doc = fitz.open(str(pdf))
        doc[page - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72)).save(str(dst))
        doc.close()
        return dst
    except ImportError:
        pass
    tmp = Path(tempfile.mkdtemp()) / "p"
    subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', str(dpi), '-png', '-singlefile', str(pdf), str(tmp)], check=True)
    shutil.move(str(tmp) + ".png", dst)
    return dst


def apercus(folder, pdf_lecture, pdf_couv, info_couv, doubles=(1, 5)):
    """Tous les aperçus viennent des PDF réels : rien n'est redessiné ni généré."""
    d = Path(folder) / "apercus"; d.mkdir(exist_ok=True)
    out = {}
    out["couverture"] = _pdf_png(pdf_lecture, 1, 110, d / "couverture.png").name
    out["couverture_a_plat"] = _pdf_png(pdf_couv, 1, 60, d / "couverture_a_plat.png").name
    hd = _pdf_png(pdf_couv, 1, 300, d / "_couv_hd.png")
    im = Image.open(hd); k = 300 / 72
    x0 = (TRIM + info_couv["marge"]) * k; dos = info_couv["dos"] * k
    zone = im.crop((int(x0 - 3 * dos), int(im.height - (info_couv["marge"] + 160) * k), int(x0 + 4 * dos), im.height))
    zone.save(d / "dos_detail.png"); out["dos_detail"] = "dos_detail.png"
    for n in doubles:                                   # double page n = pages 2n et 2n+1 du PDF de lecture
        a = Image.open(_pdf_png(pdf_lecture, 2 * n, 80, d / "_a.png")); b = Image.open(_pdf_png(pdf_lecture, 2 * n + 1, 80, d / "_b.png"))
        s = Image.new("RGB", (a.width + b.width, a.height)); s.paste(a, (0, 0)); s.paste(b, (a.width, 0))
        s.save(d / f"double_{n}.png"); out[f"double_{n}"] = f"double_{n}.png"
    m = info_couv["marge"] * k
    tranche = im.crop((int(x0), int(m), int(x0 + dos), int(im.height - m)))
    out["album"] = _album(Image.open(d / "couverture.png"), tranche, d / "album.png").name
    out["etagere"] = _etagere(tranche, d / "etagere.png").name
    for f in d.glob("_*.png"): f.unlink()
    return out


def _album(couv, dos, dst):
    """Album fin : la vraie couverture, le vrai dos (6 mm) et une tranche de pages très mince, en légère perspective."""
    W = 900; couv = couv.resize((W, W)); dos = dos.resize((max(10, int(W * 6.35 / 216)), W))
    canvas_ = Image.new("RGB", (W + 220, W + 160), (238, 230, 214))
    ombre = Image.new("L", canvas_.size, 0); ImageDraw.Draw(ombre).rectangle((90, 110, 90 + W + dos.width + 20, 110 + W + 30), fill=120)
    canvas_.paste((150, 130, 110), (0, 0), ombre.filter(ImageFilter.GaussianBlur(28)))
    canvas_.paste(dos, (70, 60)); canvas_.paste(couv, (70 + dos.width, 60))
    tr = Image.new("RGB", (8, W - 8), (250, 246, 236)); dr = ImageDraw.Draw(tr)
    for y in range(0, tr.height, 3): dr.line((0, y, 8, y), fill=(226, 218, 200))
    canvas_.paste(tr, (70 + dos.width + W, 64))
    canvas_.save(dst); return Path(dst)


def _etagere(tranche, dst):
    """Le dos réel du livre, debout sur une étagère (agrandi pour lire le numéro) : même fichier que l'imprimé."""
    h = 760; w = max(26, int(tranche.width * h / tranche.height))
    t = tranche.resize((w, h), Image.LANCZOS)
    im = Image.new("RGB", (420, h + 120), (244, 236, 220)); dr = ImageDraw.Draw(im)
    dr.rectangle((0, h + 60, 420, h + 120), fill=(170, 128, 86)); dr.rectangle((0, h + 60, 420, h + 66), fill=(205, 165, 118))
    im.paste(t, ((420 - w) // 2, 60))
    im.save(dst); return Path(dst)


# ---------------------------------------------------------------- livre finalisé : manifeste, gel, sauvegarde
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def finaliser(folder, fichiers, meta):
    """Manifeste du livre finalisé : liste et empreintes des fichiers gardés. Ensuite, plus aucun appel de génération."""
    folder = Path(folder)
    man = {"version_fabrication": VERSION, "version_moteur": M.VERSION, "finalise_le": time.strftime("%Y-%m-%dT%H:%M:%S"),
           **meta, "fichiers": {f: sha(folder / f) for f in fichiers if (folder / f).exists()}}
    (folder / "final.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return man


def est_finalise(folder):
    return (Path(folder) / "final.json").exists()


def sauvegarder(folder, dest_dir):
    """Archive du livre finalisé (texte, images originales, références, PDF, aperçus, manifeste). Restaurable sans génération."""
    folder = Path(folder); dest = Path(dest_dir); dest.mkdir(parents=True, exist_ok=True)
    z = dest / f"{folder.name}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zz:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and "rendu" not in p.parts:
                zz.write(p, str(p.relative_to(folder)))
    return z


def restaurer(zip_path, folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zz:
        zz.extractall(folder)
    man = json.loads((folder / "final.json").read_text(encoding="utf-8"))
    bad = [f for f, h in man["fichiers"].items() if not (folder / f).exists() or sha(folder / f) != h]
    return {"ok": not bad, "fichiers_abimes": bad}
