"""
Client d'embedding — appelle Ollama /api/embeddings.
API compatible OpenAI : même client utilisable avec text-embedding-3-small
en changeant uniquement OLLAMA_BASE_URL et EMBED_MODEL.
"""

from __future__ import annotations

import asyncio
from typing import Sequence

import httpx
import structlog
from opentelemetry import trace
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt, wait_exponential
)

from src.config import settings

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class EmbedderError(Exception):
    """Levée quand Ollama retourne une erreur ou est injoignable."""


class Embedder:
    """
    Génère des embeddings via Ollama.

    Usage :
        async with Embedder() as embedder:
            vectors = await embedder.embed_batch(["chunk1", "chunk2"])
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "Embedder":
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.embed_timeout),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, EmbedderError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def embed_one(self, text: str) -> list[float]:
        """Embed un seul texte. Tracé par OTel."""
        with tracer.start_as_current_span("embedder.embed_one") as span:
            span.set_attribute("model", settings.embed_model)
            span.set_attribute("text_length", len(text))

            assert self._client is not None, "Utiliser comme context manager"

            try:
                resp = await self._client.post(
                    "/api/embeddings",
                    json={"model": settings.embed_model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                vector = data.get("embedding")
                if not vector:
                    raise EmbedderError(f"Réponse Ollama invalide : {data}")

                span.set_attribute("vector_dim", len(vector))
                return vector

            except httpx.HTTPStatusError as exc:
                span.record_exception(exc)
                raise EmbedderError(
                    f"Ollama HTTP {exc.response.status_code} : {exc.response.text}"
                ) from exc
            except httpx.HTTPError as exc:
                span.record_exception(exc)
                raise

    async def embed_batch(
        self,
        texts: Sequence[str],
        concurrency: int = 4,
    ) -> list[list[float]]:
        """
        Embed plusieurs textes avec concurrence contrôlée.
        Ollama ne supporte pas le batch natif — on parallélise côté client.
        """
        with tracer.start_as_current_span("embedder.embed_batch") as span:
            span.set_attribute("batch_size", len(texts))
            span.set_attribute("concurrency", concurrency)

            semaphore = asyncio.Semaphore(concurrency)

            async def _embed_with_sem(text: str) -> list[float]:
                async with semaphore:
                    return await self.embed_one(text)

            vectors = await asyncio.gather(*[_embed_with_sem(t) for t in texts])

            logger.info(
                "batch_embedded",
                count=len(texts),
                model=settings.embed_model,
                vector_dim=len(vectors[0]) if vectors else 0,
            )
            return list(vectors)
