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

# Calendrier mural personnalisé : seul (sa propre formule) ou ajouté à une commande de livres (même colis, prix réduit)
PRIX_CALENDRIER = int(os.getenv("PRIX_CALENDRIER", "3490"))
PRIX_CALENDRIER_AJOUT = int(os.getenv("PRIX_CALENDRIER_AJOUT", "2990"))
FORMULES["calendrier"] = {"nom": "Le calendrier de son année", "livres": 0, "prix_livre": 0, "prix": PRIX_CALENDRIER, "mode": "payment"}
# Cahier de coloriage personnalisé : même principe (seul, ou ajouté à une commande)
PRIX_COLORIAGE = int(os.getenv("PRIX_COLORIAGE", "2490"))
PRIX_COLORIAGE_AJOUT = int(os.getenv("PRIX_COLORIAGE_AJOUT", "1990"))
FORMULES["coloriage"] = {"nom": "Le cahier de coloriage", "livres": 0, "prix_livre": 0, "prix": PRIX_COLORIAGE, "mode": "payment"}
EXTRAS = ("calendrier", "coloriage")         # produits qui ne sont pas des livres (seuls, ou ajoutés à une commande)
# Objets Printful (gourde, tasse, sac à dos) : seulement en ajout à une commande, livraison comprise (colis Printful à part)
OBJETS = {"gourde": {"nom": "Gourde à paille personnalisée", "prix": int(os.getenv("PRIX_GOURDE", "4990"))},
          "tasse": {"nom": "Tasse émaillée personnalisée", "prix": int(os.getenv("PRIX_TASSE", "2490"))},
          "sac": {"nom": "Sac à dos personnalisé", "prix": int(os.getenv("PRIX_SAC", "6490"))}}


def objets_valides(objets):
    return [k for k in dict.fromkeys(objets or []) if k in OBJETS]

# Livraison (centimes), un seul colis par commande. Offerte dès 6 livres en France ; supplément pour les autres pays.
PORT_FR = {1: int(os.getenv("PORT_1", "790")), 3: int(os.getenv("PORT_3", "990"))}
SUPPLEMENT_PAYS = {"FR": 0, "BE": int(os.getenv("PORT_SUPPL_UE", "400")), "LU": int(os.getenv("PORT_SUPPL_UE", "400")),
                   "MC": int(os.getenv("PORT_SUPPL_UE", "400")), "CH": int(os.getenv("PORT_SUPPL_CH", "900"))}


def frais_port(formule, pays="FR"):
    n = FORMULES[formule]["livres"]
    base = PORT_FR[1] if formule in EXTRAS else 0 if n >= 6 else PORT_FR.get(n, PORT_FR[3])
    return base + SUPPLEMENT_PAYS.get((pays or "FR").upper(), SUPPLEMENT_PAYS["BE"])


def avec_calendrier(formule, calendrier):
    """Un calendrier est-il AJOUTÉ à une commande de livres ? (la formule « calendrier » le compte déjà dans son prix)"""
    return bool(calendrier) and formule != "calendrier"


def total(formule, pays="FR", calendrier=False, coloriage=False, objets=()):
    return (FORMULES[formule]["prix"] + sum(OBJETS[k]["prix"] for k in objets_valides(objets)) + (PRIX_CALENDRIER_AJOUT if avec_calendrier(formule, calendrier) else 0)
            + (PRIX_COLORIAGE_AJOUT if coloriage and formule != "coloriage" else 0) + frais_port(formule, pays))


def lignes(formule, pays="FR", calendrier=False, coloriage=False, objets=()):
    """Détail facturable d'une commande, tel qu'encaissé : [(libellé, quantité, prix unitaire TTC en centimes, catégorie)].
    Catégorie = livre | calendrier | coloriage | objet | port (sert au taux de TVA)."""
    f = FORMULES[formule]
    out = []
    if f["livres"]:
        out.append((f"Livre illustré personnalisé ({f['nom']})", f["livres"], f["prix_livre"], "livre"))
    if formule == "calendrier":
        out.append(("Calendrier mural personnalisé (12 mois)", 1, PRIX_CALENDRIER, "calendrier"))
    elif calendrier:
        out.append(("Calendrier mural personnalisé (12 mois), en ajout", 1, PRIX_CALENDRIER_AJOUT, "calendrier"))
    if formule == "coloriage":
        out.append(("Cahier de coloriage personnalisé (30 dessins)", 1, PRIX_COLORIAGE, "coloriage"))
    elif coloriage:
        out.append(("Cahier de coloriage personnalisé (30 dessins), en ajout", 1, PRIX_COLORIAGE_AJOUT, "coloriage"))
    for k in objets_valides(objets):
        out.append((f"{OBJETS[k]['nom']}, livraison comprise", 1, OBJETS[k]["prix"], "objet"))
    port = frais_port(formule, pays)
    if port:
        out.append(("Livraison", 1, port, "port"))
    return out


def grille():
    """Prix affichés par le site (en centimes) : une seule source pour la page d'accueil et la commande."""
    return {"formules": {k: {"nom": f["nom"], "livres": f["livres"], "prix_livre": f["prix_livre"], "prix": f["prix"]} for k, f in FORMULES.items()},
            "port_fr": {str(k): v for k, v in PORT_FR.items()}, "port_offert_des": 6, "supplement_pays": SUPPLEMENT_PAYS,
            "calendrier": {"seul": PRIX_CALENDRIER, "ajout": PRIX_CALENDRIER_AJOUT, "port": PORT_FR[1]},
            "coloriage": {"seul": PRIX_COLORIAGE, "ajout": PRIX_COLORIAGE_AJOUT, "port": PORT_FR[1]},
            "objets": {k: {"nom": v["nom"], "prix": v["prix"]} for k, v in OBJETS.items()}}


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


def checkout(order_id, formule, email, base_url, pays="FR", calendrier=False, coloriage=False, objets=()):
    """Paiement unique : les livres (quantité × prix du livre), le calendrier s'il y en a un, puis la livraison sur une ligne
    à part (si elle n'est pas offerte)."""
    f = FORMULES[formule]
    items = []
    if f["livres"]:
        items.append({"price_data": {"currency": "eur", "unit_amount": f["prix_livre"],
                                     "product_data": {"name": f"Mon Héros du Mois – livre personnalisé ({f['nom']})"}}, "quantity": f["livres"]})
    if formule == "calendrier" or calendrier:
        prix = PRIX_CALENDRIER if formule == "calendrier" else PRIX_CALENDRIER_AJOUT
        items.append({"price_data": {"currency": "eur", "unit_amount": prix,
                                     "product_data": {"name": "Mon Héros du Mois – calendrier mural personnalisé (12 mois)"}}, "quantity": 1})
    if formule == "coloriage" or coloriage:
        prix = PRIX_COLORIAGE if formule == "coloriage" else PRIX_COLORIAGE_AJOUT
        items.append({"price_data": {"currency": "eur", "unit_amount": prix,
                                     "product_data": {"name": "Mon Héros du Mois – cahier de coloriage personnalisé (30 pages)"}}, "quantity": 1})
    for k in objets_valides(objets):
        items.append({"price_data": {"currency": "eur", "unit_amount": OBJETS[k]["prix"],
                                     "product_data": {"name": f"Mon Héros du Mois – {OBJETS[k]['nom'].lower()} (livraison comprise)"}}, "quantity": 1})
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
