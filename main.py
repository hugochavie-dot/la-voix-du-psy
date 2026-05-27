#!/usr/bin/env python3
"""
Pipeline Psych IA Ressources — collecte, validation, téléchargement et index RAG.

Usage :
  python main.py --sources sources.json --output data --dry-run
  python main.py --sources sources.json --output data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.downloader import download_pdf
from src.index_writer import write_indexes
from src.metadata_builder import build_metadata_record, write_metadata
from src.pdf_extractor import extract_pdf_text
from src.rag_chunker import append_rag_jsonl, chunk_text, iter_rag_records
from src.safety import ensure_user_templates
from src.source_validator import validate_source


def _ensure_dirs(output_dir: Path) -> dict[str, Path]:
    return {
        "root": output_dir,
        "downloads": output_dir / "downloads",
        "metadata": output_dir / "metadata",
        "rag_texts": output_dir / "rag_ready" / "texts",
        "rag_jsonl": output_dir / "rag_ready" / "rag_chunks.jsonl",
        "to_verify": output_dir / "to_verify",
        "user": output_dir / "created_by_user",
    }


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def run_pipeline(
    sources_path: Path,
    output_dir: Path,
    *,
    dry_run: bool = False,
    skip_download: bool = False,
) -> int:
    config = load_config(sources_path)
    dirs = _ensure_dirs(output_dir)

    if not dry_run:
        for key in ("downloads", "metadata", "rag_texts", "to_verify", "user"):
            dirs[key].mkdir(parents=True, exist_ok=True)
        # Réinitialiser le JSONL RAG à chaque exécution complète
        if dirs["rag_jsonl"].exists():
            dirs["rag_jsonl"].unlink()

    enabled_sources = [s for s in config.sources if s.get("enabled")]
    downloadable: list[dict] = []
    ignored: list[tuple[dict, list[str]]] = []
    metadata_records: list[dict] = []
    reasons_map: dict[str, list[str]] = {}
    files_planned: list[str] = []

    _print_header("1. Chargement sources.json")
    print(f"Description : {config.description}")
    print(f"Sources totales : {len(config.sources)}")
    print(f"Sources activées : {len(enabled_sources)}")
    print(f"Éditeurs de confiance : {', '.join(config.trusted_publishers)}")
    print(f"Motifs bloqués : {', '.join(config.blocked_patterns)}")

    _print_header("2. Validation des sources")
    for source in config.sources:
        validation = validate_source(source, config.trusted_publishers, config.blocked_patterns)
        reasons_map[str(source.get("id"))] = validation.reasons

        meta_path = dirs["metadata"] / f"{source.get('id')}.json"
        files_planned.append(str(meta_path.relative_to(output_dir)))

        if source.get("enabled") and validation.can_download:
            downloadable.append(source)
            print(f"  [TÉLÉCHARGABLE] {source.get('id')} — {source.get('title')}")
        elif source.get("enabled"):
            ignored.append((source, validation.reasons))
            print(f"  [IGNORÉE]      {source.get('id')} — {validation.index_status}")
            for reason in validation.reasons:
                print(f"                 → {reason}")
        else:
            ignored.append((source, validation.reasons))
            print(f"  [DÉSACTIVÉE]    {source.get('id')}")

    _print_header("3. Fichiers utilisateur et règles de sécurité")
    user_files = ensure_user_templates(dirs["user"], project_root=ROOT, dry_run=dry_run)
    for uf in user_files:
        rel = uf.relative_to(output_dir) if uf.is_relative_to(output_dir) else uf
        files_planned.append(str(rel))
        print(f"  {'[DRY-RUN] ' if dry_run else ''}Modèle : {rel}")

    _print_header("4. Téléchargement et métadonnées")
    rag_sources_processed = 0

    for source in config.sources:
        validation = validate_source(source, config.trusted_publishers, config.blocked_patterns)
        local_path: str | None = None
        downloaded = False
        error: str | None = None
        status = validation.index_status

        if validation.can_download and not skip_download:
            pdf_dest = dirs["downloads"] / f"{source.get('id')}.pdf"
            files_planned.append(str(pdf_dest.relative_to(output_dir)))

            if dry_run:
                print(f"  [DRY-RUN] Téléchargement : {source.get('id')} → {pdf_dest.name}")
                status = "downloadable"
            else:
                path, dl_error = download_pdf(source, dirs["downloads"], dry_run=False)
                if path:
                    downloaded = True
                    local_path = str(path.relative_to(output_dir))
                    status = "downloaded"
                    print(f"  [OK] Téléchargé : {source.get('id')} ({path.stat().st_size // 1024} Ko)")

                    text_path, ext_error = extract_pdf_text(path, dirs["rag_texts"])
                    if text_path:
                        files_planned.append(str(text_path.relative_to(output_dir)))
                        text = text_path.read_text(encoding="utf-8")
                        chunks = chunk_text(text)
                        records = list(iter_rag_records(source, chunks))
                        append_rag_jsonl(records, dirs["rag_jsonl"])
                        rag_sources_processed += 1
                        print(f"       Texte extrait : {len(chunks)} chunks RAG")
                    else:
                        error = ext_error
                        status = "error"
                        print(f"  [ERREUR] Extraction : {source.get('id')} — {ext_error}")
                else:
                    error = dl_error
                    status = "error"
                    print(f"  [ERREUR] Téléchargement : {source.get('id')} — {dl_error}")
        elif validation.can_download and skip_download:
            status = "downloadable"

        record = build_metadata_record(
            source,
            index_status=status,
            downloaded=downloaded,
            local_path=local_path,
            error=error,
        )
        metadata_records.append(record)
        write_metadata(dirs["metadata"], record, dry_run=dry_run)

    _print_header("5. Index globaux")
    index_paths = write_indexes(output_dir, metadata_records, reasons_map, dry_run=dry_run)
    for name, path in index_paths.items():
        files_planned.append(str(path.relative_to(output_dir)))
        print(f"  {'[DRY-RUN] ' if dry_run else ''}Index {name} : {path.relative_to(output_dir)}")

    _print_header("Résumé")
    print(f"Mode              : {'DRY-RUN' if dry_run else 'EXÉCUTION'}")
    print(f"Sources activées  : {len(enabled_sources)}")
    print(f"Téléchargeables   : {len(downloadable)}")
    print(f"Ignorées/désactiv.: {len(ignored)}")
    print(f"PDF traités RAG   : {rag_sources_processed}")
    print(f"Dossier sortie    : {output_dir.resolve()}")

    if dry_run:
        print("\nFichiers qui seraient créés :")
        for fp in sorted(set(files_planned)):
            print(f"  - {fp}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline Psych IA Ressources")
    parser.add_argument("--sources", default="sources.json", help="Chemin vers sources.json")
    parser.add_argument("--output", default="data", help="Dossier de sortie (data/)")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture ni téléchargement")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Valider et indexer sans télécharger (métadonnées uniquement)",
    )
    args = parser.parse_args()

    sources_path = Path(args.sources)
    if not sources_path.is_absolute():
        sources_path = ROOT / sources_path

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    try:
        return run_pipeline(
            sources_path,
            output_dir,
            dry_run=args.dry_run,
            skip_download=args.skip_download,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
