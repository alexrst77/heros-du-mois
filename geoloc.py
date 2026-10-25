# -*- coding: utf-8 -*-
"""Localisation APPROXIMATIVE des visiteurs (ville, région, pays) à partir de l'adresse IP, pour l'admin.

- Base hors ligne « IP to City Lite » de DB-IP (licence CC BY 4.0, attribution affichée dans l'admin), téléchargée une fois par
  mois sur le volume du serveur : aucune donnée n'est envoyée à un service extérieur.
- L'adresse IP n'est JAMAIS enregistrée : seuls ville, région et pays sont gardés avec le parcours du visiteur.
- Tant que la base n'est pas là (premier démarrage, téléchargement en cours), la localisation est simplement vide."""
import os, gzip, shutil, threading, time, urllib.request, ipaddress
import commandes as db

DOSSIER = db.DATA / "geo"
_lecteur, _verrou, _en_cours = None, threading.Lock(), [False]
SOURCE = "https://download.db-ip.com/free/dbip-city-lite-{}.mmdb.gz"


def _fichier():
    l = sorted(DOSSIER.glob("dbip-city-lite-*.mmdb")) if DOSSIER.exists() else []
    return l[-1] if l else None


def _telecharger():
    """Télécharge la base du mois (ou du mois précédent si elle n'est pas encore publiée), en tâche de fond."""
    try:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        t = time.gmtime()
        mois = [f"{t.tm_year}-{t.tm_mon:02d}", f"{t.tm_year - (t.tm_mon == 1)}-{(t.tm_mon - 2) % 12 + 1:02d}"]
        for m in mois:
            dst = DOSSIER / f"dbip-city-lite-{m}.mmdb"
            if dst.exists():
                return
            try:
                tmp = DOSSIER / f".{m}.gz"
                req = urllib.request.Request(SOURCE.format(m), headers={"User-Agent": "MonHerosDuMois/1.0"})
                with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f)
                with gzip.open(tmp, "rb") as g, open(str(dst) + ".part", "wb") as f:
                    shutil.copyfileobj(g, f)
                os.replace(str(dst) + ".part", dst); tmp.unlink(missing_ok=True)
                for vieux in DOSSIER.glob("dbip-city-lite-*.mmdb"):          # on ne garde que la plus récente
                    if vieux != dst:
                        vieux.unlink(missing_ok=True)
                global _lecteur
                _lecteur = None
                print("géolocalisation : base", dst.name, "installée")
                return
            except Exception as e:
                print("géolocalisation : base", m, "indisponible :", e)
    finally:
        _en_cours[0] = False


def _reader():
    global _lecteur
    f = _fichier()
    if f is None or (time.time() - f.stat().st_mtime) > 40 * 86400:      # absente ou vieille de plus d'un mois : mise à jour
        with _verrou:
            if not _en_cours[0] and os.getenv("GEOLOC", "1") == "1":
                _en_cours[0] = True
                threading.Thread(target=_telecharger, daemon=True).start()
    if f is None:
        return None
    if _lecteur is None:
        with _verrou:
            if _lecteur is None:
                try:
                    import maxminddb
                    _lecteur = maxminddb.open_database(str(f))
                except Exception as e:
                    print("géolocalisation : lecture impossible :", e)
                    return None
    return _lecteur


def ip_de(req):
    return (req.headers.get("X-Forwarded-For") or req.remote_addr or "").split(",")[0].strip()


PAYS = {"FR": "France", "BE": "Belgique", "CH": "Suisse", "LU": "Luxembourg", "MC": "Monaco", "CA": "Canada", "DE": "Allemagne",
        "ES": "Espagne", "IT": "Italie", "GB": "Royaume-Uni", "US": "États-Unis", "MA": "Maroc", "DZ": "Algérie", "TN": "Tunisie",
        "SN": "Sénégal", "CI": "Côte d'Ivoire", "RE": "La Réunion", "GP": "Guadeloupe", "MQ": "Martinique", "PT": "Portugal", "NL": "Pays-Bas"}


def localiser(ip, pays_entete=None):
    """{'ville', 'region', 'pays'} (noms en français quand la base les a), ou None. N'enregistre rien."""
    try:
        a = ipaddress.ip_address(ip)
        if a.is_private or a.is_loopback:
            return None
    except ValueError:
        return None
    r = _reader()
    if r is None:
        return {"ville": None, "region": None, "pays": PAYS.get(pays_entete, pays_entete)} if pays_entete else None
    try:
        d = r.get(ip) or {}
    except Exception:
        return None
    nom = lambda x: ((x or {}).get("names") or {}).get("fr") or ((x or {}).get("names") or {}).get("en")
    code = (d.get("country") or {}).get("iso_code")
    sub = (d.get("subdivisions") or [{}])[0]
    return {"ville": nom(d.get("city")), "region": nom(sub), "pays": PAYS.get(code) or nom(d.get("country")) or code}
