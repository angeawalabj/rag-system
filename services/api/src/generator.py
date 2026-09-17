"""
Generator — construit le prompt augmenté et streame la réponse du LLM.
Ollama API est OpenAI-compatible : /v1/chat/completions avec stream=True.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog
from opentelemetry import trace

from src.config import settings
from src.retriever import RetrievedChunk

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# ─── Templates de prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es un assistant expert. Réponds UNIQUEMENT en te basant sur le contexte fourni ci-dessous.

Règles strictes :
- Si la réponse ne se trouve pas dans le contexte, dis explicitement : "Je ne trouve pas cette information dans les documents fournis."
- Ne fabrique aucune information absente du contexte.
- Cite tes sources avec leur numéro entre crochets : [1], [2], etc.
- Réponds en français sauf si la question est posée dans une autre langue.
- Sois concis et précis.
"""

def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Formate les chunks en bloc de contexte numéroté."""
    lines = []
    for i, chunk in enumerate(chunks, 1):
        source_info = chunk.source
        if chunk.page:
            source_info += f" (p.{chunk.page})"
        lines.append(f"[{i}] Source : {source_info}\n{chunk.text}")
    return "\n\n".join(lines)


def build_messages(question: str, chunks: list[RetrievedChunk]) -> list[dict]:
    """Construit la liste de messages pour l'API chat."""
    context = build_context_block(chunks)
    return [
        {"role": "system",    "content": SYSTEM_PROMPT},
        {"role": "user",      "content": f"Contexte :\n{context}\n\nQuestion : {question}"},
    ]


# ─── Événements SSE ──────────────────────────────────────────────────────────

def token_event(token: str) -> dict:
    return {"type": "token", "token": token, "done": False}

def sources_event(chunks: list[RetrievedChunk]) -> dict:
    return {
        "type": "sources",
        "done": True,
        "sources": [
            {
                "index":       i + 1,
                "chunk_id":    c.chunk_id,
                "source":      c.source,
                "source_type": c.source_type,
                "page":        c.page,
                "score":       c.score,
                "text_preview": c.text[:200] + "…" if len(c.text) > 200 else c.text,
            }
            for i, c in enumerate(chunks)
        ],
    }

def error_event(message: str) -> dict:
    return {"type": "error", "message": message, "done": True}


# ─── Generator ────────────────────────────────────────────────────────────────

class Generator:
    """
    Streame la réponse du LLM token par token via Ollama /v1/chat/completions.
    Retourne un AsyncGenerator d'événements SSE (dicts JSON).
    """

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.llm_timeout),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def stream(
        self,
        question: str,
        chunks:   list[RetrievedChunk],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Yield des événements SSE :
        - {"type": "token",   "token": "...", "done": false}  — un token à la fois
        - {"type": "sources", "done": true,   "sources": [...]} — fin + sources
        - {"type": "error",   "message": "...", "done": true}  — en cas d'erreur
        """
        with tracer.start_as_current_span("generator.stream") as span:
            span.set_attribute("model",    settings.llm_model)
            span.set_attribute("chunks",   len(chunks))
            span.set_attribute("question", question[:80])

            if not chunks:
                yield error_event(
                    "Aucun document pertinent trouvé pour cette question. "
                    "Essaie d'ingérer des documents d'abord."
                )
                return

            messages  = build_messages(question, chunks)
            token_count = 0

            try:
                async with self._http.stream(
                    "POST",
                    "/v1/chat/completions",
                    json={
                        "model":    settings.llm_model,
                        "messages": messages,
                        "stream":   True,
                        "options": {
                            "temperature": 0.1,   # conservateur pour un RAG
                            "top_p":       0.9,
                        },
                    },
                ) as resp:
                    resp.raise_for_status()

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break

                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        delta = (
                            payload
                            .get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            token_count += 1
                            yield token_event(delta)

                span.set_attribute("tokens_streamed", token_count)
                logger.info(
                    "generation_done",
                    tokens=token_count,
                    model=settings.llm_model,
                )

                # Dernier événement : sources
                yield sources_event(chunks)

            except httpx.HTTPStatusError as exc:
                span.record_exception(exc)
                logger.error("ollama_http_error", status=exc.response.status_code)
                yield error_event(f"Erreur LLM : HTTP {exc.response.status_code}")

            except httpx.TimeoutException:
                span.record_exception(Exception("LLM timeout"))
                logger.error("ollama_timeout", model=settings.llm_model)
                yield error_event(
                    f"Timeout LLM ({settings.llm_timeout}s). "
                    "Le modèle est peut-être surchargé."
                )

            except Exception as exc:
                span.record_exception(exc)
                logger.error("generation_error", error=str(exc))
                yield error_event(f"Erreur interne : {exc}")
