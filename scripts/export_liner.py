#!/usr/bin/env python3
"""Exporte les cours vers output/liner/ pour import dans Liner (liner.com)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.liner_exporter import OUTPUT_DIR, export_for_liner


def main() -> int:
    report = export_for_liner()
    print(f"\nExport Liner : {report.output_dir.resolve()}")
    print(f"  PDF  : {len(report.pdf_files)} module(s) → dossier pdf/")
    print(f"  MD   : {len(report.markdown_files)} fichier(s) → dossier markdown/")
    print("\nImport dans Liner :")
    print("  1. Ouvrir https://liner.com → My Space")
    print("  2. Uploader les PDF depuis output/liner/pdf/")
    print("  3. Surligner et poser des questions à l'IA Liner sur vos cours")
    return 0 if report.pdf_files else 1


if __name__ == "__main__":
    raise SystemExit(main())
