"""Parcours « Créer son livre » de bout en bout, sans aucun appel payant (ni OpenAI, ni Stripe, ni Lulu).
Lancement :  python3 tests/test_parcours.py   (base de données temporaire, jamais celle du site)"""
import os, sys, json, time, io, shutil, tempfile
from pathlib import Path
RACINE = Path(__file__).resolve().parent.parent
os.environ.update(DATA_DIR=tempfile.mkdtemp(prefix="mhm-test-"), OPENAI_API_KEY="", STRIPE_SECRET_KEY="", PUBLIC_URL="", RAILWAY_ENVIRONMENT="")
sys.path.insert(0, str(RACINE)); os.chdir(RACINE)
import app as A, boutique as B, parcours as PC, commandes as db, procede as P, paiement, moteur_livre as M
from PIL import Image
c = A.app.test_client()
ok = lambda cond, m: print(("OK  " if cond else "ÉCHEC ") + m) or (cond or FAILS.append(m))
FAILS = []

cat = c.get("/api/catalogue").get_json()
ok(len(cat["themes"]) == 8 and len(cat["polices"]) == 8 and [s["cle"] for s in cat["styles"]] == ["gouache"], "catalogue : 8 thèmes, 8 polices, styles vendables = gouache")
ok(cat["prix"]["numerique"] == 990 and cat["prix"]["relie"] == 2790 and cat["prix"]["complement"] == 1800, "prix : numérique 9,90, relié 27,90, complément 18,00 (tarifs existants)")
ok(c.get("/creer").data.find(b"creer") > 0 and b"Choisir ce style" in c.get("/creer").data, "/creer : nouveau configurateur")
ok(b"Ton h\xc3\xa9ros" in c.get("/creer?formule=pack3").data or b"index" in c.get("/creer?formule=pack3").data or c.get("/creer?formule=pack3").status_code == 200, "/creer?formule=pack3 : ancien créateur (packs)")
ok(b"creer.html" not in c.get("/creer?commande=abc").data and b"Choisir ce style" not in c.get("/creer?commande=abc").data, "retour de paiement ancien : ancien créateur")

# brouillon
r = c.post("/api/projets", json={"donnees": {"age_lecteur": "3-5"}, "etape": "theme"}).get_json()
pid, J = r["id"], r["jeton"]; H = {"X-Projet-Jeton": J}
ok(c.get(f"/api/projets/{pid}").status_code == 404, "projet sans jeton : 404")
ok(c.get(f"/api/projets/{pid}?j=mauvais").status_code == 404, "projet avec un autre jeton : 404")
d = {"age_lecteur": "3-5", "theme": "aventure", "sujet": "pirates", "message": "courage", "style": "gouache", "police": "manuscrite", "cherche": "coccinelle", "langue": "fr",
     "heros": {"prenom": "Lina", "age": "5", "genre": "fille", "voie": "avatar", "passions": "dessin", "plat": "crêpes",
               "avatar": {"genre": "fille", "peau": "p3", "coiffure": "couettes", "couleur_cheveux": "roux", "yeux": "vert", "lunettes": "rondes", "couleur_lunettes": "bleu", "taches": "oui", "tenue": "salopette", "couleur_tenue": "bleu"}},
     "personnages": [{"type": "animal", "relation": "animal de compagnie", "nom": "Pistache", "avatar": {"type": "chat", "taille": "petit", "couleur": "roux", "motif": "raye", "couleur2": "blanc", "yeux": "verts", "collier": "rouge"}},
                     {"type": "personne", "relation": "grand-mère", "nom": "Mamie Jo", "age": "70", "voie": "description", "desc": "cheveux gris en chignon, lunettes rondes"}],
     "evenements": {"types": ["Vacances"], "texte": "Les vacances à l'île de Ré"}, "dedicace": {"de": "Papa et Maman", "texte": "Pour toi, Lina.\nQue chaque page te fasse rêver."}}
r = c.put(f"/api/projets/{pid}", json={"donnees": d, "etape": "recap"}, headers=H).get_json()
ok(r["ok"] and r["a_revoir"] == [], "sauvegarde du brouillon complet, rien à revoir")
# changement de thème : sujet devenu incompatible signalé, le reste gardé
d2 = dict(d, theme="famille")
r = c.put(f"/api/projets/{pid}", json={"donnees": d2, "etape": "theme"}, headers=H).get_json()
ok(r["a_revoir"] == ["sujet"], "thème changé : seul le sujet est à revoir")
p = c.get(f"/api/projets/{pid}", headers=H).get_json()
ok(p["donnees"]["heros"]["prenom"] == "Lina" and p["donnees"]["style"] == "gouache" and p["etape"] == "theme", "reprise du brouillon : choix conservés, étape gardée")
c.put(f"/api/projets/{pid}", json={"donnees": d, "etape": "recap"}, headers=H)
# dédicace
r = c.post(f"/api/projets/{pid}/dedicace", json={"i": 3}, headers=H).get_json()
ok("courageuse" in r["texte"] and "Lina" in r["texte"], "« Aidez-moi à écrire » : dédicace accordée au féminin")

# photo : dépôt, recadrage, accès protégé
buf = io.BytesIO(); Image.new("RGB", (800, 600), (200, 150, 120)).save(buf, "JPEG"); buf.seek(0)
r = c.post(f"/api/projets/{pid}/photos", data={"photo": (buf, "p.jpg"), "role": "heros", "consentement": "non"}, headers=H)
ok(r.status_code == 400, "photo sans consentement : refusée")
buf = io.BytesIO(); Image.new("RGB", (800, 600), (200, 150, 120)).save(buf, "JPEG"); buf.seek(0)
r = c.post(f"/api/projets/{pid}/photos", data={"photo": (buf, "p.jpg"), "role": "heros", "consentement": "oui", "x": ".1", "y": "0", "w": ".75", "h": "1"}, headers=H).get_json()
phid = r["id"]
ok(c.get(f"/api/projets/{pid}/photos/{phid}").status_code == 404, "photo sans jeton : 404")
r2 = c.get(f"/api/projets/{pid}/photos/{phid}", headers=H)
ok(r2.status_code == 200 and "no-store" in r2.headers["Cache-Control"], "photo avec jeton : servie, jamais en cache")
im = Image.open(io.BytesIO(r2.data)); ok(im.size == (600, 600) and not im.info.get("exif"), "photo recadrée (600×600), sans métadonnées")
other = c.post("/api/projets", json={"donnees": {}}).get_json()
ok(c.get(f"/api/projets/{pid}/photos/{phid}", headers={"X-Projet-Jeton": other["jeton"]}).status_code == 404, "photo d'un autre projet : 404")

# formulaire de fabrication : tous les choix transmis
p = PC.get(pid)
form, errs = PC.formulaire(p)
ok(not errs, "formulaire de fabrication construit " + str(errs))
pc = form["parcours"]
ok(pc["mots"] == [20, 32] and pc["police"] == "manuscrite" and pc["cherche_en"] and pc["sujet"] == "Pirates" and "Courage" in pc["consigne_message"], "âge, police, cherche et trouve, sujet, valeur transmis")
import generator as G
cfg = G.build_config(form)
ids = [x["id"] for x in cfg["personnages"]]
ok(ids == ["heros", "animal_1", "proche_1"] and not cfg["problemes"], "personnages : héros, chat, grand-mère (proche) " + str(ids))
snap = P.snapshot(form, cfg)
ok(P.word_range("5", snap) == (20, 32) and P.cherche_item(snap) and "pirate" in P.monde(snap), "instantané : mots, élément caché, décor")
# photo du héros : référence d'identité réellement envoyée
d3 = json.loads(json.dumps(d)); d3["heros"]["voie"] = "photo"; d3["heros"]["photo"] = phid; d3["photo_ok"] = True
c.put(f"/api/projets/{pid}", json={"donnees": d3, "etape": "recap"}, headers=H)
form, errs = PC.formulaire(PC.get(pid)); cfg = G.build_config(form)
ok(cfg["personnages"][0].get("photo", "").endswith(".jpg") and "PHOTO" in cfg["personnages"][0]["desc"], "voie photo : photo en référence du portrait")
pr = G.portrait_prompt(cfg["personnages"][0], True, False, has_photo=True)
ok("IDENTITY reference only" in pr, "prompt du portrait : photo comme référence d'identité")
# style non gouache : prompt et clé de cache changent ; gouache : identiques à avant
old_form = {"prenom": "Noé", "age": "5", "avatar": form["avatar"], "theme": "x", "univers": "La jungle"}
k1 = G.build_config(old_form)["personnages"][0]["cle"]
ok(k1 == G.portrait_key({k: v for k, v in G.build_config(old_form)["personnages"][0].items() if k != "cle"}), "ancienne commande : clé de portrait inchangée")
snap_old = P.snapshot(old_form, G.build_config(old_form))
ok("parcours" not in snap_old["histoire"] and P.prompt_image(snap_old) == P.PROMPT_IMAGE, "ancienne commande : instantané et prompt identiques")

# achat numérique (sans Stripe : mode test)
r = c.post(f"/api/projets/{pid}/acheter", json={"formule": "ebook", "email": "test@exemple.fr", "cgv": True}, headers=H)
ok(r.status_code == 400, "achat sans renonciation : refusé")
r = c.post(f"/api/projets/{pid}/acheter", json={"formule": "ebook", "email": "test@exemple.fr", "cgv": True, "renonce_retractation": True}, headers=H).get_json()
oid = r["id"]; o = db.get(oid)
ok(o["formule"] == "ebook" and o["montant"] == 990 and o["statut"] == "attente_paiement", "commande numérique 9,90 €, en attente de paiement (rien de lancé)")
ok(c.put(f"/api/projets/{pid}", json={"donnees": d}, headers=H).status_code == 409, "projet figé après le passage au paiement")
st = c.get(f"/api/mon-livre/{pid}", headers=H).get_json()
ok(st["etat"]["etat"] == "attente_paiement", "suivi : attente de paiement")
st = c.get(f"/api/mon-livre/{pid}?annule=1", headers=H).get_json()
ok(PC.get(pid)["statut"] == "brouillon", "paiement annulé : brouillon de nouveau modifiable")
r = c.post(f"/api/projets/{pid}/acheter", json={"formule": "ebook", "email": "test@exemple.fr", "cgv": True, "renonce_retractation": True}, headers=H).get_json()
oid = r["id"]

# paiement confirmé deux fois (webhook + retour) : un seul crédit, une seule fabrication
started = []
orig = B.start_book
B.start_book = lambda b, auto=False, reprise=False: started.append(b)
a1 = B.confirm_paid(oid); a2 = B.confirm_paid(oid)
B.start_book = orig
with db._db() as cx:
    n_cred = cx.execute("select count(*) from credits where projet_id=?", (pid,)).fetchone()[0]
ok(a1 and not a2 and started == [oid] and n_cred == 1, "notification reçue deux fois : un seul crédit, une seule génération")
st = c.get(f"/api/mon-livre/{pid}", headers=H).get_json()
ok(st["etat"]["etat"] == "en_cours" and st["etat"]["atteint"] == "paye", "suivi : paiement confirmé, état réel")

# fabrication simulée (aucun appel IA) : livre du kit avec la police et la dédicace du parcours
job = oid; folder = A.OUT / job; folder.mkdir(parents=True, exist_ok=True)
book = json.loads((P.KIT / "noe-demo.json").read_text())
for f in [book["cover"]] + book["spreads"]:
    shutil.copy(P.KIT / f, folder / Path(f).name)
book["cover"] = Path(book["cover"]).name; book["spreads"] = [Path(x).name for x in book["spreads"]]
book["police"] = form["parcours"]["police"]; book["dedicace"] = form["parcours"]["dedicace"]; book["volumeNumber"] = 1
book.setdefault("coverTitle", {"lines": ["Lina", "et les pirates"], "numero": 1})
(folder / "livre.json").write_text(json.dumps(book, ensure_ascii=False))
pdf = folder / "Lina.pdf"
rep = M.render(book, pdf, base=folder, work=folder / "rendu")
ok(rep["pages"] == 21 and not rep["problemes_rendu"], "PDF de lecture : 21 pages (dédicace), police du parcours")
fab = P.fabrication_files(book, folder, pdf, 1, "Lina"); ap = fab.pop("apercus")
P.finaliser(folder, book, pdf, 1, {"titre": book["title"], "pages": 21, "mineurs": [], "cout": 0}, ap)
db.update(oid, job_id=job, pdf=pdf.name, titre=book["title"], statut="expediee")
import fitz
ok(len(fitz.open(folder / "impression_interieur.pdf")) == 24, "intérieur d'impression : 24 pages (dédicace en page 2)")

st = c.get(f"/api/mon-livre/{pid}", headers=H).get_json()
ok(st["etat"]["etat"] == "pret" and len(st["pages"]) == 18 and st["credit"]["montant"] == 990, "Mon livre : prêt, 18 pages, crédit de 9,90 €")
ok(c.get(st["pdf"]).status_code == 200 and c.get(st["couverture"]).status_code == 200, "PDF et images servis avec le jeton")
ok(c.get(f"/api/mon-livre/{pid}/livre.pdf").status_code == 404, "PDF sans jeton : 404")

# correction d'une page : nouvelle version, images inchangées, v1 conservée
pages = list(st["pages"]); pages[2] = "Lina regarde la mer. Le bateau danse sur l'eau. « On y va ! » dit-elle en riant."
r = c.post(f"/api/mon-livre/{pid}/textes", json={"pages": pages}, headers=H).get_json()
st2 = c.get(f"/api/mon-livre/{pid}", headers=H).get_json()
ok(r.get("version") == 2 and st2["pages"][2] == pages[2] and st2["doubles"] == st["doubles"] and (folder / "livre.json").exists() and json.loads((folder / "livre.json").read_text())["pages"][2]["text"] != pages[2],
   "correction d'une page : version 2, images inchangées, version 1 conservée")
trop = list(pages); trop[0] = " ".join(["mot"] * 200)
ok(c.post(f"/api/mon-livre/{pid}/textes", json={"pages": trop}, headers=H).status_code == 400, "texte trop long pour la page : refusé")
r = c.post(f"/api/mon-livre/{pid}/correction-image", json={"double_page": 3, "demande": "Ses cheveux devraient être roux"}, headers=H).get_json()
ok(r["restantes"] == 1, "demande de retouche d'illustration enregistrée (limite affichée)")

# livre relié avec déduction
dv = c.post(f"/api/mon-livre/{pid}/devis-relie", json={"quantite": 1, "pays": "FR"}, headers=H).get_json()
ok(dv["deduction"] == 990 and dv["port"] == 790 and dv["total"] == 2790 - 990 + 790, "devis relié : 27,90 − 9,90 + 7,90 = 25,80 €")
dv3 = c.post(f"/api/mon-livre/{pid}/devis-relie", json={"quantite": 3, "pays": "FR"}, headers=H).get_json()
ok(dv3["deduction"] == 990 and dv3["total"] == 3 * 2790 - 990 + 990, "3 exemplaires : déduction appliquée une seule fois")
adr = {"nom": "Alex Test", "adresse1": "1 rue du Port", "code_postal": "75001", "ville": "Paris", "pays": "FR", "telephone": "0601020304"}
ok(c.post(f"/api/mon-livre/{pid}/commander-relie", json={"quantite": 1, "adresse": adr, "cgv": True}, headers=H).status_code == 400, "commande reliée sans validation du contenu : refusée")
r = c.post(f"/api/mon-livre/{pid}/commander-relie", json={"quantite": 2, "adresse": adr, "cgv": True, "valide": True}, headers=H).get_json()
nid = r["id"]; on = db.get(nid)
ok(on["montant"] == 2 * 2790 - 990 + 990 and on["quantite"] == 2 and on["job_id"].endswith("-p" + nid), "commande reliée : 2 exemplaires, montant serveur, fichier figé")
gel = A.OUT / on["job_id"]
import fabrication as F
ok(F.est_finalise(gel) and json.loads((gel / "livre.json").read_text())["pages"][2]["text"] == pages[2], "version figée = version relue (v2), finalisée")
# double usage de la déduction : seconde commande pendant que la première est réservée
r2 = c.post(f"/api/mon-livre/{pid}/commander-relie", json={"quantite": 1, "adresse": adr, "cgv": True, "valide": True}, headers=H).get_json()
ok(db.get(r2["id"])["montant"] == 2790 + 790, "deuxième commande simultanée : pas de seconde déduction")
B.confirm_paid(nid)
with db._db() as cx:
    cr = dict(cx.execute("select * from credits where projet_id=?", (pid,)).fetchone())
ok(cr["statut"] == "utilise" and cr["commande_papier"] == nid and db.get(nid)["statut"] == "a_verifier", "paiement relié confirmé : déduction consommée, commande à vérifier")
# correction APRÈS la commande reliée : le fichier envoyé ne change pas
pages[4] = "Une autre phrase toute neuve pour Lina, qui rit très fort sur le pont du bateau."
c.post(f"/api/mon-livre/{pid}/textes", json={"pages": pages}, headers=H)
ok(json.loads((gel / "livre.json").read_text())["pages"][4]["text"] != pages[4], "correction ultérieure : le fichier de la commande reliée ne change pas")
dv = c.post(f"/api/mon-livre/{pid}/devis-relie", json={"quantite": 1, "pays": "FR"}, headers=H).get_json()
ok(dv["deduction"] == 0 and dv["credit_deja_utilise"], "après usage : plus de déduction")
# session expirée : crédit libéré (autre projet)
ok(PC.credit_de(pid)["statut"] == "utilise", "crédit utilisé une seule fois")

# anciennes commandes et produits intacts
oc = c.post("/api/commandes", json={"prenom": "Léo", "age": "5", "theme": "La peur du noir", "univers": "La jungle",
     "commande": {"formule": "pack3", "email": "a@b.fr", "cgv": True, "adresse": adr}})
ok(oc.status_code == 200 and db.get(oc.get_json()["id"])["formule"] == "pack3", "ancien créateur : commande de pack inchangée")
ok(c.get(f"/mon-livre/{pid}").status_code == 404 and c.get(f"/mon-livre/{pid}?j={J}").status_code == 200, "page Mon livre protégée par le jeton")
ok(PC.admin_stats()["achats_numeriques"] >= 1, "statistiques : achats numériques comptés")

# retouche publiée par l'admin : nouvelle version avec UNE image changée
with db._db() as cx:
    corr = dict(cx.execute("select * from corrections where projet_id=?", (pid,)).fetchone())
fold, bk, vv = PC.livre_courant(PC.get(pid))
shutil.copy(fold / bk["spreads"][0], fold / f"spread-3-retouche-{corr['id']}.png")
with db._lock, db._db() as cx:
    cx.execute("update corrections set statut='a_valider', fichier=? where id=?", (f"spread-3-retouche-{corr['id']}.png", corr["id"]))
r = c.post(f"/admin/api/corrections/{corr['id']}/publier").get_json()
st3 = c.get(f"/api/mon-livre/{pid}", headers=H).get_json()
ok(r["version"] == vv + 1 and "retouche" in st3["doubles"][2] and st3["doubles"][1] == st["doubles"][1], "retouche publiée : seule la double page 3 change, nouvelle version")
ok("retouche" not in json.dumps(json.loads((gel / "livre.json").read_text())), "retouche : la commande reliée déjà passée garde son fichier")
# ---------------- tarif actuel : livre imprimé payé directement (ce que propose le configurateur), e-book en option
r = c.post("/api/projets", json={"donnees": d, "etape": "recap"}).get_json()
pid2, J2 = r["id"], r["jeton"]; H2 = {"X-Projet-Jeton": J2}
c.put(f"/api/projets/{pid2}", json={"donnees": d, "etape": "recap"}, headers=H2)
q = c.post(f"/api/projets/{pid2}/devis", json={"pays": "FR"}, headers=H2).get_json()
ok(q["total"] == paiement.total("livre", "FR") == 2790 + 790, f"devis livre imprimé : {q['total']} = 27,90 + 7,90 (tarif actuel)")
q = c.post(f"/api/projets/{pid2}/devis", json={"pays": "FR", "ebook": True}, headers=H2).get_json()
ok(q["total"] == paiement.total("livre", "FR", ebook=True), "devis avec e-book en option : même calcul que l'ancien créateur")
ok(c.post(f"/api/projets/{pid2}/acheter", json={"email": "t@exemple.fr", "cgv": True}, headers=H2).status_code == 400, "livre imprimé sans adresse : refusé")
ok(c.post(f"/api/projets/{pid2}/acheter", json={"email": "t@exemple.fr", "cgv": True, "adresse": adr, "ebook": True}, headers=H2).status_code == 400, "e-book en option sans renonciation : refusé")
r = c.post(f"/api/projets/{pid2}/acheter", json={"email": "t@exemple.fr", "cgv": True, "adresse": adr}, headers=H2).get_json()
o2 = db.get(r["id"])
ok(o2["formule"] == "livre" and o2["montant"] == paiement.total("livre", "FR") and o2["adresse"]["ville"] == adr["ville"], "commande livre imprimé : formule livre, montant et adresse")
started = []
orig = B.start_book
B.start_book = lambda b, auto=False, reprise=False: started.append(b)
B.confirm_paid(o2["id"])
B.start_book = orig
with db._db() as cx:
    n2 = cx.execute("select count(*) from credits where projet_id=?", (pid2,)).fetchone()[0]
ok(started == [o2["id"]] and n2 == 0 and PC.get(pid2)["statut"] == "generation", "paiement : fabrication lancée, aucune déduction créée")
st = c.get(f"/api/mon-livre/{pid2}", headers=H2).get_json()
ok(st["papier_inclus"] and not st["pdf_ouvert"], "Mon livre : livre imprimé inclus, pas de PDF sans l'option")
ok(c.post(f"/api/mon-livre/{pid2}/commander-relie", json={}, headers=H2).status_code == 409 and c.post(f"/api/mon-livre/{pid2}/textes", json={}, headers=H2).status_code == 409,
   "livre imprimé déjà commandé : pas de relié avec déduction ni de correction en libre-service")

print("\nÉCHECS :", FAILS if FAILS else "aucun"); sys.exit(1 if FAILS else 0)
