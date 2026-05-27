"""Découpage du texte en chunks RAG (800–1200 caractères)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

MIN_CHUNK = 800
MAX_CHUNK = 1200


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, *, min_size: int = MIN_CHUNK, max_size: int = MAX_CHUNK) -> list[str]:
    """
    Découpe un texte en segments de 800 à 1200 caractères environ.

    Privilégie les coupures en fin de phrase.
    """
    text = _normalize_whitespace(text)
    if not text:
        return []

    if len(text) <= max_size:
        return [text]

    sentences = _split_sentences(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = sentence
        else:
            # phrase unique trop longue : coupe dure
            start = 0
            while start < len(sentence):
                chunks.append(sentence[start : start + max_size])
                start += max_size
            current = ""

        if len(current) >= min_size:
            chunks.append(current)
            current = ""

    if current:
        if chunks and len(current) < min_size // 2:
            chunks[-1] = f"{chunks[-1]} {current}".strip()
        else:
            chunks.append(current)

    return [c for c in chunks if c.strip()]


def iter_rag_records(source: dict[str, Any], chunks: list[str]) -> Iterator[dict[str, Any]]:
    """Génère les enregistrements JSONL pour chaque chunk."""
    source_id = str(source.get("id", "source"))
    for index, chunk in enumerate(chunks, start=1):
        yield {
            "chunk_id": f"{source_id}_{index:04d}",
            "source_id": source_id,
            "title": source.get("title"),
            "subject": source.get("subject"),
            "level": source.get("level"),
            "document_type": source.get("document_type"),
            "license": source.get("license"),
            "url": source.get("url"),
            "chunk_number": index,
            "chunk_text": chunk,
        }


def write_rag_jsonl(
    records: list[dict[str, Any]],
    dest: Path,
    *,
    dry_run: bool = False,
) -> Path:
    """Écrit data/rag_ready/rag_chunks.jsonl (append si fichier existant en mode réel)."""
    if dry_run:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return dest


def append_rag_jsonl(records: list[dict[str, Any]], dest: Path) -> None:
    """Ajoute des lignes au fichier JSONL global."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
