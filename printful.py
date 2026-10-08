# -*- coding: utf-8 -*-
"""Client de l'API Printful (gourdes, sacs à dos, tasses… avec le héros dessus).
Réglage Railway : PRINTFUL_API_KEY (jeton privé limité à la boutique « site »).
Aucune commande n'est jamais confirmée sans décision explicite : les tests créent des brouillons (rien fabriqué, rien facturé)."""
import os, json, time, urllib.request, urllib.error

BASE = "https://api.printful.com"
MOTS = ["bottle", "tumbler", "backpack", "kid", "youth", "toddler", "baby", "mug", "puzzle", "pillow", "blanket", "lunch", "tote", "sticker", "poster"]
_cache = {"catalogue": None, "t": 0}


class PrintfulError(Exception):
    pass


def configured():
    return bool(os.getenv("PRINTFUL_API_KEY"))


def _http(method, path, data=None):
    if not configured():
        raise PrintfulError("PRINTFUL_API_KEY absent dans Railway")
    h = {"Authorization": "Bearer " + os.getenv("PRINTFUL_API_KEY", ""), "Accept": "application/json",
         "User-Agent": "MonHerosDuMois/1.0"}
    body = None
    if data is not None:
        body = json.dumps(data).encode(); h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}").get("result")
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            j = json.loads(txt); msg = (j.get("error") or {}).get("message") or j.get("result") or txt
        except ValueError:
            msg = txt
        raise PrintfulError(f"Printful {e.code} : {str(msg)[:300]}")
    except urllib.error.URLError as e:
        raise PrintfulError(f"Printful injoignable : {e.reason}")


def etat():
    """Connexion : nom de la boutique liée au jeton."""
    try:
        s = _http("GET", "/stores")
        s = s[0] if isinstance(s, list) and s else (s or {})
    except PrintfulError:
        s = _http("GET", "/store")
    return {"ok": True, "boutique": s.get("name"), "id": s.get("id"), "type": s.get("type"), "devise": s.get("currency")}


def catalogue():
    if not _cache["catalogue"] or time.time() - _cache["t"] > 6 * 3600:
        _cache["catalogue"] = _http("GET", "/products") or []; _cache["t"] = time.time()
    return _cache["catalogue"]


def chercher(mots=None):
    mots = [m.strip().lower() for m in (mots or MOTS) if m.strip()]
    res = []
    for p in catalogue():
        t = f"{p.get('title', '')} {p.get('type_name', '')} {p.get('model', '')}".lower()
        if p.get("is_discontinued"):
            continue
        if any(m in t for m in mots):
            res.append({"id": p["id"], "titre": p.get("title"), "type": p.get("type_name"), "marque": p.get("brand"),
                        "image": p.get("image"), "variantes": p.get("variant_count"), "devise": p.get("currency"),
                        "techniques": [x.get("display_name") for x in p.get("techniques") or []]})
    return res


def produit(pid):
    r = _http("GET", f"/products/{int(pid)}")
    p, vs = r.get("product") or {}, r.get("variants") or []
    eu = [v for v in vs if v.get("in_stock") and (v.get("availability_regions") or {}).get("EU") not in (None, "discontinued")] or vs
    prix = sorted(float(v.get("price") or 0) for v in eu if v.get("price"))
    return {"id": p.get("id"), "titre": p.get("title"), "description": (p.get("description") or "")[:600], "devise": p.get("currency"),
            "prix_min": prix[0] if prix else None, "prix_max": prix[-1] if prix else None, "en_europe": len(eu) != len(vs) or any((v.get("availability_regions") or {}).get("EU") for v in vs),
            "zones": [{"id": f.get("id"), "type": f.get("type"), "titre": f.get("title")} for f in p.get("files") or []],
            "variantes": [{"id": v["id"], "nom": v.get("name"), "taille": v.get("size"), "couleur": v.get("color"), "prix": v.get("price")} for v in eu[:30]]}


def port(variant_id, pays="FR", cp="77000", devise="EUR"):
    return _http("POST", "/shipping/rates", {"recipient": {"country_code": pays, "zip": cp}, "items": [{"variant_id": int(variant_id), "quantity": 1}],
                                             "currency": devise, "locale": "fr_FR"})


# ---------------------------------------------------------------- fichiers d'impression et commandes
PLACEMENTS_PRIO = ("front", "default", "front_large", "front_dtf", "embroidery_front")
DEFAUTS = {848: {"placement": "default", "width": 2550, "height": 1350}, 407: {"placement": "default", "width": 2550, "height": 1050},
           389: {"placement": "front", "width": 2850, "height": 3450}}          # sans clé (essais en local) : formats indicatifs


def specs(pid, variante=None):
    """Variante, emplacement principal et dimensions EXACTES du fichier d'impression (en pixels), mis en cache."""
    import budget
    cache = budget.DATA / f"printful_specs_{int(pid)}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        d = json.loads(cache.read_text(encoding="utf-8"))
    else:
        info = produit(pid)
        pf = _http("GET", f"/mockup-generator/printfiles/{int(pid)}")
        d = {"produit": int(pid), "titre": info["titre"], "variantes": info["variantes"], "placements": pf.get("available_placements") or {},
             "printfiles": {str(x["printfile_id"]): x for x in pf.get("printfiles") or []},
             "par_variante": {str(v["variant_id"]): v.get("placements") or {} for v in pf.get("variant_printfiles") or []}}
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    vid = str(variante or (d["variantes"][0]["id"] if d["variantes"] else ""))
    pls = d["par_variante"].get(vid) or next(iter(d["par_variante"].values()), {})
    principal = next((p for p in PLACEMENTS_PRIO if p in pls), next((p for p in pls if "mockup" not in p and "inside" not in p and "label" not in p), None))
    if not principal:
        raise PrintfulError(f"produit {pid} : aucun emplacement d'impression trouvé")
    f = d["printfiles"][str(pls[principal])]
    autres = []
    if "all-over" in (d.get("titre") or "").lower():      # tout imprimé : les autres panneaux reçoivent une couleur unie assortie
        autres = [{"placement": p, "width": d["printfiles"][str(i)]["width"], "height": d["printfiles"][str(i)]["height"]}
                  for p, i in pls.items() if p != principal and "mockup" not in p and "label" not in p]
    return {"produit": int(pid), "titre": d.get("titre"), "variante": int(vid) if vid else None, "placement": principal,
            "width": int(f["width"]), "height": int(f["height"]), "dpi": f.get("dpi"), "autres": autres}


def specs_ou_defaut(pid, variante=None):
    if configured():
        return specs(pid, variante)
    d = DEFAUTS.get(int(pid), {"placement": "default", "width": 2400, "height": 2400})
    return {"produit": int(pid), "titre": f"produit {pid}", "variante": variante, "autres": [], "dpi": 150, **d}


def creer_commande(external_id, adresse, email, items, confirmer=False):
    """UNE commande Printful (un colis) pour tous les objets d'une commande du site.
    confirmer=False : brouillon (rien fabriqué ni facturé tant que tu ne confirmes pas chez Printful ou dans l'admin)."""
    a = adresse or {}
    r = {"name": a.get("nom"), "address1": a.get("adresse1"), "address2": a.get("adresse2") or None, "city": a.get("ville"),
         "zip": a.get("code_postal"), "country_code": (a.get("pays") or "FR").upper(), "phone": a.get("telephone"), "email": email}
    data = {"external_id": str(external_id)[:32], "shipping": "STANDARD", "recipient": r, "items": items}
    return _http("POST", "/orders" + ("?confirm=true" if confirmer else ""), data)


def confirmer_commande(order_id):
    return _http("POST", f"/orders/{int(order_id)}/confirm")


def commande(order_id):
    o = _http("GET", f"/orders/{int(order_id)}") or {}
    suivi = [s.get("tracking_url") for s in o.get("shipments") or [] if s.get("tracking_url")]
    return {"statut": o.get("status"), "suivi": suivi, "cout": (o.get("costs") or {}).get("total"), "devise": (o.get("costs") or {}).get("currency")}


def maquettes(pid, variante, files, attente=90):
    """Photos du produit fini générées par Printful (outil de maquette : aucune commande). files = [(emplacement, url, w, h)]."""
    data = {"variant_ids": [int(variante)], "format": "jpg",
            "files": [{"placement": p, "image_url": u, "position": {"area_width": w, "area_height": h, "width": w, "height": h, "top": 0, "left": 0}}
                      for p, u, w, h in files]}
    t = _http("POST", f"/mockup-generator/create-task/{int(pid)}", data) or {}
    key, t0 = t.get("task_key"), time.time()
    while key and time.time() - t0 < attente:
        time.sleep(4)
        r = _http("GET", f"/mockup-generator/task?task_key={key}") or {}
        if r.get("status") == "completed":
            out = []
            for m in r.get("mockups") or []:
                out.append({"titre": m.get("placement"), "url": m.get("mockup_url")})
                out += [{"titre": x.get("title"), "url": x.get("url")} for x in m.get("extra") or []]
            return [x for x in out if x["url"]]
        if r.get("status") == "failed":
            raise PrintfulError("maquette Printful : " + str(r.get("error") or "échec"))
    raise PrintfulError("Printful prépare encore la maquette : réessaie dans une minute")
