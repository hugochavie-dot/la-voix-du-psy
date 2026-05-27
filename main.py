"""Pipeline RAG psychologie — entrée CLI.

Usage :
    python main.py --sources sources.json --output data
    python main.py --sources sources.json --output data --dry-run

Étapes :
    1. Charger `sources.json`
    2. Valider chaque source (légal, domaine, motifs bloqués)
    3. Télécharger uniquement ce qui est autorisé (PDF open access)
    4. Générer les métadonnées JSON
    5. Extraire le texte (pypdf) + découper en chunks RAG
    6. Écrire les index CSV/JSON et la liste `to_verify`
    7. Initialiser les fichiers utilisateur (glossaire, quiz, fiches, règles)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config_loader import SourcesConfig, load_config
from src.downloader import DownloadResult, download_source
from src.index_writer import write_index, write_to_verify
from src.metadata_builder import Metadata, build_metadata, write_metadata
from src.pdf_extractor import extract_text
from src.rag_chunker import build_chunks, write_jsonl
from src.source_validator import (
    STATUS_DISABLED,
    STATUS_DOWNLOADABLE,
    STATUS_LOCAL_USER_CONTENT,
    STATUS_REFERENCE_ONLY,
    STATUS_TO_VERIFY,
    ValidationResult,
    validate_all,
)


SYSTEM_RULES_TEXT = """\
Règles de sécurité pédagogique — Psych IA Ressources

1. L'IA ne remplace pas un psychologue.
2. L'IA ne pose pas de diagnostic.
3. L'IA ne propose pas de traitement médical.
4. L'IA cite ses sources.
5. L'IA distingue cours de base et recherche avancée.
6. L'IA oriente vers un professionnel en cas de détresse.
7. L'IA explique clairement les limites de ses réponses.

En cas d'urgence : 15 (SAMU) ou 3114 (numéro national de prévention du suicide).
"""

USER_TEMPLATES = {
    "glossaire_psychologie.json": {
        "version": 1,
        "description": "Glossaire personnel — ajoutez vos définitions et exemples.",
        "entries": [
            {"terme": "Conditionnement classique", "definition": "...", "source": "..."}
        ],
    },
    "banque_quiz.json": {
        "version": 1,
        "description": "Banque de quiz QCM personnels.",
        "quiz": [
            {
                "id": "q001",
                "level": "L1",
                "subject": "psychologie_generale",
                "question": "Qui a formulé la théorie du conditionnement opérant ?",
                "choices": ["Pavlov", "Skinner", "Watson", "Bandura"],
                "answer_index": 1,
                "explanation": "B. F. Skinner — années 1930-1950.",
            }
        ],
    },
    "banque_fiches_revision.json": {
        "version": 1,
        "description": "Fiches de révision créées par l'utilisateur.",
        "fiches": [
            {
                "id": "fiche_001",
                "level": "L1",
                "subject": "psychologie_generale",
                "title": "Apprentissage par conditionnement",
                "summary": "...",
                "key_points": ["...", "..."],
            }
        ],
    },
    "concepts_links.json": {
        "version": 1,
        "description": "Liens entre notions (graphe de concepts).",
        "concepts": [
            {
                "notion": "Mémoire de travail",
                "level": "L2",
                "subject": "psychologie_cognitive",
                "liens": [
                    {"notion_liee": "Attention", "relation": "prérequis cognitif"}
                ],
            }
        ],
    },
}

logger = logging.getLogger("main")


@dataclass
class Paths:
    """Tous les chemins de sortie du pipeline."""

    output: Path
    downloads: Path
    metadata: Path
    rag_ready: Path
    rag_texts: Path
    rag_jsonl: Path
    to_verify: Path
    created_by_user: Path
    index_csv: Path
    index_json: Path
    to_verify_csv: Path

    @classmethod
    def from_output(cls, output: Path) -> "Paths":
        return cls(
            output=output,
            downloads=output / "downloads",
            metadata=output / "metadata",
            rag_ready=output / "rag_ready",
            rag_texts=output / "rag_ready" / "texts",
            rag_jsonl=output / "rag_ready" / "rag_chunks.jsonl",
            to_verify=output / "to_verify",
            created_by_user=output / "created_by_user",
            index_csv=output / "index_resources.csv",
            index_json=output / "index_resources.json",
            to_verify_csv=output / "to_verify" / "sources_a_verifier.csv",
        )

    def ensure(self) -> None:
        for p in (
            self.output,
            self.downloads,
            self.metadata,
            self.rag_ready,
            self.rag_texts,
            self.to_verify,
            self.created_by_user,
        ):
            p.mkdir(parents=True, exist_ok=True)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _init_user_files(paths: Paths) -> list[Path]:
    """Crée les fichiers utilisateur s'ils n'existent pas (no overwrite)."""
    created: list[Path] = []
    for name, payload in USER_TEMPLATES.items():
        target = paths.created_by_user / name
        if not target.exists():
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            created.append(target)
    rules = paths.created_by_user / "system_rules.txt"
    if not rules.exists():
        rules.write_text(SYSTEM_RULES_TEXT, encoding="utf-8")
        created.append(rules)
    return created


def _print_dry_run_report(config: SourcesConfig, results: list[ValidationResult], paths: Paths) -> None:
    """Affiche un récap lisible sans rien écrire (sauf templates utilisateur)."""
    bins: dict[str, list[ValidationResult]] = {
        STATUS_DOWNLOADABLE: [],
        STATUS_REFERENCE_ONLY: [],
        STATUS_DISABLED: [],
        STATUS_LOCAL_USER_CONTENT: [],
        STATUS_TO_VERIFY: [],
    }
    for r in results:
        bins.setdefault(r.status, []).append(r)

    print("=" * 72)
    print("DRY-RUN — Aucun fichier de données ne sera écrit (sauf templates user).")
    print("=" * 72)
    print(f"Description : {config.description}")
    print(f"Sources totales : {len(config.sources)}")
    print()

    for status, label in [
        (STATUS_DOWNLOADABLE, "À télécharger"),
        (STATUS_REFERENCE_ONLY, "Référence seulement"),
        (STATUS_DISABLED, "Désactivées"),
        (STATUS_LOCAL_USER_CONTENT, "Contenu utilisateur local"),
        (STATUS_TO_VERIFY, "À vérifier"),
    ]:
        rs = bins.get(status, [])
        print(f"[{label}] ({len(rs)})")
        for r in rs:
            print(f"  - {r.source.id} :: {r.source.title}")
            if r.reasons:
                print(f"      raison(s) : {' ; '.join(r.reasons)}")
        print()

    print("Fichiers/dossiers qui SERAIENT créés :")
    print(f"  {paths.downloads}/")
    print(f"  {paths.metadata}/<source_id>.json")
    print(f"  {paths.index_csv}")
    print(f"  {paths.index_json}")
    print(f"  {paths.to_verify_csv}")
    print(f"  {paths.rag_texts}/<source_id>.txt")
    print(f"  {paths.rag_jsonl}")
    print(f"  {paths.created_by_user}/{{glossaire,banque_quiz,fiches,concepts_links,system_rules}}.*")


def run(
    sources_path: Path,
    output_path: Path,
    *,
    dry_run: bool,
    delay_seconds: float,
) -> int:
    """Exécute le pipeline complet (ou simulation si `dry_run`)."""
    paths = Paths.from_output(output_path)
    paths.ensure()

    config = load_config(sources_path)
    logger.info("Sources chargées : %d", len(config.sources))

    results = validate_all(
        config.sources,
        blocked_patterns=config.blocked_patterns,
        trusted_publishers=config.trusted_publishers,
    )

    _init_user_files(paths)

    if dry_run:
        _print_dry_run_report(config, results, paths)
        return 0

    metadatas: list[Metadata] = []
    project_root = Path(__file__).resolve().parent

    import time

    to_download = [r for r in results if r.status == STATUS_DOWNLOADABLE]
    for i, r in enumerate(to_download):
        if i > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)

        dl = download_source(r.source, dest_dir=paths.downloads)
        meta = build_metadata(r.source, r, dl, project_root=project_root)
        metadatas.append(meta)
        write_metadata(meta, paths.metadata)

        if dl.success and dl.local_path is not None:
            extraction = extract_text(dl.local_path, dest_dir=paths.rag_texts, source_id=r.source.id)
            if extraction.error:
                logger.warning("Extraction PDF échouée pour %s : %s", r.source.id, extraction.error)
                continue

            text = (extraction.text_path or Path()).read_text(encoding="utf-8") if extraction.text_path else ""
            chunks = build_chunks(r.source, text)
            existing = []
            if paths.rag_jsonl.exists():
                with paths.rag_jsonl.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                            if obj.get("source_id") != r.source.id:
                                existing.append(line.rstrip("\n"))
                        except json.JSONDecodeError:
                            continue
            with paths.rag_jsonl.open("w", encoding="utf-8") as fh:
                for line in existing:
                    fh.write(line + "\n")
                for ch in chunks:
                    fh.write(json.dumps(ch.to_dict(), ensure_ascii=False) + "\n")
            logger.info("Indexé %s — %d chunks", r.source.id, len(chunks))

    for r in results:
        if r.status == STATUS_DOWNLOADABLE:
            continue
        meta = build_metadata(r.source, r, None, project_root=project_root)
        metadatas.append(meta)
        write_metadata(meta, paths.metadata)

    write_index(metadatas, csv_path=paths.index_csv, json_path=paths.index_json)
    flagged = write_to_verify(results, csv_path=paths.to_verify_csv)
    logger.info(
        "Index écrit : %d sources, %d à vérifier",
        len(metadatas),
        flagged,
    )
    if not paths.rag_jsonl.exists():
        paths.rag_jsonl.touch()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="psych-ia-ressources",
        description="Pipeline de collecte et indexation RAG de sources libres en psychologie",
    )
    parser.add_argument("--sources", default="sources.json", help="Chemin vers sources.json")
    parser.add_argument("--output", default="data", help="Dossier de sortie (data/)")
    parser.add_argument("--dry-run", action="store_true", help="Affiche le plan sans rien télécharger")
    parser.add_argument("--delay", type=float, default=2.0, help="Délai entre téléchargements (secondes)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs DEBUG")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    try:
        return run(
            Path(args.sources),
            Path(args.output),
            dry_run=args.dry_run,
            delay_seconds=args.delay,
        )
    except FileNotFoundError as exc:
        logger.error("Fichier introuvable : %s", exc)
        return 2
    except ValueError as exc:
        logger.error("Configuration invalide : %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
