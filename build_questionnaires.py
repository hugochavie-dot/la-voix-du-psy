#!/usr/bin/env python3
"""Génère les questionnaires patients HTML par thème."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.questionnaires_exporter import (
    DATA_PATH,
    QUESTIONNAIRES_DIR,
    build_questionnaires_site,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export HTML des questionnaires patients par thème"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help=f"Fichier JSON source (défaut: {DATA_PATH.name})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=QUESTIONNAIRES_DIR,
        help=f"Dossier de sortie (défaut: {QUESTIONNAIRES_DIR})",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Ne pas effacer le dossier de sortie avant export",
    )
    args = parser.parse_args()

    report = build_questionnaires_site(
        data_path=args.data,
        output_dir=args.output,
        clean=not args.no_clean,
    )

    print(f"\nQuestionnaires : {report.output_dir.resolve()}")
    print(f"  → Ouvrir : {report.output_dir / 'index.html'}")
    print(f"  Thèmes exportés : {len(report.built)}")
    for e in report.built:
        print(f"    · {e.titre} ({e.notion_liee}) → {e.href}")

    return 0 if report.built else 1


if __name__ == "__main__":
    raise SystemExit(main())
