# -*- coding: utf-8 -*-
"""Pages d'atterrissage pour Google : une page par recherche (livre personnalisé, Noël, anniversaire, doudou, calendrier…).

Chaque page a son titre, sa description, son H1, un vrai contenu (ce qu'on reçoit, comment ça marche, questions) et des liens vers
la création et vers les autres pages. Aucun avis, aucun chiffre inventé ; aucun prix affiché (comme l'accueil)."""
import os, json, time
from html import escape
from flask import Blueprint, Response, request

bp = Blueprint("seo", __name__)
MAJ = "2026-10-18"        # date de dernière modification du contenu (sitemap)


def base():
    return (os.getenv("PUBLIC_URL") or request.host_url).rstrip("/")


IA = ("Les illustrations sont créées avec l'intelligence artificielle à partir de l'avatar que vous composez, puis vérifiées et "
      "retravaillées par notre équipe page par page avant l'impression : ce qui ne va pas est refait.")

PAGES = {
    "livre-personnalise-enfant": dict(
        titre="Livre personnalisé enfant : il devient le héros de l'histoire",
        desc="Un vrai livre illustré dont votre enfant est le héros, avec son prénom, son doudou et ses animaux. Avatar sans photo, couverture rigide, livré chez vous.",
        h1="Le livre personnalisé où votre enfant est le héros",
        kicker="Livre personnalisé enfant",
        intro="Son prénom, son visage dessiné d'après l'avatar que vous composez, son doudou, son chat ou son chien : tout le monde a sa place dans une vraie histoire illustrée, imprimée et reliée, que vous lisez ensemble le soir.",
        image=("/static/vitrine/photo_04.webp", "Un livre personnalisé Mon Héros du Mois tenu à deux mains"),
        cta=("Créer son avatar gratuitement", "/creer?formule=livre"),
        sections=[
            ("Un vrai livre, pas un simple prénom collé", [
                "Dans beaucoup de livres « personnalisés », seul le prénom change. Ici, l'histoire est écrite pour votre enfant : son âge, ses compagnons, le thème que vous choisissez et l'univers de l'aventure.",
                "<ul><li>20 pages, dont 18 pages d'histoire illustrées</li><li>Couverture rigide, format carré de 21,6 cm</li><li>Des phrases courtes, écrites pour être lues à voix haute aux 3 à 8 ans</li><li>Son doudou et jusqu'à trois animaux, ses frères et sœurs s'il le souhaite</li></ul>"]),
            ("Aucune photo de votre enfant", [
                "Vous composez son avatar en quelques minutes : coiffure, couleur des cheveux et des yeux, teint, lunettes, tenue. Vous voyez le résultat en direct. C'est cet avatar qui sert de modèle aux illustrations : aucune photo n'est demandée ni envoyée."]),
            ("Un thème qui lui parle", [
                "La peur du noir, l'arrivée d'un petit frère, la rentrée, les émotions, le partage, ou simplement une aventure pour rire : vous choisissez le thème, et l'univers où il part (la forêt enchantée, l'espace, le fond de la mer, les dinosaures, les pirates…)."]),
            ("Comment c'est fait", [IA, "Vous voyez gratuitement l'aperçu de sa couverture avant de payer. Le livre est ensuite imprimé par Lulu, imprimeur professionnel, et livré chez vous en 7 à 15 jours ouvrés."]),
        ],
        faq=[("Pour quel âge ?", "Les histoires sont écrites pour les enfants de 3 à 8 ans, à lire à voix haute. L'âge de votre enfant guide la longueur des phrases."),
             ("Faut-il envoyer une photo ?", "Non. Vous composez son avatar sur le site, sans aucune photo."),
             ("Peut-on commander plusieurs livres ?", "Oui : chaque livre a son propre thème et son propre univers, avec le même héros. Ils sont imprimés et expédiés ensemble, dans un seul colis."),
             ("Existe-t-il une version à lire sur tablette ?", "Oui, le livre existe aussi en e-book (PDF), seul ou en plus du livre imprimé.")],
        liens=["livre-doudou-personnalise", "livre-personnalise-noel", "livre-anniversaire-personnalise", "livre-emotions-enfant"]),

    "livre-personnalise-noel": dict(
        titre="Livre personnalisé de Noël pour enfant, à son prénom",
        desc="Un livre de Noël où votre enfant vit la magie de Noël avec son doudou et ses animaux. Illustré, relié, livré chez vous. Commandez avant le 1er décembre.",
        h1="Un livre de Noël dont votre enfant est le héros",
        kicker="Cadeau de Noël personnalisé",
        intro="Sous le sapin, un livre qui parle de lui : votre enfant, son doudou et ses animaux vivent la magie de Noël dans une histoire illustrée, imprimée et reliée à son prénom.",
        image=("/static/vitrine/univ/noel.webp", "Illustration de l'univers « La magie de Noël » d'un livre personnalisé"),
        cta=("Créer son livre de Noël", "/creer?fete=noel"),
        sections=[
            ("Pour Noël, commandez avant le 1er décembre", [
                "Chaque livre est créé après votre commande, vérifié et retravaillé, puis imprimé et expédié. Comptez 7 à 15 jours ouvrés : commandé avant le 1er décembre, il arrive pour Noël."]),
            ("Ce que contient le livre", [
                "<ul><li>Une histoire de Noël écrite pour son âge, avec son prénom</li><li>Ses compagnons : son doudou, ses animaux, ses frères et sœurs</li><li>18 pages illustrées, couverture rigide</li><li>Votre petit mot imprimé au dos si c'est un cadeau</li></ul>"]),
            ("À offrir avec le reste de son univers", [
                "Avec le même avatar, vous pouvez ajouter son <a href=\"/calendrier-personnalise-enfant\">calendrier de l'année</a> et son <a href=\"/cahier-coloriage-personnalise\">cahier de coloriage</a> : tout part dans le même colis."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Peut-on l'offrir de la part des grands-parents ?", "Oui : cochez « C'est pour offrir », indiquez de la part de qui et un petit mot, imprimé au dos du livre."),
             ("Jusqu'à quand commander pour Noël ?", "Jusqu'au 1er décembre pour une livraison en France avant Noël."),
             ("Le livre parle-t-il seulement de Noël ?", "Oui, l'histoire se passe pendant les fêtes. Vous pouvez aussi commander d'autres aventures dans d'autres univers, avec le même héros.")],
        liens=["cadeau-personnalise-enfant", "livre-personnalise-enfant", "calendrier-personnalise-enfant"]),

    "livre-anniversaire-personnalise": dict(
        titre="Livre d'anniversaire personnalisé pour enfant",
        desc="Pour son anniversaire, un livre illustré dont il est le héros : son prénom, son âge, son doudou et ses animaux. Couverture rigide, livré chez vous.",
        h1="Un livre d'anniversaire où il est le héros de sa fête",
        kicker="Cadeau d'anniversaire",
        intro="Pour ses 3, 5 ou 7 ans, une histoire où c'est lui qu'on fête : son prénom, son âge, son doudou et ses animaux, dans un vrai livre illustré à garder.",
        image=("/static/vitrine/univ/anniversaire.webp", "Illustration de l'univers « Mon anniversaire » d'un livre personnalisé"),
        cta=("Créer son livre d'anniversaire", "/creer?fete=anniversaire"),
        sections=[
            ("Une histoire pour son âge", [
                "Indiquez sa date d'anniversaire : l'histoire est écrite pour l'âge qu'il aura, avec des phrases à sa mesure, à lire à voix haute."]),
            ("Un cadeau qu'on garde", [
                "Couverture rigide, 18 pages illustrées, son prénom sur la couverture. Si c'est un cadeau, votre petit mot est imprimé au dos du livre."]),
            ("Les fêtes de toute l'année", [
                "Il existe aussi une formule de six livres de fête : son anniversaire et cinq fêtes que vous choisissez (Noël, Pâques, Halloween, la galette des rois, le Nouvel An chinois, Hanoukka, Diwali, l'Aïd…)."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Combien de temps pour le recevoir ?", "7 à 15 jours ouvrés après la commande : pensez-y au moins trois semaines avant la fête."),
             ("Peut-on y mettre son doudou ?", "Oui : son doudou a un nom et devient un vrai personnage de l'histoire, comme ses animaux.")],
        liens=["livre-personnalise-enfant", "cadeau-personnalise-enfant", "livre-doudou-personnalise"]),

    "livre-doudou-personnalise": dict(
        titre="Un livre personnalisé où son doudou devient un héros",
        desc="Son doudou, son chien ou son chat deviennent les compagnons de son aventure dans un livre illustré personnalisé. Sans photo, livré chez vous.",
        h1="Son doudou et ses animaux, héros de son histoire",
        kicker="Livre avec son doudou",
        intro="Le lapin tout râpé qu'il emmène partout, le chat de la maison, le chien du week-end : dans ses livres, ils ont un nom, une couleur, une place dans l'aventure. Et ils peuvent même être le héros du livre.",
        image=("/static/vitrine/photo_08.webp", "Un livre ouvert illustré, l'enfant et son ours en peluche dans l'espace"),
        cta=("Composer son équipe", "/creer"),
        sections=[
            ("Son doudou, tel qu'il est", [
                "Lapin, ours, chat, chien ou éléphant : vous choisissez le type, la couleur et l'accessoire (nœud, écharpe), et vous lui donnez son vrai nom. Dans l'histoire, il reste une peluche : il accompagne l'enfant, il ne devient pas un animal vivant."]),
            ("Jusqu'à trois animaux", [
                "Chat, chien (labrador, berger australien, bouledogue français, jack russell…), lapin, hamster, oiseau, tortue ou poisson, avec sa couleur, son pelage et son collier. Vous pouvez aussi ajouter un frère ou une sœur."]),
            ("Le héros du livre, c'est vous qui choisissez", [
                "Par défaut, l'enfant est le héros et ses compagnons l'accompagnent. Mais vous pouvez faire de son doudou ou de son chien le héros de l'aventure."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Faut-il une photo du doudou ?", "Non, vous le composez sur le site en choisissant son type, sa couleur et son accessoire."),
             ("Combien de compagnons au maximum ?", "Son doudou, plus quatre compagnons au total entre les animaux (trois au plus) et les frères et sœurs (deux au plus).")],
        liens=["livre-personnalise-enfant", "livre-emotions-enfant", "cadeau-personnalise-enfant"]),

    "livre-emotions-enfant": dict(
        titre="Livre personnalisé : peur du noir, émotions, nouveau bébé",
        desc="Un livre personnalisé pour accompagner votre enfant : peur du noir, colère, arrivée d'un petit frère, rentrée, propreté. Il est le héros de l'histoire.",
        h1="Un livre pour l'aider à grandir, dont il est le héros",
        kicker="Livres pour accompagner",
        intro="Quand l'enfant se reconnaît dans le héros, il entre plus facilement dans l'histoire. Choisissez le sujet qu'il vit en ce moment : l'histoire l'aborde avec douceur, à sa hauteur.",
        image=("/static/vitrine/photo_03.webp", "Un parent et son enfant lisent ensemble un livre illustré"),
        cta=("Choisir le thème de son livre", "/creer"),
        sections=[
            ("Les thèmes proposés", [
                "<ul><li>La peur du noir, les cauchemars, dormir dans son grand lit</li><li>Les émotions, gérer la colère, la confiance en soi</li><li>L'arrivée d'un petit frère ou d'une petite sœur</li><li>La rentrée à l'école, le premier jour à la crèche, oser se faire des amis</li><li>Devenir propre, dire au revoir à la tétine, se brosser les dents</li><li>Aller chez le médecin ou le dentiste, un déménagement, quand papa et maman se séparent</li><li>Ou simplement une aventure pour rire</li></ul>"]),
            ("Un mot pour nous", [
                "À la commande, vous pouvez nous dire ce qu'il vit en ce moment (« il a peur des bruits de la nuit, mais adore chanter ») : l'histoire en tient compte."]),
            ("Comment c'est fait", [IA, "Ces livres ne remplacent pas l'avis d'un professionnel : ce sont des histoires pour en parler ensemble, le soir."]),
        ],
        faq=[("Peut-on combiner un thème et un univers ?", "Oui : par exemple la peur du noir dans une forêt enchantée, ou la rentrée chez les dinosaures."),
             ("Peut-on commander plusieurs thèmes ?", "Oui, un livre par thème, avec le même héros. Les livres d'une commande partent dans le même colis.")],
        liens=["livre-personnalise-enfant", "livre-doudou-personnalise"]),

    "calendrier-personnalise-enfant": dict(
        titre="Calendrier personnalisé enfant : 12 mois illustrés avec lui",
        desc="Un calendrier mural où votre enfant, son doudou et ses animaux illustrent chaque mois. Son anniversaire et vos dates de famille imprimés. Spirale, 28 × 22 cm.",
        h1="Le calendrier de son année, illustré avec lui",
        kicker="Calendrier personnalisé",
        intro="La neige en janvier, les flaques d'avril, la plage en juillet, les feuilles d'automne : chaque mois, votre enfant et ses compagnons dans une illustration de saison, avec son anniversaire et vos dates de famille sur la grille.",
        image=("/static/vitrine/cal_photo_1.webp", "Un enfant tient son calendrier personnalisé à son prénom"),
        cta=("Créer son calendrier", "/creer?produit=calendrier"),
        sections=[
            ("Ce que contient le calendrier", [
                "<ul><li>12 mois illustrés avec votre enfant, son doudou et ses animaux</li><li>Format paysage 28 × 22 cm, reliure à spirale, à accrocher</li><li>Le premier mois de votre choix : janvier, ou n'importe quel mois à venir</li><li>Son mois d'anniversaire devient sa fête illustrée, et le jour J est marqué</li><li>Les jours fériés, les fêtes que vous cochez et vos dates de famille imprimés sur la grille</li></ul>"]),
            ("Seul ou avec ses livres", [
                "Le calendrier se commande seul, ou en plus de ses livres et de son <a href=\"/cahier-coloriage-personnalise\">cahier de coloriage</a> : même avatar, même colis."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Peut-on ajouter les anniversaires de la famille ?", "Oui, jusqu'à 15 dates de famille (anniversaire de Mamie, rentrée, vacances…), qui reviennent chaque année à la même date."),
             ("Pour quelle année ?", "Il couvre les 12 mois qui suivent le premier mois que vous choisissez.")],
        liens=["cahier-coloriage-personnalise", "cadeau-personnalise-enfant", "livre-personnalise-noel"]),

    "cahier-coloriage-personnalise": dict(
        titre="Cahier de coloriage personnalisé à son prénom",
        desc="30 pages de coloriages et de jeux où votre enfant est le héros : coloriages à son prénom, coloriages magiques, points à relier, labyrinthes.",
        h1="Le cahier de coloriage dont il est le héros",
        kicker="Coloriage personnalisé",
        intro="Astronaute, pompier, pirate, à la plage ou à Noël : votre enfant, son doudou et ses animaux dessinés au trait, prêts à colorier, avec un titre à son prénom sur chaque page.",
        image=("/static/vitrine/colo_photo_1.webp", "Un cahier de coloriage personnalisé ouvert, avec des crayons"),
        cta=("Créer son cahier", "/creer?produit=coloriage"),
        sections=[
            ("30 pages de coloriages et de jeux", [
                "<ul><li>18 coloriages que vous choisissez parmi près de 70 idées</li><li>5 coloriages magiques (une couleur par numéro)</li><li>3 points à relier, 2 labyrinthes, un dessin à terminer, une page « Dessine ton doudou »</li><li>Une page « Ce cahier appartient à » et une page de solutions</li></ul>"]),
            ("Fait pour les feutres", [
                "Grand format 21,6 × 27,9 cm à spirale, imprimé au recto seulement : les feutres ne traversent pas sur le dessin suivant."]),
            ("Comment c'est fait", [IA, "Les jeux (labyrinthes, points à relier, coloriages magiques) sont construits et vérifiés par programme : chaque labyrinthe a bien une solution."]),
        ],
        faq=[("À partir de quel âge ?", "Les dessins ont de grandes zones à colorier ; les labyrinthes et les points à relier s'adaptent à l'âge de l'enfant."),
             ("Peut-on choisir les pages ?", "Oui, ou garder notre sélection variée, ou compléter au hasard.")],
        liens=["calendrier-personnalise-enfant", "cadeau-personnalise-enfant", "livre-personnalise-enfant"]),


    "livre-grand-frere-grande-soeur": dict(
        titre="Livre personnalisé grand frère, grande sœur : un cadeau pour l'aîné",
        desc="Un bébé arrive ? Offrez à l'aîné un livre dont il est le héros, qui parle de son nouveau rôle de grand frère ou de grande sœur. Illustré, relié, sans photo.",
        h1="Un livre pour l'aîné qui devient grand frère ou grande sœur",
        kicker="Arrivée d'un bébé",
        intro="Quand un bébé arrive, tout le monde pense à lui. L'aîné, lui aussi, mérite d'être au centre de l'histoire : un livre où il est le héros, qui parle avec douceur de ce qui change et de la place qu'il garde.",
        image=("/static/vitrine/photo_05.webp", "Un livre personnalisé ouvert sur une double page illustrée"),
        cta=("Créer son livre de grand frère ou grande sœur", "/creer"),
        sections=[
            ("Une histoire pour ce qu'il vit", [
                "Choisissez le thème « L'arrivée d'un petit frère ou d'une petite sœur ». L'histoire parle des émotions de l'aîné, de la jalousie qui peut venir, de la fierté et de tout ce qu'il pourra montrer au bébé, sans jamais lui faire la leçon.",
                "À la commande, un petit mot nous aide à coller à votre situation : le prénom du bébé, la date prévue, ce que l'aîné attend avec impatience."]),
            ("Le bébé dans l'histoire ?", [
                "Vous pouvez ajouter le petit frère ou la petite sœur à son équipe : l'aîné reste le héros du livre."]),
            ("Un vrai livre à garder", [
                "<ul><li>18 pages illustrées, couverture rigide</li><li>Son doudou et ses animaux dans l'aventure</li><li>Votre petit mot imprimé au dos si c'est un cadeau</li></ul>"]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("À offrir avant ou après la naissance ?", "Les deux fonctionnent : avant, pour préparer l'aîné ; à la naissance, pour qu'il ait lui aussi son cadeau."),
             ("Faut-il une photo ?", "Non, vous composez son avatar sur le site, sans photo.")],
        liens=["livre-emotions-enfant", "livre-doudou-personnalise", "cadeau-personnalise-enfant"]),

    "livre-paques-personnalise": dict(
        titre="Livre personnalisé de Pâques pour enfant",
        desc="Une chasse aux œufs dont votre enfant est le héros, avec son doudou et ses animaux. Un livre illustré personnalisé pour Pâques, livré chez vous.",
        h1="Un livre de Pâques dont votre enfant est le héros",
        kicker="Cadeau de Pâques",
        intro="Une chasse aux œufs dans un jardin en fleurs, avec son doudou et ses animaux : à Pâques, offrez-lui une histoire qui parle de lui plutôt qu'un chocolat de plus.",
        image=("/static/vitrine/univ/paques.webp", "Illustration de l'univers « La chasse aux œufs de Pâques » d'un livre personnalisé"),
        cta=("Créer son livre de Pâques", "/creer?fete=paques"),
        sections=[
            ("Ce que contient le livre", [
                "<ul><li>Une histoire de Pâques écrite pour son âge, avec son prénom</li><li>Ses compagnons : son doudou, ses animaux, ses frères et sœurs</li><li>18 pages illustrées, couverture rigide</li></ul>"]),
            ("Pensez au délai", [
                "Chaque livre est créé après la commande, vérifié et retravaillé, puis imprimé : comptez 7 à 15 jours ouvrés. Commandez au moins trois semaines avant Pâques."]),
            ("Toutes les fêtes de l'année", [
                "La formule des six livres de fête réunit son anniversaire et cinq fêtes de votre choix : Pâques, Noël, Halloween, la galette des rois, le carnaval, le Nouvel An chinois, Hanoukka, Diwali, l'Aïd…"]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Peut-on commander pour plusieurs enfants ?", "Oui, un avatar et une commande par enfant."),
             ("Le livre parle-t-il de religion ?", "Non, l'histoire reste sur la fête de famille : la chasse aux œufs, le printemps, le partage.")],
        liens=["livre-personnalise-noel", "livre-anniversaire-personnalise", "cadeau-personnalise-enfant"]),

    "livre-personnalise-par-age": dict(
        titre="Livre personnalisé selon l'âge : 2-4 ans, 5-7 ans, 8-10 ans",
        desc="Un livre personnalisé écrit pour l'âge de votre enfant : phrases courtes pour les petits, plus d'histoire pour les grands. De 2 à 10 ans.",
        h1="Un livre personnalisé écrit pour son âge",
        kicker="Par âge",
        intro="Vous indiquez son année de naissance : la longueur des phrases et la quantité de texte s'adaptent. Les illustrations restent grandes et pleines de détails à chercher, à tout âge.",
        image=("/static/vitrine/photo_03.webp", "Un parent et son enfant lisent ensemble un livre illustré"),
        cta=("Créer son livre", "/creer"),
        sections=[
            ("2 à 4 ans : une phrase ou deux par page", [
                "Environ 20 à 32 mots par page : des phrases courtes, des sons à répéter, des situations du quotidien. Parfait pour un premier rituel du soir, avec son doudou dans chaque aventure."]),
            ("5 à 7 ans : une vraie aventure", [
                "Environ 26 à 38 mots par page : un problème à résoudre, des amis à aider, un peu de suspense. C'est aussi l'âge des thèmes qui accompagnent : la rentrée, la peur du noir, l'arrivée d'un bébé."]),
            ("8 à 10 ans : plus d'histoire", [
                "Environ 32 à 46 mots par page : plus de dialogues et d'aventure, à lire avec lui ou à lui laisser lire tout seul."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Et si son anniversaire arrive bientôt ?", "Indiquez sa date d'anniversaire : son âge est calculé au jour de la commande, et un livre d'anniversaire est écrit pour l'âge qu'il aura."),
             ("Mon enfant ne sait pas encore lire, est-ce adapté ?", "Oui, les histoires sont écrites pour être lues à voix haute par un adulte.")],
        liens=["livre-personnalise-enfant", "idees-histoires", "livre-emotions-enfant"]),
    "cadeau-personnalise-enfant": dict(
        titre="Cadeau personnalisé enfant : livres, calendrier, coloriage",
        desc="Un cadeau personnalisé où l'enfant est le héros : livre illustré, calendrier, cahier de coloriage, gourde, tasse, sac à dos. Un seul avatar, sans photo.",
        h1="Un cadeau personnalisé où l'enfant est le héros",
        kicker="Idées cadeaux",
        intro="Composez son avatar une fois, avec son doudou et ses animaux : il devient le héros de ses livres, de son calendrier, de son cahier de coloriage et de ses objets de tous les jours. Pour Noël, un anniversaire, ou sans occasion.",
        image=("/static/vitrine/photo_10.webp", "Plusieurs livres personnalisés Mon Héros du Mois"),
        cta=("Créer son avatar gratuitement", "/creer"),
        sections=[
            ("Toutes les idées, avec le même héros", [
                "<ul><li><a href=\"/livre-personnalise-enfant\">Ses livres d'aventures</a> : une vraie histoire illustrée, couverture rigide</li><li><a href=\"/calendrier-personnalise-enfant\">Son calendrier</a> : 12 mois illustrés avec lui</li><li><a href=\"/cahier-coloriage-personnalise\">Son cahier de coloriage</a> : 30 pages de coloriages et de jeux</li><li>Sa gourde, sa tasse émaillée, son sac à dos, illustrés à son prénom</li></ul>"]),
            ("Offert de votre part", [
                "Cochez « C'est pour offrir » : votre nom et votre petit mot sont imprimés au dos des créations. Les livres, le calendrier et le cahier partent ensemble dans un seul colis."]),
            ("Pour les occasions", [
                "Un <a href=\"/livre-personnalise-noel\">livre de Noël</a>, un <a href=\"/livre-anniversaire-personnalise\">livre d'anniversaire</a>, ou des histoires pour l'accompagner dans <a href=\"/livre-emotions-enfant\">ce qu'il vit en ce moment</a>."]),
            ("Comment c'est fait", [IA]),
        ],
        faq=[("Faut-il une photo de l'enfant ?", "Non, son avatar suffit : vous le composez sur le site en quelques minutes."),
             ("Peut-on tout recevoir en une fois ?", "Les livres, le calendrier et le cahier arrivent dans un même colis ; les objets arrivent dans un colis à part, dans les mêmes délais.")],
        liens=["livre-personnalise-noel", "livre-anniversaire-personnalise", "calendrier-personnalise-enfant", "cahier-coloriage-personnalise"]),
}

def _eur(c):
    return f"{c / 100:.2f}".replace(".", ",") + " €"


def _tarifs():
    import paiement as P
    g = P.grille(); F = g["formules"]
    lignes = lambda rows: "<table class='t'>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>"
    livres = [("1 livre", _eur(F["livre"]["prix"])), (f"3 livres ({_eur(F['pack3']['prix_livre'])} le livre)", _eur(F["pack3"]["prix"])),
              (f"6 livres ({_eur(F['pack6']['prix_livre'])} le livre)", _eur(F["pack6"]["prix"])), (f"12 livres ({_eur(F['pack12']['prix_livre'])} le livre)", _eur(F["pack12"]["prix"])),
              ("Les 6 livres de fête", _eur(F["fetes"]["prix"]))]
    livres += [(f"Grand livre A4, {v['livres']} histoires", _eur(v["prix"])) for k, v in sorted(F.items()) if v.get("grand")]
    ebook = [("E-book (PDF) seul", _eur(g["ebook"]["seul"])), ("E-book en plus d'un livre imprimé", _eur(g["ebook"]["ajout"]) + " par livre")]
    autres = [("Calendrier seul", _eur(g["calendrier"]["seul"])), ("Calendrier avec une autre création", _eur(g["calendrier"]["ajout"])),
              ("Cahier de coloriage seul", _eur(g["coloriage"]["seul"])), ("Cahier de coloriage avec une autre création", _eur(g["coloriage"]["ajout"]))]
    autres += [(v["nom"] + ", livraison comprise", _eur(v["prix"])) for v in g["objets"].values()]
    port = [("1 livre, un calendrier ou un cahier seul", _eur(g["port_fr"]["1"])), ("2 à 5 livres", _eur(g["port_fr"]["3"])),
            ("6 livres et plus", "offerte"), ("E-book seul", "par e-mail, sans frais"),
            ("La Réunion", "prix réel de l'envoi, sans marge, affiché avant le paiement"),
            ("Belgique, Luxembourg, Monaco", "+ " + _eur(g["supplement_pays"]["BE"])), ("Suisse", "+ " + _eur(g["supplement_pays"]["CH"]))]
    return [("Ses livres d'aventures", [lignes(livres), "Couverture rigide, 18 pages illustrées. Les livres d'une commande partent ensemble, dans un seul colis."]),
            ("E-book", [lignes(ebook), "Le PDF à lire sur tablette ou téléphone, envoyé par e-mail. Vous pourrez commander la version imprimée plus tard, sans recréer le livre."]),
            ("Calendrier, cahier de coloriage et objets", [lignes(autres)]),
            ("Livraison en France", [lignes(port), "Un seul colis pour les livres, le calendrier et le cahier ; les objets arrivent dans un colis à part, livraison comprise."]),
            ("Ce qui est compris", ["Création de l'avatar, aperçu de sa couverture avant de payer, création des illustrations, vérification et retouches par notre équipe, impression et reliure. Paiement sécurisé par Stripe, en une seule fois, sans abonnement."])]


def _avis():
    import avis
    l = sorted(avis.publies(), key=lambda a: a["date"], reverse=True)
    if not l:
        return [("Les premiers avis arrivent", ["Nous débutons : les avis publiés ici sont uniquement ceux de clients ayant reçu leur commande, avec leurs photos. Nous n'en inventons aucun. "
                                                 "En attendant, vous pouvez <a href=\"/#feuilleter\">feuilleter nos livres</a> et voir sa couverture gratuitement avant de commander."])]
    r = avis.resume()
    cartes = "".join(f"<figure class='av'><div class='et' aria-label='{a['note']} étoiles sur 5'>{'★' * a['note']}{'☆' * (5 - a['note'])}</div>"
                     + "".join(f"<img src='/avis-photo/{p}' alt='Photo du livre reçu' loading='lazy'>" for p in a.get("photos", [])[:2])
                     + f"<blockquote>{escape(a['texte'])}</blockquote><figcaption>{escape(a['nom'])} · {a['date'][8:10]}/{a['date'][5:7]}/{a['date'][:4]}</figcaption></figure>" for a in l)
    return [(f"{r['nombre']} avis vérifiés · {str(r['moyenne']).replace('.', ',')}/5", ["<div class='avs'>" + cartes + "</div>",
            "Avis vérifiés : seuls les clients ayant reçu leur commande peuvent laisser un avis, via un lien personnel. Tous les avis sont publiés, positifs comme négatifs, sauf s'ils sont hors sujet, injurieux ou contiennent des données personnelles."])]


def _idees():
    import univers as U
    mondes = [u["nom"] for u in U.public() if not u.get("fete")]
    fetes = [u["nom"] for u in U.public() if u.get("fete")]
    themes = ["La peur du noir", "Les cauchemars", "Dormir dans son grand lit", "Les émotions", "Gérer la colère", "La confiance en soi",
              "L'arrivée d'un petit frère ou d'une petite sœur", "La rentrée à l'école", "Le premier jour à la crèche", "Oser se faire des amis",
              "Apprendre à partager", "Apprendre à attendre", "Dire la vérité", "La politesse", "Accepter la différence", "Devenir propre",
              "Dire au revoir à la tétine", "Se brosser les dents", "S'habiller tout seul", "Ranger sa chambre", "Goûter de nouveaux aliments",
              "Aller chez le médecin", "Aller chez le dentiste", "Les écrans : savoir s'arrêter", "Un déménagement", "Quand papa et maman se séparent",
              "Partir en vacances", "Prendre soin de la nature", "Une aventure pour rire"]
    puces = lambda l: "<ul class='puces'>" + "".join(f"<li>{escape(x)}</li>" for x in l) + "</ul>"
    return [(f"{len(themes)} thèmes", [puces(themes), "Et ses passions en plus : les camions, la danse, le foot, les dinosaures… indiquez-les à la commande, l'histoire en tient compte."]),
            (f"{len(mondes)} mondes à explorer", [puces(mondes)]),
            ("Les fêtes de l'année", [puces(fetes)]),
            ("Exemples d'associations", ["<ul><li>La peur du noir dans une forêt enchantée</li><li>La rentrée chez les dinosaures</li><li>L'arrivée d'un bébé au fond de la mer</li><li>La confiance en soi dans la ville des super-héros</li></ul>"])]


CONSTRUIRE = {"tarifs": _tarifs, "avis-clients": _avis, "idees-histoires": _idees}

PAGES.update({
    "tarifs": dict(titre="Tarifs : livres personnalisés, e-book, calendrier, coloriage",
                   desc="Tous nos prix : livre personnalisé, packs de 3, 6 et 12 livres, e-book, calendrier, cahier de coloriage, objets et livraison. Paiement en une fois, sans abonnement.",
                   h1="Nos tarifs, sans surprise", kicker="Tarifs", intro="Vous composez son avatar gratuitement et voyez sa couverture avant de payer. Voici tous les prix, livraison comprise ou non.",
                   image=("/static/vitrine/photo_01.webp", "Quatre livres personnalisés Mon Héros du Mois"), cta=("Créer son avatar gratuitement", "/creer"), sections=[],
                   faq=[("Y a-t-il un abonnement ?", "Non. Tout se paie en une fois, à la commande."), ("Peut-on payer en plusieurs fois ?", "Pas pour l'instant : le paiement se fait en une fois, par carte, via Stripe.")],
                   liens=["livre-personnalise-enfant", "cadeau-personnalise-enfant", "avis-clients"]),
    "avis-clients": dict(titre="Avis clients vérifiés : leurs livres personnalisés en photos",
                         desc="Les avis et les photos des familles qui ont reçu leur livre personnalisé Mon Héros du Mois. Uniquement des avis vérifiés, positifs comme négatifs.",
                         h1="Ce qu'en disent les familles", kicker="Avis vérifiés", intro="Uniquement des clients qui ont reçu leur commande, avec leurs vraies photos.",
                         image=("/static/vitrine/photo_10.webp", "Plusieurs livres personnalisés Mon Héros du Mois"), cta=("Créer son avatar gratuitement", "/creer"), sections=[],
                         faq=[("Comment laisser un avis ?", "Quelques jours après la livraison, nous vous envoyons un lien personnel par e-mail. Le lien est aussi dans « Mon compte »."),
                              ("Les avis sont-ils vérifiés ?", "Oui : seuls les clients dont la commande a été expédiée peuvent en laisser un. Tous les avis conformes sont publiés, positifs comme négatifs.")],
                         liens=["tarifs", "livre-personnalise-enfant", "aide"]),
    "idees-histoires": dict(titre="Idées d'histoires pour un livre personnalisé enfant",
                            desc="Thèmes (peur du noir, rentrée, émotions, arrivée d'un bébé…), mondes (espace, dinosaures, pirates, fées…) et fêtes : toutes les idées pour son livre personnalisé.",
                            h1="Des idées d'histoires pour son livre", kicker="Inspiration",
                            intro="Un thème qui lui parle, un monde qui le fait rêver : vous choisissez les deux, et ses compagnons partent avec lui.",
                            image=("/static/vitrine/photo_02.webp", "Le livre « Jade et la vallée des dinosaures » posé sur une table"), cta=("Choisir son histoire", "/creer"), sections=[],
                            faq=[("Peut-on proposer sa propre idée ?", "Oui, en partie : indiquez ses passions et un mot pour nous à la commande, l'histoire en tient compte.")],
                            liens=["livre-emotions-enfant", "livre-personnalise-par-age", "livre-personnalise-enfant"]),
    "aide": dict(titre="Centre d'aide : commande, livraison, paiement, avatar",
                 desc="Toutes les réponses : comment créer l'avatar, délais de livraison, paiement, e-book, cadeau, défaut d'impression, données de l'enfant.",
                 h1="Centre d'aide", kicker="Questions fréquentes", intro="Les réponses aux questions les plus fréquentes. Une autre question ? Écrivez-nous, un humain vous répond.",
                 image=("/static/vitrine/photo_07.webp", "Un livre personnalisé dans sa boîte cadeau"), cta=("Nous écrire", "/#contact"), sections=[
                     ("Créer son livre", ["<ul><li>L'avatar se compose sur le site, sans photo, en quelques minutes.</li><li>Vous voyez gratuitement l'aperçu de sa couverture avant de payer.</li><li>Vous choisissez le thème et le monde de chaque livre, ou nous les proposons.</li></ul>"]),
                     ("Livraison", ["Comptez 7 à 15 jours ouvrés : création, vérification et retouches, impression, expédition avec suivi. Pour Noël, commandez avant le 1er décembre. Livraison en France, à La Réunion, en Belgique, au Luxembourg, à Monaco et en Suisse."]),
                     ("Paiement", ["Par carte, en une seule fois, via Stripe : nous ne voyons jamais votre carte. Aucun abonnement."]),
                     ("Un souci avec votre livre ?", ["Livre abîmé ou défaut d'impression : envoyez-nous une photo dans les 30 jours, nous le réimprimons sans frais. Le livre étant personnalisé, il n'y a pas de droit de rétractation (voir les <a href=\"/cgv\">conditions de vente</a>)."]),
                     ("Les données de votre enfant", ["Elles servent uniquement à créer ses créations. Nous ne les partageons pas et nous les effaçons après la livraison (voir la <a href=\"/confidentialite\">politique de confidentialité</a>)."]),
                     ("Comment c'est fait", [IA])],
                 faq=[("Puis-je suivre ma commande ?", "Oui, dans « Mon compte », avec le numéro de suivi dès l'expédition."),
                      ("Puis-je offrir le livre ?", "Oui : cochez « C'est pour offrir », votre petit mot est imprimé au dos."),
                      ("L'e-book, c'est quoi ?", "Le PDF de son livre, à lire sur tablette ou téléphone. Vous pouvez commander la version imprimée plus tard, sans recréer le livre.")],
                 liens=["tarifs", "avis-clients", "livre-personnalise-enfant"]),
})


COURT = {"livre-personnalise-enfant": "Livre personnalisé enfant", "livre-personnalise-noel": "Livre de Noël personnalisé",
         "livre-anniversaire-personnalise": "Livre d'anniversaire", "livre-doudou-personnalise": "Livre avec son doudou",
         "livre-emotions-enfant": "Peur du noir, émotions, bébé", "calendrier-personnalise-enfant": "Calendrier personnalisé",
         "cahier-coloriage-personnalise": "Cahier de coloriage personnalisé", "cadeau-personnalise-enfant": "Idées cadeaux enfant",
         "livre-grand-frere-grande-soeur": "Grand frère, grande sœur", "livre-paques-personnalise": "Livre de Pâques",
         "livre-personnalise-par-age": "Par âge", "tarifs": "Tarifs", "avis-clients": "Avis clients", "idees-histoires": "Idées d'histoires",
         "aide": "Centre d'aide"}

CSS = """
.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--ciel) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--trait)}
.top .in{display:flex;align-items:center;gap:16px;height:68px}.top .logo-img{height:46px;width:auto}.top .btn{margin-left:auto}
.ariane{font-size:14px;color:var(--encre-2);margin:18px 0 0}.ariane a{color:var(--encre-2)}
.tete{display:grid;grid-template-columns:1.1fr .9fr;gap:36px;align-items:center;padding:34px 0 50px}
.kick{display:inline-block;font:900 13px/1 var(--texte);letter-spacing:1.4px;text-transform:uppercase;background:var(--encre);color:#fff;padding:8px 12px;border-radius:999px;margin-bottom:14px}
h1{font:400 clamp(32px,4.6vw,52px)/1.08 var(--titre);margin:0 0 16px;letter-spacing:-.4px}
.intro{font-size:19px;color:var(--encre-2);margin:0 0 24px;max-width:56ch}
.tete img{width:100%;height:auto;border-radius:24px;border:2px solid var(--encre);box-shadow:8px 8px 0 var(--luciole);aspect-ratio:1;object-fit:cover}
.ia-l{font:800 14px/1.4 var(--texte);color:var(--encre-2);margin:14px 0 0}
.corps{display:grid;grid-template-columns:1fr;gap:6px;max-width:780px;padding-bottom:30px}
.corps h2{font:400 clamp(26px,3vw,34px)/1.15 var(--titre);margin:30px 0 8px}
.corps p,.corps li{color:var(--encre-2)}.corps ul{padding-left:20px}.corps li{margin:4px 0}
.faq{max-width:780px;margin:10px 0 40px}.faq h2{font:400 clamp(26px,3vw,34px)/1.15 var(--titre);margin:30px 0 12px}
.faq details{background:var(--papier);border:1px solid var(--trait);border-radius:16px;padding:14px 18px;margin:0 0 10px}
.faq summary{font-weight:800;cursor:pointer}.faq p{margin:10px 0 0;color:var(--encre-2)}
.fin{background:var(--nuit);color:#fff;border-radius:26px;padding:34px 26px;text-align:center;margin:20px 0 40px}
.fin h2{font:400 clamp(26px,3vw,34px)/1.15 var(--titre);margin:0 0 10px;max-width:none}.fin p{color:#E9E3FF;margin:0 0 20px}
.voir{margin:0 0 50px}.voir h2{font:400 24px/1.2 var(--titre);margin:0 0 12px}
.voir ul{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:10px}
.voir a{display:inline-block;padding:10px 16px;border-radius:999px;background:var(--papier);border:1.5px solid var(--encre);font-weight:800;text-decoration:none}
table.t{width:100%;border-collapse:collapse;background:var(--papier);border:1px solid var(--trait);border-radius:16px;overflow:hidden;margin:6px 0 10px}
table.t td{padding:12px 16px;border-bottom:1px solid var(--trait);color:var(--encre)}table.t td:last-child{text-align:right;font-weight:800;white-space:nowrap}
table.t tr:last-child td{border-bottom:0}
.avs{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;margin:8px 0}
.av{margin:0;background:var(--papier);border:1px solid var(--trait);border-radius:18px;padding:16px}.av img{width:100%;border-radius:12px;margin:8px 0 0}
.av .et{color:#E9A800;letter-spacing:2px}.av blockquote{margin:10px 0;color:var(--encre)}.av figcaption{font-weight:800;font-size:14px;color:var(--encre-2)}
.puces{columns:2;column-gap:28px}@media (max-width:600px){.puces{columns:1}}
@media (max-width:820px){.tete{grid-template-columns:1fr;gap:22px;padding-top:20px}.tete img{max-width:420px}}
"""


def liens_pied():
    return "".join(f'<a href="/{k}">{escape(v)}</a>' for k, v in COURT.items())


CB = ('<span class="pm" aria-label="Carte bancaire">CB</span><span class="pm visa" aria-label="Visa">VISA</span>'
      '<span class="pm mc" aria-label="Mastercard"><i></i><i></i></span>')

PIED_CSS = """
.pied{padding:44px 0 120px;color:var(--encre-2);font-size:15px;border-top:1px solid var(--trait);margin-top:20px}
.pied .cols{display:grid;grid-template-columns:repeat(4,1fr);gap:26px}
.pied h3{font:900 15px/1.2 var(--texte);color:var(--encre);margin:0 0 10px}
.pied ul{list-style:none;margin:0;padding:0}.pied li{margin:0 0 8px}.pied a{color:var(--encre-2);text-decoration:none}.pied a:hover{text-decoration:underline}
.pied .bas{display:flex;flex-wrap:wrap;gap:14px 24px;align-items:center;justify-content:space-between;margin-top:30px;padding-top:20px;border-top:1px solid var(--trait)}
.pied .paie{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.pied .paie b{color:var(--encre);margin-right:4px}
.pm{display:inline-grid;place-items:center;min-width:46px;height:30px;padding:0 8px;border:1px solid var(--trait);border-radius:7px;background:#fff;font:900 12px/1 var(--texte);color:#1A1F71}
.pm.visa{font-style:italic;letter-spacing:.5px}.pm.mc{position:relative;width:46px}.pm.mc i{position:absolute;top:7px;width:16px;height:16px;border-radius:50%;background:#EB001B}
.pm.mc i+i{left:22px;background:#F79E1B;opacity:.9}.pm.mc i:first-child{left:12px}
@media (max-width:820px){.pied .cols{grid-template-columns:1fr 1fr}}
.barre{position:fixed;left:0;right:0;bottom:0;z-index:50;padding:10px 14px calc(10px + env(safe-area-inset-bottom));background:color-mix(in srgb,var(--ciel) 92%,transparent);
  backdrop-filter:blur(10px);border-top:1px solid var(--trait);transform:translateY(110%);transition:transform .25s}
.barre.on{transform:none}.barre .btn{width:100%;justify-content:center;text-align:center}
@media (min-width:821px){.barre{display:none}}
"""


def pied():
    """Pied de page commun (accueil et pages) : découvrir, occasions, inspiration, service, moyens de paiement."""
    col = lambda t, l: f"<div><h3>{t}</h3><ul>" + "".join(f'<li><a href="{u}">{escape(x)}</a></li>' for x, u in l) + "</ul></div>"
    return ("<footer class='pied'><div class='wrap'><div class='cols'>"
            + col("Découvrir", [("Créer son avatar", "/creer"), ("Feuilleter nos livres", "/#feuilleter"), ("Avis clients", "/avis-clients"), ("Tarifs", "/tarifs"),
                                ("Comment c'est fait", "/#ia")])
            + col("Occasions", [("Noël", "/livre-personnalise-noel"), ("Anniversaire", "/livre-anniversaire-personnalise"), ("Pâques", "/livre-paques-personnalise"),
                                ("Grand frère, grande sœur", "/livre-grand-frere-grande-soeur"), ("Toutes les idées cadeaux", "/cadeau-personnalise-enfant")])
            + col("Inspiration", [("Idées d'histoires", "/idees-histoires"), ("Par âge", "/livre-personnalise-par-age"), ("Peur du noir, émotions", "/livre-emotions-enfant"),
                                  ("Livre avec son doudou", "/livre-doudou-personnalise"), ("Livre personnalisé enfant", "/livre-personnalise-enfant"),
                                  ("Calendrier personnalisé", "/calendrier-personnalise-enfant"), ("Cahier de coloriage", "/cahier-coloriage-personnalise")])
            + col("Service", [("Centre d'aide", "/aide"), ("Mon compte", "/compte"), ("Nous contacter", "/#contact"), ("Conditions de vente", "/cgv"),
                              ("Mentions légales", "/mentions-legales"), ("Confidentialité", "/confidentialite")])
            + "</div><div class='bas'><div class='paie'><b>Paiement sécurisé</b>" + CB + "</div>"
            + "<a href='https://www.instagram.com/monherosdumois/' rel='noopener' target='_blank'>Instagram</a></div></div></footer>"
            + "<style>" + PIED_CSS + "</style>")


def barre(href="/creer", texte="Créer son avatar gratuitement"):
    """Bouton fixe en bas de l'écran du téléphone, qui apparaît quand le bouton du haut n'est plus visible."""
    return (f"<div class='barre' id='barreCta'><a class='btn' href='{href}'>{escape(texte)}</a></div>"
            "<script>(function(){var b=document.getElementById('barreCta');function v(){b.classList.toggle('on',scrollY>520&&(innerHeight+scrollY)<document.body.scrollHeight-260)}"
            "addEventListener('scroll',v,{passive:true});v();})();</script>")


def rendre(slug):
    p = PAGES[slug]
    b = base()
    url = f"{b}/{slug}"
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{b}/"},
              {"@type": "ListItem", "position": 2, "name": COURT[slug], "item": url}]},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in p["faq"]]}]
    if slug in CONSTRUIRE:
        p = dict(p, sections=CONSTRUIRE[slug]() + p["sections"])
    sections = "".join(f"<h2>{escape(h)}</h2>" + "".join(x if x.startswith("<") else f"<p>{x}</p>" for x in paras) for h, paras in p["sections"])
    faq = "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in p["faq"])
    voir = "".join(f'<li><a href="/{k}">{escape(COURT[k])}</a></li>' for k in p["liens"])
    verif = os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()
    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(p['titre'])} – Mon Héros du Mois</title>
<meta name="description" content="{escape(p['desc'])}">
<link rel="canonical" href="{url}">
{f'<meta name="google-site-verification" content="{escape(verif)}">' if verif else ''}
<link rel="icon" type="image/png" href="/static/marque/favicon-64.png"><link rel="apple-touch-icon" href="/static/marque/apple-touch-icon.png">
<meta property="og:type" content="website"><meta property="og:site_name" content="Mon Héros du Mois"><meta property="og:locale" content="fr_FR">
<meta property="og:title" content="{escape(p['titre'])}"><meta property="og:description" content="{escape(p['desc'])}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{b}{p['image'][0]}">
<meta name="twitter:card" content="summary_large_image"><meta name="theme-color" content="#2E1A6E">
<link rel="preload" as="image" href="{p['image'][0]}">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<link rel="stylesheet" href="/static/theme.css">
<script src="/static/mesure.js"></script>
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="in wrap"><a href="/" aria-label="Mon Héros du Mois, accueil"><img class="logo-img" src="/static/marque/logo-h.webp" alt="Mon Héros du Mois" width="640" height="247"></a>
<a class="btn petit" href="{p['cta'][1]}">Créer son avatar</a></div></header>
<main class="wrap">
<nav class="ariane" aria-label="Fil d'Ariane"><a href="/">Accueil</a> › {escape(COURT[slug])}</nav>
<section class="tete">
  <div><span class="kick">{escape(p['kicker'])}</span><h1>{escape(p['h1'])}</h1><p class="intro">{escape(p['intro'])}</p>
    <a class="btn" href="{p['cta'][1]}">{escape(p['cta'][0])}</a>
    <p class="ia-l">Gratuit pour commencer, sans inscription. Vous voyez sa couverture avant de payer.</p></div>
  <img src="{p['image'][0]}" alt="{escape(p['image'][1])}" width="800" height="800" fetchpriority="high">
</section>
<section class="corps">{sections}</section>
<section class="faq"><h2>Vos questions</h2>{faq}</section>
<section class="fin"><h2>Ce soir, votre enfant est le héros</h2><p>Composez son avatar en quelques minutes, puis choisissez ses créations. Vous ne payez qu'à la fin.</p>
  <a class="btn" href="{p['cta'][1]}">{escape(p['cta'][0])}</a></section>
<nav class="voir" aria-label="À voir aussi"><h2>À voir aussi</h2><ul>{voir}</ul></nav>
</main>
{pied()}{barre(p['cta'][1] if p['cta'][1].startswith('/creer') else '/creer')}
</body>
</html>"""
    return Response(html, mimetype="text/html")


def _route(slug):
    return lambda: rendre(slug)


for _s in PAGES:
    bp.add_url_rule(f"/{_s}", f"page_{_s.replace('-', '_')}", _route(_s), methods=["GET"])


@bp.after_app_request
def noindex_hors_domaine(r):
    """L'adresse technique Railway ne doit pas concurrencer le vrai domaine dans Google."""
    if request.host.endswith(".up.railway.app") and request.method == "GET":
        r.headers["X-Robots-Tag"] = "noindex"
    return r
