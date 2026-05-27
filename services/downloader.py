"""Téléchargement robuste de fichiers autorisés."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from app.core.enums import LegalStatus, Level, Subject
from app.core.logging_config import setup_logging
from app.core.paths import file_storage_path
from app.services.legal_checker import check_url_legal
from app.services.pdf_resolvers import (
    BROWSER_HEADERS,
    find_pdf_link_on_page,
    resolve_pdf_download_url,
)
from config.settings import settings

logger = setup_logging("downloader")


class DownloadError(Exception):
    pass


class DownloadRejected(DownloadError):
    pass


def _safe_filename(title: str, ext: str = ".pdf") -> str:
    base = re.sub(r"[^\w\s\-àâäéèêëïîôùûüç]", "", title, flags=re.I)
    base = re.sub(r"\s+", "_", base.strip())[:80] or "document"
    if not base.lower().endswith(ext):
        base += ext
    return base


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _can_fetch_url(url: str) -> bool:
    """Respect basique de robots.txt."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(settings.user_agent, url)
    except Exception as e:
        logger.debug("robots.txt non lu pour %s: %s", url, e)
        return True  # prudent : autoriser si robots inaccessible


def _request_headers() -> dict[str, str]:
    return {**BROWSER_HEADERS, "User-Agent": settings.user_agent}


def fetch_page_metadata(url: str) -> tuple[str, str]:
    """Récupère titre et extrait de texte HTML (sans télécharger PDF payant)."""
    resp = requests.get(
        url,
        timeout=settings.download_timeout,
        headers=_request_headers(),
        allow_redirects=True,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    title = (soup.title.string or "").strip() if soup.title else url
    text = soup.get_text(separator=" ", strip=True)[:8000]
    return title, text


def download_pdf_from_url(
    url: str,
    title_hint: str | None,
    level: Level,
    subject: Subject,
    legal_status: LegalStatus,
    user_authorized: bool = False,
    *,
    pdf_url: str | None = None,
    source_page_url: str | None = None,
) -> tuple[Path, str, str]:
    """
    Télécharge un PDF si autorisé.
    Retourne (chemin_local, content_hash, titre).
    """
    if legal_status == LegalStatus.REJECTED:
        raise DownloadRejected("Statut légal rejected — téléchargement refusé")

    if legal_status == LegalStatus.UNKNOWN and not user_authorized:
        raise DownloadRejected(
            "Statut unknown — marquez la source comme autorisée ou vérifiez la licence"
        )

    page_url = source_page_url or url
    if not _can_fetch_url(page_url):
        raise DownloadRejected(f"robots.txt interdit le fetch: {page_url}")

    legal = check_url_legal(page_url, user_authorized=user_authorized)
    if legal.legal_status == LegalStatus.REJECTED:
        raise DownloadRejected("; ".join(legal.reasons))

    download_url = resolve_pdf_download_url(url, pdf_url)
    logger.info("Téléchargement PDF: %s (source: %s)", download_url, page_url)
    resp = requests.get(
        download_url,
        timeout=settings.download_timeout,
        headers=_request_headers(),
        stream=True,
        allow_redirects=True,
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "").lower()
    data = b""
    for chunk in resp.iter_content(chunk_size=8192):
        data += chunk
        if len(data) > settings.download_max_bytes:
            raise DownloadError("Fichier trop volumineux")

    if not data:
        raise DownloadError("Réponse vide")

    if not data.startswith(b"%PDF"):
        if "html" in content_type or data[:15].lower().startswith(b"<!doctype"):
            html = data.decode("utf-8", errors="ignore")
            linked = find_pdf_link_on_page(download_url, html)
            if linked and linked != download_url:
                return download_pdf_from_url(
                    linked,
                    title_hint,
                    level,
                    subject,
                    legal_status,
                    user_authorized=user_authorized,
                    source_page_url=page_url,
                )
        raise DownloadRejected(
            "Le fichier reçu n'est pas un PDF valide (page HTML ou accès bloqué)"
        )

    content_hash = _content_hash(data)
    title = title_hint or download_url.split("/")[-1].split("?")[0]
    filename = f"{content_hash[:12]}_{_safe_filename(title)}"
    dest = file_storage_path(level, subject, filename, source_url=page_url)

    if dest.exists():
        logger.info("Doublon évité (fichier existant): %s", dest)
        return dest, content_hash, title

    dest.write_bytes(data)
    logger.info("Enregistré: %s (%d octets)", dest, len(data))
    return dest, content_hash, title


def copy_local_file(
    source_path: Path,
    title: str,
    level: Level,
    subject: Subject,
) -> tuple[Path, str]:
    """Copie un fichier local vers l'arborescence data/."""
    if not source_path.exists():
        raise DownloadError(f"Fichier introuvable: {source_path}")

    data = source_path.read_bytes()
    if len(data) > settings.download_max_bytes:
        raise DownloadError("Fichier trop volumineux")

    content_hash = _content_hash(data)
    ext = source_path.suffix or ".pdf"
    filename = f"{content_hash[:12]}_{_safe_filename(title, ext)}"
    dest = file_storage_path(level, subject, filename, source_url="")

    if dest.exists():
        return dest, content_hash

    shutil.copy2(source_path, dest)
    return dest, content_hash
