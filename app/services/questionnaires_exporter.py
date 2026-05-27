"""Export HTML des questionnaires patients par thème."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging_config import setup_logging
from app.core.paths import PROJECT_ROOT
from app.services.html_exporter import _escape, _write_css

logger = setup_logging("questionnaires_exporter")

QUESTIONNAIRES_DIR = PROJECT_ROOT / "output" / "questionnaires"
DATA_PATH = PROJECT_ROOT / "questionnaires_patient.json"

LIKERT_LABELS = [
    "Jamais",
    "Rarement",
    "Parfois",
    "Souvent",
    "Très souvent",
]

LEVEL_LABELS = {
    "L1": "Licence 1",
    "L2": "Licence 2",
    "L3": "Licence 3",
}

SUBJECT_LABELS = {
    "psychopathologie": "Psychopathologie",
    "psychologie_du_travail": "Psychologie du travail",
    "psychologie_du_developpement": "Développement",
    "psychologie_generale": "Psychologie générale",
    "psychologie_differentielle": "Psychologie différentielle",
    "biologie_neurosciences": "Neurosciences",
}


@dataclass
class QuestionnaireEntry:
    theme_id: str
    titre: str
    notion_liee: str
    niveau: str
    href: str


@dataclass
class QuestionnairesReport:
    built: list[QuestionnaireEntry] = field(default_factory=list)
    output_dir: Path = QUESTIONNAIRES_DIR


def _slugify(text: str) -> str:
    base = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", base).strip("-")[:50] or "theme"


def _page_shell(*, title: str, body: str, css_href: str, catalog_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(title)} — Questionnaires patients</title>
  <link rel="stylesheet" href="{_escape(css_href)}" />
</head>
<body>
  <header class="site-header">
    <a href="{_escape(catalog_href)}">← Catalogue des questionnaires</a>
  </header>
  <main class="content">{body}</main>
  <footer class="site-footer">
    <p>Ces questionnaires ne remplacent pas un psychologue. En cas de détresse : 3114.</p>
  </footer>
</body>
</html>
"""


def _extra_css() -> str:
    return """
.questionnaire-form { margin-top: 1.5rem; }
.q-block {
  margin-bottom: 1.75rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px dashed var(--border);
}
.q-block label.q-text { display: block; font-weight: 600; margin-bottom: 0.75rem; }
.likert { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.likert label {
  display: flex; align-items: center; gap: 0.35rem;
  padding: 0.45rem 0.75rem; border-radius: 999px;
  border: 1px solid var(--border); background: var(--card);
  font-size: 0.85rem; cursor: pointer;
}
.likert input { accent-color: var(--accent); }
.q-textarea {
  width: 100%; min-height: 5rem; padding: 0.75rem;
  border-radius: 12px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); font: inherit;
}
.btn-primary {
  padding: 0.85rem 1.5rem; border: none; border-radius: 12px;
  background: var(--accent); color: #0f1419; font-weight: 700; cursor: pointer;
}
.btn-primary:hover { filter: brightness(1.08); }
.result-box {
  margin-top: 2rem; padding: 1.25rem; border-radius: 16px;
  border: 1px solid var(--border); background: var(--card);
}
.warning-box {
  margin: 1.5rem 0; padding: 1rem 1.25rem; border-radius: 12px;
  border: 1px solid #b45309; background: rgba(180, 83, 9, 0.12);
  color: #fcd34d; font-size: 0.92rem;
}
.objectifs { margin: 1rem 0; padding-left: 1.25rem; }
.objectifs li { margin: 0.35rem 0; color: var(--muted); }
.notions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }
.notions span {
  padding: 0.25rem 0.65rem; border-radius: 999px;
  background: #243044; font-size: 0.8rem;
}
"""


def _likert_html(q_id: str, inverse: bool = False) -> str:
    options = "".join(
        f'<label><input type="radio" name="{_escape(q_id)}" value="{i}" '
        f'data-inverse="{"1" if inverse else "0"}" required /> {_escape(lbl)}</label>'
        for i, lbl in enumerate(LIKERT_LABELS)
    )
    return f'<div class="likert">{options}</div>'


def _questionnaire_js(theme_id: str) -> str:
    return f"""
<script>
(function() {{
  const form = document.getElementById("qform-{theme_id}");
  const result = document.getElementById("qresult-{theme_id}");
  if (!form || !result) return;

  form.addEventListener("submit", function(e) {{
    e.preventDefault();
    let score = 0;
    let count = 0;
    form.querySelectorAll('input[type="radio"]:checked').forEach(function(input) {{
      let val = parseInt(input.value, 10);
      if (input.dataset.inverse === "1") val = 4 - val;
      score += val;
      count += 1;
    }});
    const max = count * 4;
    const pct = max ? Math.round((score / max) * 100) : 0;
    let msg = "Score indicatif : " + score + " / " + max + " (" + pct + "%). ";
    if (pct >= 60) {{
      msg += "Plusieurs items ressortent : notez vos réponses ouvertes et envisagez d'en parler à un professionnel.";
    }} else if (pct >= 35) {{
      msg += "Quelques signaux à observer : le journal quotidien peut aider à mieux comprendre.";
    }} else {{
      msg += "Peu d'items élevés cette semaine : continuez à observer vos habitudes.";
    }}
    msg += " Ce score n'est pas un diagnostic.";
    result.hidden = false;
    result.querySelector(".result-text").textContent = msg;
    result.scrollIntoView({{ behavior: "smooth" }});
  }});
}})();
</script>
"""


def _write_theme_page(theme: dict, dest: Path) -> QuestionnaireEntry:
    theme_id = theme["id"]
    slug = _slugify(theme_id)
    theme_dir = dest / slug
    theme_dir.mkdir(parents=True, exist_ok=True)

    questions_html = []
    for q in theme.get("questions", []):
        q_id = q["id"]
        block = f'<div class="q-block"><label class="q-text">{_escape(q["texte"])}</label>'
        if q.get("type") == "texte":
            block += f'<textarea class="q-textarea" name="{_escape(q_id)}" rows="3"></textarea>'
        else:
            block += _likert_html(q_id, inverse=bool(q.get("inverse")))
        block += "</div>"
        questions_html.append(block)

    objectifs = "".join(f"<li>{_escape(o)}</li>" for o in theme.get("objectifs", []))
    conseils = "".join(f"<li>{_escape(c)}</li>" for c in theme.get("conseils", []))
    notions = "".join(
        f"<span>{_escape(n)}</span>" for n in theme.get("notions_connexes", [])
    )

    body = f"""
    <h1>{_escape(theme["titre"])}</h1>
    <p class="meta">
      <span class="badge">{_escape(LEVEL_LABELS.get(theme.get("niveau", ""), theme.get("niveau", "")))}</span>
      <span class="badge">{_escape(SUBJECT_LABELS.get(theme.get("matiere", ""), theme.get("matiere", "")))}</span>
      · Notion : {_escape(theme.get("notion_liee", ""))}
    </p>
    <div class="warning-box">
      ⚠️ Auto-réflexion pédagogique uniquement — pas de diagnostic. Consultez un professionnel si besoin (3114).
    </div>
    <p>{_escape(theme.get("intro", ""))}</p>
    <h2>Objectifs</h2>
    <ul class="objectifs">{objectifs}</ul>
    <h2>Questionnaire</h2>
    <form id="qform-{theme_id}" class="questionnaire-form">
      {"".join(questions_html)}
      <button type="submit" class="btn-primary">Voir mon bilan indicatif</button>
    </form>
    <div id="qresult-{theme_id}" class="result-box" hidden>
      <h3>Bilan indicatif</h3>
      <p class="result-text"></p>
      <h4>Conseils pédagogiques</h4>
      <ul>{conseils}</ul>
      <h4>Notions liées (programme L1/L2/L3)</h4>
      <div class="notions">{notions}</div>
    </div>
    {_questionnaire_js(theme_id)}
    """

    (theme_dir / "index.html").write_text(
        _page_shell(
            title=theme["titre"],
            body=body,
            css_href="../assets/cours.css",
            catalog_href="../index.html",
        ),
        encoding="utf-8",
    )

    return QuestionnaireEntry(
        theme_id=theme_id,
        titre=theme["titre"],
        notion_liee=theme.get("notion_liee", ""),
        niveau=theme.get("niveau", ""),
        href=f"{slug}/index.html",
    )


def _write_catalog(entries: list[QuestionnaireEntry], dest: Path, disclaimer: str) -> None:
    by_level: dict[str, list[QuestionnaireEntry]] = {}
    for e in entries:
        by_level.setdefault(e.niveau, []).append(e)

    sections = []
    for level in ("L1", "L2", "L3"):
        items = sorted(by_level.get(level, []), key=lambda x: x.titre.lower())
        if not items:
            continue
        lis = "".join(
            f'<li><a href="{_escape(e.href)}">{_escape(e.titre)}</a>'
            f' <span class="meta">— {_escape(e.notion_liee)}</span></li>'
            for e in items
        )
        label = LEVEL_LABELS.get(level, level)
        sections.append(f"<section><h2>{_escape(label)}</h2><ul>{lis}</ul></section>")

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"""
    <h1>Questionnaires patients par thème</h1>
    <p class="meta">Généré le {built_at} · {len(entries)} thème(s)</p>
    <div class="warning-box">{_escape(disclaimer)}</div>
    <p>Ces questionnaires reprennent les thèmes de vos fiches (<code>concepts_links.json</code>)
    adaptés en langage accessible pour l'auto-réflexion.</p>
    {"".join(sections) if sections else "<p>Aucun questionnaire.</p>"}
    """

    (dest / "index.html").write_text(
        _page_shell(
            title="Catalogue questionnaires",
            body=body,
            css_href="assets/cours.css",
            catalog_href="index.html",
        ),
        encoding="utf-8",
    )

    manifest = {
        "generated_at": built_at,
        "questionnaires": [
            {
                "id": e.theme_id,
                "titre": e.titre,
                "notion_liee": e.notion_liee,
                "niveau": e.niveau,
                "href": e.href,
            }
            for e in entries
        ],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_questionnaires_site(
    *,
    data_path: Path | None = None,
    output_dir: Path | None = None,
    clean: bool = True,
) -> QuestionnairesReport:
    """Génère output/questionnaires/ à partir de questionnaires_patient.json."""
    src = data_path or DATA_PATH
    dest = output_dir or QUESTIONNAIRES_DIR
    report = QuestionnairesReport(output_dir=dest)

    if not src.exists():
        raise FileNotFoundError(f"Fichier introuvable : {src}")

    data = json.loads(src.read_text(encoding="utf-8"))
    disclaimer = data.get("meta", {}).get("disclaimer", "")

    if clean and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _write_css(dest)
    extra_css_path = dest / "assets" / "cours.css"
    extra_css_path.write_text(
        extra_css_path.read_text(encoding="utf-8") + _extra_css(),
        encoding="utf-8",
    )

    for theme in data.get("themes", []):
        entry = _write_theme_page(theme, dest)
        report.built.append(entry)
        logger.info("Questionnaire exporté : %s", theme["titre"])

    _write_catalog(report.built, dest, disclaimer)
    return report
