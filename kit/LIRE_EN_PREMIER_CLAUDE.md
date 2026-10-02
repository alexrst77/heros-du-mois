# Mission : reproduire le procédé des livres Mila et Noé

Intègre ce kit au site existant « Mon Héros du Mois ». Inspecte d'abord le code, puis corrige le parcours complet. L'objectif est le même langage visuel et la même mise en page que les références fournies. Ne promets pas une identité pixel par pixel entre deux générations.

Ce kit ne contient ni connexion au site, ni clé API, ni serveur de production. Le moteur PDF fonctionne localement sans API. L'adaptateur OpenAI, les tâches en arrière-plan, le stockage et la validation doivent être raccordés à l'architecture réelle du site.

## Démarrage obligatoire : test sans génération payante

1. Installe les dépendances de requirements.txt dans un environnement Python.
2. Lance `python render_book.py noe-demo.json --output test/Noe.pdf`.
3. Vérifie les 20 pages et les planches contact dans test/render-work/. Ce test réutilise les illustrations réellement utilisées dans la conversation.
4. Branche ce même moteur, ou porte fidèlement ses calculs dans la pile du site. Ne remplace pas ses fondus par des cartes, rectangles, cadres ou photos miniatures.

## Ce qui a effectivement été fait dans la conversation

Une couverture validée a servi de référence visuelle à chaque génération. Neuf images panoramiques 2:1 ont été créées, une par double page. Chaque image est placée à cheval sur deux pages carrées ; les textes sont ajoutés après génération. Des erreurs de composition ont été corrigées visuellement avant assemblage. Le moteur joint reprend les dimensions, les polices, les fondus et les positions du PDF Noé. Les scènes de Mila montrent la variante plus lumineuse.

Le nom exact du modèle derrière l'outil de cette conversation n'est pas exposé ici. Ne prétends pas le connaître. Choisis un modèle image accessible au compte, compatible avec images de référence et format panoramique, compare son résultat aux références et conserve le choix validé. Ne bascule pas silencieusement sur un modèle moins qualitatif.

## Chaîne de production à implémenter

Configuration enregistrée -> fiche des personnages -> références personnalisées validées -> récit et storyboard -> couverture -> neuf panoramas -> contrôle des images -> assemblage PDF -> contrôle rendu -> disponible.

- Photographier logiquement la configuration à la commande : snapshot immuable, version et hash. Ne pas réutiliser les valeurs par défaut du formulaire.
- Chaque enfant, doudou et animal a un identifiant stable. Préserver chaque nom, espèce, teinte, motif, couleur des yeux, taille, vêtement, lunettes et accessoire. Conserver « aucun » comme valeur explicite. Ne jamais fusionner les animaux.
- Les PNG d'avatars précédents sont des bases : ils ne représentent pas automatiquement la configuration finale.
- Créer une référence propre pour chaque personnage et une fiche de groupe quand plusieurs personnages coexistent. Vérifier les caractéristiques contre les données avant de générer le livre.
- Séparer références de STYLE et références d'IDENTITÉ. Mila et Noé montrent le style ; ne pas injecter leurs traits à un autre enfant. La référence personnalisée commande l'identité.
- À chaque appel image, envoyer réellement les fichiers image, pas seulement leurs URL ou noms écrits dans le prompt. La couverture personnalisée et les fiches des personnages présents servent de références fixes.
- Les appels API du site ne récupèrent pas automatiquement le contexte de cette conversation : chaque tâche doit disposer explicitement des consignes et références nécessaires.
- Aucun doudou ou animal configuré ne disparaît d'une scène qui le mentionne ; une absence volontaire doit être prévue au storyboard.

## Histoire et storyboard

Utiliser prompts/storyboard.txt. Créer 18 textes, organisés en neuf doubles pages, plus couverture et quatrième. Environ 30–45 mots par page pour la cible 4–7 ans de ces exemples ; adapter le langage à l'âge réel. Une intrigue, des actions visibles, des dialogues naturels, une résolution et une fin douce. Ne pas recycler l'histoire de Noé avec un autre prénom.

Chaque double page doit fournir : texte gauche, texte droit, action, lieu, lumière, palette, identifiants des personnages présents, détails invariants, composition gauche/droite, zone calme pour le texte. Les textes et actions doivent correspondre. Les références factices, titres provisoires et données manquantes doivent être résolus avant génération.

## Images

Utiliser prompts/illustration.txt comme base, complétée pour chaque scène. Produire UNE image panoramique 2:1 par double page, sans aucun texte. La coupure centrale se situe à x=50 %. Garder visages et détails indispensables hors de x=44–56 %. Une scène peut se prolonger sur les deux pages ; ne pas y placer deux copies involontaires du même enfant. Pour deux moments successifs, le demander explicitement.

Modèle, qualité et dimensions doivent être des paramètres serveur, contrôlés selon la documentation actuelle et l'accès du compte. Un prompt disant « 2:1 » ne remplace pas les paramètres de taille. Vérifier les dimensions décodées. Ne pas étirer une image 3:2 pour en faire du 2:1 ni couper les personnages pour la forcer. Choisir un modèle prenant en charge le format demandé ou signaler la limite.

La qualité des livres joints a été obtenue avec contrôle et corrections. Limiter les corrections automatiques (par exemple deux par scène), conserver les images déjà validées, puis demander une revue si un écart persiste. Un score de vision seul ne garantit pas la fidélité.

## Mise en page à conserver

- 20 pages AU TOTAL : couverture + 18 pages d'histoire + quatrième.
- Pages carrées 210 × 210 mm pour la version de lecture, soit 595,2756 points.
- Fond plein cadre ; chaque panorama est coupé en deux sans déformation.
- Texte réel sélectionnable, ajouté dans le PDF ; jamais dessiné par le générateur dans les scènes.
- Police DejaVu Serif fournie, corps 14,8 pt, interligne 21 pt, marges latérales 45 pt, texte à 43 pt du bas. Hauteur maximale 147 pt : si dépassement, raccourcir le texte ou revoir la composition, pas de réduction silencieuse de la police.
- Fondu RGBA continu de 225 pt : opacité 0,96 jusqu'à 135 pt du bas, puis décroissance douce jusqu'à zéro à 225 pt. Code exact dans render_book.py.
- Noé : fond de lecture #171B3A, texte #FFF7E8. Mila : scènes claires #F5F0DF / #163E49 ; scènes nocturnes #092D43 / #FFF7E8. Choisir en fonction de chaque scène, pas appliquer un filtre global.
- Couverture : le fichier de démonstration porte déjà son titre. Pour les nouveaux livres, préférer une illustration avec zone de titre et composer le titre séparément pour contrôler l'orthographe. Ne pas ajouter le titre une deuxième fois aux images existantes.
- Le format joint est une version de lecture. Avant impression, obtenir les gabarits de l'imprimeur : fond perdu, résolution effective, profil couleur, couverture séparée, dos et pagination. Le moteur ne certifie pas un PDF prêt pour n'importe quel imprimeur.

## Architecture du site

Exécuter la génération côté serveur dans une tâche durable, pas dans une requête navigateur longue. Clé API uniquement serveur. Sauvegarder progression, références, prompts versionnés, modèle effectif, identifiants de requêtes, images et rapports de contrôle. Reprendre une tâche interrompue à son étape manquante.

La clé de cache inclut : configuration, histoire/scène, hashes des références, version du prompt, modèle et réglages. Une modification d'accessoire invalide les références personnalisées et scènes concernées. Les téléchargements répétés servent le PDF stocké : ne pas régénérer à chaque lecture.

Gestion de débit et erreurs : concurrence bornée, reprise avec temporisation pour erreurs transitoires, limites de tentatives/coût, traitement explicite des refus et paramètres invalides. Ne pas contourner un refus ni masquer une erreur par une image générique.

États internes conseillés : queued, references, storyboard, illustrating, reviewing, assembling, ready, needs_review, failed. Ne passer à ready qu'après les contrôles. Ne jamais déclencher l'impression d'une génération non validée.

## Vérification avant livraison

1. Le test local Noé doit produire 20 pages lisibles avec ses neuf panoramas, sans appel API.
2. Tester une commande avec deux animaux très différents et un doudou, dont un accessoire inhabituel. Vérifier les champs à chaque étape et les références réellement envoyées.
3. Générer un seul panorama pilote pour calibrer le rendu avant les huit autres.
4. Vérifier identité, nombre de personnages, scènes, couleurs, anatomie, texte parasite et placement à la pliure.
5. Rendre les 20 pages en images ; vérifier texte, contraste, débordements, coupures, caractères et couverture.
6. Tester l'interruption/reprise et un changement de configuration pour exclure les anciennes images du cache.

Livre-moi les modifications concrètes, le résultat du test local et un livre pilote généré par le site. Signale clairement ce qui a été testé localement, ce qui a été testé avec l'API et ce qui reste à brancher. N'affirme pas que le site est corrigé sans avoir exécuté ce parcours.

Documentation officielle vérifiée le 2 octobre 2026 : https://developers.openai.com/api/docs/guides/image-generation
Le guide présente les éditions avec images de référence et les réglages d'image. Vérifier les paramètres du modèle choisi au moment du raccordement. Ce kit n'impose pas un identifiant de modèle non testé sur le compte.
