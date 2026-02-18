"""LLM prompt caching service for optimizing API calls.

Implements:
- Prompt caching to reduce redundant LLM API calls
- Cache statistics for metrics
- TTL-based cache expiration
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """A cached LLM response."""

    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    token_savings: int = 0


@dataclass
class CacheStats:
    """Statistics for cache performance."""

    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    tokens_saved: int = 0
    cache_size: int = 0
    oldest_entry: datetime | None = None
    newest_entry: datetime | None = None

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests * 100


class LLMPromptCache:
    """In-memory cache for LLM prompts and responses.

    Caches LLM responses to avoid redundant API calls for identical requests.
    Uses TTL-based expiration and LRU eviction.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl_seconds: int = 3600,
        enabled: bool = True,
    ):
        """Initialize LLM prompt cache.

        Args:
            max_size: Maximum number of cache entries
            default_ttl_seconds: Default TTL for cache entries (1 hour)
            enabled: Whether caching is enabled
        """
        self.max_size = max_size
        self.default_ttl = timedelta(seconds=default_ttl_seconds)
        self.enabled = enabled
        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()

    def _generate_key(
        self,
        operation: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        **kwargs: Any,
    ) -> str:
        """Generate a cache key from request parameters.

        Args:
            operation: Type of LLM operation
            model: Model name
            messages: Message list
            temperature: Temperature setting
            **kwargs: Additional parameters

        Returns:
            SHA256 hash key
        """
        key_data = {
            "operation": operation,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        # Create deterministic JSON string
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self,
        operation: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        """Get cached response if available.

        Args:
            operation: Type of LLM operation
            model: Model name
            messages: Message list
            temperature: Temperature setting
            **kwargs: Additional parameters

        Returns:
            Tuple of (cached_value, cache_hit)
        """
        self._stats.total_requests += 1

        if not self.enabled:
            self._stats.misses += 1
            return None, False

        key = self._generate_key(operation, model, messages, temperature, **kwargs)

        entry = self._cache.get(key)

        if entry is None:
            self._stats.misses += 1
            return None, False

        # Check expiration
        if datetime.utcnow() > entry.expires_at:
            del self._cache[key]
            self._stats.misses += 1
            return None, False

        # Cache hit
        entry.hit_count += 1
        self._stats.hits += 1
        self._stats.tokens_saved += entry.token_savings

        logger.debug(
            "LLM cache hit",
            operation=operation,
            hit_count=entry.hit_count,
            tokens_saved=entry.token_savings,
        )

        return entry.value, True

    def set(
        self,
        operation: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        value: Any,
        token_count: int = 0,
        ttl_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Cache an LLM response.

        Args:
            operation: Type of LLM operation
            model: Model name
            messages: Message list
            temperature: Temperature setting
            value: Response to cache
            token_count: Total tokens used (for savings tracking)
            ttl_seconds: Optional custom TTL
            **kwargs: Additional parameters
        """
        if not self.enabled:
            return

        # Evict if at capacity
        if len(self._cache) >= self.max_size:
            self._evict_oldest()

        key = self._generate_key(operation, model, messages, temperature, **kwargs)
        ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self.default_ttl
        now = datetime.utcnow()

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + ttl,
            hit_count=0,
            token_savings=token_count,
        )

        self._cache[key] = entry
        self._stats.cache_size = len(self._cache)

        # Update timestamp tracking
        if self._stats.oldest_entry is None or now < self._stats.oldest_entry:
            self._stats.oldest_entry = now
        self._stats.newest_entry = now

        logger.debug(
            "LLM response cached",
            operation=operation,
            key=key[:16],
            ttl_seconds=ttl.total_seconds(),
        )

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entry."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at,
        )
        del self._cache[oldest_key]

    def invalidate(
        self,
        operation: str | None = None,
    ) -> int:
        """Invalidate cache entries.

        Args:
            operation: Optional operation type to invalidate

        Returns:
            Number of entries invalidated
        """
        if operation is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        # Invalidate by operation prefix
        keys_to_delete = [
            k for k, v in self._cache.items()
            if v.value.get("operation") == operation
        ]

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats instance
        """
        self._stats.cache_size = len(self._cache)
        return self._stats

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        expired_keys = [
            k for k, v in self._cache.items()
            if now > v.expires_at
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)


# Global cache instance
_llm_cache: LLMPromptCache | None = None


def get_llm_cache(
    max_size: int = 1000,
    default_ttl_seconds: int = 3600,
) -> LLMPromptCache:
    """Get the global LLM cache instance.

    Args:
        max_size: Maximum cache size
        default_ttl_seconds: Default TTL

    Returns:
        LLMPromptCache singleton
    """
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMPromptCache(
            max_size=max_size,
            default_ttl_seconds=default_ttl_seconds,
        )
    return _llm_cache


class CachedLLMService:
    """LLM service wrapper with caching support.

    Wraps the LLMService to add caching for repeated operations.
    Particularly useful for:
    - Cluster summaries that don't change frequently
    - Priority assessments for unchanged clusters
    - Topic generation for similar signals
    """

    def __init__(
        self,
        llm_service: Any,  # LLMService
        cache: LLMPromptCache | None = None,
    ):
        """Initialize cached LLM service.

        Args:
            llm_service: Underlying LLM service
            cache: Optional cache instance
        """
        self.llm = llm_service
        self.cache = cache or get_llm_cache()

    async def generate_cluster_summary(
        self,
        signals: list,
        topic: str,
        use_cache: bool = True,
        cache_ttl: int = 1800,  # 30 minutes
    ) -> str:
        """Generate cluster summary with caching.

        Args:
            signals: Signals in the cluster
            topic: Cluster topic
            use_cache: Whether to use cache
            cache_ttl: Cache TTL in seconds

        Returns:
            Generated or cached summary
        """
        operation = "generate_cluster_summary"
        model = self.llm.model
        temperature = self.llm.temperature

        # Build cache key from signal IDs and topic
        signal_ids = sorted([str(s.id) for s in signals])
        messages = [
            {"role": "context", "content": json.dumps({"topic": topic, "signal_ids": signal_ids})}
        ]

        if use_cache and self.cache.enabled:
            cached, hit = self.cache.get(operation, model, messages, temperature)
            if hit:
                return cached

        # Generate fresh summary
        summary = await self.llm.generate_cluster_summary(signals, topic)

        # Cache the result
        self.cache.set(
            operation=operation,
            model=model,
            messages=messages,
            temperature=temperature,
            value=summary,
            token_count=len(summary.split()) * 2,  # Rough token estimate
            ttl_seconds=cache_ttl,
        )

        return summary

    async def assess_priority(
        self,
        cluster: Any,  # Cluster
        signals: list,
        use_cache: bool = True,
        cache_ttl: int = 900,  # 15 minutes
    ) -> Any:  # PriorityScores
        """Assess cluster priority with caching.

        Args:
            cluster: Cluster to assess
            signals: Signals in the cluster
            use_cache: Whether to use cache
            cache_ttl: Cache TTL in seconds

        Returns:
            PriorityScores
        """
        operation = "assess_priority"
        model = self.llm.model
        temperature = self.llm.temperature

        # Build cache key from cluster state
        messages = [
            {
                "role": "context",
                "content": json.dumps({
                    "cluster_id": str(cluster.id),
                    "topic": cluster.topic,
                    "summary": cluster.summary,
                    "signal_count": len(signals),
                    "latest_signal": str(signals[0].id) if signals else None,
                }),
            }
        ]

        if use_cache and self.cache.enabled:
            cached, hit = self.cache.get(operation, model, messages, temperature)
            if hit:
                return cached

        # Generate fresh assessment
        priority = await self.llm.assess_priority(cluster, signals)

        # Cache the result
        self.cache.set(
            operation=operation,
            model=model,
            messages=messages,
            temperature=temperature,
            value=priority,
            token_count=50,  # Estimate for priority response
            ttl_seconds=cache_ttl,
        )

        return priority

    async def generate_topic_from_signal(
        self,
        signal: Any,  # Signal
        use_cache: bool = True,
        cache_ttl: int = 3600,  # 1 hour
    ) -> str:
        """Generate topic from signal with caching.

        Args:
            signal: Signal to generate topic from
            use_cache: Whether to use cache
            cache_ttl: Cache TTL in seconds

        Returns:
            Generated topic
        """
        operation = "generate_topic_from_signal"
        model = self.llm.model
        temperature = 0.5  # Topic generation uses different temp

        # Cache key based on content hash
        content_hash = hashlib.sha256(signal.content.encode()).hexdigest()[:16]
        messages = [
            {"role": "context", "content": json.dumps({"content_hash": content_hash})}
        ]

        if use_cache and self.cache.enabled:
            cached, hit = self.cache.get(operation, model, messages, temperature)
            if hit:
                return cached

        # Generate fresh topic
        topic = await self.llm.generate_topic_from_signal(signal)

        # Cache the result
        self.cache.set(
            operation=operation,
            model=model,
            messages=messages,
            temperature=temperature,
            value=topic,
            token_count=20,  # Estimate for topic
            ttl_seconds=cache_ttl,
        )

        return topic

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache performance statistics.

        Returns:
            Dictionary with cache stats
        """
        stats = self.cache.get_stats()
        return {
            "hits": stats.hits,
            "misses": stats.misses,
            "total_requests": stats.total_requests,
            "hit_rate_percent": round(stats.hit_rate, 2),
            "tokens_saved": stats.tokens_saved,
            "cache_size": stats.cache_size,
            "oldest_entry": stats.oldest_entry.isoformat() if stats.oldest_entry else None,
            "newest_entry": stats.newest_entry.isoformat() if stats.newest_entry else None,
        }
