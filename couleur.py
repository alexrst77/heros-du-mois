# -*- coding: utf-8 -*-
"""Correction automatique de la dominante jaune-orangée des images générées (défaut connu de gpt-image-1,
aggravé à chaque passage en mode « edit »). Balance des blancs douce en Lab : on ramène la moyenne de l'image
vers une référence neutre (celle des illustrations de Léo), en épargnant les sources de lumière chaudes saturées
(lanternes, soleil) et les tons chair. L'original est conservé à côté (_brut.png)."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageCms

_SRGB = ImageCms.createProfile("sRGB")
_LAB = ImageCms.createProfile("LAB")
_TO_LAB = ImageCms.buildTransformFromOpenProfiles(_SRGB, _LAB, "RGB", "LAB")
_TO_RGB = ImageCms.buildTransformFromOpenProfiles(_LAB, _SRGB, "LAB", "RGB")

TARGET_A, TARGET_B = 4.0, 13.0   # moyenne a*/b* visée : médiane des pages de Léo (b* de 7 à 21)
TRIGGER_B = 17.0                 # en dessous, on ne touche à rien (le rendu de Léo reste intact)
STRENGTH = 0.9                  # part de l'écart corrigée


def warm_share(im):
    hsv = np.asarray(im.resize((128, 128)).convert("HSV")).astype(np.float32)
    h, s = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255
    return float(((h > 15) & (h < 55) & (s > 0.3)).mean())


def stats(im):
    lab = np.asarray(ImageCms.applyTransform(im.convert("RGB").resize((256, 256)), _TO_LAB))
    a, b = lab[..., 1].view(np.int8).astype(np.float32), lab[..., 2].view(np.int8).astype(np.float32)
    return float(a.mean()), float(b.mean())


def neutralize(im):
    """Renvoie (image corrigée, infos). Ne touche pas une image déjà équilibrée."""
    im = im.convert("RGB")
    lab = np.asarray(ImageCms.applyTransform(im, _TO_LAB))       # a*, b* stockés en octets signés par Pillow
    L = lab[..., 0].astype(np.float32) / 255 * 100
    a, b = lab[..., 1].view(np.int8).astype(np.float32), lab[..., 2].view(np.int8).astype(np.float32)
    ma, mb = float(a.mean()), float(b.mean())
    da = max(0.0, ma - TARGET_A) * STRENGTH
    db = max(0.0, mb - TARGET_B) * STRENGTH
    info = dict(a_avant=round(ma, 1), b_avant=round(mb, 1), chaud_avant=round(warm_share(im), 2))
    if mb < TRIGGER_B and ma < TARGET_A + 6:
        return im, dict(info, corrige=False)
    chroma = np.hypot(a, b)
    # épargne : lumières chaudes très saturées et hautes lumières (sources), ombres profondes moins corrigées
    w = 1.0 - 0.55 * np.clip((chroma - 45) / 35, 0, 1)
    w *= 1.0 - 0.35 * np.clip((L - 88) / 12, 0, 1)
    w *= 0.55 + 0.45 * np.clip(L / 35, 0, 1)
    a2 = a - da * w
    b2 = b - db * w
    # les ombres récupèrent une teinte froide légère (comme chez Léo) au lieu d'un brun uniforme
    shadow = np.clip((45 - L) / 45, 0, 1) * min(1.0, db / 12)
    b2 -= 2.0 * shadow
    enc = lambda x: np.clip(np.round(x), -127, 127).astype(np.int8).view(np.uint8)
    out = np.stack([lab[..., 0], enc(a2), enc(b2)], -1)
    res = ImageCms.applyTransform(Image.fromarray(out, "LAB"), _TO_RGB)
    na, nb = stats(res)
    return res, dict(info, corrige=True, a_apres=round(na, 1), b_apres=round(nb, 1), chaud_apres=round(warm_share(res), 2))


def fix_file(path):
    """Corrige l'image sur place ; garde l'original en *_brut.png. Renvoie les infos de correction."""
    path = Path(path)
    im = Image.open(path); im.load()
    res, info = neutralize(im)
    if info.get("corrige"):
        im.convert("RGB").save(path.with_name(path.stem + "_brut.png"))
        res.save(path)
    return info
