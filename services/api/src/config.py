"""Configuration RAG API — chargée depuis les variables d'environnement."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = Field("rag-api")
    host:         str = Field("0.0.0.0")
    port:         int = Field(8000)
    log_level:    str = Field("INFO")

    # ── Qdrant ───────────────────────────────────────────────────────────────
    qdrant_url:         str = Field("http://localhost:6333")
    qdrant_collection:  str = Field("documents")

    # ── Ollama ───────────────────────────────────────────────────────────────
    ollama_base_url:    str = Field("http://localhost:11434")
    embed_model:        str = Field("nomic-embed-text")
    llm_model:          str = Field("llama3.2:3b")
    llm_timeout:        int = Field(120)
    embed_timeout:      int = Field(60)

    # ── RAG pipeline ─────────────────────────────────────────────────────────
    rag_top_k:              int   = Field(5)
    rag_score_threshold:    float = Field(0.70)

    # ── Cache Redis ──────────────────────────────────────────────────────────
    redis_url:  str = Field("redis://localhost:6379/1")
    cache_ttl:  int = Field(3600)   # secondes

    # ── Observabilité ────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = Field("http://localhost:4317")


settings = Settings()
