#!/usr/bin/env bash
# Lance l'API Psych IA Ressources
set -euo pipefail
cd "$(dirname "$0")"
if [[ -d .venv ]]; then
  source .venv/bin/activate
fi
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
