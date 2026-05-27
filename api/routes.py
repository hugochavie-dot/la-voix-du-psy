"""Endpoints REST + admin."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.core.enums import DocumentType, LegalStatus, Level, Subject
from app.core.paths import PROJECT_ROOT, ensure_project_dirs
from app.db.database import get_db
from app.db.models import ConceptLink, Document, IndexJob, Source
from app.services.html_exporter import OUTPUT_DIR, build_cours_site
from app.services.questionnaires_exporter import QUESTIONNAIRES_DIR, build_questionnaires_site
from app.services.indexer import index_document, search_rag
from app.services.analysis_service import generate_analysis
from app.services.source_manager import add_source_from_file, add_source_from_url

router = APIRouter()


class AddUrlRequest(BaseModel):
    url: HttpUrl
    title: str | None = None
    level: Level | None = None
    subject: Subject | None = None
    document_type: DocumentType | None = None
    user_authorized: bool = False
    auto_index: bool = True


class UpdateSourceRequest(BaseModel):
    title: str | None = None
    level: Level | None = None
    subject: Subject | None = None
    legal_status: LegalStatus | None = None
    tags: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    level: str | None = None
    subject: str | None = None


class AnalyseRequest(BaseModel):
    nom: str
    email: str
    niveau: str
    situation: str
    objectif: str
    message: str
    situation_label: str | None = None
    objectif_label: str | None = None
    niveau_label: str | None = None


@router.get("/health")
def health():
    return {"status": "ok", "project": str(PROJECT_ROOT)}


@router.get("/sources")
def list_sources(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    sources = db.query(Source).offset(skip).limit(limit).all()
    return [_serialize_source(s) for s in sources]


@router.get("/sources/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "Source introuvable")
    out = _serialize_source(s)
    if s.document:
        out["document"] = _serialize_document(s.document)
    return out


@router.post("/sources/url")
def create_from_url(body: AddUrlRequest, db: Session = Depends(get_db)):
    ensure_project_dirs()
    source = add_source_from_url(
        db,
        str(body.url),
        title=body.title,
        level=body.level,
        subject=body.subject,
        document_type=body.document_type,
        user_authorized=body.user_authorized,
        auto_index=body.auto_index,
    )
    return _serialize_source(source)


@router.post("/sources/upload")
async def upload_file(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    level: str | None = Form(None),
    subject: str | None = Form(None),
    user_authorized: bool = Form(False),
    db: Session = Depends(get_db),
):
    ensure_project_dirs()
    upload_dir = PROJECT_ROOT / "storage" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    lvl = Level(level) if level else None
    subj = Subject(subject) if subject else None
    source = add_source_from_file(
        db,
        dest,
        title=title or file.filename,
        level=lvl,
        subject=subj,
        user_authorized=user_authorized,
        user_created=True,
    )
    return _serialize_source(source)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: UpdateSourceRequest, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "Source introuvable")
    if body.title is not None:
        s.title = body.title
    if body.level is not None:
        s.level = body.level.value
    if body.subject is not None:
        s.subject = body.subject.value
    if body.legal_status is not None:
        s.legal_status = body.legal_status.value
    if body.tags is not None:
        s.tags = json.dumps(body.tags, ensure_ascii=False)
    db.commit()
    if s.document:
        if body.level:
            s.document.level = body.level.value
        if body.subject:
            s.document.subject = body.subject.value
        if body.legal_status:
            s.document.legal_status = body.legal_status.value
        db.commit()
    return _serialize_source(s)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "Source introuvable")
    if s.document:
        db.delete(s.document)
    db.delete(s)
    db.commit()
    return {"deleted": source_id}


@router.post("/sources/{source_id}/reindex")
def reindex_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s or not s.document:
        raise HTTPException(404, "Document introuvable pour cette source")
    job = index_document(db, s.document.id, force=True)
    return {"status": job.status, "message": job.message}


@router.get("/duplicates")
def list_duplicates(db: Session = Depends(get_db)):
    return [
        _serialize_source(s)
        for s in db.query(Source).filter(Source.is_duplicate == True).all()
    ]


@router.get("/errors")
def list_errors(db: Session = Depends(get_db)):
    return [
        _serialize_source(s)
        for s in db.query(Source).filter(Source.error_message.isnot(None)).all()
    ]


@router.post("/search")
def rag_search(body: SearchRequest):
    return search_rag(
        body.query,
        n_results=body.n_results,
        level=body.level,
        subject=body.subject,
    )


@router.post("/analyse")
def analyse_personnalisee(body: AnalyseRequest):
    """
    Analyse pédagogique personnalisée avec citations OpenStax (RAG JSONL).
    Ne remplace pas un professionnel de santé mentale.
    """
    if len(body.message.strip()) < 20:
        raise HTTPException(400, "Message trop court (minimum 20 caractères).")
    if body.niveau not in {"L1", "L2", "L3", "autre"}:
        raise HTTPException(400, "Niveau invalide.")
    return generate_analysis(body.model_dump())


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).all()
    return [_serialize_document(d) for d in docs]


@router.get("/concepts")
def list_concepts(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ConceptLink)
    if q:
        query = query.filter(ConceptLink.notion.ilike(f"%{q}%"))
    rows = query.limit(200).all()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.notion, []).append(
            {"notion_liee": row.notion_liee, "relation": row.relation}
        )
    return [{"notion": n, "liens": links} for n, links in grouped.items()]


@router.post("/cours/build")
def build_cours_html(
    document_id: int | None = Query(None),
    max_pages: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Génère le site HTML des cours (output/cours/)."""
    ids = [document_id] if document_id else None
    report = build_cours_site(db, document_ids=ids, max_pages=max_pages)
    return {
        "output_dir": str(report.output_dir),
        "built": len(report.built),
        "skipped": report.skipped,
        "catalog_url": "/cours/index.html" if (OUTPUT_DIR / "index.html").exists() else None,
    }


@router.post("/questionnaires/build")
def build_questionnaires_html():
    """Génère les questionnaires patients HTML (output/questionnaires/)."""
    report = build_questionnaires_site()
    return {
        "output_dir": str(report.output_dir),
        "built": len(report.built),
        "catalog_url": "/questionnaires/index.html"
        if (QUESTIONNAIRES_DIR / "index.html").exists()
        else None,
    }


@router.get("/index-jobs")
def list_index_jobs(limit: int = 50, db: Session = Depends(get_db)):
    jobs = (
        db.query(IndexJob)
        .order_by(IndexJob.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": j.id,
            "document_id": j.document_id,
            "status": j.status,
            "message": j.message,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


def _serialize_source(s: Source) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "url": s.url,
        "local_path_input": s.local_path_input,
        "document_type": s.document_type,
        "level": s.level,
        "subject": s.subject,
        "legal_status": s.legal_status,
        "license_note": s.license_note,
        "institution": s.institution,
        "tags": json.loads(s.tags) if s.tags else [],
        "is_duplicate": s.is_duplicate,
        "error_message": s.error_message,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _serialize_document(d: Document) -> dict:
    return {
        "id": d.id,
        "source_id": d.source_id,
        "title": d.title,
        "author": d.author,
        "institution": d.institution,
        "year": d.year,
        "source_url": d.source_url,
        "license_note": d.license_note,
        "document_type": d.document_type,
        "level": d.level,
        "subject": d.subject,
        "keywords": d.keywords,
        "summary_short": d.summary_short,
        "summary_pedagogical": d.summary_pedagogical,
        "difficulty": d.difficulty,
        "legal_status": d.legal_status,
        "language": d.language,
        "file_format": d.file_format,
        "local_path": d.local_path,
        "indexed": d.indexed,
        "added_at": d.added_at.isoformat() if d.added_at else None,
    }
