"""Écriture des index globaux (CSV + JSON) et de la liste `to_verify`."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.metadata_builder import Metadata
from src.source_validator import (
    STATUS_TO_VERIFY,
    ValidationResult,
)

INDEX_FIELDS = [
    "id",
    "title",
    "status",
    "level",
    "subject",
    "document_type",
    "legal_status",
    "license",
    "enabled",
    "download",
    "downloaded",
    "url",
    "pdf_url",
    "local_path",
    "error",
]


def write_index(metadatas: list[Metadata], *, csv_path: Path, json_path: Path) -> None:
    """Écrit l'index global au format CSV et JSON."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [m.to_dict() for m in metadatas]

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in INDEX_FIELDS})

    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_to_verify(results: list[ValidationResult], *, csv_path: Path) -> int:
    """Liste les sources nécessitant une vérification manuelle (motifs bloqués,
    domaine inconnu, pdf_url manquante…)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    flagged = [r for r in results if r.status == STATUS_TO_VERIFY]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "title", "raisons", "url", "pdf_url"])
        for r in flagged:
            writer.writerow(
                [
                    r.source.id,
                    r.source.title,
                    " ; ".join(r.reasons),
                    r.source.url or "",
                    r.source.pdf_url or "",
                ]
            )
    return len(flagged)
