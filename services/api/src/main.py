"""
RAG API — point d'entrée FastAPI.

Routes :
  POST /query          Requête RAG avec streaming SSE
  GET  /query/history  Historique des requêtes (PostgreSQL)
  GET  /collections    Collections Qdrant disponibles
  DELETE /cache/{col}  Invalide le cache d'une collection
  GET  /health         Healthcheck
  GET  /metrics        Prometheus metrics
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from sse_starlette.sse import EventSourceResponse

from src.cache import RAGCache
from src.config import settings
from src.generator import Generator
from src.retriever import Retriever

logger = structlog.get_logger(__name__)

# ─── Métriques Prometheus ─────────────────────────────────────────────────────

QUERIES_TOTAL = Counter(
    "rag_queries_total",
    "Total requêtes RAG",
    ["collection", "cache_hit"],
)
QUERY_DURATION = Histogram(
    "rag_query_duration_seconds",
    "Durée end-to-end d'une requête RAG",
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
)
CHUNKS_RETRIEVED = Histogram(
    "rag_chunks_retrieved",
    "Nombre de chunks retournés par retrieve",
    buckets=[0, 1, 2, 3, 5, 8],
)

# ─── OTel ─────────────────────────────────────────────────────────────────────

def setup_otel() -> None:
    resource = Resource({SERVICE_NAME: settings.service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint
        ))
    )
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_otel()

    qdrant    = AsyncQdrantClient(url=settings.qdrant_url)
    redis_cli = aioredis.from_url(settings.redis_url, decode_responses=True)
    retriever = Retriever(qdrant)
    generator = Generator()
    cache     = RAGCache(redis_cli)

    app.state.qdrant    = qdrant
    app.state.redis     = redis_cli
    app.state.retriever = retriever
    app.state.generator = generator
    app.state.cache     = cache

    logger.info("rag_api_started", port=settings.port)
    yield

    await retriever.close()
    await generator.close()
    await redis_cli.aclose()
    await qdrant.close()
    logger.info("rag_api_stopped")


# ─── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG API",
    description="Pipeline RAG : retrieve → augment → generate (streaming SSE)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)

tracer = trace.get_tracer(__name__)


# ─── Schémas ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question:        str   = Field(..., min_length=3, max_length=1000)
    collection:      str   = Field(default="documents")
    top_k:           int   = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    use_cache:       bool  = Field(default=True)

class CollectionInfo(BaseModel):
    name:         str
    vector_count: int


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.post("/query")
async def query(req: QueryRequest):
    """
    Requête RAG streamée via SSE.

    Le client reçoit une séquence d'événements JSON :
    - `{"type":"token", "token":"...", "done":false}` — tokens du LLM
    - `{"type":"sources", "done":true, "sources":[...]}` — fin + sources
    - `{"type":"error",  "done":true, "message":"..."}` — erreur éventuelle
    """
    retriever: Retriever = app.state.retriever
    generator: Generator = app.state.generator
    cache:     RAGCache  = app.state.cache

    request_id = str(uuid.uuid4())[:8]
    log = logger.bind(request_id=request_id, question=req.question[:60])

    async def event_stream():
        with tracer.start_as_current_span("rag.query") as span:
            span.set_attribute("question",   req.question[:80])
            span.set_attribute("collection", req.collection)
            span.set_attribute("top_k",      req.top_k)

            t_start = time.perf_counter()

            # ── Cache lookup ─────────────────────────────────────────────────
            cached = None
            if req.use_cache:
                cached = await cache.get(req.question, req.collection, req.top_k)

            if cached:
                QUERIES_TOTAL.labels(
                    collection=req.collection, cache_hit="true"
                ).inc()
                log.info("cache_hit")
                # Rejoue les tokens depuis le cache
                for token in cached.get("tokens", []):
                    yield {"data": json.dumps({"type": "token", "token": token, "done": False})}
                yield {"data": json.dumps({
                    "type": "sources", "done": True,
                    "sources": cached.get("sources", []),
                    "cached": True,
                })}
                return

            QUERIES_TOTAL.labels(
                collection=req.collection, cache_hit="false"
            ).inc()

            # ── Retrieve ─────────────────────────────────────────────────────
            try:
                chunks = await retriever.retrieve(
                    question=req.question,
                    collection=req.collection,
                    top_k=req.top_k,
                    score_threshold=req.score_threshold,
                )
                CHUNKS_RETRIEVED.observe(len(chunks))
                span.set_attribute("chunks_retrieved", len(chunks))
            except Exception as exc:
                log.error("retrieve_error", error=str(exc))
                yield {"data": json.dumps({
                    "type": "error",
                    "message": f"Erreur de recherche : {exc}",
                    "done": True,
                })}
                return

            # ── Generate (stream) ─────────────────────────────────────────────
            all_tokens:  list[str]  = []
            final_sources: list     = []

            async for event in generator.stream(req.question, chunks):
                yield {"data": json.dumps(event)}

                if event.get("type") == "token":
                    all_tokens.append(event["token"])
                elif event.get("type") == "sources":
                    final_sources = event.get("sources", [])

            # ── Mise en cache de la réponse complète ─────────────────────────
            if req.use_cache and all_tokens:
                await cache.set(
                    req.question, req.collection, req.top_k,
                    {"tokens": all_tokens, "sources": final_sources},
                )

            elapsed = time.perf_counter() - t_start
            QUERY_DURATION.observe(elapsed)
            span.set_attribute("duration_s", round(elapsed, 3))
            log.info("query_done", duration=round(elapsed, 2), tokens=len(all_tokens))

    return EventSourceResponse(event_stream())


@app.get("/collections", response_model=list[CollectionInfo])
async def list_collections():
    """Liste les collections Qdrant avec leur nombre de vecteurs."""
    qdrant: AsyncQdrantClient = app.state.qdrant
    result = await qdrant.get_collections()
    infos  = []
    for col in result.collections:
        info = await qdrant.get_collection(col.name)
        infos.append(CollectionInfo(
            name=col.name,
            vector_count=info.vectors_count or 0,
        ))
    return infos


@app.delete("/cache/{collection}", status_code=200)
async def invalidate_cache(collection: str):
    """Invalide le cache Redis pour une collection."""
    cache: RAGCache = app.state.cache
    count = await cache.invalidate_collection(collection)
    return {"message": f"{count} entrée(s) de cache supprimée(s)", "collection": collection}


@app.get("/health")
async def health():
    """Healthcheck — vérifie Qdrant et Redis."""
    qdrant: AsyncQdrantClient = app.state.qdrant
    redis:  aioredis.Redis    = app.state.redis

    qdrant_ok = False
    redis_ok  = False

    try:
        await qdrant.get_collections()
        qdrant_ok = True
    except Exception:
        pass

    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    status = "ok" if (qdrant_ok and redis_ok) else "degraded"
    return {
        "status":   status,
        "service":  settings.service_name,
        "version":  "1.0.0",
        "checks":   {"qdrant": qdrant_ok, "redis": redis_ok},
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
