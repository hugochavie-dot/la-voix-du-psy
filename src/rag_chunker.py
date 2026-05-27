"""Découpe le texte en chunks RAG (800–1200 caractères) avec recouvrement.

Le découpage privilégie les frontières naturelles (fin de paragraphe, fin
de phrase) pour éviter de couper au milieu d'une idée.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.config_loader import Source

MIN_CHARS = 800
MAX_CHARS = 1200
OVERLAP_CHARS = 100


@dataclass
class Chunk:
    """Un fragment de texte enrichi des métadonnées de la source."""

    chunk_id: str
    source_id: str
    title: str
    subject: str
    level: str
    document_type: str
    license: str | None
    url: str | None
    chunk_number: int
    chunk_text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "title": self.title,
            "subject": self.subject,
            "level": self.level,
            "document_type": self.document_type,
            "license": self.license,
            "url": self.url,
            "chunk_number": self.chunk_number,
            "chunk_text": self.chunk_text,
        }


def _find_breakpoint(text: str, start: int, hard_end: int) -> int:
    """Trouve un point de coupe propre entre `start+MIN_CHARS` et `hard_end`."""
    soft_start = start + MIN_CHARS
    if soft_start >= hard_end:
        return hard_end
    window = text[soft_start:hard_end]
    for sep in ("\n\n", "\n", ". ", "? ", "! ", "; "):
        idx = window.rfind(sep)
        if idx != -1:
            return soft_start + idx + len(sep)
    return hard_end


def chunk_text(text: str) -> list[str]:
    """Découpe `text` en chunks de longueur cible 800–1200 avec léger overlap."""
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        hard_end = min(i + MAX_CHARS, n)
        if hard_end - i <= MAX_CHARS and hard_end == n:
            chunks.append(text[i:hard_end].strip())
            break
        end = _find_breakpoint(text, i, hard_end)
        chunks.append(text[i:end].strip())
        if end >= n:
            break
        i = max(end - OVERLAP_CHARS, end)
    return [c for c in chunks if c]


def build_chunks(source: Source, text: str) -> list[Chunk]:
    """Construit les `Chunk` enrichis pour une source donnée."""
    out: list[Chunk] = []
    for n, piece in enumerate(chunk_text(text), start=1):
        out.append(
            Chunk(
                chunk_id=f"{source.id}_{n:04d}",
                source_id=source.id,
                title=source.title,
                subject=source.subject,
                level=source.level,
                document_type=source.document_type,
                license=source.license,
                url=source.url,
                chunk_number=n,
                chunk_text=piece,
            )
        )
    return out


def write_jsonl(chunks: Iterable[Chunk], dest: Path) -> int:
    """Écrit (ou réécrit) les chunks dans un fichier JSONL et retourne le nombre."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with dest.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count
