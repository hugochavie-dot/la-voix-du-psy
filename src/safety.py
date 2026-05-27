"""Garde-fous : domaines de confiance, motifs bloqués, statut légal.

Ces fonctions appliquent les règles éthiques/légales du projet :
- pas de scraping de plateformes pirates,
- uniquement des éditeurs reconnus,
- ouverture explicite (`open_access` ou licence présente).
"""

from __future__ import annotations

from urllib.parse import urlparse


def domain_of(url: str | None) -> str:
    """Retourne le domaine d'une URL, ou chaîne vide."""
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def is_trusted_domain(url: str | None, trusted_publishers: list[str]) -> bool:
    """Vérifie qu'un domaine (ou un sous-domaine) est dans la liste blanche."""
    host = domain_of(url)
    if not host:
        return False
    for trusted in trusted_publishers:
        t = trusted.lower().strip()
        if not t:
            continue
        if host == t or host.endswith("." + t):
            return True
    return False


def contains_blocked_pattern(url: str | None, blocked_patterns: list[str]) -> str | None:
    """Retourne le motif détecté si l'URL contient un motif interdit."""
    if not url:
        return None
    lowered = url.lower()
    for pattern in blocked_patterns:
        if pattern and pattern.lower() in lowered:
            return pattern
    return None


def has_legal_clearance(legal_status: str | None, license_: str | None) -> bool:
    """`open_access` OU une licence explicite est requise pour télécharger."""
    if (legal_status or "").lower() == "open_access":
        return True
    if license_ and license_.strip():
        return True
    return False
