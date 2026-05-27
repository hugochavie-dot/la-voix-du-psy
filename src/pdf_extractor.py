"""Extraction de texte depuis les PDF téléchargés (pypdf)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader


def extract_pdf_text(pdf_path: Path, texts_dir: Path, *, dry_run: bool = False) -> tuple[Path | None, str | None]:
    """
    Extrait le texte brut d'un PDF et le sauvegarde dans data/rag_ready/texts/.

    Retourne (chemin_texte, message_erreur).
    """
    if not pdf_path.is_file():
        return None, f"PDF introuvable : {pdf_path}"

    dest = texts_dir / f"{pdf_path.stem}.txt"
    if dry_run:
        return dest, None

    texts_dir.mkdir(parents=True, exist_ok=True)
    try:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
        full_text = "\n\n".join(parts).strip()
        if not full_text:
            return None, "aucun texte extrait du PDF"
        dest.write_text(full_text, encoding="utf-8")
        return dest, None
    except Exception as exc:  # noqa: BLE001 — erreur documentaire variée
        return None, str(exc)


def load_text(text_path: Path) -> str:
    """Charge un fichier texte extrait."""
    return text_path.read_text(encoding="utf-8")


def source_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Reconstruit un dict source minimal depuis une métadonnée."""
    return {
        "id": metadata.get("id"),
        "title": metadata.get("title"),
        "url": metadata.get("url"),
        "pdf_url": metadata.get("pdf_url"),
        "document_type": metadata.get("document_type"),
        "level": metadata.get("level"),
        "subject": metadata.get("subject"),
        "legal_status": metadata.get("legal_status"),
        "license": metadata.get("license"),
    }
