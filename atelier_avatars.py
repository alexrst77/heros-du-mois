# -*- coding: utf-8 -*-
"""Atelier : peint les NOUVEAUX modèles d'avatar (même style que le pack), sur le serveur (clé OpenAI de production).
Admin > Réglages > « Peindre les nouveaux avatars », puis « Télécharger le zip » : les images sont ensuite détourées,
masquées (build_masks.py / build_extras.py) et ajoutées à static/avatars/ (relues à la main avant la mise en ligne)."""
import os, io, base64, json, threading, time, zipfile
from pathlib import Path
import commandes as db

PACK = Path(__file__).parent / "style" / "avatars"
DOSSIER = db.DATA / "atelier_avatars"; DOSSIER.mkdir(parents=True, exist_ok=True)

COMMUN = ("Keep EXACTLY the same painting style, brush texture, soft lighting, line quality, colour richness, scale, framing, "
          "camera angle and centring as the reference image. One single character, full body, on a plain flat pure white background "
          "(#FFFFFF), no ground shadow, no scenery, no text, no frame.")
NOUVEAUX = {
    "enfant-garcon-long": ("enfant-court.png", "The same little boy (same face, same age, same pose, same yellow star pyjamas, same skin) but with LONG "
                           "straight hair reaching his shoulders, clearly a boy."),
    "enfant-garcon-mi-long": ("enfant-court.png", "The same little boy (same face, same age, same pose, same yellow star pyjamas, same skin) but with "
                              "MEDIUM-LENGTH hair: soft layered hair covering the ears and reaching the chin, slightly wavy, clearly a boy."),
    "animal-chien-labrador": ("animal-chien.png", "Turn this dog into a friendly young LABRADOR RETRIEVER (golden yellow coat, broad head, floppy ears, "
                              "otter tail), same pose and same size in the frame, no collar."),
    "animal-chien-berger-australien": ("animal-chien.png", "Turn this dog into a cute AUSTRALIAN SHEPHERD (blue merle coat with white blaze, white chest "
                                       "and copper points, semi-floppy ears, fluffy fur), same pose and same size in the frame, no collar."),
    "animal-chien-bouledogue": ("animal-chien.png", "Turn this dog into a cute FRENCH BULLDOG (fawn coat, big upright bat ears, short flat muzzle, "
                                "compact muscular body), same pose and same size in the frame, no collar."),
    "animal-chien-jack-russell": ("animal-chien.png", "Turn this dog into a cute JACK RUSSELL TERRIER (white coat with tan patches on the head and one "
                                  "on the back, folded ears, small sturdy body), same pose and same size in the frame, no collar."),
    "animal-tortue": ("animal-hamster.png", "Instead of this hamster, paint a cute little pet TORTOISE (land turtle) with a rounded green-brown shell "
                      "with clear hexagonal plates, friendly face with big dark eyes, sitting in the same place and at the same size in the frame."),
    "animal-poisson": ("animal-hamster.png", "Instead of this hamster, paint a cute little pet GOLDFISH, bright orange, with big dark eyes and flowing "
                       "fins, shown on its own (no bowl, no water), floating at the same place and size in the frame."),
}
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
        for nom, (base, consigne) in NOUVEAUX.items():
            if fichier(nom).exists() and nom not in refaire:
                continue
            try:
                G.check_budget()
                with open(PACK / base, "rb") as fh:
                    r = G._client().images.edit(model=G.IMAGE_MODEL, image=[fh], prompt=consigne + " " + COMMUN, size="1024x1024",
                                                quality=os.getenv("ATELIER_QUALITE", "high"), n=1)
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
        z.writestr("consignes.json", json.dumps({n: v[1] for n, v in NOUVEAUX.items()}, ensure_ascii=False, indent=1))
    buf.seek(0)
    return buf
