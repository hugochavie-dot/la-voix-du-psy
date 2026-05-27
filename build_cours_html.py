#!/usr/bin/env python3
"""Génère le site HTML des cours à partir des documents en base."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.database import SessionLocal, init_db
from app.services.html_exporter import OUTPUT_DIR, build_cours_site


def main() -> int:
    parser = argparse.ArgumentParser(description="Export HTML des cours (PDF → site statique)")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Dossier de sortie (défaut: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--document-id",
        type=int,
        action="append",
        dest="document_ids",
        help="Exporter uniquement ces IDs (répétable)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limiter le nombre de pages par PDF (utile pour tests)",
    )
    parser.add_argument(
        "--include-non-eligible",
        action="store_true",
        help="Inclure les documents unknown/rejected (déconseillé)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Ne pas effacer le dossier de sortie avant export",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        report = build_cours_site(
            db,
            output_dir=args.output,
            document_ids=args.document_ids,
            max_pages=args.max_pages,
            include_non_eligible=args.include_non_eligible,
            clean=not args.no_clean,
        )
    finally:
        db.close()

    print(f"\nSite généré : {report.output_dir.resolve()}")
    print(f"  → Ouvrir : {report.output_dir / 'index.html'}")
    print(f"  Cours exportés : {len(report.built)}")
    for e in report.built:
        print(f"    · [{e.document_id}] {e.title} ({e.page_count} p., {e.part_count} partie(s))")

    if report.skipped:
        print(f"  Ignorés : {len(report.skipped)}")
        for s in report.skipped:
            print(f"    · [{s['id']}] {s['title']}: {s['reason']}")

    return 0 if report.built else 1


if __name__ == "__main__":
    raise SystemExit(main())
