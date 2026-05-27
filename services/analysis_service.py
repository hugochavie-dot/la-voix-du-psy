"""Analyse pédagogique personnalisée fondée sur la RAG OpenStax."""

from __future__ import annotations

import re
from pathlib import Path

from app.services.jsonl_rag import search_jsonl_rag
from config.settings import settings

OBJECTIF_TERMS: dict[str, str] = {
    "comprendre": "comportement émotions cognition personnalité motivation stress coping",
    "relations": "psychologie sociale attachement communication relations influence",
    "confiance": "estime de soi confiance personnalité développement identité",
    "nouveau-depart": "changement motivation résilience adaptation bien-être",
    "serenite": "stress relaxation équilibre émotions régulation mindfulness",
}

SITUATION_TERMS: dict[str, str] = {
    "equilibre": "équilibre bien-être stress coping lifestyle",
    "stress-pro": "stress burnout travail charge professionnelle santé",
    "motivation": "motivation objectifs engagement comportement",
    "relations": "relations sociales conflits communication attachement",
    "developpement": "développement personnel croissance apprentissage",
}

NIVEAU_MODULES: dict[str, list[str]] = {
    "L1": ["Psychologie générale", "Introduction psychologie sociale", "Statistiques descriptives"],
    "L2": ["Psychologie cognitive", "Psychopathologie I", "Psychologie de la santé"],
    "L3": ["Psychologie clinique", "Neuropsychologie", "Mémoire de recherche"],
    "autre": ["Psychologie générale", "Introduction à la psychologie cognitive"],
}


def _load_system_rules() -> str:
    rules_path = Path(settings.project_root) / "config" / "system_rules.txt"
    if rules_path.is_file():
        return rules_path.read_text(encoding="utf-8")
    return ""


def _build_search_query(
    message: str,
    objectif: str,
    situation: str,
    niveau: str,
) -> str:
    parts = [message.strip()]
    if objectif in OBJECTIF_TERMS:
        parts.append(OBJECTIF_TERMS[objectif])
    if situation in SITUATION_TERMS:
        parts.append(SITUATION_TERMS[situation])
    if niveau in ("L1", "L2", "L3"):
        parts.append(f"psychology level {niveau}")
    return " ".join(p for p in parts if p)


def _clean_excerpt(text: str, max_len: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len]
    last_space = cut.rfind(" ")
    if last_space > max_len // 2:
        cut = cut[:last_space]
    return cut.rstrip(".,; ") + "…"


def _extract_key_sentence(text: str, query_tokens: set[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    best = ""
    best_score = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 40:
            continue
        lower = sentence.lower()
        score = sum(1 for t in query_tokens if t in lower)
        if score > best_score:
            best_score = score
            best = sentence
    return best or _clean_excerpt(text, 220)


def generate_analysis(payload: dict) -> dict:
    """
    Génère une analyse pédagogique avec citations OpenStax.

    payload: nom, email, niveau, situation, objectif, message
    """
    nom = (payload.get("nom") or "").strip()
    niveau = payload.get("niveau") or "L1"
    objectif = payload.get("objectif") or ""
    situation = payload.get("situation") or ""
    message = payload.get("message") or ""

    search_query = _build_search_query(message, objectif, situation, niveau)
    query_tokens = set(re.findall(r"[a-z0-9\u00e0-\u024f]{3,}", search_query.lower()))

    chunks = search_jsonl_rag(
        search_query,
        n_results=5,
        level="L1" if niveau == "autre" else niveau,
        source_id="openstax_psychology_2e",
    )

    # Recherche élargie si filtres trop stricts
    if len(chunks) < 2:
        chunks = search_jsonl_rag(search_query, n_results=5, source_id="openstax_psychology_2e")
    if len(chunks) < 2:
        chunks = search_jsonl_rag(message, n_results=5, source_id="openstax_psychology_2e")

    citations = []
    for rank, chunk in enumerate(chunks, start=1):
        excerpt = _extract_key_sentence(chunk["text"], query_tokens)
        citations.append({
            "rang": rank,
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "title": chunk["title"],
            "url": chunk["url"],
            "license": chunk.get("license"),
            "chunk_number": chunk.get("chunk_number"),
            "score": chunk.get("score"),
            "extrait": excerpt,
            "citation_apa": (
                f"{chunk['title']} (OpenStax, chunk {chunk.get('chunk_number', '?')}). "
                f"{chunk.get('url', '')}"
            ),
        })

    objectif_label = payload.get("objectif_label") or objectif
    situation_label = payload.get("situation_label") or situation
    niveau_label = payload.get("niveau_label") or niveau

    if citations:
        synthese_intro = (
            f"Bonjour {nom}, voici une analyse pédagogique fondée sur le manuel "
            f"**OpenStax Psychology 2e** (CC BY-NC-SA 4.0), en lien avec votre objectif "
            f"« {objectif_label} » et votre situation « {situation_label} »."
        )
        points = []
        for cite in citations[:3]:
            points.append(
                f"• D'après OpenStax (chunk {cite['chunk_number']}) : « {cite['extrait']} »"
            )
        synthese_corps = (
            "Les extraits ci-dessus proviennent directement du manuel libre OpenStax. "
            "Ils éclairent des mécanismes psychologiques pertinents pour votre description, "
            "sans constituer un diagnostic ni un avis clinique."
        )
    else:
        synthese_intro = (
            f"Bonjour {nom}, nous n'avons pas trouvé de passage OpenStax suffisamment "
            "pertinent pour votre demande précise."
        )
        synthese_corps = (
            "Essayez de reformuler votre message avec des mots-clés psychologiques "
            "(stress, motivation, relations, émotions, comportement). "
            "L'analyse reste strictement pédagogique."
        )

    modules = NIVEAU_MODULES.get(niveau, NIVEAU_MODULES["autre"])
    recommandations = [
        f"Consulter les modules {niveau_label} : {', '.join(modules)}.",
        "Relire les chapitres OpenStax cités ci-dessous et noter les concepts clés.",
        "Utiliser le glossaire et les quiz de la plateforme pour ancrer les notions.",
    ]
    if situation in ("stress-pro", "equilibre"):
        recommandations.append(
            "Explorer le chapitre OpenStax « Stress, Lifestyle, and Health »."
        )
    if objectif == "relations":
        recommandations.append(
            "Explorer le chapitre OpenStax « Social Psychology »."
        )

    return {
        "profil": {
            "nom": nom,
            "niveau": niveau,
            "niveau_label": niveau_label,
            "objectif": objectif,
            "objectif_label": objectif_label,
            "situation": situation,
            "situation_label": situation_label,
        },
        "synthese": {
            "introduction": synthese_intro,
            "points": points if citations else [],
            "conclusion": synthese_corps,
        },
        "citations": citations,
        "recommandations": recommandations,
        "source_principale": {
            "title": "OpenStax Psychology 2e",
            "url": "https://openstax.org/details/books/psychology-2e",
            "license": "CC BY-NC-SA 4.0",
            "source_id": "openstax_psychology_2e",
        },
        "avertissement": (
            "Cette analyse est générée à des fins éducatives uniquement. "
            "Elle ne remplace pas un psychologue et ne constitue pas un diagnostic. "
            "En cas de détresse : 3114 (24h/24)."
        ),
        "meta": {
            "search_query": search_query,
            "chunks_found": len(citations),
            "rag_backend": "jsonl",
            "rag_path": str(settings.rag_chunks_path),
        },
    }
