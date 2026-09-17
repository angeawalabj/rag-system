"""
Cache Redis pour les résultats RAG.
Clé = SHA256(question + collection + top_k).
TTL configurable, invalidation par collection.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


class RAGCache:

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    def _key(self, question: str, collection: str, top_k: int) -> str:
        raw = f"{question}|{collection}|{top_k}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"rag:cache:{digest}"

    def _inv_key(self, collection: str) -> str:
        """Clé du set d'invalidation pour une collection."""
        return f"rag:inv:{collection}"

    async def get(
        self, question: str, collection: str, top_k: int
    ) -> dict | None:
        key = self._key(question, collection, top_k)
        raw = await self._redis.get(key)
        if raw:
            logger.info("cache_hit", key=key[:20])
            return json.loads(raw)
        return None

    async def set(
        self,
        question:   str,
        collection: str,
        top_k:      int,
        value:      dict[str, Any],
    ) -> None:
        key = self._key(question, collection, top_k)
        await self._redis.setex(key, settings.cache_ttl, json.dumps(value))
        # Enregistre la clé dans le set d'invalidation de la collection
        await self._redis.sadd(self._inv_key(collection), key)
        logger.info("cache_set", key=key[:20], ttl=settings.cache_ttl)

    async def invalidate_collection(self, collection: str) -> int:
        """Invalide tous les résultats mis en cache pour une collection."""
        inv_key = self._inv_key(collection)
        keys    = await self._redis.smembers(inv_key)
        if keys:
            await self._redis.delete(*keys)
            await self._redis.delete(inv_key)
        logger.info("cache_invalidated", collection=collection, keys=len(keys))
        return len(keys)
