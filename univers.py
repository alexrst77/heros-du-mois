# -*- coding: utf-8 -*-
"""Univers des livres et calendrier des fêtes.
Une seule liste pour l'éditeur (/api/univers), la génération (décor des images, consignes d'histoire)
et l'abonnement (le livre du mois suit les fêtes que la famille a cochées)."""
from datetime import date, timedelta

# cle : identifiant stable ; image : décor pour les illustrations (anglais) ; histoire : consigne pour l'auteur
UNIVERS = [
    dict(cle="foret", nom="Une forêt enchantée",
         image="an enchanted forest: mossy roots, ferns, flowers, mushrooms, streams; palette of deep greens, teal and warm amber light"),
    dict(cle="espace", nom="L'espace et les étoiles",
         image="space and stars: planets, nebulae, a small rocket, moon craters; palette of indigo, violet and soft gold starlight"),
    dict(cle="mer", nom="Le fond de la mer",
         image="under the sea: coral, kelp forests, shells, light rays through the water, bubbles; palette of turquoise, coral pink and pearly gold"),
    dict(cle="dinosaure", nom="Le temps des dinosaures",
         image="a prehistoric valley: giant ferns, friendly dinosaurs, volcanoes far away, warm mist; palette of sage green, terracotta and apricot light"),
    dict(cle="chateau", nom="Un château de chevaliers",
         image="a fairy-tale castle: towers, banners, gardens, torches, a drawbridge; palette of warm stone, royal blue and candle-light gold"),
    dict(cle="jungle", nom="La jungle",
         image="a lush jungle: giant leaves, lianas, exotic flowers, waterfalls, glowing insects; palette of emerald, jade, turquoise water, coral and magenta flowers, cool blue shade"),
    dict(cle="pole", nom="Le pôle Nord",
         image="the North Pole: snow fields, ice caves, northern lights, cosy igloo; palette of icy blue, lilac, white and warm lantern orange"),
    dict(cle="pirates", nom="L'île aux pirates",
         image="a sunny pirate island: a friendly wooden ship with patched sails, palm trees, a treasure map, turquoise lagoon, sandy coves; palette of turquoise, sand, warm red and gold",
         histoire="Pirates gentils : chasse au trésor, cartes, devinettes ; jamais d'armes ni de combat."),
    dict(cle="fees", nom="Le royaume des fées et des licornes",
         image="a fairy kingdom: giant flowers, mushroom houses, a rainbow waterfall, gentle unicorns, sparkling dew; palette of lilac, rose, mint and pearly light"),
    dict(cle="cirque", nom="Le cirque des étoiles",
         image="a magical travelling circus: a striped big top, garlands of bulbs, acrobats, a friendly seal and elephant, confetti; palette of crimson, cream, navy and gold lights",
         histoire="Cirque joyeux et bienveillant : les animaux sont des amis, jamais maltraités ni enfermés."),
    dict(cle="ferme", nom="La ferme des petits matins",
         image="a cosy family farm: red barn, orchard, vegetable garden, hay bales, ducks pond, gentle farm animals; palette of meadow green, barn red, butter yellow and sky blue"),
    dict(cle="savane", nom="La grande savane",
         image="the African savanna: acacia trees, golden grass, a watering hole, giraffes, elephants, zebras, a huge sunset sun; palette of ochre, saffron, olive green and rosy sky"),
    dict(cle="superheros", nom="La ville des super-héros",
         image="a bright toy-like city of little super-heroes: rooftops, capes in the wind, friendly robots, hot-air balloons; palette of primary red, sky blue, sunshine yellow and white",
         histoire="Super-pouvoirs doux (gentillesse, courage, entraide) ; aucun combat, aucun méchant effrayant."),
    dict(cle="desert", nom="Le désert et l'oasis",
         image="a golden desert with soft dunes, a palm oasis, a caravan of friendly camels, a starry desert night with lanterns; palette of sand gold, terracotta, deep teal water and indigo night"),
    dict(cle="montagne", nom="La montagne et les marmottes",
         image="alpine mountains: flower meadows, a wooden chalet, marmots, a clear lake, snowy peaks; palette of pine green, glacier blue, wildflower pink and warm wood"),

    # ---------------- fêtes : proposées au bon moment de l'année
    dict(cle="anniversaire", nom="Mon anniversaire", fete="son anniversaire",
         image="a joyful birthday party: balloons, bunting, a big cake with candles, wrapped presents, confetti, friends and family around; palette of sunny yellow, coral, sky blue, mint and warm light",
         histoire="Livre d'anniversaire : l'enfant fête ses {age} ans (le dire dans l'histoire). Préparatifs, gâteau, bougies à souffler, un vœu, les amis et la famille ; l'aventure du jour lui fait découvrir qu'il a grandi."),
    dict(cle="noel", nom="La magie de Noël", fete="Noël",
         image="a magical Christmas: snowy village, a decorated fir tree, garlands, wrapped presents, cosy fireplace, Santa's workshop with friendly elves, reindeer; palette of deep red, fir green, snow white and warm gold candle light",
         histoire="Noël chaleureux : préparatifs en famille, décorations, lutins, le traîneau du Père Noël, le plaisir d'offrir. Ne jamais dire ni laisser entendre que le Père Noël n'existe pas."),
    dict(cle="halloween", nom="La nuit d'Halloween", fete="Halloween",
         image="a friendly Halloween night: glowing carved pumpkins, children in cute costumes, a smiling ghost, autumn leaves, a not-scary old house with warm windows; palette of pumpkin orange, plum purple, moss green and warm candle light",
         histoire="Halloween drôle et jamais effrayant : déguisements, bonbons partagés, petits fantômes gentils. Pas de sang, pas de monstres menaçants."),
    dict(cle="paques", nom="La chasse aux œufs de Pâques", fete="Pâques",
         image="a spring Easter garden: blossoming trees, tulips, colourful painted eggs hidden in the grass, baskets, rabbits and chicks, chocolate; palette of pastel yellow, mint, lilac, pink and fresh green",
         histoire="Pâques : chasse aux œufs dans le jardin, printemps, cloches et lapins, chocolat partagé."),
    dict(cle="galette", nom="La galette des rois", fete="l'Épiphanie",
         image="a cosy winter kitchen and a little kingdom of paper crowns: a golden galette, the fève, paper crowns, winter light through frosty windows; palette of buttery gold, royal blue, cream and warm brown",
         histoire="La galette des rois : la fève, la couronne, le plus jeune sous la table qui désigne les parts, partager la galette."),
    dict(cle="carnaval", nom="Le carnaval", fete="Mardi gras",
         image="a joyful carnival parade: colourful costumes and masks, confetti, streamers, floats, crêpes and beignets, music; palette of every bright colour on a sunny blue sky",
         histoire="Carnaval / Mardi gras : se déguiser, défiler, confettis, crêpes et beignets."),
    dict(cle="ramadan", nom="Les lanternes du Ramadan", fete="le Ramadan",
         image="a warm Ramadan evening: glowing fanous lanterns, crescent moon, a family table at sunset with dates, milk, soup and pastries, decorated balcony with string lights; palette of deep indigo night, warm amber, emerald and gold",
         histoire="Le Ramadan vu par un enfant : les lanternes, le coucher du soleil, le repas partagé en famille, les dattes et le lait, la patience, la générosité. Ton familial et respectueux, aucun discours religieux ni jugement ; l'enfant n'est pas obligé de jeûner."),
    dict(cle="aid", nom="La fête de l'Aïd", fete="l'Aïd el-Fitr",
         image="a festive Eid morning: a family in new festive clothes, a table with pastries (cornes de gazelle, makrout, baklava), mint tea, lanterns, garlands, visiting relatives and neighbours, gifts for children; palette of turquoise, rose, gold and soft morning light",
         histoire="L'Aïd el-Fitr : matin de fête, nouveaux habits, gâteaux préparés ensemble, visites à la famille, partage avec les voisins, petits cadeaux pour les enfants. Ton familial et respectueux, aucun discours religieux, aucune représentation de figure religieuse."),
    dict(cle="nouvelan_chinois", nom="Le Nouvel An chinois", fete="le Nouvel An chinois",
         image="a Lunar New Year celebration: red lanterns, a friendly dancing dragon in the street, paper cut decorations, dumplings, red envelopes, plum blossoms; palette of vermilion red, gold, jade green and night blue",
         histoire="Nouvel An chinois : la danse du dragon, les lanternes rouges, les raviolis faits en famille, les enveloppes rouges, l'animal de l'année."),
    dict(cle="hanoukka", nom="Les lumières de Hanoukka", fete="Hanoukka",
         image="a cosy Hanukkah evening: a menorah with glowing candles in the window, a family table with latkes and sufganiyot, a dreidel spinning, blue and silver decorations, snowy night outside; palette of royal blue, silver, warm candle gold and cream",
         histoire="Hanoukka : allumer une bougie de plus chaque soir, la toupie (dreidel), les beignets et latkes, la famille réunie. Ton familial et respectueux, sans discours religieux."),
    dict(cle="diwali", nom="Les lumières de Diwali", fete="Diwali",
         image="a Diwali night: rows of glowing diyas (oil lamps), colourful rangoli patterns, marigold garlands, sweets, a family on a terrace with sparklers far from faces; palette of saffron, magenta, marigold gold and deep night purple",
         histoire="Diwali : allumer les petites lampes, dessiner un rangoli, les douceurs partagées, la lumière qui chasse l'obscurité. Ton familial et respectueux, sans discours religieux."),
]
PUCES = {'anniversaire': 'Anniversaire', 'noel': 'Noël', 'halloween': 'Halloween', 'paques': 'Pâques', 'galette': 'Galette des rois', 'carnaval': 'Mardi gras', 'ramadan': 'Ramadan', 'aid': 'Aïd', 'nouvelan_chinois': 'Nouvel An chinois', 'hanoukka': 'Hanoukka', 'diwali': 'Diwali'}
PAR_CLE = {u["cle"]: u for u in UNIVERS}
PAR_NOM = {u["nom"]: u for u in UNIVERS}
NOMS = [u["nom"] for u in UNIVERS if not u.get("fete")]          # rotation des univers « hors fêtes » de l'abonnement

# dates des fêtes (les fêtes lunaires sont approximatives à un ou deux jours près ; seule la période compte ici)
_FIXES = {"noel": (12, 25), "halloween": (10, 31), "galette": (1, 6)}
_DATES = {
    "paques": ["2027-03-28", "2028-04-16", "2029-04-01", "2030-04-21"],
    "carnaval": ["2027-02-09", "2028-02-29", "2029-02-13", "2030-03-05"],
    "ramadan": ["2027-02-08", "2028-01-28", "2029-01-16", "2030-01-05"],
    "aid": ["2027-03-10", "2028-02-27", "2029-02-15", "2030-02-04"],
    "nouvelan_chinois": ["2027-02-06", "2028-01-26", "2029-02-13", "2030-02-03"],
    "hanoukka": ["2026-12-04", "2027-12-24", "2028-12-12", "2029-12-01"],
    "diwali": ["2026-11-08", "2027-10-29", "2028-10-17", "2029-11-05"],
}


def dates_fete(cle, annees=range(2026, 2031), anniv=None):
    if cle == "anniversaire":
        try:
            m, j = (int(x) for x in (anniv or "").split("-"))
            return [date(a, m, min(j, 28) if m == 2 and j == 29 else j) for a in annees]
        except ValueError:
            return []
    if cle in _FIXES:
        m, j = _FIXES[cle]
        return [date(a, m, j) for a in annees]
    return [date.fromisoformat(d) for d in _DATES.get(cle, [])]


def fete_a_venir(cles, jour=None, avant=12, apres=45, anniv=None):
    """Fête cochée par la famille qui tombe dans la fenêtre où le livre arrivera à temps
    (livre fabriqué maintenant, reçu ~2 semaines plus tard). Renvoie le nom d'univers ou None."""
    jour = jour or date.today()
    meilleur = None
    for c in cles or []:
        for d in dates_fete(c, anniv=anniv):
            if jour + timedelta(days=avant) <= d <= jour + timedelta(days=apres):
                if not meilleur or d < meilleur[0]:
                    meilleur = (d, PAR_CLE[c]["nom"])
    return meilleur and meilleur[1]


def cle_de(nom):
    """Nom d'univers (choisi dans l'éditeur ou ancien libellé) -> clé, ou None."""
    if nom in PAR_NOM:
        return PAR_NOM[nom]["cle"]
    n = (nom or "").lower()
    for mot, c in (("forêt", "foret"), ("espace", "espace"), ("étoile", "espace"), ("mer", "mer"), ("dino", "dinosaure"),
                   ("château", "chateau"), ("jungle", "jungle"), ("pôle", "pole"), ("noël", "noel"), ("aïd", "aid"),
                   ("ramadan", "ramadan"), ("halloween", "halloween"), ("pâques", "paques")):
        if mot in n:
            return c
    return None


def public():
    """Liste pour l'éditeur et la vitrine."""
    import vignettes
    return [{"nom": u["nom"], "cle": u["cle"], "fete": u.get("fete"), "puce": PUCES.get(u["cle"]), "court": COURTS.get(u["cle"], u["nom"]),
             "img": f"/vignette/{u['cle']}.webp" if vignettes.chemin(u["cle"]) else None} for u in UNIVERS]


COURTS = {"foret": "Forêt enchantée", "espace": "Parmi les étoiles", "mer": "Sous l’océan", "dinosaure": "Terre des dinosaures",
          "chateau": "Château des chevaliers", "pirates": "Île aux pirates", "jungle": "Cœur de la jungle", "pole": "Pôle Nord",
          "fees": "Royaume des fées", "cirque": "Cirque des étoiles", "ferme": "Ferme des petits matins", "savane": "Grande savane",
          "superheros": "Ville des super-héros", "desert": "Désert et oasis", "montagne": "Montagne des marmottes",
          "anniversaire": "Son anniversaire", "noel": "Noël", "halloween": "Halloween", "paques": "Pâques", "galette": "Galette des rois",
          "carnaval": "Mardi gras", "ramadan": "Ramadan", "aid": "Aïd", "nouvelan_chinois": "Nouvel An chinois", "hanoukka": "Hanoukka",
          "diwali": "Diwali"}


DELAI = 35          # pack fêtes : le livre est lancé 35 jours avant la fête (fabrication + impression + livraison)


def fetes_dues(cles, faites, jour=None, anniv=None, delai=DELAI):
    """Pack fêtes : fêtes cochées qui arrivent dans moins de `delai` jours et dont le livre n'est pas encore fait.
    Renvoie [(clé de suivi 'noel-2026', nom d'univers, date)] triées par date."""
    jour = jour or date.today()
    out = []
    for c in cles or []:
        for d in dates_fete(c, anniv=anniv):
            k = f"{c}-{d.year}"
            if jour < d <= jour + timedelta(days=delai) and k not in (faites or []):
                out.append((k, PAR_CLE[c]["nom"], d))
    return sorted(out, key=lambda x: x[2])
