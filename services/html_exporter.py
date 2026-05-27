"""Export des documents pédagogiques en site HTML statique."""

from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging_config import setup_logging
from app.core.paths import PROJECT_ROOT
from app.db.models import Document
from app.services.legal_checker import is_rag_eligible
from app.services.metadata_extractor import extract_text_from_pdf
from app.core.enums import LegalStatus

LEVEL_ORDER = ["L1", "L2", "L3", "mixte", "recherche_avancee"]

logger = setup_logging("html_exporter")

OUTPUT_DIR = PROJECT_ROOT / "output" / "cours"
PAGES_PER_PART = 40

from app.services.html_common import LEVEL_LABELS, SUBJECT_LABELS, escape as _escape

@dataclass
class CourseEntry:
    document_id: int
    slug: str
    title: str
    level: str
    subject: str
    summary: str
    source_url: str | None
    page_count: int
    part_count: int
    href: str


@dataclass
class BuildReport:
    built: list[CourseEntry] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    output_dir: Path = OUTPUT_DIR


def _slugify(title: str, doc_id: int) -> str:
    base = re.sub(r"[^\w\s-]", "", title.lower())
    base = re.sub(r"[-\s]+", "-", base).strip("-")[:60] or "cours"
    return f"{doc_id}-{base}"


def _paragraphs(page_text: str) -> str:
    blocks = [b.strip() for b in re.split(r"\n{2,}", page_text) if b.strip()]
    if not blocks:
        lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        blocks = lines
    parts: list[str] = []
    for block in blocks:
        if len(block) < 120 and not block.endswith("."):
            parts.append(f"<h3 class=\"block-title\">{_escape(block)}</h3>")
        else:
            parts.append(f"<p>{_escape(block)}</p>")
    return "\n".join(parts) if parts else "<p class=\"empty\">(page vide)</p>"


def _write_css(dest: Path) -> None:
    css = """\
:root {
  --bg: #0f1419;
  --card: #1a2332;
  --text: #e7ecf3;
  --accent: #6eb5ff;
  --muted: #8b9cb3;
  --border: #2a3548;
}
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  line-height: 1.65;
}
a { color: var(--accent); }
header.site-header, footer.site-footer {
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border);
}
footer.site-footer {
  border-top: 1px solid var(--border);
  border-bottom: none;
  font-size: 0.85rem;
  color: var(--muted);
}
.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: calc(100vh - 120px);
}
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { border-right: none; border-bottom: 1px solid var(--border); }
}
.sidebar {
  padding: 1rem;
  border-right: 1px solid var(--border);
  background: var(--card);
  font-size: 0.9rem;
}
.sidebar h2 { font-size: 0.95rem; margin: 0 0 0.75rem; }
.sidebar ul { list-style: none; padding: 0; margin: 0; }
.sidebar li { margin: 0.35rem 0; }
.content { padding: 1.5rem 2rem; max-width: 52rem; }
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1rem; }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  background: #243044;
  font-size: 0.75rem;
  margin-right: 0.35rem;
}
.catalog { padding: 1.5rem 2rem; }
.catalog section { margin-bottom: 2rem; }
.catalog h2 { border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }
.catalog ul { padding-left: 1.2rem; }
.catalog li { margin: 0.5rem 0; }
.page-section {
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px dashed var(--border);
}
.page-section h2 {
  font-size: 1rem;
  color: var(--muted);
  margin-top: 0;
}
.block-title { font-size: 1.05rem; margin: 1rem 0 0.5rem; }
.part-nav {
  display: flex;
  gap: 1rem;
  margin: 1.5rem 0;
  flex-wrap: wrap;
}
.empty { color: var(--muted); font-style: italic; }
.fiche-summary { font-size: 1.05rem; line-height: 1.7; border-left: 3px solid var(--accent); padding-left: 1rem; }
.hub-links { margin: 1rem 0 1.5rem; }
.hub-links a { margin-right: 0.5rem; }
"""
    assets = dest / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "cours.css").write_text(css, encoding="utf-8")


def _page_shell(
    *,
    title: str,
    body: str,
    css_href: str,
    catalog_href: str = "index.html",
    nav_sidebar: str = "",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(title)} — Psych IA Cours</title>
  <link rel="stylesheet" href="{_escape(css_href)}" />
</head>
<body>
  <header class="site-header">
    <a href="{_escape(catalog_href)}">← Catalogue des cours</a>
  </header>
  <div class="layout">
    {nav_sidebar}
    <main class="content">{body}</main>
  </div>
  <footer class="site-footer">
  <p>Usage pédagogique personnel — respectez les licences des documents sources.</p>
  <p>L'IA ne remplace pas un psychologue.</p>
  </footer>
</body>
</html>
"""


def _extract_pages(doc: Document, max_pages: int | None) -> list[tuple[int, str]]:
    path = Path(doc.local_path) if doc.local_path else None
    if not path or not path.exists():
        return []

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = extract_text_from_pdf(path, max_pages=max_pages)
    elif suffix in (".md", ".txt"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        pages = [(1, text)]
    else:
        return []
    return pages


def _write_document_html(
    doc: Document,
    doc_dir: Path,
    *,
    max_pages: int | None = None,
) -> CourseEntry | None:
    pages = _extract_pages(doc, max_pages)
    if not pages:
        return None

    slug = _slugify(doc.title, doc.id)
    doc_dir = doc_dir / slug
    doc_dir.mkdir(parents=True, exist_ok=True)

    parts: list[list[tuple[int, str]]] = []
    for i in range(0, len(pages), PAGES_PER_PART):
        parts.append(pages[i : i + PAGES_PER_PART])

    part_links: list[tuple[str, str]] = []
    css_rel = "../assets/cours.css"

    for part_idx, part_pages in enumerate(parts, start=1):
        part_name = f"part-{part_idx:03d}.html"
        sections = []
        for page_num, text in part_pages:
            sections.append(
                f'<section class="page-section" id="page-{page_num}">'
                f"<h2>Page {page_num}</h2>\n{_paragraphs(text)}\n</section>"
            )

        part_label = f"Pages {part_pages[0][0]}–{part_pages[-1][0]}"
        part_links.append((part_name, part_label))

        toc = "".join(
            f'<li><a href="#page-{n}">Page {n}</a></li>' for n, _ in part_pages
        )
        sidebar = f"""
    <aside class="sidebar">
      <h2>Sommaire</h2>
      <ul>{toc}</ul>
      <p><a href="index.html">Toutes les parties</a></p>
    </aside>"""

        meta_bits = [
            f'<span class="badge">{_escape(LEVEL_LABELS.get(doc.level, doc.level))}</span>',
            f'<span class="badge">{_escape(SUBJECT_LABELS.get(doc.subject, doc.subject))}</span>',
        ]
        if doc.source_url:
            meta_bits.append(
                f'<a href="{_escape(doc.source_url)}" target="_blank" rel="noopener">Source originale</a>'
            )

        prev_part = f"part-{part_idx - 1:03d}.html" if part_idx > 1 else None
        next_part = f"part-{part_idx + 1:03d}.html" if part_idx < len(parts) else None
        part_nav = '<div class="part-nav">'
        if prev_part:
            part_nav += f'<a href="{prev_part}">← Partie précédente</a>'
        if next_part:
            part_nav += f'<a href="{next_part}">Partie suivante →</a>'
        part_nav += "</div>"

        body = f"""
    <h1>{_escape(doc.title)}</h1>
    <p class="meta">{" · ".join(meta_bits)} · {part_label}</p>
    {doc.summary_short and f'<p class="meta">{_escape(doc.summary_short)}</p>' or ''}
    {part_nav}
    {"".join(sections)}
    {part_nav}
    """

        (doc_dir / part_name).write_text(
            _page_shell(
                title=f"{doc.title} — {part_label}",
                body=body,
                css_href=css_rel,
                catalog_href="../index.html",
                nav_sidebar=sidebar,
            ),
            encoding="utf-8",
        )

    toc_parts = "".join(
        f'<li><a href="{_escape(name)}">{_escape(label)}</a></li>'
        for name, label in part_links
    )
    index_body = f"""
    <h1>{_escape(doc.title)}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(doc.level, doc.level))}</span>
      <span class="badge">{_escape(SUBJECT_LABELS.get(doc.subject, doc.subject))}</span>
      · {len(pages)} pages · {len(parts)} partie(s)
    </p>
    {doc.summary_pedagogical and f'<p>{_escape(doc.summary_pedagogical)}</p>' or ''}
    <h2>Parties du cours</h2>
    <ul>{toc_parts}</ul>
    """
    (doc_dir / "index.html").write_text(
        _page_shell(
            title=doc.title,
            body=index_body,
            css_href=css_rel,
            catalog_href="../index.html",
        ),
        encoding="utf-8",
    )

    return CourseEntry(
        document_id=doc.id,
        slug=slug,
        title=doc.title,
        level=doc.level,
        subject=doc.subject,
        summary=doc.summary_short or "",
        source_url=doc.source_url,
        page_count=len(pages),
        part_count=len(parts),
        href=f"{slug}/index.html",
    )


def _write_catalog(entries: list[CourseEntry], dest: Path) -> None:
    by_level: dict[str, list[CourseEntry]] = {}
    for e in entries:
        by_level.setdefault(e.level, []).append(e)

    sections = []
    def _level_key(level: str) -> int:
        try:
            return LEVEL_ORDER.index(level)
        except ValueError:
            return 99

    fr_section = ""
    fr_entries = [e for e in entries if e.document_id == 0]
    pdf_entries = [e for e in entries if e.document_id != 0]

    if fr_entries:
        fr_by_level: dict[str, list[CourseEntry]] = {}
        for e in fr_entries:
            fr_by_level.setdefault(e.level, []).append(e)
        fr_parts = []
        for level in sorted(fr_by_level.keys(), key=_level_key):
            lis = []
            for e in sorted(fr_by_level[level], key=lambda x: x.title.lower()):
                subj = SUBJECT_LABELS.get(e.subject, e.subject)
                lis.append(
                    f'<li><a href="{_escape(e.href)}">{_escape(e.title)}</a>'
                    f' <span class="meta">— {e.page_count} leçons</span></li>'
                )
            fr_parts.append(
                f"<section><h3>{_escape(LEVEL_LABELS.get(level, level))}</h3><ul>{''.join(lis)}</ul></section>"
            )
        fr_section = f"""
    <section>
      <h2>Cours en français (programme L1 / L2 / L3)</h2>
      {"".join(fr_parts)}
    </section>"""

    for level in sorted(
        {e.level for e in pdf_entries},
        key=_level_key,
    ):
        items = sorted(
            [e for e in pdf_entries if e.level == level],
            key=lambda e: e.title.lower(),
        )
        lis = []
        for e in items:
            subj = SUBJECT_LABELS.get(e.subject, e.subject)
            extra = f" ({e.page_count} p.)" if e.page_count else ""
            lis.append(
                f'<li><a href="{_escape(e.href)}">{_escape(e.title)}</a>'
                f' <span class="meta">— {subj}{extra}</span></li>'
            )
        label = LEVEL_LABELS.get(level, level)
        sections.append(f"<section><h2>{_escape(label)}</h2><ul>{''.join(lis)}</ul></section>")

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf_section = ""
    if sections:
        pdf_section = f"""
    <section>
      <h2>Manuels et documents (PDF)</h2>
      {"".join(sections)}
    </section>"""

    body = f"""
    <h1>Catalogue des cours</h1>
    <p class="meta">Généré le {built_at} · {len(entries)} module(s)</p>
    <nav class="hub-links">
      <a href="/hub/">Accueil</a> ·
      <a href="/fiches/">Fiches</a> ·
      <a href="/resumes/">Résumés</a>
    </nav>
    {fr_section}
    {pdf_section or ("" if fr_section else "<p>Aucun cours exporté.</p>")}
    """
    (dest / "index.html").write_text(
        _page_shell(title="Catalogue", body=body, css_href="assets/cours.css"),
        encoding="utf-8",
    )

    manifest = {
        "generated_at": built_at,
        "courses": [
            {
                "document_id": e.document_id,
                "slug": e.slug,
                "title": e.title,
                "level": e.level,
                "subject": e.subject,
                "href": e.href,
                "page_count": e.page_count,
            }
            for e in entries
        ],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_cours_site(
    db: Session,
    *,
    output_dir: Path | None = None,
    document_ids: list[int] | None = None,
    max_pages: int | None = None,
    include_non_eligible: bool = False,
    clean: bool = True,
) -> BuildReport:
    """Génère le site HTML dans output/cours/."""
    dest = output_dir or OUTPUT_DIR
    report = BuildReport(output_dir=dest)

    if clean and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _write_css(dest)

    query = db.query(Document)
    if document_ids:
        query = query.filter(Document.id.in_(document_ids))
    documents = query.all()

    for doc in documents:
        status = LegalStatus(doc.legal_status)
        if not include_non_eligible and not is_rag_eligible(status):
            report.skipped.append({
                "id": doc.id,
                "title": doc.title,
                "reason": f"statut légal non exportable: {doc.legal_status}",
            })
            continue

        if "2212.02797" in (doc.source_url or ""):
            report.skipped.append({
                "id": doc.id,
                "title": doc.title,
                "reason": "document hors psychologie (arXiv erroné)",
            })
            continue

        try:
            entry = _write_document_html(doc, dest, max_pages=max_pages)
            if entry:
                report.built.append(entry)
                logger.info("Export HTML: %s (%s pages)", doc.title, entry.page_count)
            else:
                report.skipped.append({
                    "id": doc.id,
                    "title": doc.title,
                    "reason": "fichier absent ou texte non extrait",
                })
        except Exception as e:
            logger.exception("Erreur export document %s", doc.id)
            report.skipped.append({"id": doc.id, "title": doc.title, "reason": str(e)})

    from app.services.cours_fr_exporter import build_fr_courses

    fr_entries = build_fr_courses(dest)
    report.built.extend(fr_entries)

    _write_catalog(report.built, dest)
    return report
