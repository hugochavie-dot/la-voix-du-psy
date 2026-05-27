#!/usr/bin/env python3
"""
Télécharge les sources définies dans config/sources.json.
Usage: python scripts/download_sources.py [--dry-run] [--only-id ID]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ajouter la racine projet au path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.logging_config import setup_logging
from app.core.paths import ensure_project_dirs, sources_config_path
from app.db.database import SessionLocal, init_db
from app.services.source_manager import add_source_from_url

logger = setup_logging("download_sources")


def load_sources_config() -> list[dict]:
    path = sources_config_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Télécharger les sources autorisées")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans télécharger")
    parser.add_argument("--only-id", type=str, help="Traiter une seule entrée par id")
    args = parser.parse_args()

    ensure_project_dirs()
    init_db()
    sources = load_sources_config()

    if args.only_id:
        sources = [s for s in sources if s.get("id") == args.only_id]

    db = SessionLocal()
    ok, skip, err = 0, 0, 0

    try:
        for entry in sources:
            sid = entry.get("id", "?")
            if not entry.get("enabled", True):
                logger.info("[%s] désactivé — ignoré", sid)
                skip += 1
                continue

            url = entry.get("url")
            if not url:
                logger.info("[%s] pas d'URL (référence locale) — ignoré", sid)
                skip += 1
                continue

            if entry.get("download") is False and not entry.get("pdf_url"):
                logger.info("[%s] download=false — ignoré", sid)
                skip += 1
                continue

            if args.dry_run:
                print(f"[DRY] {sid}: {url} → legal={entry.get('legal_status')}")
                continue

            logger.info("Traitement [%s] %s", sid, url)
            try:
                from app.core.enums import Level, Subject

                level = Level(entry["level"]) if entry.get("level") else None
                subject = Subject(entry["subject"]) if entry.get("subject") else None
                user_auth = entry.get("legal_status") == "authorized"

                add_source_from_url(
                    db,
                    url,
                    title=entry.get("title"),
                    level=level,
                    subject=subject,
                    user_authorized=user_auth or entry.get("user_authorized", False),
                    auto_index=entry.get("auto_index", True),
                    pdf_url=entry.get("pdf_url"),
                )
                ok += 1
            except Exception as e:
                logger.error("[%s] erreur: %s", sid, e)
                err += 1
    finally:
        db.close()

    logger.info("Terminé — ok=%d skip=%d err=%d", ok, skip, err)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
