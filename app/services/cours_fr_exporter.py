"""Export des cours français (L1/L2/L3) depuis concepts_links.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import PROJECT_ROOT
from app.core.logging_config import setup_logging
from app.services.html_common import LEVEL_LABELS, SUBJECT_LABELS, escape as _escape, page_shell

logger = setup_logging("cours_fr_exporter")

CONCEPTS_PATH = PROJECT_ROOT / "concepts_links.json"
LEVEL_ORDER = ["L1", "L2", "L3", "mixte", "recherche_avancee"]

SUBJECT_ORDER = [
    "psychologie_generale",
    "psychologie_sociale",
    "psychologie_du_developpement",
    "neurosciences",
    "statistiques",
    "methodologie_experimentale",
    "epistemologie",
    "psychologie_cognitive",
    "psychopathologie",
    "psychologie_differentielle",
    "psychologie_clinique",
    "psychologie_du_travail",
    "memoire_recherche",
]


@dataclass
class LessonBlock:
    notion: str
    level: str
    subject: str
    intro: str
    liens: list[dict]


def _slugify(text: str) -> str:
    base = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", base).strip("-")[:60] or "lecon"


def _level_sort(level: str) -> int:
    try:
        return LEVEL_ORDER.index(level)
    except ValueError:
        return 99


def _subject_sort(subject: str) -> int:
    try:
        return SUBJECT_ORDER.index(subject)
    except ValueError:
        return 99


def _load_lessons() -> list[LessonBlock]:
    if not CONCEPTS_PATH.exists():
        return []
    raw = json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    return [
        LessonBlock(
            notion=e.get("notion", ""),
            level=e.get("level", "L2"),
            subject=e.get("subject", "psychologie_generale"),
            intro=e.get("intro", ""),
            liens=e.get("liens", []),
        )
        for e in raw
        if e.get("notion")
    ]


def _notion_index(lessons: list[LessonBlock]) -> dict[str, tuple[str, str]]:
    """notion → (module_rel_path, lesson_file)"""
    index: dict[str, tuple[str, str]] = {}
    for lesson in lessons:
        module = f"fr/{lesson.level}/{lesson.subject}"
        index[lesson.notion] = (module, f"{_slugify(lesson.notion)}.html")
    return index


def _list_html(items: list[str], *, ordered: bool = False) -> str:
    if not items:
        return ""
    tag = "ol" if ordered else "ul"
    inner = "".join(f"<li>{_escape(i)}</li>" for i in items)
    return f"<{tag}>{inner}</{tag}>"


def _write_lesson(
    lesson: LessonBlock,
    module_dir: Path,
    *,
    lesson_num: int,
    notion_index: dict[str, tuple[str, str]],
    module_href: str,
) -> str:
    filename = f"{_slugify(lesson.notion)}.html"
    linked_sections: list[str] = []
    for link in lesson.liens:
        target = link.get("notion_liee", "")
        relation = link.get("relation", "")
        if target in notion_index:
            mod, file = notion_index[target]
            href = f"../../{mod}/{file}" if mod != f"fr/{lesson.level}/{lesson.subject}" else file
            linked_sections.append(
                f'<li><a href="{_escape(href)}">{_escape(target)}</a> '
                f"<em>({_escape(relation)})</em></li>"
            )
        else:
            linked_sections.append(
                f"<li>{_escape(target)} <em>({_escape(relation)})</em></li>"
            )

    objectives = [
        f"Définir et illustrer : {lesson.notion}",
        "Identifier les auteurs ou expériences de référence associés",
        "Relier cette leçon à au moins deux autres notions du programme",
    ]
    questions = [
        f"Expliquez {lesson.notion} en 3–5 phrases.",
        "Citez un exemple concret ou une étude classique.",
        "Quels liens avec les chapitres voisins du même module ?",
    ]

    fiche_slug = f"fr-{_slugify(f'notion-{lesson.notion}')}"
    resume_slug = f"fr-resume-{_slugify(f'notion-{lesson.notion}')}"
    body = f"""
    <nav class="part-nav">
      <a href="index.html">← Module {_escape(SUBJECT_LABELS.get(lesson.subject, lesson.subject))}</a>
      <a href="/cours/index.html">Catalogue</a>
    </nav>
    <h1>Leçon {lesson_num} — {_escape(lesson.notion)}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(lesson.level, lesson.level))}</span>
      <span class="badge">{_escape(SUBJECT_LABELS.get(lesson.subject, lesson.subject))}</span>
    </p>
    <h2>Objectifs</h2>
    {_list_html(objectives, ordered=True)}
    <h2>Cours</h2>
    <p>{_escape(lesson.intro)}</p>
    <h2>Notions connexes</h2>
    <ul>{"".join(linked_sections)}</ul>
    <h2>Entraînement</h2>
    {_list_html(questions, ordered=True)}
    <p class="meta">
      <a href="/fiches/{_escape(fiche_slug)}/">Fiche de révision</a> ·
      <a href="/resumes/{_escape(resume_slug)}/">Résumé</a>
    </p>
    """

    (module_dir / filename).write_text(
        page_shell(
            title=f"{lesson.notion} — Leçon {lesson_num}",
            body=body,
            css_href="../../../assets/cours.css",
        ),
        encoding="utf-8",
    )
    return filename


def _write_module(
    level: str,
    subject: str,
    lessons: list[LessonBlock],
    dest: Path,
    notion_index: dict[str, tuple[str, str]],
) -> CourseEntry:
    module_rel = f"fr/{level}/{subject}"
    module_dir = dest / module_rel
    module_dir.mkdir(parents=True, exist_ok=True)

    lesson_items: list[str] = []
    for i, lesson in enumerate(lessons, start=1):
        fname = _write_lesson(
            lesson,
            module_dir,
            lesson_num=i,
            notion_index=notion_index,
            module_href=f"{module_rel}/index.html",
        )
        lesson_items.append(
            f'<li><a href="{_escape(fname)}">Leçon {i} — {_escape(lesson.notion)}</a></li>'
        )

    subj_label = SUBJECT_LABELS.get(subject, subject)
    level_label = LEVEL_LABELS.get(level, level)
    module_body = f"""
    <p class="meta"><a href="/cours/index.html">← Catalogue des cours</a></p>
    <h1>Cours — {subj_label}</h1>
    <p class="meta">
      <span class="badge">{_escape(level_label)}</span>
      · {len(lessons)} leçons · Programme français
    </p>
    <p>Ce module couvre les notions essentielles de {subj_label.lower()} pour le {level_label.lower()}.</p>
    <h2>Leçons</h2>
    <ol>{"".join(lesson_items)}</ol>
    <p class="meta"><a href="/fiches/">Fiches de révision</a> · <a href="/resumes/">Résumés</a></p>
    """

    (module_dir / "index.html").write_text(
        page_shell(
            title=f"Cours {subj_label} — {level_label}",
            body=module_body,
            css_href="../../assets/cours.css",
        ),
        encoding="utf-8",
    )

    from app.services.html_exporter import CourseEntry

    return CourseEntry(
        document_id=0,
        slug=module_rel,
        title=f"Cours {subj_label} ({level_label})",
        level=level,
        subject=subject,
        summary=f"{len(lessons)} leçons — programme français",
        source_url=None,
        page_count=len(lessons),
        part_count=1,
        href=f"{module_rel}/index.html",
    )


def build_fr_courses(dest: Path) -> list[CourseEntry]:
    """Génère les modules de cours FR dans output/cours/fr/."""
    lessons = _load_lessons()
    if not lessons:
        return []

    notion_index = _notion_index(lessons)
    modules: dict[tuple[str, str], list[LessonBlock]] = {}
    for lesson in lessons:
        key = (lesson.level, lesson.subject)
        modules.setdefault(key, []).append(lesson)

    entries: list[CourseEntry] = []
    for (level, subject) in sorted(modules.keys(), key=lambda k: (_level_sort(k[0]), _subject_sort(k[1]))):
        block_lessons = modules[(level, subject)]
        entry = _write_module(level, subject, block_lessons, dest, notion_index)
        entries.append(entry)
        logger.info(
            "Cours FR: %s / %s (%s leçons)",
            level,
            subject,
            len(block_lessons),
        )

    return entries
