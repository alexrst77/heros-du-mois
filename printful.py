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
