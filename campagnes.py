# -*- coding: utf-8 -*-
"""E-mails aux clients depuis l'admin : un e-mail personnel à une personne, ou une campagne (nouveautés, offres) à un groupe.

Règles (prospection par e-mail, CNIL / art. L34-5 du Code des postes et communications électroniques) :
- clients ayant déjà commandé : autorisé pour des produits analogues (« soft opt-in »), car ils ont été informés à la commande et
  peuvent s'y opposer à tout moment ;
- inscrits sans commande : SEULEMENT ceux qui ont accepté de recevoir les nouveautés (case non cochée par défaut) ;
- jamais aux désinscrits ; chaque e-mail a un lien de désinscription en un clic ; l'expéditeur est clairement identifié."""
import os, re, time, json, secrets, threading, hashlib
from html import escape
from flask import Blueprint, request, jsonify, abort
import commandes as db

bp = Blueprint("campagnes", __name__)
MAX_ENVOIS = int(os.getenv("CAMPAGNE_MAX", "280"))       # Brevo gratuit : 300 e-mails par jour
TROIS_ANS = 3 * 365 * 86400                               # durée de conservation annoncée dans la politique de confidentialité
AUDIENCES = {"clients": "Clients ayant commandé", "inscrits": "Inscrits ayant accepté les nouveautés", "tous": "Les deux"}

with db._db() as _c:
    _c.executescript("""
create table if not exists consentements (email text primary key, le real, source text);
create table if not exists campagnes (id text primary key, cree real, sujet text, audience text, prevus integer, envoyes integer default 0,
  statut text, message text);
create table if not exists campagne_envois (campagne text, email text, envoye real, clic real, primary key (campagne, email));
""")


def consentir(email, source, oui=True):
    e = (email or "").strip().lower()
    if not e:
        return
    with db._lock, db._db() as c:
        if oui:
            c.execute("insert or replace into consentements values (?,?,?)", (e, time.time(), source))
        else:
            c.execute("delete from consentements where email=?", (e,))


def consent(email):
    with db._db() as c:
        return bool(c.execute("select 1 from consentements where email=?", ((email or "").lower(),)).fetchone())


def _prenom_client(email):
    """Prénom à mettre dans « Bonjour … » : celui du compte, sinon celui de la dernière commande (destinataire)."""
    with db._db() as c:
        r = c.execute("select nom from clients where email=?", (email,)).fetchone()
        if r and r["nom"]:
            return r["nom"].split()[0].capitalize()
        r = c.execute("select adresse from commandes where lower(email)=? order by cree desc limit 1", (email,)).fetchone()
    try:
        return (json.loads(r["adresse"]).get("nom") or "").split()[0].capitalize() if r and r["adresse"] else ""
    except (ValueError, IndexError, AttributeError):
        return ""


def audience(qui):
    """Adresses e-mail du groupe (minuscules, sans doublon, sans désinscrits)."""
    with db._db() as c:
        stop = {r[0] for r in c.execute("select email from desinscrits")}
        clients = {(r[0] or "").lower() for r in c.execute(
            "select email from commandes where statut not in ('attente_paiement','erreur','annulee') and montant>0 and formule not like 'essai%' "
            "and cree>?", (time.time() - TROIS_ANS,))}
        inscrits = {(r[0] or "").lower() for r in c.execute("select email from consentements where le>?", (time.time() - TROIS_ANS,))}
    if qui == "clients":
        l = clients
    elif qui == "inscrits":
        l = inscrits - clients
    elif qui == "tous":
        l = clients | inscrits
    else:
        l = set()
    return sorted(e for e in l if e and "@" in e and e not in stop)


def compter():
    return {k: len(audience(k)) for k in AUDIENCES}


def _corps(message, prenom):
    t = (message or "").replace("{prenom}", prenom or "").replace("Bonjour ,", "Bonjour,")
    paras = [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]
    return "".join(f"<p style='margin:0 0 10px'>{escape(p).replace(chr(10), '<br>')}</p>" for p in paras)


def _html(sujet, intro, bouton, lien, site, stop, pourquoi):
    btn = (f'<p style="margin:22px 0"><a href="{escape(lien)}" style="display:inline-block;background:#FFC23D;color:#24184D;font:800 17px system-ui,sans-serif;'
           f'text-decoration:none;padding:14px 26px;border-radius:999px">{escape(bouton)}</a></p>') if bouton and lien else ""
    return f"""<!doctype html><html><body style="margin:0;background:#F7F2FF;font-family:Georgia,serif;color:#24184D">
<div style="max-width:560px;margin:0 auto;padding:28px 18px;text-align:center">
 <p style="margin:0 0 10px"><img src="{site}/static/marque/logo-mail.png" alt="Mon Héros du Mois" width="220" style="width:220px;max-width:70%;height:auto;border:0"></p>
 <h1 style="font-size:26px;margin:0 0 14px">{escape(sujet)}</h1>
 <div style="background:#fff;border-radius:16px;padding:20px 18px;font:16px/1.5 system-ui,sans-serif;text-align:left">{intro}</div>
 {btn}
 <p style="font:13px system-ui,sans-serif;color:#6B6F8E;margin:0">{escape(pourquoi)} Une question ? Répondez simplement à ce mail.<br>
 {f'<a href="{escape(stop)}" style="color:#6B6F8E">Ne plus recevoir nos e-mails</a> · ' if stop else ''}<a href="{site}" style="color:#5A33C9">{site.replace('https://', '')}</a></p>
</div></body></html>"""


def envoyer_un(email, sujet, message, bouton="", chemin="", cid=None, pourquoi="", perso=False):
    """Un e-mail (personnalisé avec {prenom}), lien suivi (clic) et lien de désinscription. Renvoie True s'il est parti."""
    import boutique as B, suivi
    from urllib.parse import quote_plus
    site = (os.getenv("PUBLIC_URL") or "https://www.monherosdumois.fr").rstrip("/")
    if suivi.desinscrit(email) and not perso:
        return False
    prenom = _prenom_client(email)
    lien = ""
    if bouton and chemin:
        lien = suivi._suivi_lien(f"camp:{cid}:{hashlib.sha1(email.encode()).hexdigest()[:10]}", chemin, site) if cid else site + chemin
    stop = f"{site}/stop-rappels?e={quote_plus(email)}&t={suivi._jeton_mail(email)}"
    texte = (message or "").replace("{prenom}", prenom).replace("Bonjour ,", "Bonjour,") + (f"\n\n{bouton} : {lien}" if lien else "") + \
            f"\n\nNe plus recevoir nos e-mails : {stop}"
    ok = B.send_mail(sujet, texte, reply_to=B.CONTACT, to=email, html=_html(sujet, _corps(message, prenom), bouton, lien, site, stop, pourquoi))
    if ok and cid:
        with db._lock, db._db() as c:
            c.execute("insert or replace into campagne_envois (campagne, email, envoye) values (?,?,?)", (cid, email, time.time()))
            c.execute("update campagnes set envoyes=envoyes+1 where id=?", (cid,))
    return bool(ok)


POURQUOI = {"clients": "Vous recevez ce message car vous avez commandé chez Mon Héros du Mois.",
            "inscrits": "Vous recevez ce message car vous avez accepté de recevoir nos nouveautés.",
            "tous": "Vous recevez ce message car vous avez commandé chez Mon Héros du Mois ou accepté de recevoir nos nouveautés."}


def lancer(qui, sujet, message, bouton, chemin):
    emails = audience(qui)
    if not emails:
        raise ValueError("Personne dans ce groupe pour l'instant.")
    if len(emails) > MAX_ENVOIS:
        raise ValueError(f"{len(emails)} destinataires : au-delà de {MAX_ENVOIS} par envoi (limite de ton compte d'envoi). Dis-le-moi pour l'augmenter.")
    cid = secrets.token_hex(6)
    with db._lock, db._db() as c:
        c.execute("insert into campagnes (id, cree, sujet, audience, prevus, envoyes, statut, message) values (?,?,?,?,?,?,?,?)",
                  (cid, time.time(), sujet, qui, len(emails), 0, "en_cours", message))

    def tache():
        for e in emails:
            try:
                envoyer_un(e, sujet, message, bouton, chemin, cid, POURQUOI[qui])
            except Exception as ex:
                print("campagne : envoi impossible à", e, ex)
            time.sleep(.4)
        with db._lock, db._db() as c:
            c.execute("update campagnes set statut='envoyee' where id=?", (cid,))
    threading.Thread(target=tache, daemon=True).start()
    return cid, len(emails)


def historique():
    with db._db() as c:
        L = [dict(r) for r in c.execute("select * from campagnes order by cree desc limit 30")]
        for x in L:
            x["clics"] = c.execute("select count(*) from campagne_envois where campagne=? and clic is not null", (x["id"],)).fetchone()[0]
            x["achats"] = c.execute("select count(distinct e.email) from campagne_envois e join commandes o on lower(o.email)=e.email "
                                    "where e.campagne=? and o.cree>e.envoye and o.statut not in ('attente_paiement','erreur','annulee') and o.montant>0",
                                    (x["id"],)).fetchone()[0]
    return L


def noter_clic(cle):
    """Lien suivi d'une campagne (/rl?c=camp:<id>:<empreinte>) : le clic est compté."""
    m = re.fullmatch(r"camp:([0-9a-f]{12}):([0-9a-f]{10})", cle or "")
    if not m:
        return
    with db._lock, db._db() as c:
        for r in c.execute("select email from campagne_envois where campagne=?", (m.group(1),)).fetchall():
            if hashlib.sha1(r["email"].encode()).hexdigest()[:10] == m.group(2):
                c.execute("update campagne_envois set clic=coalesce(clic, ?) where campagne=? and email=?", (time.time(), m.group(1), r["email"]))


# ------------------------------------------------------------------ admin
def _admin():
    import boutique
    if not boutique.admin_ok():
        abort(403)


LIENS = {"/creer": "Créer son avatar", "/livre-personnalise-noel": "Son livre de Noël", "/cadeau-personnalise-enfant": "Voir les idées cadeaux",
         "/compte": "Mon compte", "/": "Voir le site"}


@bp.get("/admin/api/campagnes")
def admin_campagnes():
    _admin()
    import boutique
    return jsonify(audiences={k: {"nom": v, "n": n} for (k, v), n in zip(AUDIENCES.items(), compter().values())}, historique=historique(),
                   liens=LIENS, mail=boutique.mail_configure(), max=MAX_ENVOIS, test=os.getenv("CONTACT_EMAIL", "monherosdumois@gmail.com"))


def _lire():
    d = request.get_json(force=True, silent=True) or {}
    sujet = re.sub(r"\s+", " ", str(d.get("sujet") or "")).strip()[:120]
    message = str(d.get("message") or "").strip()[:5000]
    chemin = str(d.get("lien") or "")
    if chemin and (not chemin.startswith("/") or chemin.startswith("//")):
        chemin = "/creer"
    if not sujet or len(message) < 10:
        abort(400, "Sujet et message obligatoires.")
    return d, sujet, message, str(d.get("bouton") or "").strip()[:40], chemin


@bp.post("/admin/api/campagnes/test")
def admin_test():
    _admin()
    import boutique
    d, sujet, message, bouton, chemin = _lire()
    ok = envoyer_un(boutique.CONTACT, "[TEST] " + sujet, message, bouton, chemin, None, POURQUOI.get(d.get("audience"), ""), perso=True)
    return jsonify(ok=ok, a=boutique.CONTACT), (200 if ok else 400)


@bp.post("/admin/api/campagnes/envoyer")
def admin_envoyer():
    _admin()
    import boutique
    if not boutique.mail_configure():
        return jsonify(erreur="Aucun envoi de mail configuré (BREVO_API_KEY dans Railway)."), 400
    d, sujet, message, bouton, chemin = _lire()
    if d.get("audience") not in AUDIENCES:
        abort(400)
    try:
        cid, n = lancer(d["audience"], sujet, message, bouton, chemin)
    except ValueError as e:
        return jsonify(erreur=str(e)), 400
    return jsonify(ok=True, id=cid, n=n)


@bp.post("/admin/api/ecrire")
def admin_ecrire():
    """E-mail personnel à UNE personne (réponse, suivi, geste commercial) : envoyé tel quel, avec lien de désinscription."""
    _admin()
    import boutique
    if not boutique.mail_configure():
        return jsonify(erreur="Aucun envoi de mail configuré (BREVO_API_KEY dans Railway)."), 400
    d, sujet, message, bouton, chemin = _lire()
    email = str(d.get("email") or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(erreur="Adresse e-mail invalide."), 400
    import suivi
    if suivi.desinscrit(email):
        return jsonify(erreur="Cette personne s'est désinscrite : elle ne veut plus recevoir nos e-mails."), 400
    cid = secrets.token_hex(6)
    with db._lock, db._db() as c:
        c.execute("insert into campagnes (id, cree, sujet, audience, prevus, envoyes, statut, message) values (?,?,?,?,?,?,?,?)",
                  (cid, time.time(), sujet, "perso:" + email, 1, 0, "envoyee", message))
    ok = envoyer_un(email, sujet, message, bouton, chemin, cid, "", perso=True)
    return jsonify(ok=ok), (200 if ok else 400)


# ------------------------------------------------------------------ côté client : accepter / refuser les nouveautés
@bp.post("/api/compte/nouveautes")
def compte_nouveautes():
    import comptes
    cl = comptes.client_courant()
    if not cl:
        abort(401)
    oui = bool((request.get_json(force=True, silent=True) or {}).get("oui"))
    consentir(cl["email"], "compte", oui)
    with db._lock, db._db() as c:
        if oui:                                     # s'il s'était désinscrit, il se réinscrit
            c.execute("delete from desinscrits where email=?", (cl["email"].lower(),))
        else:
            c.execute("insert or replace into desinscrits values (?,?)", (cl["email"].lower(), time.time()))
    return jsonify(ok=True, oui=oui)
