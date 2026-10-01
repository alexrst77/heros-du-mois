# -*- coding: utf-8 -*-
"""Direction artistique centralisée de « Mon Héros du Mois ».
Tout ce qui définit le rendu d'un livre (style des images, palettes, cadrages, zones de texte,
typographie, fondus) est ici, pour s'appliquer à tous les futurs livres."""
from pathlib import Path

ROOT = Path(__file__).parent
STYLE_BOARD = ROOT / "style" / "planche_style.png"
STYLE_VERSION = "2026-10-v4"   # à changer quand le style évolue : invalide tous les portraits en cache

# ---------------------------------------------------------------- style des illustrations
STYLE_BIBLE = (
    "ART STYLE (apply to every image): a premium hand-painted children's picture-book illustration. "
    "Painterly gouache mixed with soft coloured-pencil texture, visible delicate brush strokes and fine pencil hatching, "
    "subtle watercolour-paper grain across the whole image. "
    "Characters are expressive and appealing: detailed eyes with highlights and eyelids, readable emotions, soft rounded volumes, "
    "real shading and bounce light on skin, fabric folds and patterns on clothes, individual strands and locks in the hair, "
    "fur rendered with small strokes. "
    "Environments are rich and immersive, with at least three depth planes (foreground elements partly framing the scene, "
    "a midground where the action happens, a softer atmospheric background), atmospheric perspective and many small "
    "details to discover. Lighting is carefully designed: a key light suited to the scene (sun, moon, lanterns or magical lights) "
    "against cooler coloured shadows, reflections, rim light on the characters, glowing particles when appropriate. "
    "The mood is magical, gentle and reassuring. Harmonious palette, rich but soft, never garish."
)
COLOUR_RULE = (
    "Colour grading: natural white balance, varied colours inside the image (cool blue and green shadows, clean whites, "
    "accents of the scene's own colours). Warm golden light only as local light sources, NEVER as an overall yellow, orange or sepia filter."
)
AVOID = (
    "AVOID: flat vector or clip-art look, uniform flat colour areas, simple dot eyes or schematic faces, stiff poses, "
    "characters lined up facing the camera like a group photo, empty or plain backgrounds, photographic realism, 3D render look, "
    "any text, letters, numbers, signature or watermark, any existing cartoon character or brand."
)
REFS_SCENE = (
    "REFERENCE IMAGES: the FIRST image is the approved character reference sheet of this book: reproduce the characters "
    "exactly as they appear on it (same face shape, hairstyle, hair colour, skin tone, eye colour, glasses, outfit, colours, "
    "patterns and body proportions; same plush toy; same pets with the same fur markings). "
    "The SECOND image is a style swatch board: use it ONLY for the painting technique, textures and quality of light. "
    "Never copy its content, its setting, its trees or its composition. Draw a completely NEW scene."
)

# palettes et lumières par univers (l'histoire garde sa propre palette, avec la richesse de Léo)
UNIVERS = {
    "forêt":     "an enchanted forest: mossy roots, ferns, flowers, mushrooms, streams; palette of deep greens, teal and warm amber light",
    "espace":    "space and stars: planets, nebulae, a small rocket, moon craters; palette of indigo, violet and soft gold starlight",
    "mer":       "under the sea: coral, kelp forests, shells, light rays through the water, bubbles; palette of turquoise, coral pink and pearly gold",
    "dinosaure": "a prehistoric valley: giant ferns, friendly dinosaurs, volcanoes far away, warm mist; palette of sage green, terracotta and apricot light",
    "château":   "a fairy-tale castle: towers, banners, gardens, torches, a drawbridge; palette of warm stone, royal blue and candle-light gold",
    "jungle":    "a lush jungle: giant leaves, lianas, exotic flowers, waterfalls, glowing insects; palette of emerald, jade, turquoise water, coral and magenta flowers, cool blue shade",
    "pôle":      "the North Pole: snow fields, ice caves, northern lights, cosy igloo; palette of icy blue, lilac, white and warm lantern orange",
}
DEFAULT_UNIVERS = "the world chosen for the story, rich and immersive, with a harmonious palette and warm magical light"

MOMENTS = {
    "matin": "soft early-morning light, pale gold and mint tones",
    "jour": "bright but soft daylight, dappled sunlight through the scenery",
    "crépuscule": "sunset / golden-hour light with long warm glows and violet shadows",
    "nuit": "night scene lit by warm magical lights, moonlight and glowing particles, deep blue-green shadows",
    "intérieur": "cosy interior light: lamps, warm pools of light and soft shadows",
}

# types de plans : chaque livre doit en varier
CADRAGES = {
    "plan_large": "WIDE ESTABLISHING SHOT: the environment dominates, characters are small to medium (about a quarter of the height), deep perspective, a path or a river leading the eye.",
    "action": "DYNAMIC ACTION SHOT: characters caught mid-movement (running, jumping, climbing, reaching), diagonal composition, three-quarter or side view, motion in hair and clothes.",
    "intime": "INTIMATE MOMENT: close to the characters (waist-up), a tender or emotional exchange between them, they look at each other or at something, not at the viewer.",
    "detail": "CLOSE-UP ON A DETAIL: a hand, a paw, a small magical object or a discovery fills much of the frame; faces partly visible at the side or only one character.",
    "decouverte": "DISCOVERY SHOT: seen from slightly behind or beside the characters (over-the-shoulder, three-quarter back view), they face something wondrous that occupies the scene.",
    "plongee": "HIGH-ANGLE or LOW-ANGLE VIEW: an unusual camera height (from above among the leaves, or from the ground up) that makes the scene feel big and adventurous.",
}
CADRAGE_FR = {"plan_large": "plan large", "action": "action", "intime": "moment intime", "detail": "détail",
              "decouverte": "découverte", "plongee": "plongée / contre-plongée"}

# zone réservée au texte : calme mais peinte (jamais un aplat)
ZONES = {
    "bas": "the lower 35% of the image",
    "haut": "the upper 32% of the image",
    "gauche": "the left 42% of the image",
    "droite": "the right 42% of the image",
}
ZONE_RULE = (
    "TEXT SPACE: compose the picture so that {zone} is a naturally calm area with low detail and gentle contrast "
    "({calm}), still painted with texture and colour, continuing the scene (NOT an empty band, NOT a frame). "
    "No face, no hand, no animal and no important action in that area; keep all characters and the key action in the rest of the image."
)
CALM = {"bas": "still water, soft grass, a shadowed path, moss or mist on the ground",
        "haut": "sky, soft mist, foliage in shadow, a ceiling of leaves or a starry sky",
        "gauche": "a misty background, shadowed foliage, water or sky on that side",
        "droite": "a misty background, shadowed foliage, water or sky on that side"}

# ---------------------------------------------------------------- règles de mise en page
PAGE = 612.0           # 8,5 x 8,5 pouces (21,6 cm) : format carré standard de Lulu
PX = 2048              # résolution des pages pour l'écran (≈ 240 dpi)
PX_PRINT = 2656        # résolution pour l'impression : 300 dpi sur 8,75 pouces (fond perdu compris)
BLEED = 9.0            # fond perdu Lulu : 0,125 pouce
SAFE = 36.0            # marge de sécurité Lulu : 0,5 pouce (aucun texte au-delà)
MARGIN = 44            # marges extérieures (pt)
BODY = dict(font="Serif", size=16.0, min=14.0, max=18.0, leading=1.42)
CHAP_BODY = dict(font="Serif", size=15.5, min=13.0, max=17.0, leading=1.45)
TITLE = dict(font="Serif-Bold", size=26, min=20)
INK_LIGHT = (1.0, 0.957, 0.878)      # ivoire
INK_DARK = (0.17, 0.13, 0.11)        # encre brune (fonds clairs)
TITLE_WARM = (0.96, 0.85, 0.58)      # or chaud sur fond sombre
TITLE_DARK = (0.50, 0.26, 0.10)      # terre de sienne sur fond clair
FADE = dict(
    target_lum=0.26,        # luminance visée sous un texte ivoire
    min_alpha=0.22, max_alpha=0.86,
    feather_pt=110,         # longueur minimale du dégradé
    halo_alpha=0.62,        # halo doux derrière les lettres
)
MIN_CONTRAST = 4.5          # contraste minimum texte / fond (norme WCAG AA)
