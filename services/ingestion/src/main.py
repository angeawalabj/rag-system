"""
Ingestion Service — point d'entrée FastAPI.

Routes :
  POST /ingest         Upload fichier → job asynchrone → 202
  GET  /ingest/{id}    Statut du job
  GET  /documents      Liste des documents
  GET  /health         Healthcheck
  GET  /metrics        Prometheus metrics
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from rq import Queue
from sqlalchemy import select

from src.config import settings
from src.database import AsyncSessionLocal, Document, IngestionStatus, get_session
from src.pipeline import IngestionPipeline, ensure_collection

import redis.asyncio as aioredis
import redis as sync_redis

logger = structlog.get_logger(__name__)

QUEUE_PENDING = Gauge(
    "rag_ingestion_queue_pending",
    "Nombre de jobs en attente dans la queue RQ",
)


# ─── OpenTelemetry setup ─────────────────────────────────────────────────────

def setup_otel() -> None:
    resource = Resource({SERVICE_NAME: settings.service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    logger.info("otel_configured", endpoint=settings.otel_exporter_otlp_endpoint)


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_otel()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    # Connexion Qdrant
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    await ensure_collection(qdrant)
    app.state.qdrant = qdrant

    # Queue RQ (sync Redis pour RQ)
    sync_r = sync_redis.from_url(settings.redis_url)
    app.state.queue = Queue(settings.rq_queue, connection=sync_r)

    logger.info("ingestion_service_started", port=settings.port)
    yield

    await qdrant.close()
    sync_r.close()
    logger.info("ingestion_service_stopped")


# ─── Application ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG Ingestion Service",
    description="Ingestion de documents : upload → chunk → embed → Qdrant",
    version="1.0.0",
    lifespan=lifespan,
)
FastAPIInstrumentor.instrument_app(app)


# ─── Schémas Pydantic ────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    job_id:  str
    doc_id:  str
    status:  str
    message: str

class DocumentStatus(BaseModel):
    doc_id:      str
    filename:    str
    status:      str
    chunk_count: int | None
    error:       str | None
    created_at:  str
    ingested_at: str | None

class DocumentList(BaseModel):
    total:     int
    documents: list[DocumentStatus]


# ─── Worker function (exécutée par RQ) ───────────────────────────────────────

def process_ingest_job(doc_id: str, file_path: str, collection: str) -> dict:
    """
    Fonction RQ — tourne dans un worker séparé.
    Crée ses propres connexions (chaque worker est un processus indépendant).
    """
    import asyncio
    from src.database import AsyncSessionLocal, Document
    from src.pipeline import IngestionPipeline
    from qdrant_client import AsyncQdrantClient
    from sqlalchemy import select

    async def _run() -> dict:
        qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document).where(Document.id == uuid.UUID(doc_id))
            )
            doc = result.scalar_one_or_none()
            if not doc:
                raise ValueError(f"Document {doc_id} introuvable")

            pipeline = IngestionPipeline(qdrant=qdrant, session=session)
            chunk_count = await pipeline.ingest(doc, file_path, collection)
            return {"doc_id": doc_id, "chunks": chunk_count}

    return asyncio.run(_run())


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest_document(
    file:       UploadFile = File(...),
    collection: str        = Form(default="documents"),
    session = Depends(get_session),
):
    """
    Upload un document et démarre son ingestion de façon asynchrone.
    Retourne immédiatement un job_id pour suivre le statut.
    """
    # Validation type MIME
    allowed = {"application/pdf", "text/plain", "text/markdown", "text/x-markdown"}
    if file.content_type not in allowed and not (file.filename or "").endswith((".md", ".txt", ".pdf")):
        raise HTTPException(
            status_code=415,
            detail=f"Type non supporté : {file.content_type}. Formats : PDF, TXT, MD",
        )

    # Sauvegarde temporaire
    doc_id    = uuid.uuid4()
    safe_name = Path(file.filename or "document").name
    file_path = Path(settings.upload_dir) / f"{doc_id}_{safe_name}"

    content = await file.read()
    file_path.write_bytes(content)

    # Détection du source_type
    suffix = Path(safe_name).suffix.lower()
    source_type = {"pdf": "pdf", ".md": "md", ".txt": "txt"}.get(suffix, "txt")

    # Enregistrement en DB
    doc = Document(
        id=doc_id,
        filename=safe_name,
        source_type=source_type,
        collection=collection,
        status=IngestionStatus.PENDING,
        file_size_bytes=len(content),
    )
    session.add(doc)
    await session.commit()

    # Envoi dans la queue RQ
    job = app.state.queue.enqueue(
        process_ingest_job,
        args=(str(doc_id), str(file_path), collection),
        job_id=f"ingest-{doc_id}",
        job_timeout=600,
    )

    logger.info(
        "ingest_queued",
        doc_id=str(doc_id),
        filename=safe_name,
        file_size=len(content),
        collection=collection,
        job_id=job.id,
    )

    return IngestResponse(
        job_id=job.id,
        doc_id=str(doc_id),
        status="pending",
        message=f"Document '{safe_name}' en attente de traitement",
    )


@app.get("/ingest/{doc_id}", response_model=DocumentStatus)
async def get_ingest_status(
    doc_id:  str,
    session = Depends(get_session),
):
    result = await session.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} introuvable")

    return DocumentStatus(
        doc_id=str(doc.id),
        filename=doc.filename,
        status=doc.status.value,
        chunk_count=doc.chunk_count,
        error=doc.error_message,
        created_at=doc.created_at.isoformat(),
        ingested_at=doc.ingested_at.isoformat() if doc.ingested_at else None,
    )


@app.get("/documents", response_model=DocumentList)
async def list_documents(
    collection: str | None = None,
    limit:      int        = 50,
    offset:     int        = 0,
    session = Depends(get_session),
):
    query = select(Document).order_by(Document.created_at.desc())
    if collection:
        query = query.where(Document.collection == collection)

    result = await session.execute(query.offset(offset).limit(limit))
    docs   = result.scalars().all()

    # Count total
    from sqlalchemy import func, select as sa_select
    count_q = sa_select(func.count()).select_from(Document)
    if collection:
        count_q = count_q.where(Document.collection == collection)
    total = (await session.execute(count_q)).scalar()

    return DocumentList(
        total=total or 0,
        documents=[
            DocumentStatus(
                doc_id=str(d.id),
                filename=d.filename,
                status=d.status.value,
                chunk_count=d.chunk_count,
                error=d.error_message,
                created_at=d.created_at.isoformat(),
                ingested_at=d.ingested_at.isoformat() if d.ingested_at else None,
            )
            for d in docs
        ],
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": "1.0.0",
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    # Met à jour la jauge de queue avant de servir les métriques
    try:
        QUEUE_PENDING.set(len(app.state.queue))
    except Exception:
        pass  # ne bloque jamais le scrape Prometheus
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ─── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
