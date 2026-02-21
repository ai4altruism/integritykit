"""Unit tests for LLM cache service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from integritykit.services.llm_cache import (
    CacheEntry,
    CacheStats,
    LLMPromptCache,
    CachedLLMService,
)


@pytest.mark.unit
class TestCacheStats:
    """Test CacheStats dataclass and properties."""

    def test_hit_rate_with_zero_requests_returns_zero(self):
        """Test hit_rate returns 0.0 when total_requests is 0."""
        stats = CacheStats(hits=0, misses=0, total_requests=0)

        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit_rate calculates percentage correctly."""
        stats = CacheStats(hits=75, misses=25, total_requests=100)

        assert stats.hit_rate == 75.0

    def test_hit_rate_calculation_partial(self):
        """Test hit_rate with non-round percentage."""
        stats = CacheStats(hits=33, misses=67, total_requests=100)

        assert stats.hit_rate == 33.0

    def test_hit_rate_calculation_decimal(self):
        """Test hit_rate with decimal result."""
        stats = CacheStats(hits=1, misses=2, total_requests=3)

        expected = 1 / 3 * 100
        assert abs(stats.hit_rate - expected) < 0.01


@pytest.mark.unit
class TestLLMPromptCache:
    """Test LLMPromptCache functionality."""

    def test_cache_disabled_always_misses(self):
        """Test cache returns miss when disabled."""
        cache = LLMPromptCache(enabled=False)

        # Set a value (should not cache)
        cache.set(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
            value="response",
        )

        # Try to get value (should always miss)
        value, hit = cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        assert value is None
        assert hit is False
        assert len(cache._cache) == 0

    def test_cache_miss_on_empty_cache(self):
        """Test cache returns miss on empty cache."""
        cache = LLMPromptCache()

        value, hit = cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        assert value is None
        assert hit is False

    def test_cache_hit_after_set(self):
        """Test cache returns hit after value is set."""
        cache = LLMPromptCache()

        # Set value
        cache.set(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
            value="cached response",
            token_count=50,
        )

        # Get value
        value, hit = cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        assert value == "cached response"
        assert hit is True

    def test_ttl_expiration_entry_expires_after_ttl(self):
        """Test cache entry expires after TTL."""
        cache = LLMPromptCache(default_ttl_seconds=1)

        # Set value
        cache.set(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
            value="cached response",
        )

        # Mock time to be after expiration
        with patch('integritykit.services.llm_cache.datetime') as mock_datetime:
            future_time = datetime.utcnow() + timedelta(seconds=2)
            mock_datetime.utcnow.return_value = future_time

            value, hit = cache.get(
                operation="test_op",
                model="gpt-4",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.7,
            )

        assert value is None
        assert hit is False

    def test_eviction_when_at_max_size(self):
        """Test cache evicts oldest entry when at max_size."""
        cache = LLMPromptCache(max_size=2)

        # Add first entry
        cache.set(
            operation="op1",
            model="gpt-4",
            messages=[{"role": "user", "content": "first"}],
            temperature=0.7,
            value="response1",
        )

        # Add second entry
        cache.set(
            operation="op2",
            model="gpt-4",
            messages=[{"role": "user", "content": "second"}],
            temperature=0.7,
            value="response2",
        )

        # Add third entry (should evict first)
        cache.set(
            operation="op3",
            model="gpt-4",
            messages=[{"role": "user", "content": "third"}],
            temperature=0.7,
            value="response3",
        )

        # First entry should be evicted
        value1, hit1 = cache.get(
            operation="op1",
            model="gpt-4",
            messages=[{"role": "user", "content": "first"}],
            temperature=0.7,
        )
        assert hit1 is False

        # Second entry should still exist
        value2, hit2 = cache.get(
            operation="op2",
            model="gpt-4",
            messages=[{"role": "user", "content": "second"}],
            temperature=0.7,
        )
        assert hit2 is True
        assert value2 == "response2"

        # Third entry should exist
        value3, hit3 = cache.get(
            operation="op3",
            model="gpt-4",
            messages=[{"role": "user", "content": "third"}],
            temperature=0.7,
        )
        assert hit3 is True
        assert value3 == "response3"

    def test_custom_ttl_per_entry(self):
        """Test cache respects custom TTL per entry."""
        cache = LLMPromptCache(default_ttl_seconds=3600)

        # Set value with custom short TTL
        cache.set(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
            value="cached response",
            ttl_seconds=1,
        )

        # Mock time to be after custom TTL but before default TTL
        with patch('integritykit.services.llm_cache.datetime') as mock_datetime:
            future_time = datetime.utcnow() + timedelta(seconds=2)
            mock_datetime.utcnow.return_value = future_time

            value, hit = cache.get(
                operation="test_op",
                model="gpt-4",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.7,
            )

        assert value is None
        assert hit is False

    def test_same_key_determinism_same_params_produce_same_key(self):
        """Test same parameters produce same cache key."""
        cache = LLMPromptCache()

        key1 = cache._generate_key(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        key2 = cache._generate_key(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        assert key1 == key2

    def test_different_params_produce_different_keys(self):
        """Test different parameters produce different cache keys."""
        cache = LLMPromptCache()

        key1 = cache._generate_key(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        # Different content
        key2 = cache._generate_key(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "different"}],
            temperature=0.7,
        )

        # Different temperature
        key3 = cache._generate_key(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.9,
        )

        # Different operation
        key4 = cache._generate_key(
            operation="different_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        # Different model
        key5 = cache._generate_key(
            operation="test_op",
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        assert key1 != key2
        assert key1 != key3
        assert key1 != key4
        assert key1 != key5

    def test_stats_tracking_hits_misses_tokens_saved(self):
        """Test cache tracks hits, misses, and tokens saved."""
        cache = LLMPromptCache()

        # Initial miss
        cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
        )

        # Set value with token count
        cache.set(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
            value="response",
            token_count=100,
        )

        # Hit
        cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
        )

        # Another hit
        cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
        )

        # Another miss (different content)
        cache.get(
            operation="test_op",
            model="gpt-4",
            messages=[{"role": "user", "content": "test2"}],
            temperature=0.7,
        )

        stats = cache.get_stats()
        assert stats.hits == 2
        assert stats.misses == 2
        assert stats.total_requests == 4
        assert stats.tokens_saved == 200  # 100 tokens * 2 hits

    def test_invalidate_clears_all_entries(self):
        """Test invalidate() clears all cache entries."""
        cache = LLMPromptCache()

        # Add multiple entries
        cache.set(
            operation="op1",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
            value="response1",
        )

        cache.set(
            operation="op2",
            model="gpt-4",
            messages=[{"role": "user", "content": "test2"}],
            temperature=0.7,
            value="response2",
        )

        # Invalidate all
        count = cache.invalidate()

        assert count == 2
        assert len(cache._cache) == 0

    def test_cleanup_expired_removes_expired_keeps_valid(self):
        """Test cleanup_expired() removes only expired entries."""
        cache = LLMPromptCache()

        base_time = datetime(2024, 1, 1, 12, 0, 0)
        future_time = datetime(2024, 1, 1, 12, 1, 30)  # 90 seconds later

        with patch('integritykit.services.llm_cache.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = base_time
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)

            # Add entry that will expire (60s TTL)
            cache.set(
                operation="op1",
                model="gpt-4",
                messages=[{"role": "user", "content": "test1"}],
                temperature=0.7,
                value="response1",
                ttl_seconds=60,
            )

            # Add entry that will not expire (3600s TTL)
            cache.set(
                operation="op2",
                model="gpt-4",
                messages=[{"role": "user", "content": "test2"}],
                temperature=0.7,
                value="response2",
                ttl_seconds=3600,
            )

            # Clean up expired entries (90 seconds later)
            mock_datetime.utcnow.return_value = future_time

            count = cache.cleanup_expired()

            assert count == 1
            assert len(cache._cache) == 1

            # Verify the valid entry is still accessible
            value, hit = cache.get(
                operation="op2",
                model="gpt-4",
                messages=[{"role": "user", "content": "test2"}],
                temperature=0.7,
            )
            assert hit is True
            assert value == "response2"

    def test_get_stats_returns_correct_cache_size(self):
        """Test get_stats() returns correct cache_size."""
        cache = LLMPromptCache()

        # Empty cache
        stats = cache.get_stats()
        assert stats.cache_size == 0

        # Add entries
        cache.set(
            operation="op1",
            model="gpt-4",
            messages=[{"role": "user", "content": "test1"}],
            temperature=0.7,
            value="response1",
        )

        cache.set(
            operation="op2",
            model="gpt-4",
            messages=[{"role": "user", "content": "test2"}],
            temperature=0.7,
            value="response2",
        )

        stats = cache.get_stats()
        assert stats.cache_size == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestCachedLLMService:
    """Test CachedLLMService functionality."""

    def _create_mock_llm_service(self):
        """Create mock LLM service with required attributes and methods."""
        mock_llm = MagicMock()
        mock_llm.model = "gpt-4o-mini"
        mock_llm.temperature = 0.7
        mock_llm.generate_cluster_summary = AsyncMock(return_value="Generated summary")
        mock_llm.assess_priority = AsyncMock(return_value=MagicMock())
        mock_llm.generate_topic_from_signal = AsyncMock(return_value="Generated topic")
        return mock_llm

    def _create_mock_signal(self, signal_id="123", content="Test signal content"):
        """Create mock signal."""
        signal = MagicMock()
        signal.id = signal_id
        signal.content = content
        return signal

    def _create_mock_cluster(self, cluster_id="456", topic="Test topic", summary="Test summary"):
        """Create mock cluster."""
        cluster = MagicMock()
        cluster.id = cluster_id
        cluster.topic = topic
        cluster.summary = summary
        return cluster

    async def test_cache_hit_returns_cached_value_without_calling_llm(self):
        """Test cache hit returns cached value without calling LLM."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal = self._create_mock_signal()
        signals = [signal]
        topic = "Test topic"

        # First call - cache miss, should call LLM
        result1 = await service.generate_cluster_summary(signals, topic)
        assert result1 == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 1

        # Second call - cache hit, should NOT call LLM
        result2 = await service.generate_cluster_summary(signals, topic)
        assert result2 == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 1  # Still 1, not called again

    async def test_cache_miss_calls_llm_and_caches_result(self):
        """Test cache miss calls LLM and caches result."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal = self._create_mock_signal()
        signals = [signal]
        topic = "Test topic"

        # First call - cache miss
        result = await service.generate_cluster_summary(signals, topic)

        assert result == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 1

        # Verify result is cached
        stats = service.get_cache_stats()
        assert stats["cache_size"] == 1

    async def test_use_cache_false_bypasses_cache_lookup(self):
        """Test use_cache=False bypasses cache lookup but still stores result."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal = self._create_mock_signal()
        signals = [signal]
        topic = "Test topic"

        # First call with use_cache=False - should call LLM
        result1 = await service.generate_cluster_summary(signals, topic, use_cache=False)
        assert result1 == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 1

        # Second call with use_cache=False - should call LLM again (bypasses cache read)
        result2 = await service.generate_cluster_summary(signals, topic, use_cache=False)
        assert result2 == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 2

    async def test_generate_cluster_summary_caching(self):
        """Test generate_cluster_summary caches correctly."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal1 = self._create_mock_signal(signal_id="1", content="Signal 1")
        signal2 = self._create_mock_signal(signal_id="2", content="Signal 2")
        signals = [signal1, signal2]
        topic = "Test topic"

        # First call
        result1 = await service.generate_cluster_summary(signals, topic)
        assert result1 == "Generated summary"

        # Same signals, different order - should hit cache
        signals_reversed = [signal2, signal1]
        result2 = await service.generate_cluster_summary(signals_reversed, topic)
        assert result2 == "Generated summary"
        assert mock_llm.generate_cluster_summary.call_count == 1  # Still 1

    async def test_assess_priority_caching(self):
        """Test assess_priority caches correctly."""
        mock_llm = self._create_mock_llm_service()
        mock_priority = MagicMock()
        mock_llm.assess_priority = AsyncMock(return_value=mock_priority)

        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        cluster = self._create_mock_cluster()
        signal = self._create_mock_signal()
        signals = [signal]

        # First call
        result1 = await service.assess_priority(cluster, signals)
        assert result1 == mock_priority
        assert mock_llm.assess_priority.call_count == 1

        # Second call - cache hit
        result2 = await service.assess_priority(cluster, signals)
        assert result2 == mock_priority
        assert mock_llm.assess_priority.call_count == 1  # Still 1

    async def test_generate_topic_from_signal_caching(self):
        """Test generate_topic_from_signal caches correctly."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal = self._create_mock_signal(content="Consistent signal content")

        # First call
        result1 = await service.generate_topic_from_signal(signal)
        assert result1 == "Generated topic"
        assert mock_llm.generate_topic_from_signal.call_count == 1

        # Second call with same content - cache hit
        result2 = await service.generate_topic_from_signal(signal)
        assert result2 == "Generated topic"
        assert mock_llm.generate_topic_from_signal.call_count == 1  # Still 1

        # Different content - cache miss
        signal2 = self._create_mock_signal(content="Different content")
        result3 = await service.generate_topic_from_signal(signal2)
        assert result3 == "Generated topic"
        assert mock_llm.generate_topic_from_signal.call_count == 2  # Called again

    def test_get_cache_stats_returns_formatted_dict(self):
        """Test get_cache_stats() returns formatted dictionary."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        stats = service.get_cache_stats()

        # Verify structure
        assert "hits" in stats
        assert "misses" in stats
        assert "total_requests" in stats
        assert "hit_rate_percent" in stats
        assert "tokens_saved" in stats
        assert "cache_size" in stats
        assert "oldest_entry" in stats
        assert "newest_entry" in stats

        # Verify types
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)
        assert isinstance(stats["total_requests"], int)
        assert isinstance(stats["hit_rate_percent"], float)
        assert isinstance(stats["tokens_saved"], int)
        assert isinstance(stats["cache_size"], int)

    async def test_custom_cache_ttl(self):
        """Test custom cache TTL is respected."""
        mock_llm = self._create_mock_llm_service()
        cache = LLMPromptCache()
        service = CachedLLMService(llm_service=mock_llm, cache=cache)

        signal = self._create_mock_signal()
        signals = [signal]
        topic = "Test topic"

        # Set with custom TTL
        await service.generate_cluster_summary(signals, topic, cache_ttl=60)

        # Verify entry is cached with custom TTL
        # Get the cache entry to verify TTL
        stats = service.get_cache_stats()
        assert stats["cache_size"] == 1
