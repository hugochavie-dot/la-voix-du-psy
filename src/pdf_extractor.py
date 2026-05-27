"""Extraction de texte brut à partir d'un PDF avec `pypdf`.

Le texte est nettoyé minimalement (lignes vides multiples → simple).
Les sauts de page ne sont pas conservés ; les chunks ultérieurs sont basés
sur les caractères.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger("pdf_extractor")


@dataclass
class ExtractionResult:
    """Résultat d'extraction d'un PDF."""

    source_id: str
    pdf_path: Path
    text_path: Path | None
    n_pages: int
    n_chars: int
    error: str | None = None


_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANKLINE_RE = re.compile(r"\n{3,}")


def _clean(raw: str) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", raw)
    cleaned = _BLANKLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def extract_text(pdf_path: Path, *, dest_dir: Path, source_id: str) -> ExtractionResult:
    """Extrait le texte du PDF et le sauvegarde dans `dest_dir/<source_id>.txt`."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{source_id}.txt"
    try:
        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # noqa: BLE001 — résilience PDF
                logger.warning("Page illisible dans %s : %s", pdf_path.name, exc)
                pages.append("")
        text = _clean("\n\n".join(pages))
        out.write_text(text, encoding="utf-8")
        return ExtractionResult(
            source_id=source_id,
            pdf_path=pdf_path,
            text_path=out,
            n_pages=len(reader.pages),
            n_chars=len(text),
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(
            source_id=source_id,
            pdf_path=pdf_path,
            text_path=None,
            n_pages=0,
            n_chars=0,
            error=f"extraction PDF échouée : {exc}",
        )
