"""Export des résumés et fiches de révision en HTML statique."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.enums import LegalStatus
from app.core.logging_config import setup_logging
from app.core.paths import PROJECT_ROOT
from app.db.models import Document
from app.services.html_exporter import LEVEL_LABELS, OUTPUT_DIR, SUBJECT_LABELS, _escape, _write_css
from app.services.legal_checker import is_rag_eligible
from app.services.metadata_extractor import extract_text_from_pdf

logger = setup_logging("fiches_exporter")

RESUMES_DIR = PROJECT_ROOT / "output" / "resumes"
FICHES_DIR = PROJECT_ROOT / "output" / "fiches"
CONCEPTS_PATH = PROJECT_ROOT / "concepts_links.json"
HUB_DIR = PROJECT_ROOT / "output"

LEVEL_ORDER = ["L1", "L2", "L3", "mixte", "recherche_avancee"]

FICHE_SUMMARY_CHARS = 600
MAX_NOTIONS = 12
MAX_LINKED_CONCEPTS = 6

CHAPTER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Chapter\s+(\d+)\s*:\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"Chapitre\s+(\d+)\s*:\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"CHAPITRE\s+(\d+)\s*[:\.\-]?\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"CHAPITRE\s+PREMIER\s*[:\.\-]?\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"CHAPITRE\s+DEUXI[EÈ]ME\s*[:\.\-]?\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"CHAPITRE\s+TROISI[EÈ]ME\s*[:\.\-]?\s*([^\n\r]+)", re.IGNORECASE),
]

FRENCH_ORDINAL_CHAPTER = {
    "PREMIER": 1,
    "DEUXIEME": 2,
    "DEUXIÈME": 2,
    "TROISIEME": 3,
    "TROISIÈME": 3,
    "QUATRIEME": 4,
    "QUATRIÈME": 4,
}

BULLET_RE = re.compile(
    r"(?:^|\n)\s*(?:[•\-\*]|(?<!\d)\d+\.)\s+(.{15,220}?)(?=\n\s*(?:[•\-\*]|(?<!\d)\d+\.)|\n\n|$)",
    re.MULTILINE,
)

HEADING_RE = re.compile(
    r"(?:^|\n)\s*((?:[IVXLC]+\.|[A-Z][A-Z\s]{3,40}|[0-9]+\.[0-9]*\s+[A-ZÀÂÄÉÈÊË][^\n]{5,80}))\s*$",
    re.MULTILINE,
)


@dataclass
class ResumeEntry:
    document_id: int
    slug: str
    title: str
    level: str
    subject: str
    href: str


@dataclass
class FicheEntry:
    document_id: int
    chapter_num: int
    title: str
    slug: str
    href: str


@dataclass
class ConceptLink:
    notion: str
    notion_liee: str
    relation: str


@dataclass
class ConceptBlock:
    notion: str
    level: str
    subject: str
    intro: str
    liens: list[ConceptLink]


@dataclass
class FichesResumeReport:
    resumes: list[ResumeEntry] = field(default_factory=list)
    fiches: list[FicheEntry] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


def _slugify(text: str, prefix: str = "") -> str:
    base = re.sub(r"[^\w\s-]", "", text.lower())
    base = re.sub(r"[-\s]+", "-", base).strip("-")[:50] or "item"
    return f"{prefix}-{base}" if prefix else base


def _page_shell(*, title: str, body: str, css_href: str, catalog_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(title)} — Psych IA</title>
  <link rel="stylesheet" href="{_escape(css_href)}" />
</head>
<body>
  <header class="site-header">
    <a href="{_escape(catalog_href)}">← Retour au catalogue</a>
  </header>
  <main class="content">{body}</main>
  <footer class="site-footer">
    <p>Usage pédagogique personnel — respectez les licences des documents sources.</p>
  </footer>
</body>
</html>
"""


def _load_concept_blocks() -> list[ConceptBlock]:
    if not CONCEPTS_PATH.exists():
        return []
    raw = json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    blocks: list[ConceptBlock] = []
    for entry in raw:
        liens = [
            ConceptLink(
                notion=entry.get("notion", ""),
                notion_liee=link.get("notion_liee", ""),
                relation=link.get("relation", ""),
            )
            for link in entry.get("liens", [])
        ]
        blocks.append(ConceptBlock(
            notion=entry.get("notion", ""),
            level=entry.get("level", "L2"),
            subject=entry.get("subject", "psychologie_generale"),
            intro=entry.get("intro", ""),
            liens=liens,
        ))
    return blocks


def _flat_concept_links(blocks: list[ConceptBlock]) -> list[ConceptLink]:
    return [link for block in blocks for link in block.liens]


def _level_sort_key(level: str) -> int:
    try:
        return LEVEL_ORDER.index(level)
    except ValueError:
        return 99


def _linked_concepts(text: str, concepts: list[ConceptLink]) -> list[ConceptLink]:
    lower = text.lower()
    seen: set[str] = set()
    matched: list[ConceptLink] = []
    for c in concepts:
        for name in (c.notion, c.notion_liee):
            if not name or name.lower() in seen:
                continue
            if name.lower() in lower:
                seen.add(name.lower())
                matched.append(c)
                break
        if len(matched) >= MAX_LINKED_CONCEPTS:
            break
    return matched


def _eligible_documents(db: Session, document_ids: list[int] | None) -> list[Document]:
    query = db.query(Document)
    if document_ids:
        query = query.filter(Document.id.in_(document_ids))
    return [
        doc for doc in query.all()
        if is_rag_eligible(LegalStatus(doc.legal_status))
        and "face swapping" not in (doc.title or "").lower()
        and "2212.02797" not in (doc.source_url or "")
    ]


def _chapter_match_info(match: re.Match[str]) -> tuple[int, str]:
    groups = match.groups()
    if len(groups) == 2 and groups[0].isdigit():
        return int(groups[0]), groups[1].strip()
    ordinal = (groups[0] or "").upper().replace("È", "E")
    num = FRENCH_ORDINAL_CHAPTER.get(ordinal, 0)
    title = groups[-1].strip()
    return num or 1, title


def _extract_chapters(pages: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """Retourne (numéro, titre, texte) pour chaque chapitre détecté."""
    full = "\n".join(text for _, text in pages)
    matches: list[tuple[int, re.Match[str]]] = []

    for pattern in CHAPTER_PATTERNS:
        for match in pattern.finditer(full):
            num, title = _chapter_match_info(match)
            if title and len(title) > 3:
                matches.append((match.start(), match))

    if not matches:
        return []

    matches.sort(key=lambda x: x[0])
    deduped: list[tuple[int, re.Match[str]]] = []
    seen_starts: set[int] = set()
    for start, match in matches:
        if start in seen_starts:
            continue
        seen_starts.add(start)
        deduped.append((start, match))

    chapters: list[tuple[int, str, str]] = []
    for i, (start, match) in enumerate(deduped):
        num, title = _chapter_match_info(match)
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(full)
        chapters.append((num, title, full[start:end].strip()))

    if len(chapters) > 1:
        chapters = [c for c in chapters if c[2]]
    return chapters


def _extract_bullet_notions(text: str) -> list[str]:
    notions: list[str] = []
    for match in BULLET_RE.finditer(text):
        line = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(line) >= 15 and line not in notions:
            notions.append(line)
        if len(notions) >= MAX_NOTIONS:
            break
    return notions


def _extract_section_titles(text: str) -> list[str]:
    titles: list[str] = []
    for match in HEADING_RE.finditer(text):
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if 5 < len(title) < 90 and title not in titles:
            titles.append(title)
        if len(titles) >= 8:
            break
    return titles


def _short_summary(text: str, notions: list[str]) -> str:
    if notions:
        summary = " · ".join(n[:120] for n in notions[:4])
    else:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text))
        summary = " ".join(s.strip() for s in sentences[:3] if len(s.strip()) > 40)
    if len(summary) > FICHE_SUMMARY_CHARS:
        summary = summary[: FICHE_SUMMARY_CHARS - 1] + "…"
    return summary or "Résumé non disponible pour ce chapitre."


def _keywords_from_text(text: str, max_kw: int = 8) -> list[str]:
    stops = {
        "that", "this", "with", "from", "have", "will", "their", "which",
        "dans", "pour", "avec", "cette", "comme", "plus", "sont", "être",
        "the", "and", "des", "les", "une", "par", "sur", "chapter", "chapitre",
        "document", "psychologie", "cours", "page", "hal", "openstax",
    }
    words = re.findall(r"[a-zàâäéèêëïîôùûüç]{5,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in stops:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:max_kw]]


def _list_html(items: list[str], *, ordered: bool = False) -> str:
    if not items:
        return ""
    tag = "ol" if ordered else "ul"
    inner = "".join(f"<li>{_escape(i)}</li>" for i in items)
    return f"<{tag}>{inner}</{tag}>"


def _concept_links_html(links: list[ConceptLink]) -> str:
    if not links:
        return ""
    items = []
    for link in links:
        items.append(
            f"<li><strong>{_escape(link.notion)}</strong> → "
            f"{_escape(link.notion_liee)} "
            f"<em>({_escape(link.relation)})</em></li>"
        )
    return f"<h2>Notions liées</h2><ul>{''.join(items)}</ul>"


def _write_resume(doc: Document, dest: Path, concepts: list[ConceptLink]) -> ResumeEntry | None:
    slug = _slugify(doc.title, str(doc.id))
    doc_dir = dest / slug
    doc_dir.mkdir(parents=True, exist_ok=True)

    meta_bits = [
        f'<span class="badge">{_escape(LEVEL_LABELS.get(doc.level, doc.level))}</span>',
        f'<span class="badge">{_escape(SUBJECT_LABELS.get(doc.subject, doc.subject))}</span>',
    ]
    if doc.author:
        meta_bits.append(_escape(doc.author))
    if doc.year:
        meta_bits.append(str(doc.year))

    sample = f"{doc.summary_short or ''} {doc.summary_pedagogical or ''}"
    linked = _linked_concepts(sample, concepts)
    keywords = doc.keywords or ""
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    short = doc.summary_short or ""
    if len(short) > 500:
        short = short[:497] + "…"

    body = f"""
    <h1>{_escape(doc.title)}</h1>
    <p class="meta">{" · ".join(meta_bits)}</p>
    {doc.source_url and f'<p><a href="{_escape(doc.source_url)}" target="_blank" rel="noopener">Source originale</a></p>' or ''}
    <h2>En bref</h2>
    <p class="fiche-summary">{_escape(short or "Résumé non disponible.")}</p>
    <h2>Objectifs pédagogiques</h2>
    <p>{_escape(doc.summary_pedagogical or "—")}</p>
    {kw_list and f"<h2>Mots-clés</h2>{_list_html(kw_list)}" or ""}
    {_concept_links_html(linked)}
    <p class="meta"><a href="/fiches/">Voir les fiches de révision</a> · <a href="/cours/">Voir le cours</a></p>
    """

    (doc_dir / "index.html").write_text(
        _page_shell(
            title=f"Résumé — {doc.title}",
            body=body,
            css_href="../assets/cours.css",
            catalog_href="../index.html",
        ),
        encoding="utf-8",
    )

    return ResumeEntry(
        document_id=doc.id,
        slug=slug,
        title=doc.title,
        level=doc.level,
        subject=doc.subject,
        href=f"{slug}/index.html",
    )


def _write_fiche(
    doc: Document,
    chapter_num: int,
    chapter_title: str,
    chapter_text: str,
    dest: Path,
    concepts: list[ConceptLink],
) -> FicheEntry:
    slug = _slugify(f"ch{chapter_num}-{chapter_title}", str(doc.id))
    doc_dir = dest / slug
    doc_dir.mkdir(parents=True, exist_ok=True)

    notions = _extract_bullet_notions(chapter_text)
    sections = _extract_section_titles(chapter_text)
    summary = _short_summary(chapter_text, notions)
    kws = _keywords_from_text(chapter_text)
    linked = _linked_concepts(chapter_text, concepts)

    body = f"""
    <h1>Chapitre {chapter_num} — {_escape(chapter_title)}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(doc.level, doc.level))}</span>
      <span class="badge">Fiche de révision</span>
      · Source : {_escape(doc.title)}
    </p>
    <h2>Résumé</h2>
    <p class="fiche-summary">{_escape(summary)}</p>
    {notions and f"<h2>Notions clés</h2>{_list_html(notions[:10])}" or ""}
    {sections and f"<h2>Sections du chapitre</h2>{_list_html(sections, ordered=True)}" or ""}
    {kws and f"<h2>Termes à retenir</h2>{_list_html(kws)}" or ""}
    {_concept_links_html(linked)}
    <p class="meta"><a href="/cours/">Consulter le cours complet</a></p>
    """

    (doc_dir / "index.html").write_text(
        _page_shell(
            title=f"Fiche — Ch. {chapter_num} {chapter_title}",
            body=body,
            css_href="../assets/cours.css",
            catalog_href="../index.html",
        ),
        encoding="utf-8",
    )

    return FicheEntry(
        document_id=doc.id,
        chapter_num=chapter_num,
        title=chapter_title,
        slug=slug,
        href=f"{slug}/index.html",
    )


def _write_concept_fiches(blocks: list[ConceptBlock], dest: Path) -> list[FicheEntry]:
    """Fiches synthétiques en français à partir de concepts_links.json."""
    entries: list[FicheEntry] = []
    for block in blocks:
        slug = _slugify(f"notion-{block.notion}", "fr")
        doc_dir = dest / slug
        doc_dir.mkdir(parents=True, exist_ok=True)

        relations = [f"{link.notion_liee} — {link.relation}" for link in block.liens]
        summary = block.intro or f"Notion centrale en psychologie : {block.notion}."
        if len(summary) > FICHE_SUMMARY_CHARS:
            summary = summary[: FICHE_SUMMARY_CHARS - 1] + "…"

        body = f"""
    <h1>{_escape(block.notion)}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(block.level, block.level))}</span>
      <span class="badge">Fiche de révision (FR)</span>
      <span class="badge">{_escape(SUBJECT_LABELS.get(block.subject, block.subject))}</span>
    </p>
    <h2>Résumé</h2>
    <p class="fiche-summary">{_escape(summary)}</p>
    <h2>Notions liées</h2>
    {_list_html(relations)}
    <h2>À retenir pour l'examen</h2>
    <ul>
      <li>Définir la notion avec précision (1–2 phrases).</li>
      <li>Citer un auteur ou une expérience de référence si applicable.</li>
      <li>Relier la notion à au moins deux domaines voisins.</li>
    </ul>
    <p class="meta"><a href="/cours/">Consulter les cours</a></p>
    """

        (doc_dir / "index.html").write_text(
            _page_shell(
                title=f"Fiche — {block.notion}",
                body=body,
                css_href="../assets/cours.css",
                catalog_href="../index.html",
            ),
            encoding="utf-8",
        )
        entries.append(FicheEntry(
            document_id=0,
            chapter_num=0,
            title=block.notion,
            slug=slug,
            href=f"{slug}/index.html",
        ))
    return entries


def _write_concept_resumes(blocks: list[ConceptBlock], dest: Path) -> list[ResumeEntry]:
    """Résumés synthétiques en français par notion."""
    entries: list[ResumeEntry] = []
    for block in blocks:
        slug = _slugify(f"notion-{block.notion}", "fr-resume")
        doc_dir = dest / slug
        doc_dir.mkdir(parents=True, exist_ok=True)

        fiche_slug = _slugify(f"notion-{block.notion}", "fr")
        linked_html = _concept_links_html(block.liens)
        intro = block.intro
        if len(intro) > FICHE_SUMMARY_CHARS:
            intro = intro[: FICHE_SUMMARY_CHARS - 1] + "…"

        body = f"""
    <h1>Résumé — {_escape(block.notion)}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(block.level, block.level))}</span>
      <span class="badge">{_escape(SUBJECT_LABELS.get(block.subject, block.subject))}</span>
    </p>
    <h2>En bref</h2>
    <p class="fiche-summary">{_escape(intro)}</p>
    {linked_html}
    <p class="meta"><a href="/fiches/{fiche_slug}/">Voir la fiche complète</a></p>
    """

        (doc_dir / "index.html").write_text(
            _page_shell(
                title=f"Résumé — {block.notion}",
                body=body,
                css_href="../assets/cours.css",
                catalog_href="../index.html",
            ),
            encoding="utf-8",
        )
        entries.append(ResumeEntry(
            document_id=0,
            slug=slug,
            title=block.notion,
            level=block.level,
            subject=block.subject,
            href=f"{slug}/index.html",
        ))
    return entries


def _write_catalog(
    *,
    dest: Path,
    title: str,
    entries: list[tuple[str, str, str]],
    manifest_key: str,
    manifest_items: list[dict],
) -> None:
    by_level: dict[str, list[tuple[str, str]]] = {}
    for level, label, href in entries:
        by_level.setdefault(level, []).append((label, href))

    sections_html = []
    for level in sorted(by_level.keys(), key=_level_sort_key):
        items = "".join(
            f'<li><a href="{_escape(href)}">{_escape(label)}</a></li>'
            for label, href in by_level[level]
        )
        sections_html.append(
            f"<section><h2>{_escape(LEVEL_LABELS.get(level, level))}</h2><ul>{items}</ul></section>"
        )

    body = f"""
    <h1>{_escape(title)}</h1>
    <p class="meta">Généré le {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
    <nav class="hub-links">
      <a href="/cours/">Cours</a> ·
      <a href="/resumes/">Résumés</a> ·
      <a href="/fiches/">Fiches</a>
    </nav>
    {"".join(sections_html) if sections_html else "<p>Aucun contenu exporté.</p>"}
    """

    (dest / "index.html").write_text(
        _page_shell(
            title=title,
            body=body,
            css_href="assets/cours.css",
            catalog_href="index.html",
        ),
        encoding="utf-8",
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        manifest_key: manifest_items,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_hub_page(
    *,
    concept_count: int,
    fiche_count: int,
    resume_count: int,
    course_count: int,
    questionnaire_count: int = 0,
) -> Path:
    """Page d'accueil pédagogique : output/index.html."""
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    assets = HUB_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    css_src = FICHES_DIR / "assets" / "cours.css"
    if css_src.exists():
        shutil.copy2(css_src, assets / "cours.css")
    else:
        _write_css(HUB_DIR)

    by_level: dict[str, int] = {}
    for block in _load_concept_blocks():
        by_level[block.level] = by_level.get(block.level, 0) + 1

    level_lines = "".join(
        f"<li>{_escape(LEVEL_LABELS.get(l, l))} : {n} fiches FR</li>"
        for l, n in sorted(by_level.items(), key=lambda x: _level_sort_key(x[0]))
    )

    q_link = (
        f' · <a href="/questionnaires/">Questionnaires patients ({questionnaire_count})</a>'
        if questionnaire_count
        else ""
    )
    body = f"""
    <h1>Psych IA — Ressources pédagogiques</h1>
    <p class="meta">Licence psychologie L1 / L2 / L3</p>
    <nav class="hub-links">
      <a href="/cours/">Cours ({course_count})</a> ·
      <a href="/fiches/">Fiches ({fiche_count})</a> ·
      <a href="/resumes/">Résumés ({resume_count})</a>{q_link} ·
      <a href="/liner/README.md">Export Liner</a> ·
      <a href="/">Admin</a>
    </nav>
    <section>
      <h2>Programme français ({concept_count} notions)</h2>
      <ul>{level_lines}</ul>
    </section>
    <section>
      <h2>Par niveau</h2>
      <ul>
        <li><a href="/fiches/">Licence 1</a> — générale, sociale, développement, stats, neuro, épistémologie</li>
        <li><a href="/fiches/">Licence 2</a> — cognitive, psychopathologie, stats inférentielles, différentielle, sociale</li>
        <li><a href="/fiches/">Licence 3</a> — clinique, travail, méthodologie, mémoire de recherche</li>
      </ul>
    </section>
    <section>
      <h2>Cours complet (anglais)</h2>
      <p><a href="/cours/">OpenStax Psychology 2e</a> — manuel L1 (755 pages, CC BY).</p>
      <p class="meta">39 leçons en français dans le catalogue des cours.</p>
    </section>
    """

    hub_path = HUB_DIR / "index.html"
    hub_path.write_text(
        _page_shell(
            title="Accueil pédagogique",
            body=body,
            css_href="assets/cours.css",
            catalog_href="index.html",
        ),
        encoding="utf-8",
    )
    return hub_path


def build_fiches_resume_site(
    db: Session,
    *,
    document_ids: list[int] | None = None,
    clean: bool = True,
) -> FichesResumeReport:
    """Génère output/resumes/, output/fiches/ et output/index.html."""
    report = FichesResumeReport()
    blocks = _load_concept_blocks()
    all_links = _flat_concept_links(blocks)

    for dest in (RESUMES_DIR, FICHES_DIR):
        if clean and dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        _write_css(dest)

    documents = _eligible_documents(db, document_ids)
    resume_catalog: list[tuple[str, str, str]] = []
    fiche_catalog: list[tuple[str, str, str]] = []
    resume_manifest: list[dict] = []
    fiche_manifest: list[dict] = []

    concept_fiches = _write_concept_fiches(blocks, FICHES_DIR)
    for f in concept_fiches:
        block = next((b for b in blocks if b.notion == f.title), None)
        level = block.level if block else "L2"
        report.fiches.append(f)
        fiche_catalog.append((level, f.title, f.href))
        fiche_manifest.append({
            "notion": f.title,
            "level": level,
            "href": f.href,
            "type": "concept_fr",
        })

    concept_resumes = _write_concept_resumes(blocks, RESUMES_DIR)
    for r in concept_resumes:
        report.resumes.append(r)
        resume_catalog.append((r.level, r.title, r.href))
        resume_manifest.append({
            "notion": r.title,
            "level": r.level,
            "href": r.href,
            "type": "concept_fr",
        })

    for doc in documents:
        try:
            entry = _write_resume(doc, RESUMES_DIR, all_links)
            if entry:
                report.resumes.append(entry)
                resume_catalog.append((entry.level, entry.title, entry.href))
                resume_manifest.append({
                    "document_id": entry.document_id,
                    "title": entry.title,
                    "level": entry.level,
                    "href": entry.href,
                })
                logger.info("Résumé exporté: %s", doc.title)
        except Exception as e:
            logger.exception("Erreur résumé document %s", doc.id)
            report.skipped.append({"id": doc.id, "title": doc.title, "reason": str(e)})

        path = Path(doc.local_path) if doc.local_path else None
        if not path or not path.exists() or path.suffix.lower() != ".pdf":
            continue

        try:
            pages = extract_text_from_pdf(path)
            chapters = _extract_chapters(pages)
            if not chapters:
                report.skipped.append({
                    "id": doc.id,
                    "title": doc.title,
                    "reason": "aucun chapitre détecté pour fiches",
                })
                continue

            for num, title, text in chapters:
                fiche = _write_fiche(doc, num, title, text, FICHES_DIR, all_links)
                report.fiches.append(fiche)
                fiche_catalog.append((
                    doc.level,
                    f"Ch. {num} — {title}",
                    fiche.href,
                ))
                fiche_manifest.append({
                    "document_id": doc.id,
                    "chapter": num,
                    "title": title,
                    "href": fiche.href,
                })
            logger.info("Fiches exportées: %s (%s chapitres)", doc.title, len(chapters))
        except Exception as e:
            logger.exception("Erreur fiches document %s", doc.id)
            report.skipped.append({"id": doc.id, "title": doc.title, "reason": str(e)})

    _write_catalog(
        dest=RESUMES_DIR,
        title="Catalogue des résumés",
        entries=resume_catalog,
        manifest_key="resumes",
        manifest_items=resume_manifest,
    )
    _write_catalog(
        dest=FICHES_DIR,
        title="Catalogue des fiches de révision",
        entries=fiche_catalog,
        manifest_key="fiches",
        manifest_items=fiche_manifest,
    )

    course_count = 0
    cours_manifest = OUTPUT_DIR / "manifest.json"
    if cours_manifest.exists():
        course_count = len(json.loads(cours_manifest.read_text()).get("courses", []))

    questionnaire_count = 0
    q_manifest = PROJECT_ROOT / "output" / "questionnaires" / "manifest.json"
    if q_manifest.exists():
        questionnaire_count = len(json.loads(q_manifest.read_text()).get("questionnaires", []))

    build_hub_page(
        concept_count=len(blocks),
        fiche_count=len(report.fiches),
        resume_count=len(report.resumes),
        course_count=course_count,
        questionnaire_count=questionnaire_count,
    )

    return report
