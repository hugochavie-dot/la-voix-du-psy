"""Validation légale et technique des sources avant téléchargement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class ValidationResult:
    """Résultat de validation pour une source."""

    source_id: str
    can_download: bool = False
    index_status: str = "reference_only"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_reason(self, reason: str) -> None:
        self.reasons.append(reason)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().strip()


def _domain_trusted(url: str, trusted_publishers: list[str]) -> bool:
    host = _host(url)
    if not host:
        return False
    for publisher in trusted_publishers:
        pub = publisher.lower().strip()
        if host == pub or host.endswith(f".{pub}"):
            return True
    return False


def _contains_blocked_pattern(text: str, blocked_patterns: list[str]) -> str | None:
    lowered = text.lower()
    for pattern in blocked_patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def _urls_to_check(source: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("url", "pdf_url"):
        value = source.get(key)
        if value:
            urls.append(str(value))
    return urls


def validate_source(source: dict[str, Any], config_trusted: list[str], config_blocked: list[str]) -> ValidationResult:
    """
    Valide une source selon les règles du projet.

    Statuts possibles dans index_status :
    disabled | local_user_content | reference_only | downloadable |
    to_verify | error | downloaded
    """
    source_id = str(source.get("id", "unknown"))
    result = ValidationResult(source_id=source_id)

    enabled = bool(source.get("enabled", False))
    download = bool(source.get("download", False))
    legal_status = str(source.get("legal_status", "unknown"))
    license_ = source.get("license")
    pdf_url = source.get("pdf_url")

    if not enabled:
        result.index_status = "disabled"
        result.add_reason("enabled=false")
        return result

    if legal_status == "created_by_user":
        result.index_status = "local_user_content"
        result.add_reason("contenu créé par l'utilisateur (pas de téléchargement auto)")
        return result

    if not download:
        result.index_status = "reference_only"
        result.add_reason("download=false — référence uniquement")
        return result

    # --- Source marquée download=true : contrôles stricts ---
    for url in _urls_to_check(source):
        blocked = _contains_blocked_pattern(url, config_blocked)
        if blocked:
            result.index_status = "to_verify"
            result.add_reason(f"motif bloqué détecté dans l'URL : {blocked}")
            return result

        if source.get("url") and url == source.get("url") and not _domain_trusted(url, config_trusted):
            result.index_status = "to_verify"
            result.add_reason(f"domaine non fiable pour url : {_host(url)}")
            return result

    if not pdf_url:
        result.index_status = "to_verify"
        result.add_reason("pdf_url manquante — téléchargement impossible")
        return result

    pdf_blocked = _contains_blocked_pattern(str(pdf_url), config_blocked)
    if pdf_blocked:
        result.index_status = "to_verify"
        result.add_reason(f"motif bloqué détecté dans pdf_url : {pdf_blocked}")
        return result

    if not _domain_trusted(str(pdf_url), config_trusted):
        result.index_status = "to_verify"
        result.add_reason(f"domaine pdf_url non fiable : {_host(str(pdf_url))}")
        return result

    if legal_status != "open_access" and not license_:
        result.index_status = "to_verify"
        result.add_reason("legal_status sans open_access et sans licence explicite")
        return result

    if legal_status == "unknown":
        result.index_status = "to_verify"
        result.add_reason("legal_status inconnu")
        return result

    result.can_download = True
    result.index_status = "downloadable"
    return result
