"""Modèles SQLAlchemy — sources, documents, chunks, concepts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    """Source configurée (URL ou fichier) avant/après traitement."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True, unique=True)
    local_path_input: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    document_type: Mapped[str] = mapped_column(String(64), default="autre")
    level: Mapped[str] = mapped_column(String(32), default="L1")
    subject: Mapped[str] = mapped_column(String(64), default="psychologie_generale")
    legal_status: Mapped[str] = mapped_column(String(32), default="unknown")
    license_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    institution: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    document: Mapped[Optional["Document"]] = relationship(
        "Document", back_populates="source", uselist=False
    )


class Document(Base):
    """Document traité avec métadonnées complètes."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_document_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    author: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    institution: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    license_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    document_type: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(64))
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_short: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_pedagogical: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(32), default="intermediaire")
    legal_status: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), default="fr")
    file_format: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    source: Mapped["Source"] = relationship("Source", back_populates="document")
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document"
    )


class DocumentChunk(Base):
    """Chunk texte pour RAG (référence SQLite + Chroma)."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    chroma_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    citation: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class ConceptLink(Base):
    """Lien entre notions (miroir JSON + requêtes SQL)."""

    __tablename__ = "concept_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notion: Mapped[str] = mapped_column(String(256), index=True)
    notion_liee: Mapped[str] = mapped_column(String(256))
    relation: Mapped[str] = mapped_column(String(256))


class IndexJob(Base):
    """Journal des jobs d'indexation."""

    __tablename__ = "index_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32))  # pending, success, error
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
