"""Fichiers locaux utilisateur et règles de sécurité pédagogique."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

SYSTEM_RULES = """RÈGLES SYSTÈME — IA PÉDAGOGIQUE PSYCHOLOGIE

1. L'IA ne remplace pas un psychologue, un psychiatre ni un médecin.
2. L'IA ne pose pas de diagnostic médical ou psychiatrique.
3. L'IA ne propose pas de traitement médical ni psychologique personnalisé.
4. L'IA cite ses sources (titre, auteur, institution, URL si disponible).
5. L'IA distingue clairement cours de base (L1/L2/L3) et recherche avancée.
6. En cas de détresse ou de souffrance mentionnée, l'IA oriente vers un professionnel
   de santé mentale ou une ligne d'écoute (ex. 3114 en France).
7. L'IA explique clairement les limites de ses réponses et indique quand elle manque de sources.
8. Seules les sources open access, créées par l'utilisateur ou explicitement autorisées
   entrent dans la base RAG automatique.
9. Ne jamais reproduire intégralement un ouvrage protégé ; privilégier résumés et citations courtes.
"""

GLOSSAIRE_TEMPLATE: dict[str, Any] = {
    "description": "Glossaire personnel — termes de psychologie",
    "entries": [
        {
            "terme": "exemple_conditionnement",
            "definition": "Apprentissage par association entre stimulus et réponse.",
            "niveau": "L1",
            "source": "cours personnel",
        }
    ],
}

QUIZ_TEMPLATE: dict[str, Any] = {
    "description": "Banque de quiz QCM — à compléter",
    "questions": [
        {
            "id": "q001",
            "notion": "Conditionnement",
            "level": "L1",
            "question": "Qu'est-ce qu'un stimulus conditionné ?",
            "choices": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "À compléter.",
        }
    ],
}

FICHES_TEMPLATE: dict[str, Any] = {
    "description": "Banque de fiches de révision — à compléter",
    "fiches": [
        {
            "notion": "Mémoire",
            "level": "L1",
            "points_cles": ["encodage", "stockage", "rappel"],
            "resume": "À compléter.",
        }
    ],
}

CONCEPTS_TEMPLATE: list[dict[str, Any]] = [
    {
        "notion": "Exemple de notion",
        "level": "L1",
        "subject": "psychologie_generale",
        "intro": "Texte d'introduction pédagogique.",
        "liens": [{"notion_liee": "Autre notion", "relation": "lien conceptuel"}],
    }
]


def _write_json(path: Path, payload: Any, *, dry_run: bool = False) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _write_text(path: Path, content: str, *, dry_run: bool = False) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_user_templates(
    user_dir: Path,
    *,
    project_root: Path | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """
    Crée les fichiers modèles dans data/created_by_user/ s'ils n'existent pas.

    Si concepts_links.json existe à la racine du projet, il est copié comme modèle initial.
    """
    created: list[Path] = []
    targets = {
        user_dir / "glossaire_psychologie.json": GLOSSAIRE_TEMPLATE,
        user_dir / "banque_quiz.json": QUIZ_TEMPLATE,
        user_dir / "banque_fiches_revision.json": FICHES_TEMPLATE,
    }

    for path, template in targets.items():
        if not path.exists():
            _write_json(path, template, dry_run=dry_run)
            created.append(path)

    concepts_dest = user_dir / "concepts_links.json"
    if not concepts_dest.exists():
        root_concepts = (project_root or Path.cwd()) / "concepts_links.json"
        if root_concepts.is_file() and not dry_run:
            user_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root_concepts, concepts_dest)
            created.append(concepts_dest)
        else:
            _write_json(concepts_dest, CONCEPTS_TEMPLATE, dry_run=dry_run)
            created.append(concepts_dest)

    rules_path = user_dir / "system_rules.txt"
    if not rules_path.exists():
        config_rules = (project_root or Path.cwd()) / "config" / "system_rules.txt"
        if config_rules.is_file() and not dry_run:
            user_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_rules, rules_path)
        else:
            _write_text(rules_path, SYSTEM_RULES, dry_run=dry_run)
        created.append(rules_path)

    return created
