"""Génération des index CSV/JSON et liste des sources à vérifier."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

INDEX_FIELDS = [
    "id",
    "title",
    "status",
    "enabled",
    "download",
    "legal_status",
    "license",
    "document_type",
    "level",
    "subject",
    "url",
    "pdf_url",
    "downloaded",
    "local_path",
    "notes",
    "error",
    "reasons",
]


def _row_from_record(record: dict[str, Any], reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "status": record.get("status"),
        "enabled": record.get("enabled"),
        "download": record.get("download"),
        "legal_status": record.get("legal_status"),
        "license": record.get("license"),
        "document_type": record.get("document_type"),
        "level": record.get("level"),
        "subject": record.get("subject"),
        "url": record.get("url"),
        "pdf_url": record.get("pdf_url"),
        "downloaded": record.get("downloaded"),
        "local_path": record.get("local_path"),
        "notes": record.get("notes"),
        "error": record.get("error"),
        "reasons": "; ".join(reasons or []),
    }


def write_indexes(
    data_dir: Path,
    records: list[dict[str, Any]],
    reasons_map: dict[str, list[str]],
    *,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Crée index_resources.csv, index_resources.json et to_verify/sources_a_verifier.csv."""
    rows = [_row_from_record(r, reasons_map.get(str(r.get("id")), [])) for r in records]

    paths = {
        "csv": data_dir / "index_resources.csv",
        "json": data_dir / "index_resources.json",
        "to_verify": data_dir / "to_verify" / "sources_a_verifier.csv",
    }

    if dry_run:
        return paths

    data_dir.mkdir(parents=True, exist_ok=True)
    paths["to_verify"].parent.mkdir(parents=True, exist_ok=True)

    with paths["csv"].open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with paths["json"].open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    verify_rows = [row for row in rows if row["status"] in {"to_verify", "error"}]
    with paths["to_verify"].open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(verify_rows)

    return paths
