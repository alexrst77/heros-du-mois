# Mon Héros du Mois – générateur de livres personnalisés

Éditeur d'avatars → histoire → storyboard → planche personnages (validée par le parent) → aperçu couverture + 2 doubles pages (validé) → livre de 20 pages en 21 x 21 cm, avec contrôle qualité automatique.

## Démarrage sur Mac
1. Installe Python 3 si besoin : https://www.python.org/downloads/
2. Double-clique sur **lancer.command** (la première fois : clic droit > Ouvrir). Il installe tout et crée le fichier `.env`.
3. Ajoute ta clé OpenAI dans `.env` (`OPENAI_API_KEY=`), puis relance **lancer.command**.
4. Le site s'ouvre sur http://localhost:8000.

Sans clé, ou en cochant « Mode démo », le site met en page le livre d'exemple de Léo, sans appel à l'API.

## Avatars peints (éditeur)
- 22 modèles peints dans le style de Léo (`static/avatars/`, références 1024 px dans `style/avatars/`).
- **Aperçu instantané et gratuit** : couleurs (cheveux, peau, tenue, pelage, doudou, nœud), lunettes, couleur des yeux et taches de rousseur s'appliquent directement sur le modèle peint dans le navigateur (masques calculés par `build_masks.py`). Aucun appel à OpenAI avant la commande.
- Ce qui n'apparaît que dans le livre : type de tenue, motif, collier et oreilles des animaux, accessoire du doudou autre que le nœud.

## Comment un livre est fabriqué (après paiement)
0. **Configuration** (`generator.build_config`) : enregistrée dans `config.json` avec un identifiant stable par personnage (heros, doudou, animal_1…). C'est la seule source utilisée ensuite. Les données manquantes ou invalides sont signalées, jamais remplacées en silence.
1. **Histoire** de 18 pages illustrées, puis **relecture** (prénoms, accords, pronoms). Un personnage inventé ne peut jamais reprendre le nom d'un personnage imposé.
2. **Storyboard** par identifiants : tout personnage cité par le texte est à l'image, les personnages oubliés sont déclarés, les palettes sont variées.
3. **Portraits de référence** : un par personnage, mis en cache par configuration et version de style (`art.STYLE_VERSION`), validés par le parent (redessin au cas par cas).
4. **Illustrations** : chaque page reçoit exactement les portraits de ses personnages et la planche de style (trace dans `references_transmises.jsonl`). Un **contrôle visuel** automatique vérifie chaque image ; en cas d'écart, un seul nouvel essai (`MAX_RETRIES`), puis l'échec est signalé.
5. **PDF** : 20 pages à l'écran (couverture, 18 pages, 4e) et intérieur d'impression Lulu de 24 pages (8,5 × 8,5 pouces, fond perdu, 300 dpi).

Tests : `python3 tests/test_generation.py` et `python3 tests/test_commande.py` (sans coût, tout est simulé). Livre test réel : `python3 generer_livre_test.py tests/config_jeade.json`.

## Commande, paiement, impression
- Étape 5 « La commande » : formule (un livre 34,90 € ; 29,90 €/mois ; 6 livres de fête à 12,45 €/mois pendant 12 mois), adresse, acceptation des CGV (pas de droit de rétractation pour un livre personnalisé). Rien n'est généré avant le paiement.
- **Paiement** : Stripe Checkout. Sans clé Stripe, un bouton « Simuler le paiement » permet de tout tester. Webhook : `https://TON-SITE/api/stripe/webhook` (événements `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`).
- Après paiement, le livre est fabriqué (le parent valide personnages et aperçu), puis la commande passe **« à relire »**.
- **Administration** : `/admin` (liste, PDF, contrôle qualité, « Préparer la couverture », « Coût Lulu », « Envoyer à l'impression », suivi du colis, abonnements, effacement des données). Rien ne part à l'impression sans ton clic (sauf `AUTO_IMPRESSION=1`).
- **Impression** : Lulu, en **bac à sable** par défaut (`LULU_ENV=sandbox`). Lulu télécharge les PDF sur ton site : il faut une adresse publique (`PUBLIC_URL`), donc héberger le site.
- **Abonnements** : mensuel = un nouveau livre à chaque facture Stripe payée ; le livre qui arrive juste avant une fête cochée par la famille (anniversaire, Noël, Aïd…) est un livre de fête. Formule « 6 livres de fête » = 12 mensualités de 12,45 € ; chaque livre est lancé 35 jours avant sa fête (planificateur horaire), l'abonnement Stripe s'arrête seul après la 12e mensualité.
- **Univers et fêtes** : une seule liste dans `univers.py` (éditeur, vitrine, illustrations, consignes d'histoire, dates des fêtes jusqu'en 2030 ; les fêtes lunaires sont à un ou deux jours près).
- Les données des commandes sont dans `data/` (base SQLite + configuration de chaque enfant). CGV à compléter : `static/cgv.html`.

## Mise en ligne (Railway)
1. Compte sur railway.com (offre Hobby), puis dans le Terminal : `brew install railway` (ou `npm i -g @railway/cli`), `railway login`.
2. Dans le dossier du site : `railway init` (nouveau projet), puis `railway up` (envoie le dossier ; le `Dockerfile` est utilisé, `.env` et `.venv` ne sont pas envoyés).
3. Sur railway.com, dans le service : **Volume** monté sur `/data` (commandes, livres, portraits), **Networking > Generate Domain** (adresse `…up.railway.app`).
4. **Variables** : `OPENAI_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `ADMIN_CODE` (obligatoire en ligne), `PUBLIC_URL=https://…up.railway.app`, `LULU_CLIENT_KEY`, `LULU_CLIENT_SECRET`, `LULU_ENV=sandbox`.
5. Stripe (mode test) > Développeurs > Webhooks > Ajouter une destination : `https://…up.railway.app/api/stripe/webhook`, événements `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted` ; copie le secret `whsec_…` dans `STRIPE_WEBHOOK_SECRET`.
6. Admin en ligne : `https://…up.railway.app/admin?code=TON_ADMIN_CODE`.
Mise à jour du site : `railway up` depuis le dossier. Un livre en cours de fabrication pendant une mise à jour repart tout seul au redémarrage.
Place disque : seules les images finales sont gardées ; les fichiers d'un livre expédié sont effacés après 30 jours (`PURGE_JOURS`).

## Couleurs
Chaque image générée passe par une correction de la dominante jaune-orangée (`couleur.py`) ; l'original est gardé en `*_brut.png`.

## Anciennes étapes (pour mémoire)
1. **Histoire** (`generator.write_story`) : arc en 9 étapes, dialogues, prénoms exacts, compagnons actifs. Un contrôle vérifie les prénoms et les longueurs, puis une 2e passe corrige les écarts.
2. **Storyboard** (`generator.make_storyboard`) : pour chaque page, l'action, les personnages présents, les gestes, le décor, les objets cités par le texte, le cadrage (plan large, action, moment intime, détail, découverte, plongée), la zone de texte et la lumière. Des garde-fous imposent la variété des plans et des zones, et que chaque élément cité par le texte soit visible.
3. **Planche personnages** : les avatars du formulaire (envoyés en images) et la planche de style servent de références pour peindre l'enfant, le doudou et les animaux. **Le parent valide** ou fait redessiner.
4. **Illustrations** : pour chaque scène, la planche validée et la planche de style sont passées en images de référence (`images.edit`, fidélité haute). Seuls les personnages présents sont décrits, et la zone calme pour le texte est prévue dès la composition.
5. **Aperçu** (couverture + 2 doubles pages) à valider, puis le reste du livre.
6. **Mise en page** (`layout.py`) : illustrations pleine page, texte dans la zone la plus calme, fondu continu teinté par le décor, halo doux sous les lettres, pages chapitre sur des décors d'ambiance sans personnage, et contrôle (contraste ≥ 4,5:1, aucun débordement, nombre de pages). Le résultat est enregistré dans `controle.json`.

## Les fichiers
- `art.py` : **toutes les règles graphiques** (style, univers, lumières, cadrages, zones de texte, typo, fondus). C'est le seul fichier à modifier pour changer la direction artistique.
- `style/planche_style.png` : extraits de décors de « Léo » (sans personnage), utilisés comme référence de technique picturale.
- `generator.py` : histoire, storyboard et appels images
- `layout.py` : moteur de mise en page et contrôle qualité
- `app.py` : serveur et étapes de validation
- `static/` : éditeur d'avatars et suivi de création

## Coût et durée
Un livre = 2 à 4 appels texte + 13 images (planche, couverture, 9 scènes, 2 décors), plus les éventuels « redessiner ». En qualité `high`, compte environ 2,5 à 3 € par livre, et environ 4 à 5 fois moins en `medium`. Vérifie les tarifs à jour sur platform.openai.com. Durée : 5 à 8 minutes hors validations.
`AUTO_VALIDATE=1` dans `.env` enchaîne tout sans les étapes de validation.

## Procédé des livres Mila et Noé (kit) — actif par défaut (`PROCEDE=kit`)

- `moteur_livre.py` : le moteur PDF du kit, porté sans changer un calcul (20 pages carrées 210 mm, panoramas 2:1 coupés à 50 %,
  DejaVu Serif 14,8/21 pt, fondu de 225 pt, texte à 43 pt du bas, 147 pt maximum). Test sans API :
  `python3 moteur_livre.py kit/noe-demo.json --output test/Noe.pdf` (20 pages, identique au PDF Noé d'origine).
- `procede.py` : instantané de la commande (version + empreinte) → fiches des personnages (« aucun » explicite) → portraits
  d'identité contrôlés (aucune régénération automatique) + fiche de groupe → storyboard JSON (9 doubles pages, textes vérifiés avec la police du
  moteur AVANT les images) → couverture sans texte (titre composé dans le PDF) → panorama pilote → 8 panoramas → contrôles →
  assemblage → rendu contrôlé (pages en images, planches contact). États : queued, references, storyboard, illustrating,
  reviewing, assembling, ready, needs_review, failed.
- Chaque appel image envoie les fichiers (couverture personnalisée, fiche de groupe, portraits des présents, 1 référence de STYLE
  Mila/Noé) ; tout est tracé dans `references_transmises.jsonl` (rôle, empreinte, taille demandée/reçue, modèle, prompt).
- Variables : `OPENAI_IMAGE_MODEL` (ou `OPENAI_PANO_MODEL`) doit gérer les tailles libres (gpt-image-2…), sinon la fabrication
  s'arrête avant toute dépense ; `OPENAI_PANO_SIZE` (2048x1024), `OPENAI_COVER_SIZE` (1024x1024).
  L'ancienne chaîne (`PROCEDE=ancien`) est désactivée : elle ne passe pas par le plafond de 3 $.
- Tests : `python3 tests/test_procede.py`, `tests/test_budget.py`, `tests/test_commande.py`, `tests/test_essai.py`, `tests/test_fetes.py`
  (OpenAI, Stripe et Lulu simulés : aucun appel réel, aucun paiement, aucune impression).

## Plafond de 3 $ par livre (`budget.py`, `tarifs.json`)

- **Tarifs** : `tarifs.json` (copie de travail : `DATA_DIR/tarifs.json`). Tant que tu n'as pas confirmé les prix dans l'admin
  (« J'ai vérifié ces prix… ») et lancé le calibrage (1 appel ≈ 0,02 $ qui mesure les jetons d'une image de référence), **toute
  fabrication est refusée**. Un modèle sans tarif, une qualité ou une taille hors calcul : appel refusé.
- **Avant de lancer** : borne haute de tous les appels restants (modèles, tailles, qualités, jetons max fixés ; marge 15 %),
  recalculée exactement après le storyboard. Au-delà de 3 $ (dépense déjà faite comprise) : refus, rien n'est dépensé.
- **Avant chaque appel** : réservation atomique de son coût maximal (SQLite, sûr entre fils et processus) ; après : coût réel.
  Le budget est celui de la COMMANDE : refaire un livre ne redonne pas 3 $.
- **Aucune relance** : client OpenAI `max_retries=0`, une seule image par page, pas de variantes, pas de correction automatique.
  Coupure réseau après envoi → appel « incertain », réservé, jamais renvoyé ; le livre s'arrête. Dans l'admin, « Budget API du
  livre » → « Saisir le coût constaté » (d'après platform.openai.com/usage), puis « Relancer » : seul ce qui manque est fait.
- **Sortie non conforme** → « à relire ». Tu relis le PDF, puis « Finaliser après relecture » (aucun appel) ou tu laisses en l'état.
- **Livre finalisé** (`final.json`, empreintes de tous les fichiers) : téléchargements, aperçus, réimpression = fichiers enregistrés,
  zéro appel. Sauvegarde zip dans `DATA_DIR/sauvegardes` (ou `SAUVEGARDE_DIR`), restauration vérifiée par empreintes.

## Fabrication (`fabrication.py`)

- PDF de lecture : 20 faces (couverture + 18 pages + 4e). Intérieur imprimeur : 24 pages 8,5 po + fond perdu 0,125 po
  (minimum Lulu en couverture rigide), les doubles pages tombent sur de vraies doubles pages.
- Couverture à plat 4e | dos | 1re aux dimensions de l'API Lulu (sinon maquette marquée « non confirmée »).
- **volumeNumber** : numéro du livre dans la collection (1, 2, 3…), attribué une fois (sans doublon), composé par code en bas du
  dos, toujours au même endroit, et repris sur la 4e et la dernière page.
- **Limite Lulu** : pas de texte sur le dos en dessous de 81 pages (dos de 0,25 po à 24 pages). Le numéro est composé quand même,
  mais le fichier est marqué NON prêt à imprimer et l'envoi est bloqué. Quand l'imprimeur a validé par écrit : `DOS_NUMERO_VALIDE_IMPRIMEUR=1`.
- Aperçus (`apercus/`) : couverture, couverture à plat, détail du dos, doubles pages, album sur l'étagère, tous tirés des PDF réels.
