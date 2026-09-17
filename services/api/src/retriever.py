"""
Retriever — recherche vectorielle dans Qdrant.
Responsabilité unique : trouver les chunks pertinents pour une question.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog
from opentelemetry import trace
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class RetrievedChunk:
    """Un chunk retourné par la recherche vectorielle."""
    chunk_id:    str
    text:        str
    score:       float
    source:      str
    source_type: str
    page:        int | None
    collection:  str
    doc_id:      str


class Retriever:
    """
    Orchestre : embed(question) → search(Qdrant) → filter(score) → chunks
    """

    def __init__(self, qdrant: AsyncQdrantClient) -> None:
        self._qdrant = qdrant
        self._http   = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=settings.embed_timeout,
        )

    async def close(self) -> None:
        await self._http.aclose()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        reraise=True,
    )
    async def _embed_query(self, question: str) -> list[float]:
        """Embed la question via Ollama (même modèle que l'ingestion)."""
        with tracer.start_as_current_span("retriever.embed_query") as span:
            span.set_attribute("model", settings.embed_model)
            span.set_attribute("question_len", len(question))

            resp = await self._http.post(
                "/api/embeddings",
                json={"model": settings.embed_model, "prompt": question},
            )
            resp.raise_for_status()
            vector = resp.json()["embedding"]
            span.set_attribute("vector_dim", len(vector))
            return vector

    async def retrieve(
        self,
        question:        str,
        collection:      str | None = None,
        top_k:           int | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retourne les chunks les plus pertinents pour la question.
        Filtrés par score_threshold, triés par score décroissant.
        """
        col   = collection      or settings.qdrant_collection
        k     = top_k           or settings.rag_top_k
        score = score_threshold or settings.rag_score_threshold

        with tracer.start_as_current_span("retriever.retrieve") as span:
            span.set_attribute("collection",      col)
            span.set_attribute("top_k",           k)
            span.set_attribute("score_threshold", score)

            # 1. Embed la question
            query_vector = await self._embed_query(question)

            # 2. Filtre optionnel sur la collection Qdrant
            q_filter = Filter(
                must=[FieldCondition(
                    key="collection",
                    match=MatchValue(value=col),
                )]
            ) if col else None

            # 3. Recherche vectorielle
            results = await self._qdrant.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                limit=k,
                score_threshold=score,
                query_filter=q_filter,
                with_payload=True,
            )

            chunks = [
                RetrievedChunk(
                    chunk_id=str(r.id),
                    text=r.payload.get("text", ""),
                    score=round(r.score, 4),
                    source=r.payload.get("source", ""),
                    source_type=r.payload.get("source_type", ""),
                    page=r.payload.get("page"),
                    collection=r.payload.get("collection", col),
                    doc_id=r.payload.get("doc_id", ""),
                )
                for r in results
            ]

            span.set_attribute("chunks_found", len(chunks))
            logger.info(
                "retrieve_done",
                question_preview=question[:60],
                chunks=len(chunks),
                top_score=chunks[0].score if chunks else None,
            )
            return chunks
