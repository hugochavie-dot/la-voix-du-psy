"""Téléchargement HTTP poli des PDFs autorisés.

Caractéristiques :
- User-Agent identifiable (transparence),
- timeout généreux pour les gros PDF (~60 Mo),
- streaming par chunks (mémoire constante),
- délai configurable entre requêtes (pas de scraping agressif),
- vérification basique du Content-Type / magic bytes,
- compatible Windows/Mac/Linux (utilise `pathlib`).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from src.config_loader import Source

USER_AGENT = "psych-ia-ressources/1.0 (educational use; open-access only)"
DEFAULT_TIMEOUT = 90
DEFAULT_CHUNK = 1 << 15  # 32 KiB
DEFAULT_DELAY_SECONDS = 2.0
PDF_MAGIC = b"%PDF-"

logger = logging.getLogger("downloader")


@dataclass
class DownloadResult:
    """Résultat d'un téléchargement individuel."""

    source_id: str
    success: bool
    local_path: Path | None = None
    size_bytes: int = 0
    error: str | None = None


def _safe_filename(source: Source) -> str:
    """Nom de fichier portable basé sur l'id de la source."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in source.id)
    return f"{safe}.pdf"


def download_source(
    source: Source,
    *,
    dest_dir: Path,
    timeout: int = DEFAULT_TIMEOUT,
    chunk_size: int = DEFAULT_CHUNK,
    session: requests.Session | None = None,
) -> DownloadResult:
    """Télécharge un PDF unique vers `dest_dir`."""
    if not source.pdf_url:
        return DownloadResult(source.id, False, error="pdf_url manquante")

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / _safe_filename(source)
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"}

    try:
        logger.info("Téléchargement %s -> %s", source.id, target.name)
        with sess.get(source.pdf_url, headers=headers, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and "pdf" not in content_type and "octet-stream" not in content_type:
                logger.warning("Content-Type inattendu pour %s : %s", source.id, content_type)

            tmp = target.with_suffix(target.suffix + ".part")
            total = 0
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    total += len(chunk)
            tmp.replace(target)

        with target.open("rb") as fh:
            head = fh.read(8)
        if not head.startswith(PDF_MAGIC):
            target.unlink(missing_ok=True)
            return DownloadResult(source.id, False, error="fichier téléchargé non reconnu comme PDF")

        return DownloadResult(source.id, True, local_path=target, size_bytes=total)
    except requests.RequestException as exc:
        return DownloadResult(source.id, False, error=f"erreur HTTP : {exc}")
    except OSError as exc:
        return DownloadResult(source.id, False, error=f"erreur disque : {exc}")


def download_many(
    sources: list[Source],
    *,
    dest_dir: Path,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[DownloadResult]:
    """Télécharge en série avec un délai entre chaque source (politesse)."""
    results: list[DownloadResult] = []
    session = requests.Session()
    for i, src in enumerate(sources):
        if i > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)
        results.append(download_source(src, dest_dir=dest_dir, timeout=timeout, session=session))
    return results
