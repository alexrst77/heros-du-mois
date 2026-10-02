# -*- coding: utf-8 -*-
"""Vignettes illustrées des univers et des fêtes (cartes de l'accueil), dans le style des livres Mila et Noé.
Une image carrée par carte, sans personnage identifiable ni texte, dans static/vitrine/univ/<clé>.webp.
Les cartes qui ont déjà leur image (tirée d'un vrai livre) ne sont jamais refaites.

Lancement (une fois OpenAI rechargé) : depuis l'admin, bouton « Générer les vignettes », ou
    python3 vignettes.py            -> toutes les vignettes manquantes
Coût indicatif : une image moyenne qualité par vignette (≈ 26 au maximum)."""
import os, base64, sys
from pathlib import Path
from PIL import Image
import univers as U

FIXES = Path(__file__).parent / "static" / "vitrine" / "univ"                       # tirées des vrais livres (dans le code)
OUT = Path(os.getenv("DATA_DIR") or Path(__file__).parent / "data") / "vignettes"     # générées : sur le volume, gardées entre deux mises en ligne
STYLE = [Path(__file__).parent / "kit" / "style" / f for f in ("jour-mila-2.jpg", "nuit-noe-6.jpg")]
PROMPT = ("Square illustration for a card on a premium French children's picture-book website, same painting style as the reference "
          "images (rich hand-painted gouache and fine coloured pencil, magical soft light, layered detailed scenery, fairy-tale colours). "
          "SUBJECT: {sujet}. A small child seen from behind or at a distance may appear, no recognisable face. "
          "No text, no letters, no frame, no border. Composition centred, readable at small size.")


def manquantes():
    OUT.mkdir(parents=True, exist_ok=True)
    return [u for u in U.UNIVERS if not chemin(u["cle"])]


def chemin(cle):
    for d in (FIXES, OUT):
        if (d / f"{cle}.webp").exists():
            return d / f"{cle}.webp"
    return None


def generer(progress=print):
    import generator as G
    model = os.getenv("OPENAI_VIGNETTE_MODEL") or G.IMAGE_MODEL
    faites = []
    for u in manquantes():
        G.check_budget()
        progress(f"vignette {u['cle']}")
        fhs = [open(p, "rb") for p in STYLE if p.exists()]
        try:
            r = G._retry(lambda: G._client().images.edit(model=model, image=fhs, prompt=PROMPT.format(sujet=u["image"]),
                                                       size="1024x1024", quality=os.getenv("OPENAI_VIGNETTE_QUALITY", "medium"), n=1))
        finally:
            for f in fhs: f.close()
        G._count("image", model, getattr(r, "usage", None))
        tmp = OUT / f"{u['cle']}.png"
        tmp.write_bytes(base64.b64decode(r.data[0].b64_json))
        Image.open(tmp).convert("RGB").resize((520, 520), Image.LANCZOS).save(OUT / f"{u['cle']}.webp", quality=82)
        tmp.unlink()
        faites.append(u["cle"])
    return faites


if __name__ == "__main__":
    if "--liste" in sys.argv:
        print([u["cle"] for u in manquantes()])
    else:
        print(generer())
