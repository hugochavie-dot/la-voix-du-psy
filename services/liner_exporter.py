"""Export Markdown + PDF pour import dans Liner (liner.com)."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from app.core.logging_config import setup_logging
from app.core.paths import PROJECT_ROOT
from app.services.cours_fr_exporter import (
    LEVEL_ORDER,
    SUBJECT_ORDER,
    LessonBlock,
    _load_lessons,
    _level_sort,
    _slugify,
    _subject_sort,
)
from app.services.html_common import LEVEL_LABELS, SUBJECT_LABELS

logger = setup_logging("liner_exporter")

OUTPUT_DIR = PROJECT_ROOT / "output" / "liner"

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 50
FONT_SIZE = 11
LINE_HEIGHT = 14


@dataclass
class LinerExportReport:
    markdown_files: list[Path] = field(default_factory=list)
    pdf_files: list[Path] = field(default_factory=list)
    output_dir: Path = OUTPUT_DIR


def _group_lessons(lessons: list[LessonBlock]) -> dict[tuple[str, str], list[LessonBlock]]:
    modules: dict[tuple[str, str], list[LessonBlock]] = {}
    for lesson in lessons:
        modules.setdefault((lesson.level, lesson.subject), []).append(lesson)
    return modules


def _lesson_markdown(lesson: LessonBlock, num: int) -> str:
    lines = [
        f"## Leçon {num} — {lesson.notion}",
        "",
        f"**Niveau :** {LEVEL_LABELS.get(lesson.level, lesson.level)}",
        f"**Matière :** {SUBJECT_LABELS.get(lesson.subject, lesson.subject)}",
        "",
        "### Cours",
        "",
        lesson.intro,
        "",
        "### Notions connexes",
        "",
    ]
    for link in lesson.liens:
        lines.append(f"- **{link.get('notion_liee', '')}** — {link.get('relation', '')}")
    lines.extend([
        "",
        "### Questions d'entraînement",
        "",
        f"1. Définissez *{lesson.notion}* en 3–5 phrases.",
        "2. Citez un auteur ou une expérience de référence.",
        "3. Reliez cette notion à deux autres chapitres du programme.",
        "",
        "---",
        "",
    ])
    return "\n".join(lines)


def _module_markdown(level: str, subject: str, lessons: list[LessonBlock]) -> str:
    subj = SUBJECT_LABELS.get(subject, subject)
    lvl = LEVEL_LABELS.get(level, level)
    parts = [
        f"# Cours — {subj} ({lvl})",
        "",
        f"Programme Psych IA · {len(lessons)} leçons · Usage pédagogique personnel",
        "",
        "---",
        "",
    ]
    for i, lesson in enumerate(lessons, start=1):
        parts.append(_lesson_markdown(lesson, i))
    return "\n".join(parts)


def _wrap_paragraph(text: str, width: int = 90) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        if para.startswith("#"):
            lines.append(para.lstrip("# ").strip())
            lines.append("")
            continue
        if para.startswith("- "):
            lines.extend(textwrap.wrap(para, width=width, subsequent_indent="  "))
            continue
        lines.extend(textwrap.wrap(para, width=width))
        lines.append("")
    return lines


def _markdown_to_pdf(markdown: str, dest: Path, *, title: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN
    max_y = PAGE_HEIGHT - MARGIN

    def new_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = MARGIN

    page.insert_text(
        (MARGIN, y),
        title,
        fontsize=16,
        fontname="helv",
    )
    y += 28

    for line in _wrap_paragraph(markdown):
        if y > max_y:
            new_page()
        if not line:
            y += LINE_HEIGHT // 2
            continue
        is_heading = line.isupper() or line.startswith("Leçon ")
        fontsize = FONT_SIZE + (2 if is_heading else 0)
        page.insert_text((MARGIN, y), line, fontsize=fontsize, fontname="helv")
        y += LINE_HEIGHT + (2 if is_heading else 0)

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))
    doc.close()


def _write_readme(dest: Path, report: LinerExportReport) -> None:
    content = f"""# Export Liner — Psych IA Ressources

Ce dossier contient vos cours en **Markdown** et **PDF**, prêts pour [Liner](https://liner.com).

## Importer dans Liner

### Option 1 — PDF (recommandé)
1. Ouvrez [liner.com](https://liner.com) ou l'extension navigateur Liner.
2. Allez dans **My Space** → **Upload** / import de fichier.
3. Uploadez les PDF du dossier `pdf/` (un fichier = un module de cours).
4. Surlignez et annotez directement dans Liner.

### Option 2 — Markdown
1. Ouvrez un fichier `.md` dans le navigateur (ou VS Code + preview).
2. Utilisez l'**extension Liner** pour surligner les passages importants.
3. Les surlignages sont enregistrés dans My Space.

## Contenu exporté

- **{len(report.pdf_files)}** PDF (modules par matière et niveau)
- **{len(report.markdown_files)}** fichiers Markdown
- Pas de sources HAL — programme français + OpenStax séparément

## Structure

```
liner/
  README.md          ← ce fichier
  pdf/L1/…           ← PDF par module (upload Liner)
  markdown/L1/…      ← sources Markdown
```

## OpenStax (anglais, 755 pages)

Le manuel complet reste dans `output/cours/1-psychology-2e/`.
Pour Liner, importez plutôt les modules **français** ci-dessus, ou un chapitre OpenStax à la fois.

Généré par : `python scripts/export_liner.py`
"""
    (dest / "README.md").write_text(content, encoding="utf-8")


def export_for_liner(*, output_dir: Path | None = None) -> LinerExportReport:
    """Génère output/liner/ (Markdown + PDF par module)."""
    dest = output_dir or OUTPUT_DIR
    report = LinerExportReport(output_dir=dest)

    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    lessons = _load_lessons()
    modules = _group_lessons(lessons)

    for (level, subject), block_lessons in sorted(
        modules.items(),
        key=lambda x: (_level_sort(x[0][0]), _subject_sort(x[0][1])),
    ):
        md = _module_markdown(level, subject, block_lessons)
        subj_slug = _slugify(SUBJECT_LABELS.get(subject, subject))
        rel = Path(level) / subj_slug

        md_path = dest / "markdown" / rel / "cours.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        report.markdown_files.append(md_path)

        pdf_title = f"{SUBJECT_LABELS.get(subject, subject)} — {LEVEL_LABELS.get(level, level)}"
        pdf_path = dest / "pdf" / rel.with_suffix(".pdf")
        _markdown_to_pdf(md, pdf_path, title=pdf_title)
        report.pdf_files.append(pdf_path)
        logger.info("Liner export: %s (%s leçons)", pdf_path.relative_to(dest), len(block_lessons))

    _write_readme(dest, report)
    return report
