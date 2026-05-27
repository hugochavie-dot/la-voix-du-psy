"""Configuration centralisée (Pydantic Settings)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = PROJECT_ROOT
    data_dir_name: str = "data2"  # arborescence pédagogique (voir ARCHITECTURE.md)
    sources_config: str = "sources.json"  # à la racine du projet
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'storage' / 'psych_ia.db'}"
    chroma_persist_dir: str = str(PROJECT_ROOT / "storage" / "chroma")
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    download_timeout: int = 60
    download_max_mb: int = 80
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
        "(PsychIA-Ressources/1.0; educational)"
    )
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    chunk_size: int = 800
    chunk_overlap: int = 120
    rag_chunks_path: str = str(
        PROJECT_ROOT.parent / "project" / "data" / "rag_ready" / "rag_chunks.jsonl"
    )
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def download_max_bytes(self) -> int:
        return self.download_max_mb * 1024 * 1024


settings = Settings()
