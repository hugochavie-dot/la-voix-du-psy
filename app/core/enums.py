"""Énumérations métier pour classification et statut légal."""

from __future__ import annotations

from enum import Enum


class LegalStatus(str, Enum):
    OPEN_ACCESS = "open_access"
    CREATED_BY_USER = "created_by_user"
    AUTHORIZED = "authorized"
    UNKNOWN = "unknown"
    REJECTED = "rejected"

    @property
    def usable_by_rag(self) -> bool:
        return self in {
            LegalStatus.OPEN_ACCESS,
            LegalStatus.CREATED_BY_USER,
            LegalStatus.AUTHORIZED,
        }


class Level(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    MIXTE = "mixte"
    RECHERCHE_AVANCEE = "recherche_avancee"


class Subject(str, Enum):
    PSYCHOLOGIE_GENERALE = "psychologie_generale"
    PSYCHOLOGIE_SOCIALE = "psychologie_sociale"
    PSYCHOLOGIE_COGNITIVE = "psychologie_cognitive"
    PSYCHOLOGIE_DEVELOPPEMENT = "psychologie_du_developpement"
    PSYCHOPATHOLOGIE = "psychopathologie"
    NEUROSCIENCES = "neurosciences"
    STATISTIQUES = "statistiques"
    METHODOLOGIE_EXPERIMENTALE = "methodologie_experimentale"
    EPISTEMOLOGIE = "epistemologie"
    PSYCHOLOGIE_DIFFERENTIELLE = "psychologie_differentielle"
    PSYCHOLOGIE_TRAVAIL = "psychologie_du_travail"
    PSYCHOLOGIE_CLINIQUE = "psychologie_clinique"
    MEMOIRE_RECHERCHE = "memoire_recherche"
    GLOSSAIRE = "glossaire"
    QUIZ = "quiz"
    FICHES_REVISION = "fiches_de_revision"
    LIENS_NOTIONS = "liens_entre_notions"


class DocumentType(str, Enum):
    COURS_PDF = "cours_pdf"
    PLAN_COURS = "plan_cours"
    BIBLIOGRAPHIE = "bibliographie"
    FICHE_TD = "fiche_td"
    ANNALES = "annales"
    METHODOLOGIE = "methodologie"
    ARTICLE_SCIENTIFIQUE = "article_scientifique"
    RESUME_ARTICLE = "resume_article"
    META_ANALYSE = "meta_analyse"
    MANUEL_LIBRE = "manuel_libre"
    GLOSSAIRE = "glossaire"
    QUIZ = "quiz"
    EXERCICE_CORRIGE = "exercice_corrige"
    CARTE_MENTALE = "carte_mentale"
    FICHE_REVISION = "fiche_revision"
    FICHE_ERREURS = "fiche_erreurs"
    REFERENTIEL = "referentiel"
    MAQUETTE = "maquette"
    AUTRE = "autre"


class Difficulty(str, Enum):
    DEBUTANT = "debutant"
    INTERMEDIAIRE = "intermediaire"
    AVANCE = "avance"
    EXPERT = "expert"


# Mapping niveau → sous-dossier data/
LEVEL_FOLDER_MAP: dict[Level, str] = {
    Level.L1: "L1",
    Level.L2: "L2",
    Level.L3: "L3",
    Level.MIXTE: "L1",  # défaut conservateur
    Level.RECHERCHE_AVANCEE: "recherche_avancee",
}

# Mapping matière → sous-dossier (arborescence utilisateur)
SUBJECT_FOLDER_MAP: dict[Subject, dict[Level, str]] = {
    # L1
    Subject.PSYCHOLOGIE_GENERALE: {Level.L1: "psychologie_generale"},
    Subject.PSYCHOLOGIE_SOCIALE: {
        Level.L1: "psychologie_sociale",
        Level.L2: "psychologie_sociale_avancee",
    },
    Subject.PSYCHOLOGIE_DEVELOPPEMENT: {Level.L1: "developpement"},
    Subject.METHODOLOGIE_EXPERIMENTALE: {
        Level.L1: "methodologie",
        Level.L3: "methodologie_experimentale",
    },
    Subject.STATISTIQUES: {
        Level.L1: "statistiques",
        Level.L2: "statistiques_inferentielles",
    },
    Subject.NEUROSCIENCES: {
        Level.L1: "biologie_neurosciences",
        Level.L3: "cognitif_neuro",
    },
    Subject.EPISTEMOLOGIE: {Level.L1: "epistemologie"},
    # L2
    Subject.PSYCHOLOGIE_COGNITIVE: {Level.L2: "psychologie_cognitive"},
    Subject.PSYCHOPATHOLOGIE: {Level.L2: "psychopathologie"},
    Subject.PSYCHOLOGIE_DIFFERENTIELLE: {Level.L2: "psychologie_differentielle"},
    # L3
    Subject.PSYCHOLOGIE_CLINIQUE: {Level.L3: "clinique"},
    Subject.PSYCHOLOGIE_TRAVAIL: {Level.L3: "social_travail"},
    Subject.MEMOIRE_RECHERCHE: {Level.L3: "memoire_recherche"},
    # Recherche
    Subject.GLOSSAIRE: {Level.RECHERCHE_AVANCEE: "glossaires"},
    # Données utilisateur
    Subject.FICHES_REVISION: {Level.L1: "fiches_revision"},
    Subject.QUIZ: {Level.L1: "quiz"},
    Subject.LIENS_NOTIONS: {Level.L1: "liens_entre_notions"},
}


def resolve_data_subpath(
    level: Level,
    subject: Subject,
    *,
    source_url: str = "",
    document_type: str | None = None,
) -> str:
    """Retourne le chemin relatif data2/ pour stocker un fichier."""
    url = (source_url or "").lower()
    doc = (document_type or "").lower()

    if "openstax" in url or doc == "manuel_libre":
        return "ressources_libres/OpenStax"

    if subject == Subject.GLOSSAIRE or doc == "glossaire":
        return "ressources_libres/glossaires"

    if doc in ("quiz",) or subject == Subject.QUIZ:
        return "mes_donnees/quiz"
    if doc in ("fiche_revision",) or subject == Subject.FICHES_REVISION:
        return "mes_donnees/fiches_revision"
    if doc in ("exercice_corrige",):
        return "mes_donnees/exercices_corriges"
    if doc in ("carte_mentale",):
        return "mes_donnees/cartes_mentales"
    if doc in ("fiche_erreurs",):
        return "mes_donnees/erreurs_frequentes"
    if subject == Subject.LIENS_NOTIONS:
        return "mes_donnees/liens_entre_notions"

    if level == Level.RECHERCHE_AVANCEE or "hal." in url or "hal.science" in url:
        if "hal." in url or "hal.science" in url:
            return "recherche_avancee/HAL"
        if "cnrs.fr" in url:
            return "recherche_avancee/CNRS"
        if "inserm.fr" in url:
            return "recherche_avancee/INSERM"
        if doc == "meta_analyse" or "meta-analys" in url or "meta_analys" in url:
            return "recherche_avancee/meta_analyses"
        return "recherche_avancee/articles_open_access"

    level_key = LEVEL_FOLDER_MAP.get(level, "ressources_libres")
    subj_map = SUBJECT_FOLDER_MAP.get(subject, {})
    folder = subj_map.get(level) or subj_map.get(Level.L1) or subject.value
    return f"{level_key}/{folder}"
