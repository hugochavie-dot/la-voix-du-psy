"""Vérification légale des sources avant intégration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.enums import DocumentType, LegalStatus
from app.core.logging_config import setup_logging

logger = setup_logging("legal_checker")

# Domaines et motifs de confiance (open access / public)
TRUSTED_DOMAINS = {
    "hal.science",
    "hal.archives-ouvertes.fr",
    ".hal.science",
    "hal.parisnanterre.fr",
    "univ-tlse2.hal.science",
    "arxiv.org",
    "psyarxiv.com",
    "osf.io",
    "openstax.org",
    "cnrs.fr",
    "inserm.fr",
    "education.gouv.fr",
    "enseignementsup-recherche.gouv.fr",
    "francecompetences.fr",
    "univ-",
    "universite",
    "u-psud.fr",
    "sorbonne-universite.fr",
    "wiktionary.org",
    "wikipedia.org",
    "creativecommons.org",
    "doaj.org",
    "plos.org",
    "frontiersin.org",
    "bmcpsychology.biomedcentral.com",
    "ncbi.nlm.nih.gov",  # PubMed Central open subset — vérification manuelle conseillée
}

# Motifs indiquant open access / licence libre
OPEN_ACCESS_PATTERNS = [
    r"creative\s*commons",
    r"cc\s*by",
    r"open\s*access",
    r"openaccess",
    r"libre\s*d'?acc[eè]s",
    r"domaine\s*public",
    r"public\s*domain",
    r"licence\s*ouverte",
    r"etalab",
    r"openstax",
]

# Signaux de rejet (paywall, commercial, privé)
REJECT_PATTERNS = [
    r"sci-hub",
    r"libgen",
    r"z-?library",
    r"paywall",
    r"acheter",
    r"buy\s*now",
    r"abonnement\s*requis",
    r"login\s*required",
    r"springerlink\.com(?!/open)",
    r"elsevier\.com(?!/open)",
    r"wiley\.com(?!/open)",
    r"amazon\.fr",
    r"fnac\.com",
    r"cours\s*priv",
    r"moodle.*password",
]

# Extensions / hôtes suspects
REJECT_DOMAINS = {
    "sci-hub",
    "libgen",
    "z-lib",
    "bookfi",
}


@dataclass
class LegalCheckResult:
    legal_status: LegalStatus
    reasons: list[str]
    license_hint: str | None = None
    institution_hint: str | None = None


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _matches_any(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t, re.I) for p in patterns)


def check_url_legal(
    url: str,
    page_text: str | None = None,
    document_type: DocumentType | None = None,
    user_authorized: bool = False,
    user_created: bool = False,
) -> LegalCheckResult:
    """
    Évalue le statut légal d'une URL.
    Ne garantit pas une analyse juridique complète — aide à la décision.
    """
    reasons: list[str] = []
    domain = _domain(url)
    combined = f"{url}\n{page_text or ''}"

    if user_authorized:
        return LegalCheckResult(
            LegalStatus.AUTHORIZED,
            ["Marqué manuellement comme autorisé par l'utilisateur"],
            license_hint="authorized_by_user",
        )

    if user_created:
        return LegalCheckResult(
            LegalStatus.CREATED_BY_USER,
            ["Document créé ou fourni par l'utilisateur"],
            license_hint="created_by_user",
        )

    for bad in REJECT_DOMAINS:
        if bad in domain:
            reasons.append(f"Domaine bloqué: {bad}")
            return LegalCheckResult(LegalStatus.REJECTED, reasons)

    if _matches_any(combined, REJECT_PATTERNS):
        reasons.append("Signaux de contenu protégé ou paywall détectés")
        return LegalCheckResult(LegalStatus.REJECTED, reasons)

    trusted = any(td in domain or domain.endswith(td.lstrip(".")) for td in TRUSTED_DOMAINS)
    if trusted:
        reasons.append(f"Domaine de confiance: {domain}")
        license_hint = "trusted_domain"
        if "hal" in domain:
            license_hint = "HAL open archive"
        if "openstax" in domain:
            license_hint = "OpenStax CC BY"
        return LegalCheckResult(
            LegalStatus.OPEN_ACCESS,
            reasons,
            license_hint=license_hint,
            institution_hint=domain,
        )

    if _matches_any(combined, OPEN_ACCESS_PATTERNS):
        reasons.append("Mention open access / Creative Commons détectée")
        return LegalCheckResult(
            LegalStatus.OPEN_ACCESS,
            reasons,
            license_hint="open_access_detected",
        )

    # Universités publiques (.fr avec univ / ac-)
    if domain.endswith(".fr") and (
        "univ-" in domain or "universite" in domain or domain.startswith("u-")
    ):
        reasons.append("Domaine universitaire public (.fr)")
        # Reste unknown tant qu'aucune mention de licence — prudence
        return LegalCheckResult(
            LegalStatus.UNKNOWN,
            reasons + ["Vérifier licence sur la page du cours"],
            institution_hint=domain,
        )

    reasons.append("Origine non reconnue — vérification manuelle requise")
    logger.warning("Statut unknown pour URL: %s", url)
    return LegalCheckResult(LegalStatus.UNKNOWN, reasons)


def check_local_file(
    filename: str,
    user_authorized: bool = False,
    user_created: bool = True,
) -> LegalCheckResult:
    """Fichiers locaux : par défaut créés par l'utilisateur."""
    if user_authorized:
        return LegalCheckResult(
            LegalStatus.AUTHORIZED,
            ["Fichier local marqué autorisé"],
        )
    if user_created:
        return LegalCheckResult(
            LegalStatus.CREATED_BY_USER,
            ["Fichier local uploadé par l'utilisateur"],
        )
    return LegalCheckResult(
        LegalStatus.UNKNOWN,
        ["Fichier local sans confirmation de licence"],
    )


def is_rag_eligible(status: LegalStatus) -> bool:
    return status.usable_by_rag
