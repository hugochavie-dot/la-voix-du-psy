"""Téléchargement sécurisé des PDF open access."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_DELAY_SECONDS = 2.0
DEFAULT_TIMEOUT = 120
CHUNK_SIZE = 8192
USER_AGENT = (
    "PsychIARessources/1.0 (+https://github.com/local/psych-ia-ressources; "
    "open-access educational pipeline)"
)


def download_pdf(
    source: dict[str, Any],
    dest_dir: Path,
    *,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    dry_run: bool = False,
) -> tuple[Path | None, str | None]:
    """
    Télécharge le PDF d'une source validée.

    Retourne (chemin_local, message_erreur).
    """
    pdf_url = source.get("pdf_url")
    if not pdf_url:
        return None, "pdf_url absente"

    source_id = str(source.get("id", "document"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{source_id}.pdf"

    if dry_run:
        return dest_path, None

    headers = {"User-Agent": USER_AGENT}
    try:
        time.sleep(delay_seconds)
        with requests.get(str(pdf_url), headers=headers, stream=True, timeout=DEFAULT_TIMEOUT) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not str(pdf_url).lower().endswith(".pdf"):
                return None, f"type de contenu inattendu : {content_type or 'inconnu'}"

            with dest_path.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        out.write(chunk)

        if dest_path.stat().st_size < 1024:
            dest_path.unlink(missing_ok=True)
            return None, "fichier téléchargé trop petit (probable erreur HTML)"

        return dest_path, None
    except requests.RequestException as exc:
        return None, str(exc)
