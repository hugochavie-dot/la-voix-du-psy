"""Résolution d'URL PDF directes (OpenStax, HAL, pages HTML)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from app.core.logging_config import setup_logging
from config.settings import settings

logger = setup_logging("pdf_resolvers")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}


def resolve_openstax_pdf_url(url: str) -> str | None:
    """Récupère l'URL PDF haute résolution via l'API CMS OpenStax."""
    slug_match = re.search(r"openstax\.org/(?:details/books|books)/([^/?#]+)", url)
    if not slug_match:
        return None
    slug = slug_match.group(1)
    api_url = f"https://openstax.org/apps/cms/api/books/{slug}/?format=json"
    try:
        resp = requests.get(api_url, headers=BROWSER_HEADERS, timeout=settings.download_timeout)
        resp.raise_for_status()
        pdf_url = resp.json().get("high_resolution_pdf_url")
        if pdf_url and ".pdf" in pdf_url.lower():
            logger.info("OpenStax PDF résolu: %s", pdf_url)
            return pdf_url
    except Exception as e:
        logger.warning("Résolution OpenStax échouée pour %s: %s", slug, e)
    return None


def _hal_id_from_url(url: str) -> str | None:
    m = re.search(r"(hal-[\d]+)", url, re.I)
    if not m:
        m = re.search(r"(hal-[\w-]+)", url, re.I)
    if not m:
        return None
    hal_id = m.group(1)
    # API HAL : identifiant sans suffixe de version (v1, v2…)
    return re.sub(r"v\d+$", "", hal_id, flags=re.I)


def resolve_hal_pdf_url(url: str) -> str | None:
    """Interroge l'API HAL pour obtenir le lien fichier PDF principal."""
    hal_id = _hal_id_from_url(url)
    if not hal_id:
        return None
    try:
        resp = requests.get(
            "https://api.archives-ouvertes.fr/search/",
            params={
                "q": f"halId_s:{hal_id}",
                "rows": 1,
                "wt": "json",
                "fl": "files_s,uri_s,linkExtId_s",
            },
            timeout=settings.download_timeout,
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        if not docs:
            return None
        doc = docs[0]
        uri = (doc.get("uri_s") or "").rstrip("/")
        files = doc.get("files_s") or []
        for f in files:
            if "/file/" not in f:
                continue
            filename = f.split("/file/", 1)[-1]
            if uri:
                resolved = f"{uri}/file/{filename}"
            else:
                resolved = unquote(f)
            logger.info("HAL PDF résolu: %s", resolved)
            return resolved
    except Exception as e:
        logger.warning("Résolution HAL échouée pour %s: %s", hal_id, e)
    return None


def find_pdf_link_on_page(url: str, html: str) -> str | None:
    """Repère un lien PDF sur une page HTML."""
    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = (a.get_text() or "").lower()
        if ".pdf" in href.lower() or "pdf" in label or "télécharger" in label:
            if href.startswith("http"):
                candidates.append(href)
            else:
                from urllib.parse import urljoin

                candidates.append(urljoin(url, href))
    return candidates[0] if candidates else None


def resolve_pdf_download_url(url: str, explicit_pdf_url: str | None = None) -> str:
    """
    Retourne l'URL à télécharger (PDF direct si possible).
    Garde l'URL d'origine si aucune résolution n'est possible.
    """
    if explicit_pdf_url:
        return explicit_pdf_url

    host = urlparse(url).netloc.lower()
    if "openstax.org" in host:
        resolved = resolve_openstax_pdf_url(url)
        if resolved:
            return resolved
    if "hal." in host or "hal.science" in host:
        resolved = resolve_hal_pdf_url(url)
        if resolved:
            return resolved

    return url
