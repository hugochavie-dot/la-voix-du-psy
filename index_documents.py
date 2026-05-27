#!/usr/bin/env python3
"""
Indexe tous les documents éligibles (RAG) dans ChromaDB.
Usage: python scripts/index_documents.py [--force] [--document-id ID]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.enums import LegalStatus
from app.core.logging_config import setup_logging
from app.core.paths import ensure_project_dirs
from app.db.database import SessionLocal, init_db
from app.db.models import Document
from app.services.indexer import index_document
from app.services.legal_checker import is_rag_eligible

logger = setup_logging("index_documents")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Réindexer même si déjà fait")
    parser.add_argument("--document-id", type=int, help="Indexer un seul document")
    args = parser.parse_args()

    ensure_project_dirs()
    init_db()
    db = SessionLocal()
    success, errors, skipped = 0, 0, 0

    try:
        q = db.query(Document)
        if args.document_id:
            q = q.filter(Document.id == args.document_id)
        docs = q.all()

        for doc in docs:
            status = LegalStatus(doc.legal_status)
            if not is_rag_eligible(status):
                logger.warning("Document %s ignoré (legal=%s)", doc.id, doc.legal_status)
                skipped += 1
                continue

            job = index_document(db, doc.id, force=args.force)
            if job.status == "success":
                success += 1
            else:
                errors += 1
                logger.error("Document %s: %s", doc.id, job.message)
    finally:
        db.close()

    logger.info("Indexation — success=%d errors=%d skipped=%d", success, errors, skipped)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
