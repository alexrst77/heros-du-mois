# -*- coding: utf-8 -*-
"""Objets personnalisés fabriqués par Printful : gourde à paille (CamelBak), tasse émaillée, sac à dos.

Même chaîne et mêmes garde-fous que le calendrier :
- seules les données enregistrées à la commande servent (instantané + empreinte), mêmes avatars, mêmes portraits de référence
  (repris du cache s'ils ont déjà été payés pour les livres) ;
- UNE illustration SANS TEXTE par objet, un appel, un contrôle visuel, aucune régénération automatique ; un écart -> « à relire » ;
  budget de l'objet borné AVANT tout appel (plafond BUDGET_OBJET_USD, 1,50 $ max) ;
- le prénom est composé par code ; le fichier d'impression est produit aux dimensions EXACTES demandées par Printful
  pour la variante et l'emplacement (lues dans l'API Printful, mises en cache)."""
import os, re, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageStat

import generator as G
import budget as BU
import procede as P
import printful as PF

ROOT = Path(__file__).parent
VERSION = "objets-2026-10-08-v1"
PLAFOND = min(1.5, float(os.getenv("BUDGET_OBJET_USD", "1.5")))
PROMPT_MAX = 4000
KINDS = {
    "gourde": {"id": int(os.getenv("PRINTFUL_GOURDE_ID", "848")), "nom": "la gourde", "titre": "Gourde à paille", "emoji": "🥤", "tour": True,
               "scene": "a sunny outdoor adventure: the characters walking happily together along a flowery meadow path, soft green hills, "
                        "a few round trees, butterflies and a bright blue sky with small white clouds"},
    "tasse": {"id": int(os.getenv("PRINTFUL_TASSE_ID", "407")), "nom": "la tasse", "titre": "Tasse émaillée", "emoji": "☕", "tour": True,
              "scene": "a cosy magical evening: the characters sitting together on a little grassy hill under a deep blue starry sky with a "
                       "smiling crescent moon, a few glowing paper lanterns and fireflies"},
    "sac": {"id": int(os.getenv("PRINTFUL_SAC_ID", "389")), "nom": "le sac à dos", "titre": "Sac à dos", "emoji": "🎒", "tour": False,
            "scene": "ready for a big adventure: the characters standing together in front view, smiling, on a sunny forest path with a "
                     "big friendly tree, golden sunbeams and a few flowers"},
}
NOMS = {k: v["nom"] for k, v in KINDS.items()}
CREME, ENCRE = (255, 247, 232), (30, 42, 74)


class ObjetError(P.ProcedeError):
    pass


def kind_de(folder):
    p = Path(folder) / "objet.json"
    return json.loads(p.read_text(encoding="utf-8")).get("kind") if p.exists() else None


# ====================================================================== formats
def taille_image(w, h):
    """Format de l'illustration, au plus près du rapport du fichier d'impression (le reste est rogné au centre)."""
    r = max(1 / 3, min(3, w / h))
    if not P.custom_sizes_ok(P.model()):
        return "1536x1024" if r > 1.2 else "1024x1536" if r < 0.83 else "1024x1024"
    if r >= 1:
        W, H = 1792, max(608, round(1792 / r / 16) * 16)
    else:
        W, H = max(608, round(1792 * r / 16) * 16), 1792
    return f"{W}x{H}"


def _cover(im, size):
    W, H = size
    k = max(W / im.width, H / im.height)
    im = im.resize((max(W, round(im.width * k)), max(H, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _police(px):
    from calendrier import ft
    return ft("titre", px * 72 / 300)


def fichier_impression(illu, prenom, spec, dst):
    """Illustration aux dimensions exactes de Printful + prénom sur un ruban crème (bas, centré)."""
    W, H = spec["width"], spec["height"]
    im = _cover(Image.open(illu).convert("RGB"), (W, H))
    d = ImageDraw.Draw(im, "RGBA")
    nom = (prenom or "").upper()
    if nom:
        large = W / H > 2.5                                    # tasse, gourde : bande très allongée
        px = int(min(H * (0.10 if large else 0.12), W * 0.09))
        f = _police(px)
        while d.textlength(nom, font=f) > W * 0.42 and px > 40:
            px = int(px * 0.9); f = _police(px)
        tw = d.textlength(nom, font=f)
        b = d.textbbox((0, 0), nom, font=f)
        th = b[3] - b[1]
        padx, pady = px * 0.6, px * 0.32
        cy = H - H * (0.05 if large else 0.07) - th / 2 - pady
        box = (W / 2 - tw / 2 - padx, cy - th / 2 - pady, W / 2 + tw / 2 + padx, cy + th / 2 + pady)
        d.rounded_rectangle(box, radius=int(th / 2 + pady), fill=CREME + (235,), outline=(212, 175, 55, 255), width=max(3, px // 18))
        d.text((W / 2, cy), nom, font=f, fill=ENCRE, anchor="mm")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "PNG", dpi=(spec.get("dpi") or 150,) * 2)
    return dst


def couleur_bord(illu):
    """Couleur unie assortie (moyenne des bords) pour les autres panneaux d'un objet tout imprimé."""
    im = Image.open(illu).convert("RGB").resize((64, 64))
    bande = Image.new("RGB", (64 * 2, 8))
    bande.paste(im.crop((0, 0, 64, 8)), (0, 0)); bande.paste(im.crop((0, 56, 64, 64)), (64, 0))
    return tuple(int(v) for v in ImageStat.Stat(bande).mean)


def composer(folder, snap, illu, spec):
    folder = Path(folder)
    k = KINDS[snap["kind"]]
    imp = fichier_impression(illu, snap["prenom"], spec, folder / "impression_objet.png")
    autres = []
    if spec.get("autres"):
        c = couleur_bord(illu)
        for a in spec["autres"]:
            p = folder / f"impression_{re.sub(r'[^a-z0-9_]', '', a['placement'])}.png"
            Image.new("RGB", (a["width"], a["height"]), c).save(p, "PNG")
            autres.append({"placement": a["placement"], "fichier": p.name})
    # aperçu lisible dans l'admin (et dans le mail « prêt ») : le fichier d'impression réduit, sur une page
    ap = Image.open(imp).convert("RGB"); ap.thumbnail((1400, 1400))
    ap.save(folder / "apercu_objet.jpg", quality=88)
    page = Image.new("RGB", (ap.width + 120, ap.height + 220), (250, 246, 238))
    page.paste(ap, (60, 160))
    d = ImageDraw.Draw(page)
    d.text((60, 50), f"{k['emoji']} {k['titre']} de {snap['prenom']}", font=_police(150), fill=ENCRE)
    d.text((60, 115), f"Printful #{spec['produit']} · variante {spec.get('variante')} · {spec['placement']} · {spec['width']}x{spec['height']} px",
           font=_police(70), fill=(110, 110, 110))
    titre = f"{k['titre']} de {snap['prenom']}"
    pdf = f"{snap['kind']}-{re.sub(r'[^A-Za-z0-9-]', '-', snap['prenom'])}.pdf"
    page.save(folder / pdf, "PDF", resolution=150)
    return {"titre": titre, "pdf": pdf, "impression": imp.name, "autres": autres, "apercu": "apercu_objet.jpg"}


# ====================================================================== fabrication (IA) dans le budget de l'objet
SYSTEM_OBJET = """Tu contrôles une illustration pour enfant imprimée sur un objet (gourde, tasse ou sac).
Compare l'image à la fiche. BLOQUANTS (uniquement) :
- un personnage attendu absent ou méconnaissable, ou un personnage récurrent en double ;
- un humain en trop (aucun parent, frère, sœur, grand-parent) ; un chien, un chat ou un lapin domestique en trop ; deux animaux fusionnés ;
- espèce ou couleur principale fausse ; accessoire manquant ou présent alors que la fiche dit « aucun » ;
- la peluche dessinée comme un animal vivant ; des lunettes sur un animal ou sur la peluche ;
- un visage coupé par le bord de l'image ; du texte, des lettres, des chiffres, un cadre ou un filigrane ; une anatomie très fausse.
MINEURS : nuances, détails de vêtements, lumière, décor un peu chargé.
CE N'EST PAS UN ÉCART : de petits animaux sauvages du décor (oiseaux, papillons, lucioles, écureuil, coccinelle).
Une teinte due à la lumière de la scène n'est PAS une couleur fausse. En cas de doute, ce n'est pas bloquant.
Réponds UNIQUEMENT en JSON : {"bloquants": ["consigne en anglais"], "mineurs": ["en français"], "personnages_vus": ["noms"]}"""


def snapshot(form, cfg, kind, spec):
    if cfg.get("problemes"):
        raise ObjetError("Configuration incomplète, rien n'est généré : " + " ; ".join(cfg["problemes"]))
    data = {"version": VERSION, "produit": "objet", "kind": kind, "prenom": cfg["personnages"][0]["nom"], "age": str(form.get("age")),
            "personnages": [P.fiche(x) for x in cfg["personnages"]], "protagoniste": "heros",
            "printful": {k: spec.get(k) for k in ("produit", "variante", "placement", "width", "height")}}
    data["empreinte"] = P.sha(data)
    data["empreinte_images"] = P.sha([VERSION, kind, data["personnages"]])
    return data


def _ids(snap):
    return [p["id"] for p in snap["personnages"]]


def image_prompt(snap, refs):
    k = KINDS[snap["kind"]]
    noms = ", ".join(p["nom"].upper() for p in snap["personnages"])
    style = P.PROMPT_IMAGE.split("CHARACTER BIBLE")[0].split("\n", 2)[2].strip()
    lines = [f"Use case: illustration-story. Create ONE full-bleed illustration printed on a personalised children's {snap['kind'] == 'sac' and 'BACKPACK' or snap['kind'] == 'tasse' and 'ENAMEL MUG' or 'WATER BOTTLE'}.",
             style, "CHARACTER BIBLE", P._bible_lines(_ids(snap), snap, {}), P.refs_text(refs, snap),
             f"SCENE: {k['scene']}.",
             f"CHARACTERS: exactly these recurring characters ({noms}), each shown once, close together, big and clearly visible; "
             f"{snap['personnages'][0]['nom'].upper()} is the focal point. No other human at all (no parent, sibling, grandparent).",
             "COMPOSITION: bold, simple and readable from a distance (it is printed on an object). Keep every character and face inside the "
             "central 60 % of the width. The characters are drawn a bit smaller and HIGHER in the picture: their feet and paws stay ABOVE the "
             f"bottom {'32' if k['tour'] else '22'} % of the height, which shows only grass or ground (a name ribbon is typeset there). "
             "Leave a little sky above their heads: the top 8 % may be trimmed.",
             ("The picture WRAPS AROUND A CYLINDER: the left and right edges must be simple continuous scenery (sky, grass, hills) that "
              "meet seamlessly, with no character near them." if k["tour"] else "Front view, vertical poster-like composition."),
             "No writing, letters, numbers, title, captions, watermark, typography or frame."]
    p = "\n".join(lines)
    if len(p.encode()) > PROMPT_MAX:
        lines[1] = style[:600]; p = "\n".join(lines)
    return p


def _key(snap, refs, size, quality):
    return P.sha([VERSION, P.model(), snap["empreinte_images"], snap["kind"], [P.fsha(f) for _, f in refs], size, quality])[:12]


def cible(snap, portraits, folder, size):
    folder = Path(folder)
    q = G._m("q_main", G.IMAGE_QUALITY)
    refs = P.refs_for(_ids(snap), portraits, None, folder, "jour")
    return refs, folder / f"obj-{snap['kind']}-{_key(snap, refs, size, q)}.png", q


def plan(cfg, folder, size, snap=None, portraits=None):
    q = G._m("q_main", G.IMAGE_QUALITY)
    qp = G._m("q_scene", G.PORTRAIT_QUALITY)
    img = lambda n: {"type": "image", "etape": "illustration", "modele": P.model(), "prompt_max": "x" * PROMPT_MAX, "refs": n, "size": size, "quality": q}
    ctl = {"type": "chat", "etape": "contrôle illustration", "modele": G.REVIEW_MODEL, "textes": [SYSTEM_OBJET, "x" * P.FICHE_MAX],
           "max_tokens": P.REVIEW_MAX_TOKENS, "images": [P._vision_dims(size)]}
    out = []
    for c in cfg["personnages"]:
        if not G.portrait_en_cache(c):
            out.append(P._p_image(f"portrait {c['id']}", 3, "1024x1024", qp))
        if not G.portrait_en_cache(c) or not Path(str(G.portrait_path(c)) + ".controle.json").exists():
            out.append(P._p_controle(f"contrôle portrait {c['id']}", P.SYSTEM_REF, "1024x1024"))
    if snap is None or portraits is None:
        return out + [img(3), ctl]
    refs, path, _ = cible(snap, portraits, folder, size)
    if not path.exists():
        out.append(img(len(refs)))
    if not path.with_suffix(".json").exists():
        out.append(ctl)
    return out


def _dessiner(snap, refs, path, size, q, folder):
    P.image_ok(path)
    rp = path.with_suffix(".json")
    if path.exists() and rp.exists():
        return json.loads(rp.read_text(encoding="utf-8"))
    if not path.exists():
        prompt = image_prompt(snap, refs)
        (Path(folder) / "prompts").mkdir(exist_ok=True)
        (Path(folder) / "prompts" / f"{path.stem}.txt").write_text(prompt, encoding="utf-8")
        P.image(prompt, refs, path, size, q, f"prompts/{path.stem}.txt", etape="illustration")
    v = P._vision(SYSTEM_OBJET, {"objet": snap["kind"], "personnages_attendus": snap["personnages"], "scene": KINDS[snap["kind"]]["scene"]}, path)
    r = {"retenu": path.name, "bloquants": v["bloquants"], "mineurs": v.get("mineurs", []), "controle_impossible": v.get("controle_impossible")}
    rp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def _kind(form):
    k = form.get("produit")
    if k not in KINDS:
        raise ObjetError(f"objet inconnu : {k}")
    return k


def run(form, cfg, refs, folder, job, progress):
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        return P.resume_finalise(folder)
    with P._Verrou(folder):
        livre = P.livre_id(folder)
        BU.PLAFONDS[livre] = PLAFOND
        jeton = BU.LIVRE.set(livre)
        try:
            return _run(form, cfg, refs, folder, job, progress, livre)
        finally:
            BU.LIVRE.reset(jeton)


def _run(form, cfg, refs, folder, job, progress, livre):
    def etat(e, step, pct):
        job["phase"] = e; progress(step, pct)
    def save(name, data):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    kind = _kind(form)
    etat("queued", "Format d'impression Printful", 3)
    P.disque_ok(folder)
    dep = BU.depense(livre)
    if dep["incertain"] > 0 or dep["reserve"] > 0:
        raise ObjetError("Appel(s) au résultat incertain pour cet objet : règle-les dans l'admin avant toute reprise.")
    try:
        spec = PF.specs_ou_defaut(KINDS[kind]["id"])            # AVANT tout appel payant : sans format, rien n'est généré
    except PF.PrintfulError as e:
        raise ObjetError(f"Format Printful introuvable ({e}) : rien n'a été généré")
    size = taille_image(spec["width"], spec["height"])
    snap = snapshot(form, cfg, kind, spec)
    ecarts = P.check_snapshot(snap, form)
    if ecarts:
        raise ObjetError("Les fiches ne correspondent pas à la commande : " + " ; ".join(ecarts))
    save("objet_instantane.json", dict(snap, taille_image=size))
    lignes, borne = BU.verifier_lancement(plan(cfg, folder, size), livre)
    save("budget.json", {"livre": livre, "plafond_usd": PLAFOND, "marge": BU.MARGE, "borne_lancement_usd": borne, "detail_lancement": lignes,
                         "deja_engage_usd": round(dep["total"], 4), "tarifs": BU.etat_tarifs()})
    etat("references", "Références des personnages", 15)
    portraits, rapport_refs = P.references(snap, cfg, refs, folder, lambda s: progress(s))
    save("references.json", rapport_refs)
    BU.verifier_lancement(plan(cfg, folder, size, snap, portraits), livre)
    etat("illustrating", f"Illustration de {KINDS[kind]['nom']}", 40)
    refs_i, path, q = cible(snap, portraits, folder, size)
    rapport = _dessiner(snap, refs_i, path, size, q, folder)
    etat("assembling", "Fichier d'impression", 90)
    fab = composer(folder, snap, path, spec)
    return conclure(folder, snap, spec, fab, rapport, rapport_refs, livre, job)


def conclure(folder, snap, spec, fab, rapport, rapport_refs, livre, job):
    import fabrication as F  # noqa
    folder = Path(folder)
    bloquants = [f"illustration : {x}" for x in rapport["bloquants"]]
    bloquants += [f"référence {k} : {x}" for k, v in rapport_refs.items() for x in v.get("bloquants", [])]
    impossibles = [f"contrôle visuel impossible ({rapport['controle_impossible']})"] if rapport.get("controle_impossible") else []
    mineurs = [f"illustration : {x}" for x in rapport.get("mineurs", [])]
    phase = "needs_review" if (bloquants or impossibles) else "ready"
    dep = BU.depense(livre) if livre else {"regle": 0}
    cout = round(dep["regle"], 4)
    obj = {"produit": "objet", "kind": snap["kind"], "titre": fab["titre"], "prenom": snap["prenom"], "pdf_lecture": fab["pdf"],
           "illustration": rapport.get("retenu") or Path(fab["impression"]).name, "impression": fab["impression"], "autres": fab["autres"],
           "apercu": fab["apercu"], "printful": {k: spec.get(k) for k in ("produit", "variante", "placement", "width", "height", "titre")}}
    (folder / "objet.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "controle.json").write_text(json.dumps({"etat": phase, "produit": "objet", "kind": snap["kind"], "instantane": snap["empreinte"],
                                                      "references": rapport_refs, "images": {"illustration": rapport}, "bloquants": bloquants,
                                                      "mineurs": mineurs, "controles_impossibles": impossibles, "cout_api_usd": cout, "budget": dep},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    job["phase"] = phase
    res = {"pdf": fab["pdf"], "titre": fab["titre"], "controle": bloquants + impossibles, "mineurs": mineurs, "pages": 1, "phase": phase, "cout": cout}
    if phase == "ready" and livre:
        finaliser(folder, res)
    return res


def finaliser(folder, res):
    import fabrication as F
    folder = Path(folder)
    obj = json.loads((folder / "objet.json").read_text(encoding="utf-8"))
    fichiers = [obj["pdf_lecture"], "objet.json", "objet_instantane.json", "controle.json", obj["impression"], obj["apercu"]] \
        + [a["fichier"] for a in obj["autres"]] + [p.name for p in folder.glob("obj-*.png")] + [p.name for p in folder.glob("portrait_*.png")] \
        + [x for x in ("references.json", "budget.json") if (folder / x).exists()]
    man = F.finaliser(folder, fichiers, {"produit": "objet", "kind": obj["kind"], "titre": res["titre"], "pdf_lecture": obj["pdf_lecture"],
                                         "pages": 1, "mineurs": res["mineurs"], "cout_api_usd": res["cout"],
                                         "appels_api": BU.appels(P.livre_id(folder)), "volumeNumber": None})
    try:
        F.sauvegarder(folder, Path(os.getenv("SAUVEGARDE_DIR") or BU.DATA / "sauvegardes"))
    except Exception as e:
        print("sauvegarde de l'objet impossible :", e)
    res["finalise"] = True
    return man


def finaliser_apres_relecture(folder):
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        return json.loads((folder / "final.json").read_text(encoding="utf-8"))
    obj = json.loads((folder / "objet.json").read_text(encoding="utf-8"))
    ctl = json.loads((folder / "controle.json").read_text(encoding="utf-8"))
    if not (folder / obj["impression"]).exists():
        raise ObjetError("Fichier d'impression absent : rien à finaliser")
    return finaliser(folder, {"titre": obj["titre"], "mineurs": ctl.get("mineurs", []) + ctl.get("bloquants", []), "cout": ctl.get("cout_api_usd")})


def recomposer(folder, form):
    """Admin : refait le fichier d'impression (format Printful relu) à partir de l'illustration enregistrée. Aucun appel IA."""
    import fabrication as F
    folder = Path(folder)
    if F.est_finalise(folder):
        raise ObjetError("Objet finalisé : ses fichiers sont figés")
    snap = json.loads((folder / "objet_instantane.json").read_text(encoding="utf-8"))
    illus = sorted(folder.glob(f"obj-{snap['kind']}-*.png"))
    if not illus:
        raise ObjetError("Illustration absente")
    spec = PF.specs_ou_defaut(KINDS[snap["kind"]]["id"], snap["printful"].get("variante"))
    fab = composer(folder, snap, illus[-1], spec)
    obj = json.loads((folder / "objet.json").read_text(encoding="utf-8"))
    obj.update(impression=fab["impression"], autres=fab["autres"], printful={k: spec.get(k) for k in ("produit", "variante", "placement", "width", "height", "titre")})
    (folder / "objet.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return fab


def items_printful(folder, url_de):
    """Ligne de commande Printful de cet objet : variante + fichiers (URL publiques secrètes)."""
    obj = json.loads((Path(folder) / "objet.json").read_text(encoding="utf-8"))
    pf = obj["printful"]
    files = [{"type": pf["placement"], "url": url_de(obj["impression"])}] + [{"type": a["placement"], "url": url_de(a["fichier"])} for a in obj["autres"]]
    return {"variant_id": pf["variante"], "quantity": 1, "name": obj["titre"][:100], "files": files}


def fichiers_maquette(folder, url_de):
    obj = json.loads((Path(folder) / "objet.json").read_text(encoding="utf-8"))
    pf = obj["printful"]
    files = [(pf["placement"], url_de(obj["impression"]), pf["width"], pf["height"])]
    for a in obj["autres"]:
        w, h = Image.open(Path(folder) / a["fichier"]).size
        files.append((a["placement"], url_de(a["fichier"]), w, h))
    return pf, files


def demo(form, cfg, folder, job, progress):
    folder = Path(folder)
    kind = _kind(form)
    progress("Mode démo : objet d'exemple, sans appel API", 40)
    spec = PF.specs_ou_defaut(KINDS[kind]["id"])
    snap = snapshot(form, cfg, kind, spec)
    (folder / "objet_instantane.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    illu = folder / f"obj-{kind}-demo.png"
    Image.open(ROOT / "kit" / "noe_demo" / "spread-2.jpg").convert("RGB").save(illu)
    fab = composer(folder, snap, illu, spec)
    return conclure(folder, snap, spec, fab, {"retenu": illu.name, "bloquants": [], "mineurs": []}, {}, None, job)
