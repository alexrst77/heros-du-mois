# -*- coding: utf-8 -*-
"""Client de l'API d'impression Lulu (bac à sable par défaut : aucune vraie impression).
Réglages .env : LULU_CLIENT_KEY, LULU_CLIENT_SECRET, LULU_ENV=sandbox|production, LULU_POD_PACKAGE, LULU_SHIPPING."""
import os, json, time, base64, urllib.request, urllib.parse, urllib.error

POD_PACKAGE = os.getenv("LULU_POD_PACKAGE", "0850X0850FCSTDCW080CW444GXX")  # 8,5x8,5 po, couleur standard, couverture rigide, papier épais brillant
SHIPPING = os.getenv("LULU_SHIPPING", "MAIL")
_token = {"value": None, "exp": 0}


class LuluError(Exception):
    pass


def env():
    return "production" if os.getenv("LULU_ENV", "sandbox").lower() == "production" else "sandbox"


def base():
    return "https://api.lulu.com" if env() == "production" else "https://api.sandbox.lulu.com"


def configured():
    return bool(os.getenv("LULU_CLIENT_KEY") and os.getenv("LULU_CLIENT_SECRET"))


def _http(method, url, data=None, headers=None, form=False):
    body = None
    headers = dict(headers or {})
    # Cloudflare (devant l'API Lulu) refuse l'identité par défaut de Python (« error code: 1010 ») : on se présente
    headers.setdefault("User-Agent", "MonHerosDuMois/1.0 (+https://heros-du-mois-production.up.railway.app)")
    headers.setdefault("Accept", "application/json")
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        raise LuluError(f"Lulu {e.code} sur {url.split('.com')[-1]} : {e.read().decode(errors='replace')[:600]}")
    except urllib.error.URLError as e:
        raise LuluError(f"Lulu injoignable : {e.reason}")


def token():
    if not configured():
        raise LuluError("Clés Lulu absentes : ajoute LULU_CLIENT_KEY et LULU_CLIENT_SECRET dans .env (compte sur developers.lulu.com).")
    if _token["value"] and _token["exp"] > time.time() + 60:
        return _token["value"]
    auth = base64.b64encode(f"{os.getenv('LULU_CLIENT_KEY')}:{os.getenv('LULU_CLIENT_SECRET')}".encode()).decode()
    r = _http("POST", base() + "/auth/realms/glasstree/protocol/openid-connect/token",
              {"grant_type": "client_credentials"}, {"Authorization": "Basic " + auth}, form=True)
    _token.update(value=r["access_token"], exp=time.time() + int(r.get("expires_in", 3000)))
    return _token["value"]


def api(method, path, data=None):
    return _http(method, base() + path, data, {"Authorization": "Bearer " + token(), "Cache-Control": "no-cache"})


def address(a, email):
    """Adresse du formulaire de commande -> format Lulu."""
    out = {"name": a["nom"], "street1": a["adresse1"], "city": a["ville"], "postcode": a["code_postal"],
           "country_code": a.get("pays", "FR"), "phone_number": a["telephone"], "email": email}
    if a.get("adresse2"):
        out["street2"] = a["adresse2"]
    return out


def cover_dimensions(pages, pod=None):
    """Dimensions exactes du fichier couverture (en points, fond perdu compris)."""
    r = api("POST", "/cover-dimensions/", {"pod_package_id": pod or POD_PACKAGE, "interior_page_count": pages, "unit": "pt"})
    k = 72.0 if str(r.get("unit", "pt")).lower() in ("inch", "in") else 1.0
    return float(r["width"]) * k, float(r["height"]) * k


def cost(pages, addr, email, pod=None, shipping=None, quantite=1):
    r = api("POST", "/print-job-cost-calculations/", {
        "line_items": [{"page_count": pages, "pod_package_id": pod or POD_PACKAGE, "quantity": quantite}],
        "shipping_address": address(addr, email), "shipping_option": shipping or SHIPPING})
    li = (r.get("line_item_costs") or [{}])[0]
    return {"total_ttc": r.get("total_cost_incl_tax"), "total_ht": r.get("total_cost_excl_tax"), "devise": r.get("currency"),
            "impression_ttc": li.get("total_cost_incl_tax"), "port_ttc": (r.get("shipping_cost") or {}).get("total_cost_incl_tax"),
            "frais_ttc": (r.get("fulfillment_cost") or {}).get("total_cost_incl_tax"), "livraison": shipping or SHIPPING, "quantite": quantite}


VARIANTES = [   # (code POD, description en clair) : même format carré 21,6 cm, 24 pages, couleur
    ("0850X0850FCSTDCW080CW444GXX", "Rigide · couleur standard · papier épais brillant (actuel)"),
    ("0850X0850FCPRECW080CW444GXX", "Rigide · couleur premium · papier épais brillant"),
    ("0850X0850FCSTDCW060UW444MXX", "Rigide · couleur standard · papier fin mat"),
    ("0850X0850FCPREPB080CW444GXX", "Souple · couleur premium · papier épais brillant"),
    ("0850X0850FCSTDPB080CW444GXX", "Souple · couleur standard · papier épais brillant"),
    ("0850X0850FCSTDSS080CW444GXX", "Agrafé · couleur standard · papier épais brillant"),
]


def comparer(pages, addr, email):
    """Devis Lulu (aucune commande) pour plusieurs fabrications et deux modes de livraison : impression et port séparés."""
    out = []
    for pod, label in VARIANTES:
        for ship in ("MAIL", "PRIORITY_MAIL"):
            try:
                r = api("POST", "/print-job-cost-calculations/", {
                    "line_items": [{"page_count": pages, "pod_package_id": pod, "quantity": 1}],
                    "shipping_address": address(addr, email), "shipping_option": ship})
                li = (r.get("line_item_costs") or [{}])[0]
                sc = r.get("shipping_cost") or {}
                fc = r.get("fulfillment_cost") or {}
                out.append({"pod": pod, "fabrication": label, "livraison": ship, "devise": r.get("currency"),
                            "impression_ttc": li.get("total_cost_incl_tax"), "port_ttc": sc.get("total_cost_incl_tax"),
                            "frais_ttc": fc.get("total_cost_incl_tax"), "total_ttc": r.get("total_cost_incl_tax")})
            except Exception as e:
                out.append({"pod": pod, "fabrication": label, "livraison": ship, "erreur": str(e)[:160]})
    for q in (3, 6, 12):                          # colis d'un pack : prix PAR livre, fabrication actuelle
        pod, label = VARIANTES[0]
        try:
            r = api("POST", "/print-job-cost-calculations/", {
                "line_items": [{"page_count": pages, "pod_package_id": pod, "quantity": q}],
                "shipping_address": address(addr, email), "shipping_option": "MAIL"})
            li = (r.get("line_item_costs") or [{}])[0]; sc = r.get("shipping_cost") or {}; fc = r.get("fulfillment_cost") or {}
            par = lambda v: None if v in (None, "") else round(float(v) / q, 2)
            out.append({"pod": pod, "fabrication": f"Pack de {q} (actuel) — prix par livre", "livraison": "MAIL", "devise": r.get("currency"),
                        "impression_ttc": par(li.get("total_cost_incl_tax")), "port_ttc": par(sc.get("total_cost_incl_tax")),
                        "frais_ttc": par(fc.get("total_cost_incl_tax")), "total_ttc": par(r.get("total_cost_incl_tax")), "lot": q,
                        "port_colis_ttc": sc.get("total_cost_incl_tax")})
        except Exception as e:
            out.append({"pod": pod, "fabrication": f"Pack de {q}", "livraison": "MAIL", "erreur": str(e)[:160]})
    return out


def create_print_job(order_id, items, addr, email, pod=None, shipping=None):
    """UN travail d'impression pour tout le pack (un seul colis). items : [{id, titre, interieur, couverture}]."""
    pod = pod or POD_PACKAGE
    return api("POST", "/print-jobs/", {
        "contact_email": os.getenv("LULU_CONTACT_EMAIL") or email,
        "external_id": order_id,
        "line_items": [{"external_id": it["id"], "title": it["titre"][:250], "quantity": 1, "pod_package_id": pod,
                        "printable_normalization": {"pod_package_id": pod, "cover": {"source_url": it["couverture"]},
                                                    "interior": {"source_url": it["interieur"]}}} for it in items],
        "shipping_address": address(addr, email),
        "shipping_level": shipping or SHIPPING})


def status(job_id):
    r = api("GET", f"/print-jobs/{job_id}/")
    st = r.get("status") or {}
    suivi = [u for li in (st.get("line_item_statuses") or r.get("line_items") or [])
             for u in ((li.get("messages") or {}).get("tracking_urls") or li.get("tracking_urls") or [])]
    return {"statut": st.get("name"), "message": st.get("message"), "suivi": suivi,
            "cout": (r.get("costs") or {}).get("total_cost_incl_tax")}
