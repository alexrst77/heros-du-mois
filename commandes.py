# -*- coding: utf-8 -*-
"""Base des commandes et abonnements (SQLite, fichier data/commandes.sqlite).
Statuts d'une commande : attente_paiement -> payee -> generation -> a_verifier (relecture par toi)
-> envoyee_impression -> expediee ; ou erreur / annulee."""
import sqlite3, json, time, threading, os
from pathlib import Path

DATA = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data")); DATA.mkdir(exist_ok=True)
DB = DATA / "commandes.sqlite"
_lock = threading.Lock()
JSON_COLS = {"adresse", "controle", "suivi"}

SCHEMA = """
create table if not exists commandes (
  id text primary key, cree real, maj real, formule text, email text, adresse text, statut text,
  montant integer, stripe_session text, stripe_sub text, abonnement_id text, origine text, numero integer,
  job_id text, pdf text, titre text, jeton text, lulu_id text, lulu_statut text, lulu_cout text,
  suivi text, erreur text, controle text);
create table if not exists messages (
  id integer primary key autoincrement, cree real, nom text, email text, sujet text, message text, envoye integer default 0, lu integer default 0);
create table if not exists abonnements (
  id text primary key, cree real, commande_origine text, formule text, statut text, livres_restants integer,
  prochain real, stripe_sub text, numero integer, email text);
"""


def _db():
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    return c


with _db() as _c:
    _c.executescript(SCHEMA)
    for _t, _col in (("commandes", "cout real"), ("commandes", "tentatives integer default 0"), ("commandes", "univers text"),
                     ("abonnements", "faites text"), ("abonnements", "paiements integer default 1"),
                     ("commandes", "volume_number integer")):   # colonnes ajoutées après la mise en ligne
        try:
            _c.execute(f"alter table {_t} add column {_col}")
        except sqlite3.OperationalError:
            pass


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        d[k] = json.loads(d[k]) if d[k] else None
    return d


def _enc(kw):
    return {k: (json.dumps(v, ensure_ascii=False) if k in JSON_COLS and v is not None else v) for k, v in kw.items()}


def create(**kw):
    kw = _enc(dict(kw, cree=time.time(), maj=time.time()))
    with _lock, _db() as c:
        c.execute(f"insert into commandes ({','.join(kw)}) values ({','.join('?' * len(kw))})", list(kw.values()))
    return get(kw["id"])


def get(cid):
    with _db() as c:
        return _row(c.execute("select * from commandes where id=?", (cid,)).fetchone())


def find(**kw):
    k, v = next(iter(kw.items()))
    with _db() as c:
        return _row(c.execute(f"select * from commandes where {k}=? order by cree desc", (v,)).fetchone())


def update(cid, **kw):
    kw = _enc(dict(kw, maj=time.time()))
    with _lock, _db() as c:
        c.execute(f"update commandes set {','.join(k + '=?' for k in kw)} where id=?", list(kw.values()) + [cid])
    return get(cid)


def transition(cid, old, new, **kw):
    """Change le statut seulement s'il vaut encore `old` (évite les doubles déclenchements webhook + retour)."""
    kw = _enc(dict(kw, maj=time.time(), statut=new))
    with _lock, _db() as c:
        cur = c.execute(f"update commandes set {','.join(k + '=?' for k in kw)} where id=? and statut=?",
                        list(kw.values()) + [cid, old])
        return cur.rowcount == 1


def lister(limit=200, statut=None):
    with _db() as c:
        q = "select * from commandes" + (" where statut=?" if statut else "") + " order by cree desc limit ?"
        return [_row(r) for r in c.execute(q, ((statut,) if statut else ()) + (limit,))]


def sub_create(**kw):
    kw = dict(kw, cree=time.time())
    with _lock, _db() as c:
        c.execute(f"insert into abonnements ({','.join(kw)}) values ({','.join('?' * len(kw))})", list(kw.values()))
    return sub_get(kw["id"])


def sub_get(sid):
    with _db() as c:
        return _row(c.execute("select * from abonnements where id=?", (sid,)).fetchone())


def sub_find(**kw):
    k, v = next(iter(kw.items()))
    with _db() as c:
        return _row(c.execute(f"select * from abonnements where {k}=?", (v,)).fetchone())


def sub_update(sid, **kw):
    with _lock, _db() as c:
        c.execute(f"update abonnements set {','.join(k + '=?' for k in kw)} where id=?", list(kw.values()) + [sid])
    return sub_get(sid)


def subs(statut=None):
    with _db() as c:
        q = "select * from abonnements" + (" where statut=?" if statut else "") + " order by cree desc"
        return [_row(r) for r in c.execute(q, (statut,) if statut else ())]


def due_subs(now=None):
    """Abonnements dont le prochain livre est à fabriquer (annuel, ou mensuel sans Stripe en mode test)."""
    now = now or time.time()
    with _db() as c:
        return [_row(r) for r in c.execute(
            "select * from abonnements where statut='actif' and prochain is not null and prochain<=? "
            "and (livres_restants is null or livres_restants>0)", (now,))]


def message_add(nom, email, sujet, message):
    with _lock, _db() as c:
        cur = c.execute("insert into messages (cree, nom, email, sujet, message) values (?,?,?,?,?)", (time.time(), nom, email, sujet, message))
        return cur.lastrowid


def message_update(mid, **kw):
    with _lock, _db() as c:
        c.execute(f"update messages set {','.join(k + '=?' for k in kw)} where id=?", list(kw.values()) + [mid])


def messages(limit=100):
    with _db() as c:
        return [dict(r) for r in c.execute("select * from messages order by cree desc limit ?", (limit,))]


def messages_recent(email, since):
    with _db() as c:
        return c.execute("select count(*) from messages where email=? and cree>?", (email, since)).fetchone()[0]


def assign_volume(cid):
    """volumeNumber : numéro du livre dans la collection de l'enfant (1, 2, 3…). Attribué UNE fois, atomiquement
    (BEGIN IMMEDIATE : pas de doublon même avec des demandes simultanées), puis jamais modifié (reprise, réimpression)."""
    c = sqlite3.connect(DB, timeout=30, isolation_level=None); c.row_factory = sqlite3.Row
    try:
        c.execute("begin immediate")
        o = c.execute("select * from commandes where id=?", (cid,)).fetchone()
        if o is None:
            c.execute("rollback"); return None
        if o["volume_number"]:
            c.execute("commit"); return o["volume_number"]
        if (o["formule"] or "").startswith("essai"):          # livre d'essai : le numéro du livre dont il est l'essai, jamais un nouveau
            src = c.execute("select max(volume_number) v from commandes where origine=? and formule not like 'essai%'", (o["origine"],)).fetchone()
            n = (src["v"] if src and src["v"] else 1)
        else:
            m = c.execute("select max(volume_number) v from commandes where origine=? and formule not like 'essai%'", (o["origine"] or cid,)).fetchone()
            n = (m["v"] or 0) + 1
        c.execute("update commandes set volume_number=?, maj=? where id=?", (n, time.time(), cid))
        c.execute("commit")
        return n
    except sqlite3.Error:
        try: c.execute("rollback")
        except sqlite3.Error: pass
        raise
    finally:
        c.close()
