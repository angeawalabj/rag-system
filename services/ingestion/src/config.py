"""
Configuration centralisée — chargée depuis les variables d'environnement.
Toutes les valeurs ont des défauts raisonnables pour le dev local.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str       = Field("ingestion", description="Nom du service (OTel)")
    host:         str       = Field("0.0.0.0",   description="Adresse d'écoute")
    port:         int       = Field(8001,         description="Port HTTP")
    log_level:    str       = Field("INFO",       description="Niveau de log")
    upload_dir:   str       = Field("/app/uploads")

    # ── Qdrant ───────────────────────────────────────────────────────────────
    qdrant_url:        str = Field("http://localhost:6333")
    qdrant_collection: str = Field("documents")
    qdrant_vector_size: int = Field(768, description="Dépend du modèle d'embedding")

    # ── PostgreSQL ───────────────────────────────────────────────────────────
    postgres_dsn: str = Field(
        "postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb"
    )

    # ── Redis / RQ ───────────────────────────────────────────────────────────
    redis_url:    str = Field("redis://localhost:6379/0")
    rq_queue:     str = Field("ingestion")

    # ── Ollama ───────────────────────────────────────────────────────────────
    ollama_base_url: str = Field("http://localhost:11434")
    embed_model:     str = Field("nomic-embed-text")
    embed_timeout:   int = Field(60, description="Timeout embedding en secondes")

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size:    int = Field(512)
    chunk_overlap: int = Field(64)

    # ── Observabilité ────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = Field("http://localhost:4317")


# Singleton — importé partout dans le service
settings = Settings()
