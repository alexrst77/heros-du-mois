# -*- coding: utf-8 -*-
"""Paiement Stripe Checkout (API REST, sans dépendance). Réglages .env : STRIPE_SECRET_KEY (sk_test_… pour les essais),
STRIPE_WEBHOOK_SECRET (whsec_…). Sans clé : paiement simulé (mode test local)."""
import os, json, hmac, hashlib, time, urllib.request, urllib.parse, urllib.error

FORMULES = {      # tout se paie en une fois ; les livres d'une commande partent ensemble, dans un seul colis
    "livre":  {"nom": "1 livre personnalisé", "livres": 1, "prix_livre": int(os.getenv("PRIX_LIVRE_1", "2790")), "mode": "payment"},
    "pack3":  {"nom": "3 livres personnalisés", "livres": 3, "prix_livre": int(os.getenv("PRIX_LIVRE_3", "2590")), "mode": "payment"},
    "pack6":  {"nom": "6 livres personnalisés", "livres": 6, "prix_livre": int(os.getenv("PRIX_LIVRE_6", "2490")), "mode": "payment"},
    "pack12": {"nom": "12 livres personnalisés", "livres": 12, "prix_livre": int(os.getenv("PRIX_LIVRE_12", "2290")), "mode": "payment"},
    "fetes":  {"nom": "Les 6 livres de fête", "livres": 6, "prix_livre": int(os.getenv("PRIX_LIVRE_6", "2490")), "mode": "payment"},
}
for _f in FORMULES.values():
    _f["prix"] = _f["livres"] * _f["prix_livre"]          # prix des livres, hors livraison

# Livraison (centimes), un seul colis par commande. Offerte dès 6 livres en France ; supplément pour les autres pays.
PORT_FR = {1: int(os.getenv("PORT_1", "790")), 3: int(os.getenv("PORT_3", "990"))}
SUPPLEMENT_PAYS = {"FR": 0, "BE": int(os.getenv("PORT_SUPPL_UE", "400")), "LU": int(os.getenv("PORT_SUPPL_UE", "400")),
                   "MC": int(os.getenv("PORT_SUPPL_UE", "400")), "CH": int(os.getenv("PORT_SUPPL_CH", "900"))}


def frais_port(formule, pays="FR"):
    n = FORMULES[formule]["livres"]
    base = 0 if n >= 6 else PORT_FR.get(n, PORT_FR[3])
    return base + SUPPLEMENT_PAYS.get((pays or "FR").upper(), SUPPLEMENT_PAYS["BE"])


def total(formule, pays="FR"):
    return FORMULES[formule]["prix"] + frais_port(formule, pays)


def grille():
    """Prix affichés par le site (en centimes) : une seule source pour la page d'accueil et la commande."""
    return {"formules": {k: {"nom": f["nom"], "livres": f["livres"], "prix_livre": f["prix_livre"], "prix": f["prix"]} for k, f in FORMULES.items()},
            "port_fr": {str(k): v for k, v in PORT_FR.items()}, "port_offert_des": 6, "supplement_pays": SUPPLEMENT_PAYS}


class StripeError(Exception):
    pass


def configured():
    return os.getenv("STRIPE_SECRET_KEY", "").startswith(("sk_", "rk_"))


def live():
    return os.getenv("STRIPE_SECRET_KEY", "").startswith(("sk_live", "rk_live"))


def _flat(d, prefix=""):
    out = []
    for k, v in d.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out += _flat(v, key)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out += _flat(x, f"{key}[{i}]") if isinstance(x, dict) else [(f"{key}[{i}]", str(x))]
        elif v is not None:
            out.append((key, "true" if v is True else "false" if v is False else str(v)))
    return out


def _api(method, path, data=None):
    body = urllib.parse.urlencode(_flat(data)).encode() if data else None
    req = urllib.request.Request("https://api.stripe.com/v1" + path, data=body, method=method,
                                 headers={"Authorization": "Bearer " + os.getenv("STRIPE_SECRET_KEY", "")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode())["error"]["message"]
        except Exception:
            msg = str(e)
        raise StripeError(f"Stripe : {msg}")


def checkout(order_id, formule, email, base_url, pays="FR"):
    """Paiement unique : les livres (quantité × prix du livre) + la livraison sur une ligne à part (si elle n'est pas offerte)."""
    f = FORMULES[formule]
    items = [{"price_data": {"currency": "eur", "unit_amount": f["prix_livre"],
                             "product_data": {"name": f"Mon Héros du Mois – livre personnalisé ({f['nom']})"}}, "quantity": f["livres"]}]
    port = frais_port(formule, pays)
    if port:
        items.append({"price_data": {"currency": "eur", "unit_amount": port, "product_data": {"name": "Livraison (un seul colis)"}}, "quantity": 1})
    data = {"mode": "payment", "customer_email": email, "client_reference_id": order_id, "locale": "fr", "line_items": items,
            "metadata": {"commande": order_id, "formule": formule}, "payment_intent_data": {"metadata": {"commande": order_id}},
            "success_url": f"{base_url}/creer?commande={order_id}&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base_url}/creer?commande={order_id}&annule=1"}
    s = _api("POST", "/checkout/sessions", data)
    return s["id"], s["url"]


def session(session_id):
    return _api("GET", "/checkout/sessions/" + urllib.parse.quote(session_id))


def cancel_subscription(sub_id):
    return _api("DELETE", "/subscriptions/" + urllib.parse.quote(sub_id))


def verify_webhook(payload: bytes, header: str, tolerance=300):
    """Vérifie la signature Stripe (en-tête Stripe-Signature) et renvoie l'événement."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise StripeError("STRIPE_WEBHOOK_SECRET manquant")
    parts = [p.split("=", 1) for p in (header or "").split(",") if "=" in p]
    ts = next((v for k, v in parts if k == "t"), None)
    sigs = [v for k, v in parts if k == "v1"]
    if not ts or not sigs:
        raise StripeError("signature absente")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise StripeError("signature invalide")
    if abs(time.time() - int(ts)) > tolerance:
        raise StripeError("signature expirée")
    return json.loads(payload.decode())


def invoice_subscription(inv):
    """Identifiant d'abonnement d'une facture (ancien et nouveau format de l'API Stripe)."""
    return inv.get("subscription") or (((inv.get("parent") or {}).get("subscription_details") or {}).get("subscription"))


def stop_after_period(sub_id):
    """Dernière mensualité payée : l'abonnement Stripe s'arrête à la fin de la période, sans nouveau prélèvement."""
    return _api("POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": "true"})
