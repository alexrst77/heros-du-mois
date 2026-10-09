# -*- coding: utf-8 -*-
"""Factures : numérotation continue par année (MHM-2026-0001…), PDF avec les mentions obligatoires, livre des recettes.

- Une facture par commande payée (la commande d'origine, qui porte le montant encaissé) ; jamais deux pour la même commande.
- Le détail vient de ce qui a été encaissé (lignes enregistrées à la commande) ; une facture émise n'est jamais modifiée.
- Franchise en base : « TVA non applicable, art. 293 B du CGI ». Régime réel : HT, TVA par taux, TTC (taux réglés dans l'admin).
- Refusée tant que le vendeur n'est pas identifié (nom, adresse, SIRET) : une facture sans ces mentions n'est pas valable."""
import json, time, threading, sqlite3
from pathlib import Path
import commandes as db, paiement, legal

DOSSIER = db.DATA / "factures"; DOSSIER.mkdir(exist_ok=True)
_lock = threading.Lock()
ROOT = Path(__file__).parent

with db._db() as _c:
    _c.executescript("""create table if not exists factures (
      id integer primary key autoincrement, numero text unique, commande text unique, cree real, date_vente real,
      client text, lignes text, total integer, regime text, vendeur text);""")


class FactureError(Exception):
    pass


def _row(r):
    if not r:
        return None
    d = dict(r)
    for k in ("client", "lignes", "vendeur"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def lister(annee=None):
    with db._db() as c:
        q = "select * from factures" + (" where numero like ?" if annee else "") + " order by id"
        return [_row(r) for r in c.execute(q, ((f"MHM-{annee}-%",) if annee else ()))]


def de_commande(oid):
    with db._db() as c:
        return _row(c.execute("select * from factures where commande=?", (oid,)).fetchone())


def par_numero(numero):
    with db._db() as c:
        return _row(c.execute("select * from factures where numero=?", (numero,)).fetchone())


def lignes_commande(o, livre_json):
    """Lignes encaissées : enregistrées à la commande, sinon recalculées si elles retombent exactement sur le montant payé."""
    L = (livre_json or {}).get("lignes")
    if not L:
        f = (livre_json or {}).get("form") or {}
        try:
            L = paiement.lignes(o["formule"], (o["adresse"] or {}).get("pays"), calendrier=bool(f.get("calendrier")),
                                coloriage=bool(f.get("coloriage")), objets=f.get("objets") or [])
        except KeyError:
            L = []
    if sum(q * u for _, q, u, _ in L) != (o["montant"] or 0):
        L = [("Commande Mon Héros du Mois (créations personnalisées)", 1, o["montant"] or 0, "livre")]
    return [list(x) for x in L]


def calcul(lignes, vendeur):
    """Montants par ligne et par taux. En franchise : tout est en « net », TVA 0."""
    reel = vendeur["regime_tva"] == "reel"
    taux = vendeur["taux_tva"]
    cat_princ = next((c for _, _, _, c in lignes if c != "port"), "livre")
    out, tva = [], {}
    for lib, q, pu, cat in lignes:
        ttc = q * pu
        t = (taux.get(cat_princ if cat == "port" else cat, 20.0)) if reel else 0.0
        ht = round(ttc / (1 + t / 100)) if reel else ttc
        out.append({"libelle": lib, "quantite": q, "pu_ttc": pu, "total_ttc": ttc, "taux": t, "total_ht": ht})
        if reel:
            tva[str(t)] = tva.get(str(t), 0) + (ttc - ht)
    total_ttc = sum(x["total_ttc"] for x in out)
    return {"lignes": out, "tva": tva, "total_ttc": total_ttc, "total_ht": sum(x["total_ht"] for x in out), "reel": reel}


def paiement_reel(o):
    """Vrai paiement Stripe (mode live). Les paiements de test (carte 4242) et simulés ne donnent jamais de facture."""
    return (o.get("stripe_session") or "").startswith("cs_live_")


def emettre(oid, livre_json):
    """Crée (une fois) la facture d'une commande payée. Renvoie la facture existante si elle est déjà émise."""
    o = db.get(oid)
    if not o:
        raise FactureError("commande introuvable")
    if (o["origine"] or oid) != oid:
        raise FactureError("la facture se fait sur la commande d'origine (celle qui porte le paiement)")
    if o["statut"] == "attente_paiement" or not o["montant"] or (o["formule"] or "").startswith("essai"):
        raise FactureError("seulement pour une commande payée (pas un essai, pas un test)")
    if not paiement_reel(o):
        raise FactureError("paiement de test (Stripe en mode test ou simulé) : pas de facture, pour garder une numérotation sans trou")
    deja = de_commande(oid)
    if deja:
        return deja
    v = legal.lire()
    manque = [x for x, k in (("nom ou raison sociale", "raison_sociale"), ("adresse", "adresse"), ("SIRET", "siret")) if not v.get(k)]
    if manque:
        raise FactureError("informations du vendeur à compléter (Réglages → Mon entreprise) : " + ", ".join(manque))
    a = o["adresse"] or {}
    client = {"nom": a.get("nom"), "adresse": " ".join(x for x in (a.get("adresse1"), a.get("adresse2")) if x),
              "code_postal": a.get("code_postal"), "ville": a.get("ville"), "pays": a.get("pays"), "email": o["email"]}
    L = lignes_commande(o, livre_json)
    vend = {k: v.get(k) for k in ("raison_sociale", "forme", "adresse", "siret", "tva_intra", "email", "regime_tva", "rcs")}
    vend["taux_tva"] = v["taux_tva"]
    with _lock, db._lock, db._db() as c:
        an = time.strftime("%Y")
        n = c.execute("select count(*) from factures where numero like ?", (f"MHM-{an}-%",)).fetchone()[0] + 1
        numero = f"MHM-{an}-{n:04d}"
        try:
            c.execute("insert into factures (numero, commande, cree, date_vente, client, lignes, total, regime, vendeur) values (?,?,?,?,?,?,?,?,?)",
                      (numero, oid, time.time(), o["cree"], json.dumps(client, ensure_ascii=False), json.dumps(L, ensure_ascii=False),
                       o["montant"], v["regime_tva"], json.dumps(vend, ensure_ascii=False)))
        except sqlite3.IntegrityError:
            pass
    f = de_commande(oid)
    pdf(f)
    return f


def chemin(numero):
    return DOSSIER / f"{numero}.pdf"


def pdf(f):
    """PDF de la facture, à partir de ce qui est enregistré (identique à chaque régénération)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    for nom, fic in (("Texte", "DejaVuSans.ttf"), ("Gras", "DejaVuSans-Bold.ttf"), ("Titre", "YoungSerif-Regular.ttf")):
        try:
            pdfmetrics.getFont(nom)
        except KeyError:
            pdfmetrics.registerFont(TTFont(nom, str(ROOT / "fonts" / fic)))
    v, cl = f["vendeur"], f["client"]
    c_ = calcul(f["lignes"], v)
    W, H = A4
    out = chemin(f["numero"])
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle(f"Facture {f['numero']}")
    encre, doux = (0.12, 0.15, 0.34), (0.42, 0.44, 0.56)
    e = lambda cents: f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")
    try:
        c.drawImage(ImageReader(str(ROOT / "static" / "marque" / "etoile-128.png")), 40, H - 92, 46, 46, mask="auto")
    except Exception:
        pass
    c.setFillColorRGB(*encre); c.setFont("Titre", 20); c.drawString(94, H - 66, "Mon Héros du Mois")
    c.setFont("Texte", 9); c.setFillColorRGB(*doux)
    y = H - 84
    for t in (f"{v['raison_sociale']} · {v.get('forme') or ''}", v["adresse"], f"SIRET {v['siret']}" + (f" · TVA {v['tva_intra']}" if v.get("tva_intra") else ""), v.get("email") or ""):
        c.drawString(94, y, t[:110]); y -= 12
    c.setFillColorRGB(*encre); c.setFont("Titre", 26); c.drawRightString(W - 40, H - 66, "Facture")
    c.setFont("Texte", 10)
    c.drawRightString(W - 40, H - 84, f"N° {f['numero']}")
    c.drawRightString(W - 40, H - 98, "Émise le " + time.strftime("%d/%m/%Y", time.localtime(f["cree"])))
    c.drawRightString(W - 40, H - 112, "Date de la vente : " + time.strftime("%d/%m/%Y", time.localtime(f["date_vente"])))
    c.drawRightString(W - 40, H - 126, f"Commande {f['commande']}")
    y = H - 175
    c.setFont("Gras", 10); c.drawString(40, y, "Facturé à"); c.setFont("Texte", 10)
    for t in (cl.get("nom") or "", cl.get("adresse") or "", f"{cl.get('code_postal') or ''} {cl.get('ville') or ''}", cl.get("pays") or "", cl.get("email") or ""):
        y -= 14; c.drawString(40, y, t[:90])
    y -= 34
    reel = c_["reel"]
    cols = [(40, "Désignation"), (330, "Qté"), (370, "PU TTC"), (440, "TVA" if reel else ""), (W - 40, "Total TTC" if reel else "Total")]
    c.setFillColorRGB(0.98, 0.95, 0.9); c.rect(36, y - 6, W - 72, 20, stroke=0, fill=1); c.setFillColorRGB(*encre)
    c.setFont("Gras", 9)
    for x, t in cols:
        (c.drawRightString if x == W - 40 else c.drawString)(x, y, t)
    c.setFont("Texte", 9.5)
    for l in c_["lignes"]:
        y -= 22
        c.drawString(40, y, l["libelle"][:58]); c.drawString(330, y, str(l["quantite"])); c.drawString(370, y, e(l["pu_ttc"]))
        if reel:
            c.drawString(440, y, f"{l['taux']:g} %".replace(".", ","))
        c.drawRightString(W - 40, y, e(l["total_ttc"]))
    y -= 14; c.setStrokeColorRGB(0.85, 0.82, 0.76); c.line(40, y, W - 40, y)
    y -= 22
    if reel:
        c.drawRightString(W - 140, y, "Total HT"); c.drawRightString(W - 40, y, e(c_["total_ht"]))
        for t, m in sorted(c_["tva"].items(), key=lambda x: float(x[0])):
            y -= 16; c.drawRightString(W - 140, y, f"TVA {float(t):g} %".replace(".", ",")); c.drawRightString(W - 40, y, e(m))
        y -= 20
    c.setFont("Gras", 12); c.drawRightString(W - 140, y, "Total TTC" if reel else "Total"); c.drawRightString(W - 40, y, e(c_["total_ttc"]))
    y -= 20; c.setFont("Texte", 9.5); c.setFillColorRGB(*doux)
    c.drawRightString(W - 40, y, "Payée par carte bancaire (Stripe) à la commande.")
    y -= 40
    if not reel:
        c.setFillColorRGB(*encre); c.setFont("Gras", 9.5); c.drawString(40, y, "TVA non applicable, article 293 B du Code général des impôts.")
        y -= 16
    c.setFont("Texte", 8.5); c.setFillColorRGB(*doux)
    from reportlab.lib.utils import simpleSplit
    for t in ("Produits personnalisés selon les spécifications de l'acheteur : pas de droit de rétractation (article L221-28, 3° du Code de la consommation).",
              "Garanties légales de conformité et des vices cachés applicables. Conditions générales de vente : sur le site, page « Conditions de vente »."):
        for ligne in simpleSplit(t, "Texte", 8.5, W - 80):
            c.drawString(40, y, ligne); y -= 11
        y -= 3
    c.setFont("Texte", 8); c.drawCentredString(W / 2, 30, f"{v['raison_sociale']} · {v['adresse']} · SIRET {v['siret']}"[:140])
    c.showPage(); c.save()
    return out


def livre_recettes_csv(annee=None):
    """Livre des recettes (micro-entreprise) : date, numéro, client, nature, montant, mode de règlement."""
    import csv, io
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
    w.writerow(["Date d'encaissement", "N° de facture", "Client", "Nature de la vente", "Montant TTC (€)", "Mode de règlement", "Commande"])
    for f in lister(annee):
        nature = " + ".join(f"{q} × {lib}" for lib, q, _, cat in f["lignes"] if cat != "port")
        w.writerow([time.strftime("%d/%m/%Y", time.localtime(f["date_vente"])), f["numero"], (f["client"] or {}).get("nom", ""), nature,
                    f"{f['total'] / 100:.2f}".replace(".", ","), "Carte bancaire (Stripe)", f["commande"]])
    return "﻿" + buf.getvalue()
