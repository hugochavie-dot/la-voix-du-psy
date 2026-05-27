"""Orchestration : ajout source → légal → téléchargement → métadonnées → DB."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.enums import DocumentType, LegalStatus, Level, Subject
from app.core.logging_config import setup_logging
from app.db.models import Document, Source
from app.services.classifier import classify_from_text, suggest_document_type
from app.services.downloader import (
    DownloadRejected,
    copy_local_file,
    download_pdf_from_url,
    fetch_page_metadata,
)
from app.services.legal_checker import check_local_file, check_url_legal
from app.services.metadata_extractor import extract_pdf_metadata
from app.services.indexer import index_document

logger = setup_logging("source_manager")


def add_source_from_url(
    db: Session,
    url: str,
    *,
    title: str | None = None,
    level: Level | None = None,
    subject: Subject | None = None,
    document_type: DocumentType | None = None,
    user_authorized: bool = False,
    user_created: bool = False,
    auto_index: bool = True,
    pdf_url: str | None = None,
) -> Source:
    """Pipeline complet pour une URL."""
    existing = db.query(Source).filter(Source.url == url).first()
    if existing:
        existing.is_duplicate = True
        db.commit()
        logger.info("URL déjà présente: %s", url)
        return existing

    page_title, page_text = "", ""
    try:
        page_title, page_text = fetch_page_metadata(url)
    except Exception as e:
        logger.warning("Impossible de lire la page: %s", e)

    legal = check_url_legal(
        url,
        page_text=page_text,
        user_authorized=user_authorized,
        user_created=user_created,
    )

    doc_type = document_type or suggest_document_type("", url, page_text)
    inferred_level, inferred_subject, _ = classify_from_text(
        title or page_title or url, page_text, doc_type, url
    )
    lvl = level or inferred_level
    subj = subject or inferred_subject

    source = Source(
        url=url,
        title=title or page_title,
        document_type=doc_type.value,
        level=lvl.value,
        subject=subj.value,
        legal_status=legal.legal_status.value,
        license_note=legal.license_hint,
        institution=legal.institution_hint,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    if legal.legal_status == LegalStatus.REJECTED:
        source.error_message = "; ".join(legal.reasons)
        db.commit()
        return source

    try:
        if legal.legal_status in (
            LegalStatus.OPEN_ACCESS,
            LegalStatus.AUTHORIZED,
            LegalStatus.CREATED_BY_USER,
        ) or user_authorized:
            local_path, content_hash, final_title = download_pdf_from_url(
                url,
                source.title,
                lvl,
                subj,
                legal.legal_status,
                user_authorized=user_authorized,
                pdf_url=pdf_url,
                source_page_url=url,
            )
            _create_document_from_file(
                db,
                source,
                local_path,
                content_hash,
                final_title,
                url,
                legal.legal_status,
                auto_index,
            )
    except DownloadRejected as e:
        source.error_message = str(e)
        db.commit()
        logger.warning("Téléchargement refusé: %s", e)
    except Exception as e:
        source.error_message = str(e)
        db.commit()
        logger.error("Erreur téléchargement: %s", e)

    return source


def add_source_from_file(
    db: Session,
    file_path: Path,
    *,
    title: str | None = None,
    level: Level | None = None,
    subject: Subject | None = None,
    user_authorized: bool = False,
    user_created: bool = True,
    auto_index: bool = True,
) -> Source:
    """Import d'un fichier local."""
    legal = check_local_file(
        file_path.name,
        user_authorized=user_authorized,
        user_created=user_created,
    )
    doc_type = suggest_document_type(file_path.name, "", "")
    inferred_level, inferred_subject, _ = classify_from_text(
        title or file_path.stem, "", doc_type
    )
    lvl = level or inferred_level
    subj = subject or inferred_subject

    source = Source(
        local_path_input=str(file_path),
        title=title or file_path.stem,
        document_type=doc_type.value,
        level=lvl.value,
        subject=subj.value,
        legal_status=legal.legal_status.value,
        license_note=legal.license_hint,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    try:
        dest, content_hash = copy_local_file(file_path, source.title or file_path.stem, lvl, subj)
        _create_document_from_file(
            db,
            source,
            dest,
            content_hash,
            source.title or file_path.stem,
            None,
            legal.legal_status,
            auto_index,
        )
    except Exception as e:
        source.error_message = str(e)
        db.commit()

    return source


def _create_document_from_file(
    db: Session,
    source: Source,
    path: Path,
    content_hash: str,
    title: str,
    source_url: str | None,
    legal: LegalStatus,
    auto_index: bool,
) -> Document:
    dup = db.query(Document).filter(Document.content_hash == content_hash).first()
    if dup:
        source.is_duplicate = True
        source.error_message = f"Doublon du document id={dup.id}"
        db.commit()
        return dup

    meta = {}
    if path.suffix.lower() == ".pdf":
        meta = extract_pdf_metadata(path)
    else:
        meta = {
            "title": title,
            "document_type": source.document_type,
            "level": source.level,
            "subject": source.subject,
            "difficulty": "intermediaire",
            "keywords": "",
            "summary_short": "",
            "summary_pedagogical": "",
            "language": "fr",
            "file_format": path.suffix.lstrip("."),
        }

    doc = Document(
        source_id=source.id,
        title=meta.get("title", title),
        author=meta.get("author"),
        institution=meta.get("institution") or source.institution,
        year=meta.get("year"),
        source_url=source_url or source.url,
        license_note=source.license_note,
        document_type=meta.get("document_type", source.document_type),
        level=meta.get("level", source.level),
        subject=meta.get("subject", source.subject),
        keywords=meta.get("keywords"),
        summary_short=meta.get("summary_short"),
        summary_pedagogical=meta.get("summary_pedagogical"),
        difficulty=meta.get("difficulty", "intermediaire"),
        legal_status=legal.value,
        language=meta.get("language", "fr"),
        file_format=meta.get("file_format", "pdf"),
        local_path=str(path),
        content_hash=content_hash,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if auto_index and legal.usable_by_rag:
        index_document(db, doc.id)

    return doc


def load_concepts_from_json(db: Session, json_path: Path) -> int:
    """Importe concepts_links.json en base."""
    from app.db.models import ConceptLink

    data = json.loads(json_path.read_text(encoding="utf-8"))
    count = 0
    db.query(ConceptLink).delete()
    for entry in data:
        notion = entry["notion"]
        for link in entry.get("liens", []):
            db.add(
                ConceptLink(
                    notion=notion,
                    notion_liee=link["notion_liee"],
                    relation=link["relation"],
                )
            )
            count += 1
    db.commit()
    return count
