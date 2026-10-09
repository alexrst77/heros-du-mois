# -*- coding: utf-8 -*-
"""Informations du vendeur (une seule source) et pages légales : CGV, mentions légales, politique de confidentialité.

Les informations se saisissent dans l'admin (Réglages → Mon entreprise) et sont enregistrées dans DATA/vendeur.json.
Tant qu'un champ obligatoire manque, la page publique l'affiche en jaune « à compléter » : rien n'est inventé."""
import json, re, html
from pathlib import Path
import commandes as db

FICHIER = db.DATA / "vendeur.json"
PAGES = Path(__file__).parent / "static" / "legal"

CHAMPS = {   # clé : (libellé, obligatoire, valeur par défaut)
    "raison_sociale": ("Nom ou raison sociale", True, ""),
    "forme": ("Forme juridique", True, "Entrepreneur individuel (micro-entreprise)"),
    "capital": ("Capital social (société seulement)", False, ""),
    "adresse": ("Adresse du siège", True, ""),
    "siret": ("SIRET", True, ""),
    "rcs": ("Immatriculation (RCS ou RNE)", False, ""),
    "tva_intra": ("N° de TVA intracommunautaire", False, ""),
    "directeur_publication": ("Directeur de la publication", True, ""),
    "email": ("E-mail de contact", True, "monherosdumois@gmail.com"),
    "telephone": ("Téléphone", False, ""),
    "regime_tva": ("Régime de TVA (franchise ou reel)", True, "franchise"),
    "mediateur_nom": ("Médiateur de la consommation", True, ""),
    "mediateur_url": ("Site du médiateur", True, ""),
    "hebergeur": ("Hébergeur", True, "Railway Corporation"),
    "hebergeur_adresse": ("Adresse de l'hébergeur", True, ""),
    "hebergeur_contact": ("Contact de l'hébergeur", True, "https://railway.com"),
}
TAUX_DEFAUT = {"livre": 5.5, "coloriage": 5.5, "calendrier": 20.0, "objet": 20.0}   # à faire confirmer par un comptable


def lire():
    d = {k: v[2] for k, v in CHAMPS.items()}
    d["taux_tva"] = dict(TAUX_DEFAUT)
    if FICHIER.exists():
        try:
            d.update(json.loads(FICHIER.read_text(encoding="utf-8")))
        except ValueError:
            pass
    d["taux_tva"] = {**TAUX_DEFAUT, **(d.get("taux_tva") or {})}
    return d


def enregistrer(data):
    d = lire()
    for k in CHAMPS:
        if k in data:
            d[k] = re.sub(r"\s+", " ", str(data[k] or "")).strip()[:300]
    if d["regime_tva"] not in ("franchise", "reel"):
        d["regime_tva"] = "franchise"
    if isinstance(data.get("taux_tva"), dict):
        for k in TAUX_DEFAUT:
            try:
                d["taux_tva"][k] = max(0.0, min(30.0, float(data["taux_tva"].get(k, d["taux_tva"][k]))))
            except (TypeError, ValueError):
                pass
    FICHIER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def manquants(d=None):
    d = d or lire()
    return [CHAMPS[k][0] for k, (lib, obl, _) in CHAMPS.items() if obl and not d.get(k)]


def page(nom):
    """Page légale avec les informations du vendeur ; un champ vide apparaît « à compléter » (jamais inventé)."""
    d = lire()
    src = (PAGES / f"{nom}.html").read_text(encoding="utf-8")

    def champ(m):
        k = m.group(1)
        v = d.get(k)
        if k == "regime_tva_mention":
            return ("TVA non applicable, article 293 B du Code général des impôts." if d["regime_tva"] == "franchise"
                    else "Les prix sont indiqués toutes taxes comprises (TVA française au taux applicable à chaque produit).")
        if k == "capital_txt":
            return f", au capital de {html.escape(d['capital'])}" if d.get("capital") else ""
        if v:
            if k.endswith("_url") or k == "hebergeur_contact":
                return f'<a href="{html.escape(v)}" rel="noopener">{html.escape(v)}</a>' if v.startswith("http") else html.escape(v)
            return html.escape(v)
        return f'<span class="todo">à compléter : {html.escape(CHAMPS.get(k, (k,))[0])}</span>'
    return re.sub(r"\{\{(\w+)\}\}", champ, src)
