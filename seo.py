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

COURT = {"livre-personnalise-enfant": "Livre personnalisé enfant", "livre-personnalise-noel": "Livre de Noël personnalisé",
         "livre-anniversaire-personnalise": "Livre d'anniversaire", "livre-doudou-personnalise": "Livre avec son doudou",
         "livre-emotions-enfant": "Peur du noir, émotions, bébé", "calendrier-personnalise-enfant": "Calendrier personnalisé",
         "cahier-coloriage-personnalise": "Cahier de coloriage personnalisé", "cadeau-personnalise-enfant": "Idées cadeaux enfant"}

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
footer{padding:30px 0 50px;color:var(--encre-2);font-size:14px}footer .in{display:flex;flex-wrap:wrap;gap:12px 24px}footer a{color:var(--encre-2)}
@media (max-width:820px){.tete{grid-template-columns:1fr;gap:22px;padding-top:20px}.tete img{max-width:420px}}
"""


def liens_pied():
    return "".join(f'<a href="/{k}">{escape(v)}</a>' for k, v in COURT.items())


def rendre(slug):
    p = PAGES[slug]
    b = base()
    url = f"{b}/{slug}"
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{b}/"},
              {"@type": "ListItem", "position": 2, "name": COURT[slug], "item": url}]},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in p["faq"]]}]
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
<footer><div class="in wrap"><a href="/">Accueil</a>{liens_pied()}<a href="/cgv">Conditions de vente</a><a href="/mentions-legales">Mentions légales</a><a href="/confidentialite">Confidentialité</a></div></footer>
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
