# -*- coding: utf-8 -*-
"""Plafond financier des appels API d'un livre : 3 USD maximum, contrôlé côté serveur.

- Les tarifs viennent de tarifs.json (copie de travail sur le volume : DATA_DIR/tarifs.json). Sans confirmation des tarifs
  ou sans calibrage des jetons d'image en entrée, toute fabrication est refusée (borne de coût impossible à établir).
- Avant de lancer un livre : borne haute du coût de TOUS les appels prévus (marge de sécurité comprise) ; refus si > plafond.
- Avant CHAQUE appel : réservation atomique de son coût maximal (SQLite BEGIN IMMEDIATE : sûr entre fils et entre processus),
  en comptant ce qui est déjà payé, ce qui est en cours et ce qui est incertain. Appel refusé s'il pouvait dépasser le plafond.
- Après l'appel : coût réel enregistré (usage renvoyé par l'API). Erreur sans facturation certaine (requête refusée avant
  traitement) : réservation annulée. Erreur incertaine (coupure réseau, délai dépassé, erreur serveur) : la réservation
  RESTE comptée, le livre s'arrête en « à relire » ; la même demande n'est jamais renvoyée automatiquement.
- Aucune relance automatique : client OpenAI avec max_retries=0."""
import os, json, math, time, sqlite3, threading, contextvars, base64
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR") or ROOT / "data"); DATA.mkdir(parents=True, exist_ok=True)
PLAFOND = min(3.0, float(os.getenv("BUDGET_LIVRE_USD", "3")))     # jamais au-dessus de 3 USD, même par variable d'environnement
MARGE = 1.15                                                       # marge de sécurité sur la borne haute du livre
DB = Path(os.getenv("DATA_DIR") or ROOT / "data") / "commandes.sqlite"
LIVRE = contextvars.ContextVar("livre_budget", default=None)
PLAFONDS = {}                    # plafond propre à certains produits (calendrier : 13 images), par identifiant de commande


def plafond_de(livre):
    return PLAFONDS.get(livre, PLAFOND)        # identifiant stable du livre en cours (commande)
_lock = threading.Lock()


class BudgetLivreError(RuntimeError):
    """Plafond du livre : appel ou lancement refusé (aucune dépense faite)."""


class AppelIncertain(RuntimeError):
    """Résultat inconnu (coupure après envoi) : la dépense reste réservée, rien n'est renvoyé automatiquement."""


# ---------------------------------------------------------------- tarifs
def _fichier_tarifs():
    vol = DATA / "tarifs.json"
    if not vol.exists():
        vol.write_text((ROOT / "tarifs.json").read_text(encoding="utf-8"), encoding="utf-8")
    return vol


def tarifs():
    return json.loads(_fichier_tarifs().read_text(encoding="utf-8"))


def enregistrer_tarifs(t):
    _fichier_tarifs().write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")


def etat_tarifs():
    t = tarifs(); im = t["modeles"].get("gpt-image-2", {})
    manque = []
    if not t.get("confirme_le"):
        manque.append("tarifs à confirmer sur platform.openai.com/docs/pricing (bouton dans l'admin)")
    if not im.get("jetons_image_entree_max"):
        manque.append("jetons d'une image de référence à calibrer (un appel de calibrage, bouton dans l'admin)")
    return {"ok": not manque, "manque": manque, "verifie_le": t.get("verifie_le"), "confirme_le": t.get("confirme_le"),
            "jetons_image_entree_max": im.get("jetons_image_entree_max"), "plafond": PLAFOND}


def _modele(m):
    t = tarifs()["modeles"]
    for k in sorted(t, key=len, reverse=True):
        if m == k or m.startswith(k + "-"):
            return t[k]
    raise BudgetLivreError(f"Tarif inconnu pour le modèle « {m} » : fabrication bloquée")


# ---------------------------------------------------------------- jetons
def jetons_sortie_image(size, quality, m="gpt-image-2"):
    """Jetons de sortie de gpt-image-2 (formule vérifiée contre les prix officiels par image)."""
    if _modele(m).get("sortie") != "formule_gpt_image_2":
        raise BudgetLivreError(f"Pas de formule de sortie connue pour {m}")
    q = {"low": 16, "medium": 48, "high": 96}.get(quality)
    if q is None:
        raise BudgetLivreError(f"Qualité « {quality} » hors du calcul prévu")
    w, h = (int(x) for x in size.split("x"))
    s = math.floor(q * min(w, h) / max(w, h) + 0.5)
    return math.ceil(q * s * (2_000_000 + w * h) / 4_000_000)


def jetons_texte_max(*textes):
    """Borne haute des jetons d'un texte : jamais plus d'un jeton par octet UTF-8."""
    return sum(len(str(t).encode("utf-8")) for t in textes) + 16


def jetons_vision_gpt41(w, h):
    """Image envoyée à gpt-4.1 (detail=high) : tuiles de 512 px, 85 + 170 par tuile."""
    s = min(1.0, 2048 / max(w, h)); w, h = w * s, h * s
    s = min(1.0, 768 / min(w, h)); w, h = w * s, h * s
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def cout_image_max(prompt, n_refs, size, quality, m):
    t = _modele(m)
    ref = t.get("jetons_image_entree_max")
    if n_refs and not ref:
        raise BudgetLivreError("Jetons des images de référence non calibrés : fabrication bloquée")
    return (jetons_texte_max(prompt) * t["texte_entree"] + n_refs * (ref or 0) * t["image_entree"]
            + jetons_sortie_image(size, quality, m) * t["sortie_image"]) / 1e6


def cout_chat_max(textes, max_tokens, m, images=()):
    t = _modele(m)
    vis = sum(jetons_vision_gpt41(w, h) for w, h in images)
    return ((jetons_texte_max(*textes) + vis) * t["texte_entree"] + max_tokens * t["sortie"]) / 1e6


def cout_reel(kind, m, usage):
    """Coût réel à partir de l'usage renvoyé par l'API (mêmes tarifs que la borne)."""
    t = _modele(m)
    g = lambda o, k: (o.get(k) if isinstance(o, dict) else getattr(o, k, None)) or 0
    if usage is None:
        return None
    if kind == "image":
        det = g(usage, "input_tokens_details") or {}
        txt, img = g(det, "text_tokens"), g(det, "image_tokens")
        if not (txt or img): txt = g(usage, "input_tokens")
        return (txt * t["texte_entree"] + img * t["image_entree"] + g(usage, "output_tokens") * t["sortie_image"]) / 1e6
    return (g(usage, "prompt_tokens") * t["texte_entree"] + g(usage, "completion_tokens") * t["sortie"]) / 1e6


# ---------------------------------------------------------------- registre (SQLite, atomique entre processus)
def _db():
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("""create table if not exists appels_api (id integer primary key autoincrement, livre text, etape text, modele text,
                 statut text, reserve real, reel real, cree real, maj real, detail text)""")
    return c


def depense(livre):
    """{'regle': payé, 'reserve': en cours, 'incertain': réservé faute de résultat certain, 'total': ce qui compte pour le plafond}."""
    with _db() as c:
        r = {s: 0.0 for s in ("regle", "reserve", "incertain")}
        for row in c.execute("select statut, sum(reserve) r, sum(reel) e from appels_api where livre=? group by statut", (livre,)):
            if row["statut"] == "regle": r["regle"] = row["e"] or 0
            elif row["statut"] in r: r[row["statut"]] = row["r"] or 0
        r["total"] = r["regle"] + r["reserve"] + r["incertain"]
        return r


def appels(livre):
    with _db() as c:
        return [dict(x) for x in c.execute("select * from appels_api where livre=? order by id", (livre,))]


def reserver(livre, etape, modele, maximum, detail=None):
    if not livre:
        raise BudgetLivreError("Appel API hors d'un livre identifié : refusé")
    if maximum is None or maximum <= 0:
        raise BudgetLivreError("Coût maximal de l'appel impossible à établir : refusé")
    with _lock:
        c = _db()
        try:
            c.execute("begin immediate")
            deja = sum((row["reel"] if row["statut"] == "regle" else row["reserve"]) or 0 for row in
                       c.execute("select statut, reserve, reel from appels_api where livre=? and statut in ('regle','reserve','incertain')", (livre,)))
            if deja + maximum > plafond_de(livre) + 1e-9:
                c.execute("rollback")
                raise BudgetLivreError(f"Plafond du livre : {deja:.3f} $ engagés + {maximum:.3f} $ pour « {etape} » dépasseraient {plafond_de(livre):.2f} $")
            cur = c.execute("insert into appels_api (livre, etape, modele, statut, reserve, cree, maj, detail) values (?,?,?,?,?,?,?,?)",
                            (livre, etape, modele, "reserve", maximum, time.time(), time.time(), json.dumps(detail or {}, ensure_ascii=False)))
            c.execute("commit")
            return cur.lastrowid
        except sqlite3.Error:
            try: c.execute("rollback")
            except sqlite3.Error: pass
            raise
        finally:
            c.close()


def _fin(aid, statut, reel=None, info=None):
    with _lock, _db() as c:
        c.execute("update appels_api set statut=?, reel=?, maj=?, detail=json_set(coalesce(detail,'{}'), '$.fin', ?) where id=?",
                  (statut, reel, time.time(), json.dumps(info or {}, ensure_ascii=False), aid))


def certain_sans_facturation(e):
    """Erreurs renvoyées AVANT traitement (requête invalide, clé, quota, débit) : rien n'a été généré, donc rien facturé."""
    n = type(e).__name__
    st = getattr(e, "status_code", None)
    return n in ("BadRequestError", "AuthenticationError", "PermissionDeniedError", "RateLimitError", "NotFoundError",
                 "UnprocessableEntityError", "BudgetLivreError") or (st is not None and 400 <= st < 500)


def appel(etape, modele, maximum, fn, kind, detail=None):
    """Exécute UN appel facturable dans le budget du livre courant. Jamais de seconde tentative."""
    livre = LIVRE.get()
    aid = reserver(livre, etape, modele, maximum, detail)
    try:
        r = fn()
    except Exception as e:
        if certain_sans_facturation(e):
            _fin(aid, "annule", 0.0, {"erreur": str(e)[:300]})
            raise
        _fin(aid, "incertain", None, {"erreur": f"{type(e).__name__}: {str(e)[:300]}"})
        raise AppelIncertain(f"« {etape} » : résultat incertain ({type(e).__name__}). La dépense reste réservée et la demande "
                             "n'est pas renvoyée : vérifie l'usage sur platform.openai.com, puis relance à la main si besoin.") from e
    reel = cout_reel(kind, modele, getattr(r, "usage", None))
    if reel is None:                      # usage absent : on garde le maximum réservé comme coût
        reel = maximum
    _fin(aid, "regle", reel, {"usage": _usage_dict(getattr(r, "usage", None))})
    return r


def _usage_dict(u):
    if u is None: return None
    try: return u.model_dump()
    except Exception:
        try: return dict(u)
        except Exception: return str(u)


def orphelines_vers_incertain(livre):
    """Au redémarrage : une réservation restée « en cours » sans processus vivant = résultat inconnu -> incertaine (reste comptée)."""
    with _lock, _db() as c:
        n = c.execute("update appels_api set statut='incertain', maj=?, detail=json_set(coalesce(detail,'{}'), '$.fin', ?) "
                      "where livre=? and statut='reserve'", (time.time(), json.dumps({"erreur": "processus interrompu pendant l'appel"}), livre)).rowcount
    return n


def appel_get(aid):
    with _db() as c:
        r = c.execute("select * from appels_api where id=?", (aid,)).fetchone()
        return dict(r) if r else None


def regler_incertain(aid, reel):
    """Admin : coût réel constaté sur le tableau de bord OpenAI pour un appel incertain."""
    _fin(aid, "regle", float(reel), {"regle_a_la_main": True})


# ---------------------------------------------------------------- borne haute d'un livre (avant tout appel)
def borne_livre(plan):
    """plan : liste de {'type': 'image'|'chat', ...}. Renvoie (détail, total avec marge). Lève si non calculable."""
    lignes = []
    for p in plan:
        if p["type"] == "image":
            c = cout_image_max(p["prompt_max"], p["refs"], p["size"], p["quality"], p["modele"])
        else:
            c = cout_chat_max(p["textes"], p["max_tokens"], p["modele"], p.get("images", ()))
        lignes.append({"etape": p["etape"], "max_usd": round(c, 4)})
    brut = sum(x["max_usd"] for x in lignes)
    return lignes, round(brut * MARGE, 4)


def verifier_lancement(plan, livre):
    st = etat_tarifs()
    if not st["ok"]:
        raise BudgetLivreError("Fabrication bloquée : " + " ; ".join(st["manque"]))
    lignes, total = borne_livre(plan)
    deja = depense(livre)["total"]
    if deja + total > plafond_de(livre):
        raise BudgetLivreError(f"Borne haute du livre {total:.2f} $ (marge {int((MARGE - 1) * 100)} % comprise)"
                               + (f" + {deja:.2f} $ déjà engagés" if deja else "") + f" > plafond {plafond_de(livre):.2f} $ : fabrication refusée")
    return lignes, total


# ---------------------------------------------------------------- références : taille maîtrisée (borne de jetons valable)
def normaliser_ref(src, dst_dir, cote=1024):
    """Copie d'une image de référence ramenée à `cote` px maximum (la calibration des jetons vaut pour cette taille)."""
    src = Path(src); dst = Path(dst_dir) / f"ref_{src.stem}_{cote}.png"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    im = Image.open(src).convert("RGB")
    im.thumbnail((cote, cote), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.stem}.{os.getpid()}.{threading.get_ident()}.png")
    im.save(tmp); os.replace(tmp, dst)                # écriture atomique : plusieurs fils peuvent préparer la même référence
    return dst
