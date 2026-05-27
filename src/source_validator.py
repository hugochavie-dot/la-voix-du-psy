"""Validation métier de chaque source.

Décide, pour chaque source :
- si elle est **téléchargeable** (toutes les conditions sont réunies),
- sinon, **pourquoi** elle est ignorée (raison lisible).

Le résultat sert ensuite au `downloader`, au `metadata_builder`, et à
l'index `to_verify/sources_a_verifier.csv`.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config_loader import Source
from src.safety import (
    contains_blocked_pattern,
    has_legal_clearance,
    is_trusted_domain,
)


STATUS_DOWNLOADABLE = "downloadable"
STATUS_REFERENCE_ONLY = "reference_only"
STATUS_DISABLED = "disabled"
STATUS_LOCAL_USER_CONTENT = "local_user_content"
STATUS_TO_VERIFY = "to_verify"


@dataclass
class ValidationResult:
    """Résultat de validation pour une source."""

    source: Source
    status: str
    reasons: list[str]

    @property
    def downloadable(self) -> bool:
        return self.status == STATUS_DOWNLOADABLE

    @property
    def is_local_user_content(self) -> bool:
        return self.status == STATUS_LOCAL_USER_CONTENT


def validate_source(
    source: Source,
    *,
    blocked_patterns: list[str],
    trusted_publishers: list[str],
) -> ValidationResult:
    """Évalue une source et retourne son statut + raisons."""
    reasons: list[str] = []

    if (source.legal_status or "").lower() == "created_by_user":
        return ValidationResult(source, STATUS_LOCAL_USER_CONTENT, ["Contenu local utilisateur"])

    if not source.enabled:
        reasons.append("`enabled=false`")
        return ValidationResult(source, STATUS_DISABLED, reasons)

    if not source.download:
        reasons.append("`download=false` — référencée uniquement")
        return ValidationResult(source, STATUS_REFERENCE_ONLY, reasons)

    if not has_legal_clearance(source.legal_status, source.license):
        reasons.append("statut légal non `open_access` et pas de licence explicite")
    if not source.pdf_url:
        reasons.append("aucun `pdf_url` fourni")

    candidate_url = source.pdf_url or source.url
    blocked = contains_blocked_pattern(candidate_url, blocked_patterns)
    if blocked:
        reasons.append(f"URL contient un motif bloqué : `{blocked}`")

    if candidate_url and not is_trusted_domain(candidate_url, trusted_publishers):
        reasons.append("domaine hors liste de `trusted_publishers`")

    if reasons:
        return ValidationResult(source, STATUS_TO_VERIFY, reasons)

    return ValidationResult(source, STATUS_DOWNLOADABLE, ["Toutes les conditions sont remplies"])


def validate_all(
    sources: list[Source],
    *,
    blocked_patterns: list[str],
    trusted_publishers: list[str],
) -> list[ValidationResult]:
    """Applique `validate_source` à toutes les sources."""
    return [
        validate_source(
            s,
            blocked_patterns=blocked_patterns,
            trusted_publishers=trusted_publishers,
        )
        for s in sources
    ]
