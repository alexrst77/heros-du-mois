# -*- coding: utf-8 -*-
"""Paiement Stripe Checkout (API REST, sans dépendance). Réglages .env : STRIPE_SECRET_KEY (sk_test_… pour les essais),
STRIPE_WEBHOOK_SECRET (whsec_…). Sans clé : paiement simulé (mode test local)."""
import os, json, hmac, hashlib, time, urllib.request, urllib.parse, urllib.error

FORMULES = {
    "livre":   {"nom": "Un livre personnalisé", "prix": int(os.getenv("PRIX_LIVRE", "3490")), "livres": 1, "mode": "payment"},
    "mensuel": {"nom": "Abonnement mensuel : un nouveau livre chaque mois", "prix": int(os.getenv("PRIX_MENSUEL", "2990")),
                "livres": None, "mode": "subscription"},
    "annuel":  {"nom": "Abonnement annuel : 12 livres, un par mois", "prix": int(os.getenv("PRIX_ANNUEL", "29900")),
                "livres": 12, "mode": "payment"},
}


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


def checkout(order_id, formule, email, base_url):
    f = FORMULES[formule]
    price = {"currency": "eur", "unit_amount": f["prix"], "product_data": {"name": "Mon Héros du Mois – " + f["nom"]}}
    if f["mode"] == "subscription":
        price["recurring"] = {"interval": "month"}
    data = {"mode": f["mode"], "customer_email": email, "client_reference_id": order_id, "locale": "fr",
            "line_items": [{"price_data": price, "quantity": 1}], "metadata": {"commande": order_id, "formule": formule},
            "success_url": f"{base_url}/?commande={order_id}&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base_url}/?commande={order_id}&annule=1"}
    if f["mode"] == "subscription":
        data["subscription_data"] = {"metadata": {"commande": order_id}}
    else:
        data["payment_intent_data"] = {"metadata": {"commande": order_id}}
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
