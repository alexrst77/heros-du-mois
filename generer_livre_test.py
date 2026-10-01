# -*- coding: utf-8 -*-
"""Génère un livre test complet avec la VRAIE API OpenAI, à partir d'une configuration enregistrée.
Usage : python3 generer_livre_test.py tests/config_jeade.json
Les validations du parent sont automatiques pour ce test ; le résultat doit ensuite être relu (revue humaine)."""
import os, sys, json, shutil
from pathlib import Path
ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
os.environ["AUTO_VALIDATE"] = "1"
import app, generator

payload = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tests" / "config_jeade.json").read_text(encoding="utf-8"))
form = {k: str(payload[k]) for k in ("prenom", "age", "genre", "theme", "univers") if k in payload}
form["avatar"] = generator.sanitize_avatar(payload["avatar"], generator._name(form["prenom"]), form["age"])
job = "livre_test_" + generator._fold(form["prenom"])
folder = app.OUT / job; shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
app.JOBS[job] = {"etat": "en_cours"}
print("Génération en cours (10 à 15 minutes)…")
app.run(job, form, {})
j = app.JOBS[job]
print("État :", j["etat"], j.get("erreur", ""))
if j["etat"] == "termine":
    print("PDF :", folder / j["pdf"])
    print("À corriger :", " aucun" if not j.get("controle") else "\n - " + "\n - ".join(j["controle"]))
    print(f"Détails mineurs (image gardée) : {len(j.get('mineurs', []))}, voir controle.json")
    print("Dossier à m'envoyer (compressé) :", folder)
