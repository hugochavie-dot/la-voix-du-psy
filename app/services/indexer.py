"""Indexation RAG : chunks + ChromaDB + métadonnées."""

from __future__ import annotations

import uuid
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session

from app.core.enums import LegalStatus
from app.core.logging_config import setup_logging
from app.db.models import Document, DocumentChunk, IndexJob
from app.services.legal_checker import is_rag_eligible
from app.services.metadata_extractor import extract_text_from_pdf
from config.settings import settings

logger = setup_logging("indexer")

COLLECTION_NAME = "psychologie_ressources"


def _get_chroma_collection():
    client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Ressources pédagogiques psychologie L1-L3"},
    )


def _chunk_text(pages: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Découpe en chunks avec chevauchement, en conservant la page."""
    chunks: list[tuple[int, int, str]] = []
    chunk_size = settings.chunk_size
    overlap = settings.chunk_overlap

    for page_num, text in pages:
        clean = " ".join(text.split())
        if not clean:
            continue
        start = 0
        idx = 0
        while start < len(clean):
            end = start + chunk_size
            piece = clean[start:end]
            chunks.append((page_num, idx, piece))
            idx += 1
            start = end - overlap if end < len(clean) else len(clean)
            if start >= len(clean):
                break
    return chunks


def _build_citation(doc: Document, page: int | None) -> str:
    parts = [doc.title]
    if doc.author:
        parts.append(doc.author)
    if doc.institution:
        parts.append(doc.institution)
    if doc.year:
        parts.append(str(doc.year))
    if page:
        parts.append(f"p.{page}")
    if doc.source_url:
        parts.append(doc.source_url)
    return " | ".join(parts)


def index_document(db: Session, document_id: int, force: bool = False) -> IndexJob:
    """Indexe un document dans SQLite chunks + Chroma."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    job = IndexJob(document_id=document_id, status="pending")
    db.add(job)
    db.commit()

    if not doc:
        job.status = "error"
        job.message = "Document introuvable"
        db.commit()
        return job

    status = LegalStatus(doc.legal_status)
    if not is_rag_eligible(status):
        job.status = "error"
        job.message = f"Indexation refusée — legal_status={doc.legal_status}"
        db.commit()
        logger.warning(job.message)
        return job

    if doc.indexed and not force:
        job.status = "success"
        job.message = "Déjà indexé (utilisez force=True pour réindexer)"
        db.commit()
        return job

    path = Path(doc.local_path) if doc.local_path else None
    if not path or not path.exists():
        job.status = "error"
        job.message = "Fichier local manquant"
        db.commit()
        return job

    try:
        if path.suffix.lower() == ".pdf":
            pages = extract_text_from_pdf(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
            pages = [(1, text)]

        chunks_data = _chunk_text(pages)
        if not chunks_data:
            job.status = "error"
            job.message = "Aucun texte extrait"
            db.commit()
            return job

        # Supprimer anciens chunks
        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
        collection = _get_chroma_collection()

        # Supprimer de Chroma les ids précédents (par metadata document_id)
        try:
            existing = collection.get(where={"document_id": doc.id})
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

        ids, documents, metadatas, embeddings_model = [], [], [], None

        try:
            from chromadb.utils import embedding_functions

            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.embedding_model
            )
            embeddings_model = ef
        except Exception as e:
            logger.warning("SentenceTransformer indisponible: %s — Chroma utilisera le défaut", e)
            embeddings_model = None

        for page_num, chunk_idx, text in chunks_data:
            chroma_id = str(uuid.uuid4())
            citation = _build_citation(doc, page_num)
            meta = {
                "source_id": doc.source_id,
                "document_id": doc.id,
                "title": doc.title,
                "page": page_num,
                "subject": doc.subject,
                "level": doc.level,
                "legal_status": doc.legal_status,
                "url": doc.source_url or "",
                "citation": citation,
                "difficulty": doc.difficulty,
                "document_type": doc.document_type,
            }

            chunk_row = DocumentChunk(
                document_id=doc.id,
                chroma_id=chroma_id,
                page=page_num,
                chunk_index=chunk_idx,
                text=text,
                citation=citation,
            )
            db.add(chunk_row)

            ids.append(chroma_id)
            documents.append(text)
            metadatas.append(meta)

        add_kwargs = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings_model:
            add_kwargs["embeddings"] = embeddings_model(documents)

        collection.add(**add_kwargs)

        doc.indexed = True
        job.status = "success"
        job.message = f"{len(chunks_data)} chunks indexés"
        db.commit()
        logger.info("Document %s indexé: %s chunks", doc.id, len(chunks_data))

    except Exception as e:
        logger.exception("Erreur indexation document %s", doc.id)
        job.status = "error"
        job.message = str(e)
        db.rollback()
        db.add(job)
        db.commit()

    return job


def search_rag(
    query: str,
    n_results: int = 5,
    level: str | None = None,
    subject: str | None = None,
    legal_only_usable: bool = True,
) -> list[dict]:
    """Recherche vectorielle avec filtres."""
    collection = _get_chroma_collection()

    where: dict | None = None
    conditions = []
    if level:
        conditions.append({"level": level})
    if subject:
        conditions.append({"subject": subject})
    if legal_only_usable:
        conditions.append({
            "$or": [
                {"legal_status": "open_access"},
                {"legal_status": "created_by_user"},
                {"legal_status": "authorized"},
            ]
        })

    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    try:
        from chromadb.utils import embedding_functions

        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    out = []
    if not results or not results.get("ids"):
        return out

    for i, cid in enumerate(results["ids"][0]):
        out.append({
            "id": cid,
            "text": results["documents"][0][i] if results.get("documents") else "",
            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return out
