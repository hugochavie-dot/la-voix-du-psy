#!/usr/bin/env python3
"""Génère les résumés et fiches de révision HTML à partir des documents en base."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.database import SessionLocal, init_db
from app.services.fiches_exporter import FICHES_DIR, RESUMES_DIR, build_fiches_resume_site


def main() -> int:
    parser = argparse.ArgumentParser(description="Export HTML résumés + fiches")
    parser.add_argument(
        "--document-id",
        type=int,
        action="append",
        dest="document_ids",
        help="Exporter uniquement ces IDs (répétable)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Ne pas effacer les dossiers de sortie avant export",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        report = build_fiches_resume_site(
            db,
            document_ids=args.document_ids,
            clean=not args.no_clean,
        )
    finally:
        db.close()

    print(f"\nRésumés : {RESUMES_DIR.resolve()}")
    print(f"  → {len(report.resumes)} résumé(s)")
    for r in report.resumes:
        print(f"    · [{r.document_id}] {r.title}")

    print(f"\nFiches : {FICHES_DIR.resolve()}")
    print(f"  → {len(report.fiches)} fiche(s)")
    for f in report.fiches[:5]:
        print(f"    · Ch. {f.chapter_num} {f.title}")
    if len(report.fiches) > 5:
        print(f"    · … et {len(report.fiches) - 5} autres")

    if report.skipped:
        print(f"\nIgnorés / partiels : {len(report.skipped)}")
        for s in report.skipped:
            print(f"    · [{s['id']}] {s['title']}: {s['reason']}")

    return 0 if report.resumes or report.fiches else 1


if __name__ == "__main__":
    raise SystemExit(main())
