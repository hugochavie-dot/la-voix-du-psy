"""Extraction de métadonnées depuis PDF et texte."""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from app.core.enums import Difficulty, DocumentType, LegalStatus, Level, Subject
from app.core.logging_config import setup_logging
from app.services.classifier import (
    classify_from_text,
    extract_year,
    suggest_document_type,
)

logger = setup_logging("metadata_extractor")


def extract_text_from_pdf(path: Path, max_pages: int | None = None) -> list[tuple[int, str]]:
    """Extrait le texte page par page."""
    pages: list[tuple[int, str]] = []
    try:
        doc = fitz.open(path)
        limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        for i in range(limit):
            page = doc[i]
            text = page.get_text("text") or ""
            pages.append((i + 1, text))
        doc.close()
    except Exception as e:
        logger.error("Erreur lecture PDF %s: %s", path, e)
        raise
    return pages


def extract_pdf_metadata(path: Path) -> dict:
    """Métadonnées PDF + classification."""
    pages = extract_text_from_pdf(path, max_pages=5)
    full_sample = "\n".join(t for _, t in pages)[:15000]
    title = path.stem.replace("_", " ")

    try:
        doc = fitz.open(path)
        meta = doc.metadata or {}
        if meta.get("title"):
            title = meta["title"]
        author = meta.get("author")
        doc.close()
    except Exception:
        author = None

    doc_type = suggest_document_type(path.name, "", full_sample)
    level, subject, difficulty = classify_from_text(title, full_sample, doc_type)
    year = extract_year(full_sample) or extract_year(path.name)

    keywords = _extract_keywords(full_sample)
    summary_short = _short_summary(full_sample)
    summary_ped = _pedagogical_summary(full_sample, title)

    return {
        "title": title,
        "author": author,
        "year": year,
        "document_type": doc_type.value,
        "level": level.value,
        "subject": subject.value,
        "difficulty": difficulty.value,
        "keywords": ", ".join(keywords),
        "summary_short": summary_short,
        "summary_pedagogical": summary_ped,
        "language": _detect_language(full_sample),
        "file_format": path.suffix.lstrip(".") or "pdf",
        "text_pages": pages,
    }


def _extract_keywords(text: str, max_kw: int = 12) -> list[str]:
    """Mots-clés simples par fréquence (hors stopwords basiques)."""
    stops = {
        "dans", "pour", "avec", "cette", "comme", "plus", "sont", "être",
        "the", "and", "that", "des", "les", "une", "par", "sur",
    }
    words = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in stops:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:max_kw]]


def _short_summary(text: str, max_len: int = 400) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def _pedagogical_summary(text: str, title: str) -> str:
    """Résumé pédagogique heuristique (à enrichir par LLM externe si besoin)."""
    intro = _short_summary(text, 600)
    return (
        f"Document « {title} » — ressource pédagogique de psychologie. "
        f"Points abordés (extrait) : {intro}"
    )


def _detect_language(text: str) -> str:
    fr_markers = ["psychologie", "mémoire", "cours", "étudiant", "licence"]
    en_markers = ["psychology", "memory", "chapter", "student"]
    t = text.lower()[:3000]
    fr = sum(1 for m in fr_markers if m in t)
    en = sum(1 for m in en_markers if m in t)
    return "fr" if fr >= en else "en"
