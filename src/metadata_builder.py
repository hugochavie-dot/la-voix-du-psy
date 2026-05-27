"""Construction des métadonnées JSON par source.

Chaque source produit un fichier `data/metadata/<id>.json` traçant :
identifiants, URLs, statut légal, statut de pipeline, chemin local, erreurs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config_loader import Source
from src.downloader import DownloadResult
from src.source_validator import ValidationResult


@dataclass
class Metadata:
    """Métadonnées d'une source, sérialisable en JSON."""

    id: str
    title: str
    url: str | None
    pdf_url: str | None
    document_type: str
    level: str
    subject: str
    legal_status: str
    license: str | None
    enabled: bool
    download: bool
    downloaded: bool
    local_path: str | None
    notes: str | None
    date_processed: str
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "document_type": self.document_type,
            "level": self.level,
            "subject": self.subject,
            "legal_status": self.legal_status,
            "license": self.license,
            "enabled": self.enabled,
            "download": self.download,
            "downloaded": self.downloaded,
            "local_path": self.local_path,
            "notes": self.notes,
            "date_processed": self.date_processed,
            "status": self.status,
            "error": self.error,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_metadata(
    source: Source,
    validation: ValidationResult,
    download: DownloadResult | None,
    *,
    project_root: Path,
) -> Metadata:
    """Construit l'objet `Metadata` à partir des résultats de validation et de
    téléchargement éventuel."""
    downloaded = bool(download and download.success)
    local_path: str | None = None
    if downloaded and download and download.local_path:
        try:
            local_path = str(download.local_path.relative_to(project_root))
        except ValueError:
            local_path = str(download.local_path)

    final_status = validation.status
    if downloaded:
        final_status = "downloaded"
    elif download and not download.success:
        final_status = "error"

    return Metadata(
        id=source.id,
        title=source.title,
        url=source.url,
        pdf_url=source.pdf_url,
        document_type=source.document_type,
        level=source.level,
        subject=source.subject,
        legal_status=source.legal_status,
        license=source.license,
        enabled=source.enabled,
        download=source.download,
        downloaded=downloaded,
        local_path=local_path,
        notes=source.notes,
        date_processed=_now_iso(),
        status=final_status,
        error=download.error if (download and not download.success) else None,
    )


def write_metadata(metadata: Metadata, dest_dir: Path) -> Path:
    """Sérialise une `Metadata` vers `data/metadata/<id>.json`."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{metadata.id}.json"
    target.write_text(
        json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
