"""Chemins du projet et création de l'arborescence data2/."""

import os
from pathlib import Path

from app.core.enums import Level, Subject, resolve_data_subpath

# Racine projet = parent de app/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR_NAME = os.environ.get("PSYCH_IA_DATA_DIR", "data2")
DATA_DIR = PROJECT_ROOT / DATA_DIR_NAME
STORAGE_DIR = PROJECT_ROOT / "storage"
LOGS_DIR = PROJECT_ROOT / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"

# Arborescence complète demandée
DATA_SUBDIRS = [
    # L1
    "L1/psychologie_generale",
    "L1/psychologie_sociale",
    "L1/developpement",
    "L1/methodologie",
    "L1/statistiques",
    "L1/biologie_neurosciences",
    "L1/epistemologie",
    # L2
    "L2/psychologie_cognitive",
    "L2/psychopathologie",
    "L2/psychologie_sociale_avancee",
    "L2/statistiques_inferentielles",
    "L2/psychologie_differentielle",
    # L3
    "L3/clinique",
    "L3/social_travail",
    "L3/cognitif_neuro",
    "L3/methodologie_experimentale",
    "L3/memoire_recherche",
    # Recherche
    "recherche_avancee/HAL",
    "recherche_avancee/CNRS",
    "recherche_avancee/INSERM",
    "recherche_avancee/articles_open_access",
    "recherche_avancee/meta_analyses",
    # Ressources libres
    "ressources_libres/OpenStax",
    "ressources_libres/glossaires",
    "ressources_libres/statistiques",
    # Données utilisateur
    "mes_donnees/fiches_revision",
    "mes_donnees/quiz",
    "mes_donnees/exercices_corriges",
    "mes_donnees/cartes_mentales",
    "mes_donnees/erreurs_frequentes",
    "mes_donnees/liens_entre_notions",
]


def ensure_project_dirs() -> None:
    """Crée data/, storage/, logs/ et toute l'arborescence."""
    for d in (DATA_DIR, STORAGE_DIR, LOGS_DIR, STORAGE_DIR / "chroma", STORAGE_DIR / "uploads"):
        d.mkdir(parents=True, exist_ok=True)
    for sub in DATA_SUBDIRS:
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    for sub in DATA_SUBDIRS:
        gitkeep = DATA_DIR / sub / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


def file_storage_path(
    level: Level,
    subject: Subject,
    filename: str,
    *,
    source_url: str = "",
) -> Path:
    """Chemin absolu pour enregistrer un fichier téléchargé."""
    rel = resolve_data_subpath(level, subject, source_url=source_url)
    dest_dir = DATA_DIR / rel
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / filename


def sources_config_path() -> Path:
    """Fichier sources.json (racine, puis config/ en repli)."""
    from config.settings import settings

    root = PROJECT_ROOT / settings.sources_config
    if root.exists():
        return root
    return CONFIG_DIR / "sources.json"
