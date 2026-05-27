"""Construction des fichiers de métadonnées par source."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_metadata_record(
    source: dict[str, Any],
    *,
    index_status: str,
    downloaded: bool = False,
    local_path: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Construit le dictionnaire de métadonnées normalisé."""
    return {
        "id": source.get("id"),
        "title": source.get("title"),
        "url": source.get("url"),
        "pdf_url": source.get("pdf_url"),
        "document_type": source.get("document_type"),
        "level": source.get("level"),
        "subject": source.get("subject"),
        "legal_status": source.get("legal_status"),
        "license": source.get("license"),
        "enabled": source.get("enabled"),
        "download": source.get("download"),
        "downloaded": downloaded,
        "local_path": local_path,
        "notes": source.get("notes"),
        "date_processed": _utc_now(),
        "status": index_status,
        "error": error,
    }


def write_metadata(metadata_dir: Path, record: dict[str, Any], *, dry_run: bool = False) -> Path:
    """Écrit data/metadata/{id}.json."""
    source_id = str(record["id"])
    dest = metadata_dir / f"{source_id}.json"
    if not dry_run:
        metadata_dir.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
    return dest
