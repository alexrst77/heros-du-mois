# -*- coding: utf-8 -*-
"""Aperçu RÉEL de la couverture, avant le paiement (demande d'Alex : « c'est pas grave si ça coûte en OpenAI, on limite à deux essais »).

- Mêmes personnages que la commande : portraits de référence (mis en cache : RÉUTILISÉS gratuitement si la personne commande),
  puis UNE illustration de couverture dans l'univers choisi, titrée comme le livre.
- Limites : APERCUS_PAR_VISITEUR (2) par visiteur et par 24 h, APERCUS_JOUR (40) pour tout le site, plafond 1 $ par aperçu,
  et le budget OpenAI du jour (BUDGET_OPENAI_JOUR) s'applique comme pour les commandes.
- Si la personne commande ensuite sans rien changer à ses personnages ni à l'univers du livre 1, cette illustration devient
  la couverture de son livre 1 (ce qu'elle a vu est ce qu'elle reçoit)."""
import os, json, time, threading, secrets, hashlib, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import commandes as db

DOSSIER = db.DATA / "apercus"; DOSSIER.mkdir(parents=True, exist_ok=True)
MAX_VISITEUR = int(os.getenv("APERCUS_PAR_VISITEUR", "2"))
MAX_JOUR = int(os.getenv("APERCUS_JOUR", "40"))
PLAFOND = 1.3                                   # jusqu'à 6 portraits + la couverture
FONTS = Path(__file__).parent / "fonts"

with db._db() as _c:
    _c.execute("create table if not exists apercus (id text primary key, visiteur text, cree real, statut text, etape text, erreur text, "
               "signature text, univers text, prenom text, cout real)")
    try:
        _c.execute("alter table apercus add column pct integer default 0")      # avancement affiché dans le rond
    except Exception:
        pass


def _ligne(pid):
    with db._db() as c:
        r = c.execute("select * from apercus where id=?", (pid,)).fetchone()
    return dict(r) if r else None


def _maj(pid, **kw):
    with db._lock, db._db() as c:
        c.execute(f"update apercus set {', '.join(k + '=?' for k in kw)} where id=?", (*kw.values(), pid))


def visiteur(req):
    ip = (req.headers.get("X-Forwarded-For") or req.remote_addr or "").split(",")[0].strip()
    return hashlib.sha256(("mhm-apercu:" + ip).encode()).hexdigest()[:24]


def restants(vis):
    with db._db() as c:
        n = c.execute("select count(*) from apercus where visiteur=? and cree>? and statut!='refuse'", (vis, time.time() - 86400)).fetchone()[0]
    return max(0, MAX_VISITEUR - n)


def signature(cfg, univers):
    """Ce qui doit rester identique pour que l'aperçu serve de couverture : les personnages (clés de portrait) et l'univers."""
    return hashlib.sha256(json.dumps([[c["id"], c["cle"]] for c in cfg["personnages"]] + [univers or ""]).encode()).hexdigest()[:32]


def fichier(pid):
    return DOSSIER / pid / "couverture.png"


def lancer(A, data, vis):
    """Vérifie, enregistre et lance un aperçu en tâche de fond. Renvoie (réponse, code HTTP).
    Réservé aux visiteurs connectés (compte client) : les 2 essais sont comptés par compte."""
    import generator as G, comptes
    cl = comptes.client_courant()
    if not cl:
        return {"erreur": "Connectez-vous (gratuit, sans mot de passe) pour voir sa couverture.", "connexion": True}, 401
    vis = "c:" + cl["id"]
    if restants(vis) <= 0:
        return {"erreur": f"Vous avez utilisé vos {MAX_VISITEUR} aperçus pour aujourd'hui : la couverture finale sera créée à la commande."}, 429
    with db._db() as c:
        if c.execute("select count(*) from apercus where cree>?", (time.time() - 86400,)).fetchone()[0] >= MAX_JOUR:
            return {"erreur": "Les aperçus sont très demandés aujourd'hui : réessayez demain, ou commandez directement."}, 429
    if not os.getenv("OPENAI_API_KEY"):
        return {"erreur": "Aperçu indisponible pour le moment."}, 503
    form, err = A.parse_book(data)
    if err:
        return {"erreur": err}, 400
    if not form.get("avatar"):
        return {"erreur": "Composez d'abord l'avatar."}, 400
    cfg = G.build_config(form)
    if cfg.get("problemes"):
        return {"erreur": "Complétez d'abord : " + " ; ".join(cfg["problemes"][:3])}, 400
    pid = secrets.token_hex(8)
    folder = DOSSIER / pid; folder.mkdir(parents=True)
    guides = A.save_avatar_pngs(data.get("avatar_png") or {}, folder)
    previews = A.save_previews(data.get("apercus") or {}, folder)
    refs = A.browser_refs(guides, previews)
    with db._lock, db._db() as c:
        c.execute("insert into apercus (id, visiteur, cree, statut, etape, erreur, signature, univers, prenom, cout) values (?,?,?,?,?,?,?,?,?,?)", (pid, vis, time.time(), "en_cours", "Préparation", None,
                                                                      signature(cfg, form.get("univers")), form.get("univers"), form["prenom"], 0))
    threading.Thread(target=_run, args=(pid, form, cfg, refs, folder), daemon=True).start()
    return {"id": pid, "restants": restants(vis)}, 200


def _run(pid, form, cfg, refs, folder):
    import generator as G, procede as P, budget as BU, boutique as B
    livre = f"apercu-{pid}"
    BU.PLAFONDS[livre] = PLAFOND
    jeton = BU.LIVRE.set(livre)
    try:
        G.check_budget()
        snap = P.snapshot(form, cfg)
        _maj(pid, etape="Portraits des personnages", pct=5)
        n, fait = max(1, len(cfg["personnages"])), [0]
        def avance(s):                                   # un portrait par personnage : de 5 à 60 %
            _maj(pid, etape=s, pct=5 + int(55 * fait[0] / n)); fait[0] += 1
        portraits, _ = P.references(snap, cfg, refs, folder, avance)
        ordre = sorted(cfg["personnages"], key=lambda c: (c["id"] != snap.get("protagoniste", "heros"), c["id"] != "heros",
                                                           {"doudou": 0, "enfant": 1, "animal": 2}.get(c["type"], 3)))
        ids = [c["id"] for c in ordre][:4]
        prenom = snap["prenom"]
        b = {"coverCharacterIds": ids, "characterBible": [],
             "coverBrief": f"{prenom.upper()} and companions at the heart of this world, at the very start of a wonderful adventure: a joyful, "
                           "wonder-filled moment full of warm magical light; every character clearly visible, recognisable and facing the viewer."}
        _maj(pid, etape="Illustration de la couverture", pct=62)
        crefs = P.refs_for(ids, portraits, None, folder, "couverture")
        prompt = P.cover_prompt(b, snap, crefs)
        (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
        P.image(prompt, crefs, fichier(pid), P.COVER_SIZE, G._m("q_main", G.IMAGE_QUALITY), "prompt.txt", etape="couverture (aperçu)")
        titrer(fichier(pid), folder / "apercu.jpg", prenom, form.get("univers"))
        _maj(pid, statut="pret", etape="Prête", pct=100, cout=round(BU.depense(livre)["total"], 4))
        B.log(f"aperçu {pid} ({prenom}) prêt : {BU.depense(livre)['total']:.2f} $")
    except Exception as e:
        msg = "Le budget d'aperçus du jour est atteint : réessayez demain." if "Budget" in type(e).__name__ or "budget" in str(e).lower() else \
              "L'aperçu n'a pas pu être créé. Votre essai ne compte pas : réessayez."
        _maj(pid, statut="refuse" if "budget" not in msg.lower() else "erreur", erreur=msg, etape="")
        try:
            B.log(f"aperçu {pid} impossible : {type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        BU.LIVRE.reset(jeton)


def _suite_univers(u):
    s = str(u or "").strip()
    if s.startswith("Mon "): s = "son " + s[4:]
    for a in ("La ", "Le ", "Les ", "L'"):
        if s.startswith(a): s = a.lower() + s[len(a):]
    return ("et " + s) if s else ""


def titrer(src, dst, prenom, univers):
    """Titre posé comme sur le livre (le titre exact s'écrit avec l'histoire, après la commande)."""
    im = Image.open(src).convert("RGB").resize((1024, 1024))
    voile = Image.new("L", im.size, 0); d = ImageDraw.Draw(voile)
    for y in range(420):
        d.line([(0, y), (1024, y)], fill=int(170 * (1 - y / 420) ** 1.6))
    im = Image.composite(Image.new("RGB", im.size, (20, 14, 48)), im, voile)
    d = ImageDraw.Draw(im)
    def font(nom, t):
        try:
            return ImageFont.truetype(str(FONTS / nom), t)
        except OSError:
            return ImageFont.load_default()
    def centre(txt, f, y, couleur, ombre=True):
        w = d.textlength(txt, font=f)
        if ombre:
            d.text(((1024 - w) / 2 + 2, y + 3), txt, font=f, fill=(15, 10, 35))
        d.text(((1024 - w) / 2, y), txt, font=f, fill=couleur)
    centre("M O N   H É R O S   D U   M O I S", font("DejaVuSans-Bold.ttf", 22), 54, (242, 213, 138), False)
    t = 118
    while d.textlength(prenom, font=font("YoungSerif-Regular.ttf", t)) > 880 and t > 60: t -= 6
    centre(prenom, font("YoungSerif-Regular.ttf", t), 96, (255, 246, 220))
    s = _suite_univers(univers)
    if s:
        t2 = 50
        while d.textlength(s, font=font("YoungSerif-Regular.ttf", t2)) > 900 and t2 > 28: t2 -= 3
        centre(s, font("YoungSerif-Regular.ttf", t2), 96 + t + 12, (255, 246, 220))
    im.save(dst, quality=88)


def etat(pid):
    r = _ligne(pid)
    if not r:
        return None
    return {"id": pid, "statut": r["statut"], "etape": r["etape"], "erreur": r["erreur"], "pct": r.get("pct") or 0,
            "image": f"/api/apercu/{pid}/image.jpg" if r["statut"] == "pret" else None}


def pour_commande(pid, cfg, univers):
    """Chemin de l'illustration si l'aperçu correspond exactement à la commande (mêmes personnages, même univers), sinon None."""
    r = _ligne(str(pid or "")[:32])
    if not r or r["statut"] != "pret" or not fichier(r["id"]).exists():
        return None
    return str(fichier(r["id"])) if r["signature"] == signature(cfg, univers) else None
