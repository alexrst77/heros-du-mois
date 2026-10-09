# -*- coding: utf-8 -*-
"""Atelier : (re)peint des modèles d'avatar sur le serveur (clé OpenAI de production). Aujourd'hui : tout le pack existant
(12 coiffures, 5 animaux, 5 doudous) repeint dans le style des 8 nouveaux modèles validés par Alex.
Admin > Réglages > « Repeindre le pack », puis « Télécharger le zip » : les images sont ensuite détourées,
masquées (build_masks.py / build_extras.py) et ajoutées à static/avatars/ (relues à la main avant la mise en ligne)."""
import os, io, base64, json, threading, time, zipfile
from pathlib import Path
import commandes as db

PACK = Path(__file__).parent / "style" / "avatars"
DOSSIER = db.DATA / "atelier_avatars"; DOSSIER.mkdir(parents=True, exist_ok=True)

COMMUN = ("Keep EXACTLY the same painting style, brush texture, soft lighting, line quality, colour richness, scale, framing, "
          "camera angle and centring as the reference image. One single character, full body, on a plain flat pure white background "
          "(#FFFFFF), no ground shadow, no scenery, no text, no frame.")

# Pack repeint dans le style des 8 modèles validés par Alex (octobre 2026). Image 1 = le modèle actuel (personnage, cadrage,
# couleurs : les masques de recoloration en dépendent), image 2 = un modèle du nouveau style (pinceau, lumière, finesse).
STYLE = ("Repaint the character of image 1 in the refined painting style of image 2: same rich soft brushwork, fine fur or hair strands, "
         "warm soft lighting, delicate details and colour richness as image 2. Keep EXACTLY the character, pose, expression, proportions, "
         "framing, size and position in the frame of image 1, and keep EXACTLY its colours (they are recoloured automatically later). "
         "Plain flat pure white background (#FFFFFF), no ground shadow, no scenery, no text, no frame.")
ENFANT = ("Same child as image 1 (same face, same age, same hairstyle and hair length, same chestnut-brown hair colour, same light skin tone, "
          "same brown eyes, same light freckles on the nose and cheeks, same yellow pyjama top with small cream stars). Head-and-shoulders bust "
          "portrait cropped at mid-chest exactly like image 1, the bottom edge of the top softly rounded like image 1.")
COIFFURES = {"court": "short neat hair", "bataille": "short messy tousled hair", "boucle-court": "short curly hair", "afro": "big round afro hair",
             "carre": "chin-length bob haircut with bangs", "long": "long straight hair falling past the shoulders", "long-boucle": "long curly hair",
             "couettes": "hair in two pigtails", "queue-cheval": "hair in a high ponytail", "tresses": "hair in two long braids",
             "chignon": "hair in a round top bun", "tres-court": "very short buzz-cut hair"}
ANIMAUX = {"chat": "ginger kitten with cream muzzle, chest and belly, tabby stripes", "chien": "fawn puppy with cream muzzle and chest",
           "lapin": "ginger rabbit with cream muzzle and belly", "hamster": "golden-fawn hamster with cream cheeks and belly",
           "oiseau": "yellow little bird with a cream belly and an orange beak"}
DOUDOUS = {"lapin": "rabbit", "ours": "teddy bear", "chat": "cat", "chien": "dog", "elephant": "elephant"}
REPEINDRE = {}
for k, v in COIFFURES.items():
    REPEINDRE[f"enfant-{k}"] = (f"enfant-{k}.png", "enfant-garcon-mi-long.png", f"{ENFANT} Hairstyle: {v}.")
for k, v in ANIMAUX.items():
    REPEINDRE[f"animal-{k}"] = (f"animal-{k}.png", "animal-chien-labrador.png", f"Same {v} as image 1, a real living animal, same markings.")
for k, v in DOUDOUS.items():
    REPEINDRE[f"doudou-{k}"] = (f"doudou-{k}.png", "animal-chien-labrador.png",
                                f"Same soft plush {v} cuddly toy as image 1 (NOT a living animal: button eyes, visible stitching, soft velvety fabric), "
                                "same pale blue fabric and same red bow at the neck; take only the brushwork and lighting from image 2.")
# Ce que l'atelier propose aujourd'hui : (modèle de départ, référence de style ou None, consigne)
NOUVEAUX = dict(REPEINDRE)
ETAT = {"en_cours": False, "faits": [], "erreurs": {}}


def fichier(nom):
    return DOSSIER / f"{nom}.png"


def etat():
    return {"en_cours": ETAT["en_cours"], "erreurs": ETAT["erreurs"],
            "modeles": [{"nom": n, "pret": fichier(n).exists()} for n in NOUVEAUX]}


def peindre(log=print, refaire=()):
    """Peint les modèles manquants (ou ceux de `refaire`). UN appel par image, jamais de seconde tentative automatique."""
    import generator as G
    if ETAT["en_cours"]:
        return
    ETAT.update(en_cours=True, erreurs={})
    try:
        for nom, (base, style, consigne) in NOUVEAUX.items():
            if fichier(nom).exists() and nom not in refaire:
                continue
            try:
                G.check_budget()
                fhs = [open(PACK / f, "rb") for f in (base, style) if f]
                try:
                    r = G._client().images.edit(model=G.IMAGE_MODEL, image=fhs, prompt=consigne + " " + (STYLE if style else COMMUN),
                                                size="1024x1024", quality=os.getenv("ATELIER_QUALITE", "high"), n=1)
                finally:
                    for fh in fhs: fh.close()
                G._count("image", G.IMAGE_MODEL, getattr(r, "usage", None))
                fichier(nom).write_bytes(base64.b64decode(r.data[0].b64_json))
                log(f"atelier avatars : {nom} peint")
            except Exception as e:
                ETAT["erreurs"][nom] = f"{type(e).__name__}: {str(e)[:200]}"
                log(f"atelier avatars : {nom} impossible : {e}")
                if "Budget" in type(e).__name__:
                    break
    finally:
        ETAT["en_cours"] = False


def lancer(log=print, refaire=()):
    threading.Thread(target=peindre, args=(log, tuple(refaire)), daemon=True).start()


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in NOUVEAUX:
            if fichier(n).exists():
                z.write(fichier(n), f"{n}.png")
        z.writestr("consignes.json", json.dumps({n: v[2] for n, v in NOUVEAUX.items()}, ensure_ascii=False, indent=1))
    buf.seek(0)
    return buf
