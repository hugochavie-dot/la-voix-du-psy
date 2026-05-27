"""Chargement et validation structurelle de sources.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    """Configuration globale lue depuis sources.json."""

    description: str
    sources: list[dict[str, Any]]
    blocked_patterns: list[str] = field(default_factory=list)
    trusted_publishers: list[str] = field(default_factory=list)
    config_path: Path = Path("sources.json")


def load_config(sources_path: Path | str) -> AppConfig:
    """Charge sources.json et retourne un AppConfig typé."""
    path = Path(sources_path)
    if not path.is_file():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {path}")

    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    if "sources" not in raw or not isinstance(raw["sources"], list):
        raise ValueError("sources.json doit contenir une liste 'sources'.")

    return AppConfig(
        description=str(raw.get("description", "")),
        sources=raw["sources"],
        blocked_patterns=list(raw.get("blocked_patterns", [])),
        trusted_publishers=list(raw.get("trusted_publishers", [])),
        config_path=path.resolve(),
    )
