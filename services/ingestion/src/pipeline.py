"""
Pipeline d'ingestion principal.
Orchestre : load → chunk → embed → upsert Qdrant → update PostgreSQL.
Chaque étape est tracée par OpenTelemetry et instrumentée Prometheus.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter
from opentelemetry import trace
from prometheus_client import Counter, Histogram
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, PointStruct, VectorParams
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import Document, IngestionStatus
from src.embedder import Embedder
from src.loaders import RawDocument, get_loader

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# ─── Métriques Prometheus ────────────────────────────────────────────────────

DOCS_PROCESSED = Counter(
    "rag_ingestion_documents_total",
    "Total documents traités",
    ["status"],
)
CHUNKS_CREATED = Counter(
    "rag_ingestion_chunks_total",
    "Total chunks créés",
)
INGESTION_DURATION = Histogram(
    "rag_ingestion_duration_seconds",
    "Durée d'ingestion end-to-end",
    buckets=[1, 5, 10, 30, 60, 120, 300],
)
EMBED_DURATION = Histogram(
    "rag_embed_duration_seconds",
    "Durée d'embedding d'un batch de chunks",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)


# ─── Initialisation Qdrant ───────────────────────────────────────────────────

async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Crée la collection Qdrant si elle n'existe pas encore."""
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]

    if settings.qdrant_collection not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "qdrant_collection_created",
            collection=settings.qdrant_collection,
            vector_size=settings.qdrant_vector_size,
        )


# ─── Pipeline principal ──────────────────────────────────────────────────────

class IngestionPipeline:
    """
    Orchestre l'ingestion d'un document :
    1. Chargement (loader adapté au type)
    2. Chunking (RecursiveCharacterTextSplitter)
    3. Embedding (Ollama nomic-embed-text)
    4. Upsert dans Qdrant
    5. Mise à jour du statut dans PostgreSQL
    """

    def __init__(
        self,
        qdrant: AsyncQdrantClient,
        session: AsyncSession,
    ) -> None:
        self._qdrant  = qdrant
        self._session = session
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    async def ingest(
        self,
        doc: Document,
        file_path: str,
        collection: str | None = None,
    ) -> int:
        """
        Ingère un document complet.
        Retourne le nombre de chunks créés.
        """
        collection = collection or settings.qdrant_collection
        log = logger.bind(doc_id=str(doc.id), filename=doc.filename)

        with tracer.start_as_current_span("pipeline.ingest") as span:
            span.set_attribute("doc.id",         str(doc.id))
            span.set_attribute("doc.filename",   doc.filename)
            span.set_attribute("doc.collection", collection)

            with INGESTION_DURATION.time():
                try:
                    # ── 1. Chargement ────────────────────────────────────────
                    await self._update_status(doc, IngestionStatus.PROCESSING)
                    raw_docs = await self._load(file_path, span, log)

                    # ── 2. Chunking ──────────────────────────────────────────
                    chunks = self._chunk(raw_docs, span, log)

                    # ── 3. Embedding + upsert ────────────────────────────────
                    chunk_count = await self._embed_and_upsert(
                        chunks, doc, collection, span, log
                    )

                    # ── 4. Finalisation ──────────────────────────────────────
                    await self._update_status(
                        doc,
                        IngestionStatus.COMPLETED,
                        chunk_count=chunk_count,
                    )
                    DOCS_PROCESSED.labels(status="completed").inc()
                    log.info("ingestion_completed", chunks=chunk_count)
                    return chunk_count

                except Exception as exc:
                    span.record_exception(exc)
                    await self._update_status(
                        doc,
                        IngestionStatus.FAILED,
                        error=str(exc),
                    )
                    DOCS_PROCESSED.labels(status="failed").inc()
                    log.error("ingestion_failed", error=str(exc))
                    raise

    # ── Étapes privées ────────────────────────────────────────────────────────

    async def _load(
        self, path: str, span: Any, log: Any
    ) -> list[RawDocument]:
        with tracer.start_as_current_span("pipeline.load"):
            loader = get_loader(path)
            raw_docs = await loader.load(path)
            span.set_attribute("loader.raw_docs", len(raw_docs))
            log.info("document_loaded", raw_docs=len(raw_docs))
            return raw_docs

    def _chunk(
        self, raw_docs: list[RawDocument], span: Any, log: Any
    ) -> list[tuple[str, dict]]:
        """Retourne une liste de (texte_chunk, métadonnées)."""
        with tracer.start_as_current_span("pipeline.chunk"):
            chunks_with_meta: list[tuple[str, dict]] = []

            for raw in raw_docs:
                texts = self._splitter.split_text(raw.text)
                for i, text in enumerate(texts):
                    meta = {
                        **raw.metadata,
                        "source":      raw.source,
                        "source_type": raw.source_type,
                        "chunk_index": i,
                        "chunk_total": len(texts),
                    }
                    chunks_with_meta.append((text, meta))

            span.set_attribute("chunk.total", len(chunks_with_meta))
            log.info("chunking_done", chunks=len(chunks_with_meta))
            CHUNKS_CREATED.inc(len(chunks_with_meta))
            return chunks_with_meta

    async def _embed_and_upsert(
        self,
        chunks: list[tuple[str, dict]],
        doc: Document,
        collection: str,
        span: Any,
        log: Any,
    ) -> int:
        """Embed les chunks par batch et les upsert dans Qdrant."""
        with tracer.start_as_current_span("pipeline.embed_upsert"):
            texts = [c[0] for c in chunks]
            metas = [c[1] for c in chunks]

            # Embedding par batch de 16
            BATCH = 16
            all_vectors: list[list[float]] = []

            async with Embedder() as embedder:
                for i in range(0, len(texts), BATCH):
                    batch_texts = texts[i : i + BATCH]
                    with EMBED_DURATION.time():
                        batch_vecs = await embedder.embed_batch(batch_texts)
                    all_vectors.extend(batch_vecs)

            # Construction des points Qdrant
            now = datetime.now(timezone.utc).isoformat()
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        **meta,
                        "doc_id":      str(doc.id),
                        "text":        texts[i],       # texte du chunk (pour display)
                        "collection":  collection,
                        "ingested_at": now,
                    },
                )
                for i, (vector, meta) in enumerate(zip(all_vectors, metas))
            ]

            # Upsert par batch de 100
            UPSERT_BATCH = 100
            for i in range(0, len(points), UPSERT_BATCH):
                await self._qdrant.upsert(
                    collection_name=collection,
                    points=points[i : i + UPSERT_BATCH],
                )

            span.set_attribute("upsert.count", len(points))
            log.info("upsert_done", points=len(points), collection=collection)
            return len(points)

    # ── Helpers DB ────────────────────────────────────────────────────────────

    async def _update_status(
        self,
        doc: Document,
        status: IngestionStatus,
        chunk_count: int | None = None,
        error: str | None = None,
    ) -> None:
        doc.status = status
        if chunk_count is not None:
            doc.chunk_count = chunk_count
            doc.ingested_at = datetime.now(timezone.utc)
        if error:
            doc.error_message = error[:2000]   # limite la taille en DB
        await self._session.commit()
