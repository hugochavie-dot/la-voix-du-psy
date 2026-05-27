"""Initialisation au démarrage Render — télécharge les PDFs si absents.

Exécuté avant le démarrage d'uvicorn (cf. Dockerfile CMD).
- Si `data/downloads/openstax_psychology_2e.pdf` est manquant, relance le
  pipeline `main.py` qui télécharge, extrait et chunke en RAG.
- Si tout est déjà présent, sort immédiatement (idempotent).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "downloads" / "openstax_psychology_2e.pdf"
SOURCES = ROOT / "sources.json"


def main() -> int:
    if PDF.exists() and PDF.stat().st_size > 1_000_000:
        print(f"[init] PDF déjà présent ({PDF.stat().st_size // 1024 // 1024} Mo) — skip")
        return 0

    if not SOURCES.exists():
        print(f"[init] sources.json introuvable : {SOURCES}", file=sys.stderr)
        return 0

    print("[init] PDF manquant — lancement du pipeline main.py …")
    result = subprocess.run(
        [sys.executable, "main.py", "--sources", "sources.json", "--output", "data"],
        cwd=str(ROOT),
        check=False,
    )
    if result.returncode != 0:
        print(f"[init] main.py a échoué (code {result.returncode}) — l'app démarre malgré tout", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
