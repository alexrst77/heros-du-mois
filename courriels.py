# -*- coding: utf-8 -*-
"""Journal des e-mails envoyés par le site, et leur suivi de réception (Brevo).

- Chaque envoi est noté : destinataire, sujet, type, date, envoyé ou échec (le CONTENU n'est pas gardé : un lien de connexion
  ou de téléchargement ne doit pas traîner dans une base).
- Envoi par l'API Brevo : Brevo renvoie un identifiant de message ; ses événements (remis, ouvert, cliqué, rejeté, rebond,
  spam, bloqué…) sont lus à la demande via l'API (GET /v3/smtp/statistics/events), sans webhook à configurer.
- Envoi par SMTP (Gmail) : pas de suivi possible au-delà de « envoyé »."""
import os, re, json, time, threading, urllib.request, urllib.parse
import commandes as db

with db._db() as _c:
    _c.execute("create table if not exists mails (id integer primary key autoincrement, cree real, destinataire text, sujet text, type text, "
               "fournisseur text, message_id text, statut text, evenements text, maj real, erreur text, commande text)")
    _c.execute("create index if not exists mails_dest on mails(destinataire)")

FINAUX = {"bloque", "rebond", "spam", "rejete", "desinscrit"}         # plus rien à attendre de Brevo
LIBELLES = {"envoye": "Envoyé", "echec": "Échec de l'envoi", "remis": "Reçu (remis à sa boîte)", "ouvert": "Ouvert", "clique": "Lien cliqué",
            "differe": "En attente chez le destinataire", "rebond": "Non reçu (adresse en erreur)", "bloque": "Non reçu (bloqué)",
            "spam": "Marqué comme spam", "rejete": "Non reçu (rejeté)", "desinscrit": "S'est désinscrit", "sans_suivi": "Envoyé (pas de suivi)"}
EVT = {"bounces": "rebond", "delivered": "remis", "opened": "ouvert", "uniqueOpened": "ouvert", "clicks": "clique", "hardBounces": "rebond", "softBounces": "rebond",
       "blocked": "bloque", "spam": "spam", "invalid": "rejete", "error": "rejete", "deferred": "differe", "unsubscribed": "desinscrit",
       "requests": "envoye", "loadedByProxy": "ouvert"}
ORDRE = ["echec", "envoye", "sans_suivi", "differe", "remis", "ouvert", "clique", "rebond", "bloque", "rejete", "spam", "desinscrit"]


def type_de(sujet, destinataire, contact):
    s = (sujet or "").lower()
    if destinataire and contact and destinataire.lower() == contact.lower():
        return "interne"
    for k, t in (("lien de connexion", "connexion"), ("commande confirmée", "confirmation"), ("c'est parti", "confirmation"), ("prêt", "livre prêt"),
                 ("avis", "demande d'avis"), ("expédi", "expédition"), ("[site]", "message"), ("retouche", "interne")):
        if k in s:
            return t
    return "relance / campagne"


def noter(destinataire, sujet, fournisseur, message_id=None, ok=True, erreur=None, contact=None):
    try:
        with db._lock, db._db() as c:
            c.execute("insert into mails (cree, destinataire, sujet, type, fournisseur, message_id, statut, evenements, maj, erreur) values (?,?,?,?,?,?,?,?,?,?)",
                      (time.time(), (destinataire or "").lower(), (sujet or "")[:200], type_de(sujet, destinataire, contact), fournisseur, message_id,
                       ("envoye" if fournisseur == "brevo" else "sans_suivi") if ok else "echec", "[]", time.time(), (erreur or "")[:300] or None))
    except Exception as e:
        print("journal des mails :", e)


def _evenements_brevo(message_id):
    q = urllib.parse.urlencode({"messageId": message_id, "limit": 50, "days": 30})
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/statistics/events?" + q,
                                 headers={"api-key": os.getenv("BREVO_API_KEY", ""), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return (json.loads(r.read().decode() or "{}").get("events") or [])


def actualiser(rows, max_appels=25):
    """Statut de réception des mails Brevo encore « en cours » (moins de 30 jours), lu chez Brevo. Borné en nombre d'appels."""
    if not os.getenv("BREVO_API_KEY"):
        return
    n = 0
    for m in rows:
        if n >= max_appels:
            break
        if m["fournisseur"] != "brevo" or not m["message_id"] or m["statut"] in FINAUX or m["statut"] == "echec" or time.time() - m["cree"] > 30 * 86400:
            continue
        if m["statut"] in ("ouvert", "clique") and time.time() - (m["maj"] or 0) < 6 * 3600:
            continue
        n += 1
        try:
            ev = _evenements_brevo(m["message_id"])
        except Exception as e:
            m["erreur_suivi"] = str(e)[:120]; continue
        etats = [EVT.get(e.get("event"), None) for e in ev]
        etats = [x for x in etats if x]
        if not etats:
            continue
        statut = max(etats, key=lambda x: ORDRE.index(x) if x in ORDRE else 0)
        hist = sorted([{"evenement": EVT.get(e.get("event"), e.get("event")), "date": e.get("date"), "raison": e.get("reason")} for e in ev],
                      key=lambda x: x.get("date") or "")
        m["statut"], m["evenements"] = statut, json.dumps(hist, ensure_ascii=False)
        with db._lock, db._db() as c:
            c.execute("update mails set statut=?, evenements=?, maj=? where id=?", (statut, m["evenements"], time.time(), m["id"]))


def lister(email=None, limite=200, actualiser_suivi=True):
    with db._db() as c:
        q = "select * from mails" + (" where destinataire=?" if email else "") + " order by cree desc limit ?"
        rows = [dict(r) for r in c.execute(q, ((email.lower(),) if email else ()) + (limite,))]
    if actualiser_suivi:
        actualiser(rows)
    for m in rows:
        m["libelle"] = LIBELLES.get(m["statut"], m["statut"])
        m["evenements"] = json.loads(m["evenements"] or "[]") if isinstance(m["evenements"], str) else m["evenements"]
    return rows


def passe_brevo(email, connus=()):
    """Mails envoyés AVANT le journal (ou par un autre outil) : lus chez Brevo par adresse (90 jours), groupés par message."""
    if not os.getenv("BREVO_API_KEY"):
        return []
    q = urllib.parse.urlencode({"email": email, "limit": 300, "days": 90})
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/statistics/events?" + q,
                                 headers={"api-key": os.getenv("BREVO_API_KEY", ""), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            ev = json.loads(r.read().decode() or "{}").get("events") or []
    except Exception as e:
        return [{"erreur": f"Brevo : {e}"}]
    par = {}
    for e in ev:
        mid = e.get("messageId")
        if not mid or mid in connus:
            continue
        m = par.setdefault(mid, {"message_id": mid, "sujet": e.get("subject") or "(sans sujet)", "evenements": [], "brevo": True})
        m["evenements"].append({"evenement": EVT.get(e.get("event"), e.get("event")), "date": e.get("date"), "raison": e.get("reason")})
    out = []
    for m in par.values():
        m["evenements"].sort(key=lambda x: x.get("date") or "")
        etats = [x["evenement"] for x in m["evenements"] if x["evenement"] in ORDRE]
        m["statut"] = max(etats, key=ORDRE.index) if etats else "envoye"
        m["libelle"] = LIBELLES.get(m["statut"], m["statut"])
        m["date"] = m["evenements"][0]["date"] if m["evenements"] else None
        m["type"] = type_de(m["sujet"], email, None)
        out.append(m)
    return sorted(out, key=lambda x: x.get("date") or "", reverse=True)
