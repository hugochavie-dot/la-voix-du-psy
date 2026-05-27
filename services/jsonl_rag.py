"""Recherche RAG sur rag_chunks.jsonl (OpenStax et autres sources indexées)."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.core.logging_config import setup_logging
from config.settings import settings

logger = setup_logging("jsonl_rag")

_FRENCH_STOPWORDS = {
    "a", "ai", "aie", "as", "au", "aux", "avec", "ce", "ces", "d", "dans", "de",
    "des", "du", "elle", "en", "es", "est", "et", "eu", "eux", "il", "ils", "je",
    "la", "le", "les", "leur", "lui", "ma", "mais", "me", "mes", "moi", "mon",
    "ne", "nos", "notre", "nous", "on", "ou", "par", "pas", "pour", "que", "qui",
    "quoi", "sa", "se", "ses", "son", "sur", "ta", "te", "tes", "toi", "ton",
    "tu", "un", "une", "vos", "votre", "vous", "y", "the", "and", "or", "to",
    "of", "in", "is", "it", "that", "this", "for", "are", "was", "be", "on",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9\u00e0-\u024f]{3,}", _normalize(text))
    return [t for t in tokens if t not in _FRENCH_STOPWORDS]


@lru_cache(maxsize=1)
def _load_chunks(path: str) -> tuple[list[dict], dict[str, dict]]:
    """Charge le JSONL en mémoire (cache process)."""
    file_path = Path(path)
    if not file_path.is_file():
        logger.warning("Fichier RAG introuvable : %s", file_path)
        return [], {}

    chunks: list[dict] = []
    by_id: dict[str, dict] = {}
    with file_path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Ligne %s invalide : %s", line_no, exc)
                continue
            record["_tokens"] = set(_tokenize(record.get("chunk_text", "")))
            chunks.append(record)
            chunk_id = record.get("chunk_id")
            if chunk_id:
                by_id[chunk_id] = record

    logger.info("RAG JSONL chargé : %s chunks depuis %s", len(chunks), file_path)
    return chunks, by_id


def reload_chunks() -> int:
    """Force le rechargement du cache (utile après réindexation)."""
    _load_chunks.cache_clear()
    chunks, _ = _load_chunks(str(settings.rag_chunks_path))
    return len(chunks)


def search_jsonl_rag(
    query: str,
    *,
    n_results: int = 5,
    level: str | None = None,
    source_id: str | None = None,
) -> list[dict]:
    """
    Recherche par recouvrement lexical (sans dépendance lourde).
    Retourne les chunks triés par score décroissant.
    """
    chunks, _ = _load_chunks(str(settings.rag_chunks_path))
    if not chunks:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_set = set(query_tokens)
    scored: list[tuple[float, dict]] = []

    for chunk in chunks:
        if level and chunk.get("level") not in (level, "mixte", None):
            continue
        if source_id and chunk.get("source_id") != source_id:
            continue

        chunk_tokens = chunk.get("_tokens") or set()
        if not chunk_tokens:
            continue

        overlap = query_set & chunk_tokens
        if not overlap:
            continue

        score = len(overlap) / len(query_set)
        # Bonus si plusieurs tokens rares matchent
        score += len(overlap) * 0.05
        # Bonus phrase longue dans le message utilisateur
        normalized_text = _normalize(chunk.get("chunk_text", ""))
        for token in query_tokens:
            if len(token) >= 6 and token in normalized_text:
                score += 0.1

        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)

    results: list[dict] = []
    seen_ids: set[str] = set()
    for score, chunk in scored:
        chunk_id = chunk.get("chunk_id", "")
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        results.append({
            "score": round(score, 4),
            "chunk_id": chunk.get("chunk_id"),
            "source_id": chunk.get("source_id"),
            "title": chunk.get("title"),
            "subject": chunk.get("subject"),
            "level": chunk.get("level"),
            "license": chunk.get("license"),
            "url": chunk.get("url"),
            "chunk_number": chunk.get("chunk_number"),
            "text": chunk.get("chunk_text", ""),
        })
        if len(results) >= n_results:
            break

    return results
