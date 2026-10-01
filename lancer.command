#!/bin/bash
# Double-clic sur Mac : installe ce qu'il faut au premier lancement puis ouvre le site
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
(sleep 2 && open http://localhost:8000) &
python app.py
