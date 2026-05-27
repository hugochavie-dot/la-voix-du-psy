"""Classification automatique niveau / matière à partir de métadonnées."""

from __future__ import annotations

import re

from app.core.enums import Difficulty, DocumentType, Level, Subject
from app.core.logging_config import setup_logging

logger = setup_logging("classifier")

# Règles mot-clé → (niveau, matière, difficulté)
KEYWORD_RULES: list[tuple[list[str], Level, Subject, Difficulty]] = [
    (["introduction", "l1", "licence 1", "fondamentaux"], Level.L1, Subject.PSYCHOLOGIE_GENERALE, Difficulty.DEBUTANT),
    (["psychologie sociale", "social"], Level.L1, Subject.PSYCHOLOGIE_SOCIALE, Difficulty.INTERMEDIAIRE),
    (["développement", "developpement", "enfant"], Level.L1, Subject.PSYCHOLOGIE_DEVELOPPEMENT, Difficulty.INTERMEDIAIRE),
    (["épistémologie", "epistemologie"], Level.L1, Subject.EPISTEMOLOGIE, Difficulty.INTERMEDIAIRE),
    (["biologie", "neurosciences", "cerveau"], Level.L1, Subject.NEUROSCIENCES, Difficulty.INTERMEDIAIRE),
    (["statistiques descriptives", "probabilités"], Level.L1, Subject.STATISTIQUES, Difficulty.INTERMEDIAIRE),
    (["cognitive", "mémoire", "attention", "perception"], Level.L2, Subject.PSYCHOLOGIE_COGNITIVE, Difficulty.INTERMEDIAIRE),
    (["psychopathologie", "dsm", "trouble"], Level.L2, Subject.PSYCHOPATHOLOGIE, Difficulty.AVANCE),
    (["inférentielle", "inferentielle", "anova", "régression"], Level.L2, Subject.STATISTIQUES, Difficulty.AVANCE),
    (["différentielle", "differentielle", "personnalité"], Level.L2, Subject.PSYCHOLOGIE_DIFFERENTIELLE, Difficulty.INTERMEDIAIRE),
    (["clinique", "thérapie", "entretien"], Level.L3, Subject.PSYCHOLOGIE_CLINIQUE, Difficulty.AVANCE),
    (["travail", "organisation", "ergonomie"], Level.L3, Subject.PSYCHOLOGIE_TRAVAIL, Difficulty.AVANCE),
    (["expérimentale", "experimental", "design"], Level.L3, Subject.METHODOLOGIE_EXPERIMENTALE, Difficulty.AVANCE),
    (["mémoire", "memoire", "soutenance"], Level.L3, Subject.MEMOIRE_RECHERCHE, Difficulty.AVANCE),
    (["méta-analyse", "meta-analysis", "revue systématique"], Level.RECHERCHE_AVANCEE, Subject.PSYCHOLOGIE_COGNITIVE, Difficulty.EXPERT),
    (["hal", "preprint", "doi"], Level.RECHERCHE_AVANCEE, Subject.PSYCHOLOGIE_GENERALE, Difficulty.EXPERT),
    (["openstax", "manuel libre"], Level.L1, Subject.PSYCHOLOGIE_GENERALE, Difficulty.DEBUTANT),
    (["glossaire"], Level.L1, Subject.GLOSSAIRE, Difficulty.DEBUTANT),
    (["quiz", "qcm"], Level.L1, Subject.QUIZ, Difficulty.INTERMEDIAIRE),
    (["fiche", "révision"], Level.L1, Subject.FICHES_REVISION, Difficulty.INTERMEDIAIRE),
]


def classify_from_text(
    title: str,
    text_sample: str = "",
    document_type: DocumentType | None = None,
    url: str = "",
) -> tuple[Level, Subject, Difficulty]:
    """Infère niveau, matière et difficulté."""
    combined = f"{title} {text_sample} {url}".lower()

    if document_type in (DocumentType.ARTICLE_SCIENTIFIQUE, DocumentType.META_ANALYSE):
        if not any(k in combined for k in ["vulgarisation", "introduction", "synthèse l1"]):
            return Level.RECHERCHE_AVANCEE, Subject.PSYCHOLOGIE_GENERALE, Difficulty.EXPERT

    if "openstax" in combined:
        return Level.L1, Subject.PSYCHOLOGIE_GENERALE, Difficulty.DEBUTANT

    if "hal." in url or "hal.science" in url:
        return Level.RECHERCHE_AVANCEE, Subject.PSYCHOLOGIE_GENERALE, Difficulty.EXPERT

    best_score = 0
    result = (Level.L1, Subject.PSYCHOLOGIE_GENERALE, Difficulty.INTERMEDIAIRE)

    for keywords, level, subject, diff in KEYWORD_RULES:
        score = sum(1 for k in keywords if k in combined)
        if score > best_score:
            best_score = score
            result = (level, subject, diff)

    if document_type == DocumentType.QUIZ:
        return Level.L1, Subject.QUIZ, Difficulty.INTERMEDIAIRE
    if document_type == DocumentType.GLOSSAIRE:
        return Level.L1, Subject.GLOSSAIRE, Difficulty.DEBUTANT
    if document_type == DocumentType.FICHE_REVISION:
        return Level.L1, Subject.FICHES_REVISION, Difficulty.INTERMEDIAIRE

    logger.debug("Classification: %s → %s", title[:60], result)
    return result


def suggest_document_type(filename: str, url: str, text: str) -> DocumentType:
    s = f"{filename} {url} {text[:500]}".lower()
    if "openstax" in s:
        return DocumentType.MANUEL_LIBRE
    if "quiz" in s or "qcm" in s:
        return DocumentType.QUIZ
    if "annale" in s:
        return DocumentType.ANNALES
    if "td" in s or "travaux dirigés" in s:
        return DocumentType.FICHE_TD
    if "meta" in s and "analys" in s:
        return DocumentType.META_ANALYSE
    if "article" in s or "doi" in s:
        return DocumentType.ARTICLE_SCIENTIFIQUE
    if "glossaire" in s:
        return DocumentType.GLOSSAIRE
    if "maquette" in s or "référentiel" in s or "rncp" in s:
        return DocumentType.REFERENTIEL
    if s.endswith(".pdf") or "cours" in s:
        return DocumentType.COURS_PDF
    return DocumentType.AUTRE


def extract_year(text: str) -> int | None:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    if years:
        return int(years[-1])
    return None
