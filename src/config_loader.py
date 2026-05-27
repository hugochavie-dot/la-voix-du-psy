"""Chargement et validation structurelle de `sources.json`.

Lit le fichier de configuration et expose des dataclasses typées pour la
suite du pipeline. Aucune logique métier (validation légale, téléchargement…)
n'est faite ici — uniquement de la lecture et un parsing strict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Source:
    """Représentation typée d'une source dans `sources.json`."""

    id: str
    title: str
    document_type: str = "autre"
    level: str = "mixte"
    subject: str = "psychologie_generale"
    legal_status: str = "unknown"
    license: str | None = None
    enabled: bool = False
    download: bool = False
    url: str | None = None
    pdf_url: str | None = None
    notes: str | None = None
    file: str | None = None
    local_hint: str | None = None
    auto_index: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourcesConfig:
    """Configuration complète chargée depuis `sources.json`."""

    description: str
    sources: list[Source]
    blocked_patterns: list[str]
    trusted_publishers: list[str]
    raw: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> SourcesConfig:
    """Charge `sources.json` et retourne un objet `SourcesConfig`.

    Raises:
        FileNotFoundError: fichier inexistant.
        ValueError: JSON invalide ou champs requis manquants.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fichier sources introuvable : {p}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans {p} : {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("sources.json doit contenir un objet JSON à la racine")

    raw_sources = data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("`sources` doit être une liste")

    sources: list[Source] = []
    for idx, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValueError(f"Source #{idx} : objet JSON attendu")
        if "id" not in raw or "title" not in raw:
            raise ValueError(f"Source #{idx} : champs `id` et `title` requis")
        sources.append(
            Source(
                id=str(raw["id"]),
                title=str(raw["title"]),
                document_type=str(raw.get("document_type", "autre")),
                level=str(raw.get("level", "mixte")),
                subject=str(raw.get("subject", "psychologie_generale")),
                legal_status=str(raw.get("legal_status", "unknown")),
                license=raw.get("license"),
                enabled=bool(raw.get("enabled", False)),
                download=bool(raw.get("download", False)),
                url=raw.get("url"),
                pdf_url=raw.get("pdf_url"),
                notes=raw.get("notes"),
                file=raw.get("file"),
                local_hint=raw.get("local_hint"),
                auto_index=bool(raw.get("auto_index", False)),
                raw=raw,
            )
        )

    return SourcesConfig(
        description=str(data.get("description", "")),
        sources=sources,
        blocked_patterns=[str(x) for x in data.get("blocked_patterns", [])],
        trusted_publishers=[str(x) for x in data.get("trusted_publishers", [])],
        raw=data,
    )
