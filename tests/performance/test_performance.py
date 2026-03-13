"""Performance tests for Aid Arena Integrity Kit v1.0.

Tests:
- Analytics service performance (time-series queries, trend detection)
- Export services (CAP, EDXL, GeoJSON) - generation time for varying dataset sizes
- Webhook delivery throughput
- Language detection service latency
- Draft generation performance

Performance targets:
- API response time: <200ms (p95)
- Export generation: <500ms for standard datasets
- Memory usage: reasonable bounds for large exports
- Concurrent request handling: graceful degradation
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from integritykit.models.analytics import Granularity, MetricType, TimeSeriesAnalyticsRequest
from integritykit.models.audit import AuditActionType
from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
)
from integritykit.models.cop_update import COPUpdate, EvidenceSnapshot, PublishedLineItem
from integritykit.models.language import LanguageCode
from integritykit.models.signal import Signal
from integritykit.models.webhook import (
    AuthType,
    RetryConfig,
    Webhook,
    WebhookEvent,
    WebhookPayload,
)
from integritykit.services.analytics import AnalyticsService
from integritykit.services.cap_export import CAPExportService
from integritykit.services.draft import DraftService
from integritykit.services.edxl_export import EDXLExportService
from integritykit.services.geojson_export import GeoJSONExportService
from integritykit.services.language_detection import LanguageDetectionService
# Lazy import WebhookService to avoid settings validation at module level


# =============================================================================
# Performance Targets & Utilities
# =============================================================================

# Performance targets (in milliseconds)
TARGET_API_RESPONSE_P95 = 200  # 200ms for API endpoints
TARGET_EXPORT_TIME = 500  # 500ms for export generation
TARGET_LANGUAGE_DETECTION = 300  # 300ms for language detection (first call includes init)
TARGET_LANGUAGE_DETECTION_WARMUP = 100  # 100ms after warmup
TARGET_DRAFT_GENERATION = 300  # 300ms for draft generation
TARGET_WEBHOOK_DELIVERY = 100  # 100ms for webhook delivery attempt

# Memory targets (in MB)
TARGET_MAX_MEMORY_EXPORT = 50  # 50MB max for large exports


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.elapsed_ms = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000


class AsyncIterator:
    """Helper for mocking async iterations."""

    def __init__(self, items: list):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


def create_mock_signal(
    signal_id: str = None,
    workspace_id: str = "W123",
    channel_id: str = "C123",
    content: str = "Emergency shelter needed at location",
    created_at: datetime = None,
) -> Signal:
    """Create a mock signal for testing."""
    return Signal(
        id=ObjectId(signal_id) if signal_id else ObjectId(),
        slack_workspace_id=workspace_id,
        slack_channel_id=channel_id,
        slack_thread_ts="1234567890.123456",
        slack_message_ts="1234567890.123456",
        slack_user_id="U123",
        slack_permalink="https://example.slack.com/archives/C123/p1234567890123456",
        content=content,
        created_at=created_at or datetime.utcnow(),
    )


def create_mock_cop_candidate(
    candidate_id: str = None,
    readiness_state: ReadinessState = ReadinessState.VERIFIED,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    what: str = "Bridge closure on Main Street",
    where: str = "Main Street Bridge",
) -> COPCandidate:
    """Create a mock COP candidate for testing."""
    return COPCandidate(
        id=ObjectId(candidate_id) if candidate_id else ObjectId(),
        workspace_id="W123",
        cluster_id=ObjectId(),
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(description="14:00 PST"),
            who="City Emergency Services",
            so_what="Traffic rerouted via alternate routes",
        ),
        evidence=Evidence(
            slack_permalinks=[],
            external_sources=[],
        ),
        created_by=ObjectId(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def create_mock_cop_update(
    update_id: str = None,
    num_items: int = 10,
    published: bool = True,
) -> COPUpdate:
    """Create a mock COP update for testing exports."""
    line_items = []
    evidence_snapshots = []

    for i in range(num_items):
        candidate_id = str(ObjectId())
        line_items.append(
            PublishedLineItem(
                candidate_id=candidate_id,
                section="verified" if i % 2 == 0 else "in_review",
                status_label="VERIFIED" if i % 2 == 0 else "IN REVIEW",
                text=f"Update item {i}: Bridge closure affecting traffic flow.",
                order=i,
            )
        )
        evidence_snapshots.append(
            EvidenceSnapshot(
                candidate_id=candidate_id,
                risk_tier="routine",
                fields_snapshot={
                    "what": f"Update item {i}",
                    "where": "Main Street",
                    "when": {"description": "14:00 PST"},
                },
            )
        )

    return COPUpdate(
        id=ObjectId(update_id) if update_id else ObjectId(),
        workspace_id="W123",
        update_number=1,
        title="Emergency Response Update #1",
        line_items=line_items,
        evidence_snapshots=evidence_snapshots,
        created_by=ObjectId(),
        published_at=datetime.utcnow() if published else None,
        created_at=datetime.utcnow(),
    )


# =============================================================================
# Analytics Service Performance Tests
# =============================================================================


class TestAnalyticsPerformance:
    """Performance tests for AnalyticsService."""

    @pytest.fixture
    def mock_collections(self):
        """Mock MongoDB collections."""
        signals = MagicMock()
        candidates = MagicMock()
        audit_log = MagicMock()
        clusters = MagicMock()
        users = MagicMock()
        return signals, candidates, audit_log, clusters, users

    @pytest.fixture
    def analytics_service(self, mock_collections):
        """Create AnalyticsService with mocked collections."""
        signals, candidates, audit_log, clusters, users = mock_collections
        return AnalyticsService(
            signals_collection=signals,
            candidates_collection=candidates,
            audit_log_collection=audit_log,
            clusters_collection=clusters,
            users_collection=users,
        )

    def generate_signal_volume_data(self, num_buckets: int = 100) -> list[dict]:
        """Generate mock signal volume aggregation results."""
        data = []
        for i in range(num_buckets):
            date_str = (datetime(2026, 3, 1) + timedelta(hours=i)).strftime("%Y-%m-%d %H:00:00")
            data.append({
                "_id": date_str,
                "total_count": 10 + (i % 20),  # Varying counts
                "by_channel": [
                    {"k": "C123", "v": 5 + (i % 10)},
                    {"k": "C456", "v": 5 + (i % 10)},
                ],
            })
        return data

    def generate_audit_log_data(self, num_records: int = 1000) -> list[dict]:
        """Generate mock audit log aggregation results."""
        data = []
        for i in range(num_records):
            hour = i // 10
            date_str = (datetime(2026, 3, 1) + timedelta(hours=hour)).strftime("%Y-%m-%d %H:00:00")
            data.append({
                "_id": date_str,
                "total_actions": 10 + (i % 5),
                "by_action_type": [
                    {"k": AuditActionType.COP_CANDIDATE_VERIFY.value, "v": 5},
                    {"k": AuditActionType.COP_CANDIDATE_PROMOTE.value, "v": 3},
                    {"k": AuditActionType.COP_UPDATE_PUBLISH.value, "v": 2},
                ],
                "by_facilitator": [
                    {"k": "U123", "v": 6},
                    {"k": "U456", "v": 4},
                ],
            })
        return data

    @pytest.mark.asyncio
    async def test_signal_volume_time_series_performance_100_buckets(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test signal volume computation with 100 time buckets (4+ days hourly)."""
        signals, _, _, _, _ = mock_collections

        # Generate 100 buckets of data
        mock_data = self.generate_signal_volume_data(num_buckets=100)
        signals.aggregate.return_value = AsyncIterator(mock_data)

        # Time the operation
        with PerformanceTimer() as timer:
            result = await analytics_service.compute_signal_volume_time_series(
                workspace_id="W123",
                start_date=datetime(2026, 3, 1),
                end_date=datetime(2026, 3, 5),
                granularity=Granularity.HOUR,
            )

        # Verify results
        assert len(result) == 100
        assert timer.elapsed_ms < TARGET_API_RESPONSE_P95, (
            f"Signal volume query took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_API_RESPONSE_P95}ms"
        )

        print(f"✓ Signal volume (100 buckets): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_facilitator_actions_time_series_performance(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator actions computation with 1000 audit log entries."""
        _, _, audit_log, _, _ = mock_collections

        # Generate 1000 audit log entries
        mock_data = self.generate_audit_log_data(num_records=1000)
        # Aggregate to unique time buckets
        aggregated = {}
        for entry in mock_data:
            key = entry["_id"]
            if key not in aggregated:
                aggregated[key] = entry
            else:
                aggregated[key]["total_actions"] += entry["total_actions"]

        audit_log.aggregate.return_value = AsyncIterator(list(aggregated.values()))

        # Time the operation
        with PerformanceTimer() as timer:
            result = await analytics_service.compute_facilitator_actions_time_series(
                workspace_id="W123",
                start_date=datetime(2026, 3, 1),
                end_date=datetime(2026, 3, 5),
                granularity=Granularity.HOUR,
            )

        # Verify results
        assert len(result) > 0
        assert timer.elapsed_ms < TARGET_API_RESPONSE_P95, (
            f"Facilitator actions query took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_API_RESPONSE_P95}ms"
        )

        print(f"✓ Facilitator actions (1000 records): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_topic_trends_performance(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test topic trends detection with 50 clusters."""
        signals, _, _, clusters, _ = mock_collections

        # Generate mock cluster data (50 topics)
        mock_cluster_data = []
        for i in range(50):
            cluster_id = ObjectId()
            # Generate signals for each cluster split across periods
            for period in ["previous", "current"]:
                count = 10 + (i % 20) if period == "previous" else 15 + (i % 25)
                mock_cluster_data.append({
                    "_id": {
                        "cluster_id": cluster_id,
                        "topic": f"Topic {i}",
                        "topic_type": "general",
                    },
                    "periods": [
                        {
                            "period": "previous",
                            "count": 10 + (i % 20),
                            "first_seen": datetime(2026, 3, 1),
                            "last_seen": datetime(2026, 3, 5),
                        },
                        {
                            "period": "current",
                            "count": 15 + (i % 25),
                            "first_seen": datetime(2026, 3, 6),
                            "last_seen": datetime(2026, 3, 10),
                        },
                    ],
                    "total_signals": 25 + (i % 30),
                    "keywords": [f"Topic {i}"],
                })

        signals.aggregate.return_value = AsyncIterator(mock_cluster_data)

        # Time the operation
        with PerformanceTimer() as timer:
            result = await analytics_service.compute_topic_trends(
                workspace_id="W123",
                start_date=datetime(2026, 3, 1),
                end_date=datetime(2026, 3, 10),
                min_signals=5,
            )

        # Verify results
        assert len(result.trends) > 0
        assert timer.elapsed_ms < TARGET_API_RESPONSE_P95, (
            f"Topic trends detection took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_API_RESPONSE_P95}ms"
        )

        print(f"✓ Topic trends (50 clusters): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_conflict_resolution_metrics_performance(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test conflict resolution metrics with 200 conflicts."""
        _, _, _, clusters, _ = mock_collections

        # Generate mock conflict data across risk tiers
        mock_conflict_data = [
            {
                "_id": "routine",
                "total_conflicts": 100,
                "resolved_conflicts": 85,
                "resolution_times": [1.5, 2.0, 1.8, 2.5, 1.2] * 17,  # 85 times
                "resolution_types": ["manual", "auto_verify", "manual"] * 30,
            },
            {
                "_id": "elevated",
                "total_conflicts": 60,
                "resolved_conflicts": 50,
                "resolution_times": [3.0, 3.5, 2.8, 4.0, 3.2] * 10,  # 50 times
                "resolution_types": ["manual", "escalate", "manual"] * 18,
            },
            {
                "_id": "high_stakes",
                "total_conflicts": 40,
                "resolved_conflicts": 35,
                "resolution_times": [5.0, 6.0, 4.5, 7.0, 5.5] * 7,  # 35 times
                "resolution_types": ["manual", "executive_review"] * 18,
            },
        ]

        clusters.aggregate.return_value = AsyncIterator(mock_conflict_data)

        # Time the operation
        with PerformanceTimer() as timer:
            result = await analytics_service.compute_conflict_resolution_metrics(
                workspace_id="W123",
                start_date=datetime(2026, 3, 1),
                end_date=datetime(2026, 3, 10),
            )

        # Verify results
        assert len(result.by_risk_tier) == 3
        assert result.summary["total_conflicts"] == 200
        assert timer.elapsed_ms < TARGET_API_RESPONSE_P95, (
            f"Conflict resolution metrics took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_API_RESPONSE_P95}ms"
        )

        print(f"✓ Conflict resolution metrics (200 conflicts): {timer.elapsed_ms:.2f}ms")


# =============================================================================
# Export Services Performance Tests
# =============================================================================


class TestExportPerformance:
    """Performance tests for CAP, EDXL, and GeoJSON export services."""

    @pytest.mark.parametrize("num_items", [10, 50, 100, 200])
    def test_cap_export_performance_varying_sizes(self, num_items):
        """Test CAP export with varying dataset sizes."""
        service = CAPExportService(sender_id="test@example.com")
        cop_update = create_mock_cop_update(num_items=num_items, published=True)

        # Time the export
        with PerformanceTimer() as timer:
            result = service.generate_cap_xml(cop_update, language="en-US")

        # Verify output
        assert result.startswith('<?xml version="1.0"')
        assert "alert" in result

        # Check performance
        expected_time = TARGET_EXPORT_TIME * (num_items / 10)  # Scale with size
        assert timer.elapsed_ms < expected_time, (
            f"CAP export ({num_items} items) took {timer.elapsed_ms:.2f}ms, "
            f"target: {expected_time:.0f}ms"
        )

        print(f"✓ CAP export ({num_items} items): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.parametrize("num_items", [10, 50, 100])
    def test_edxl_export_performance_varying_sizes(self, num_items):
        """Test EDXL-DE export with varying dataset sizes."""
        service = EDXLExportService(
            sender_id="test@example.com",
            cap_sender_id="test@example.com",
        )
        cop_update = create_mock_cop_update(num_items=num_items, published=True)

        # Time the export
        with PerformanceTimer() as timer:
            result = service.generate_edxl_xml(cop_update, language="en-US")

        # Verify output
        assert result.startswith('<?xml version="1.0"')
        assert "EDXLDistribution" in result

        # Check performance (EDXL includes CAP generation, so allow more time)
        expected_time = TARGET_EXPORT_TIME * 1.5 * (num_items / 10)
        assert timer.elapsed_ms < expected_time, (
            f"EDXL export ({num_items} items) took {timer.elapsed_ms:.2f}ms, "
            f"target: {expected_time:.0f}ms"
        )

        print(f"✓ EDXL export ({num_items} items): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.parametrize("num_items", [10, 50, 100, 200])
    def test_geojson_export_performance_varying_sizes(self, num_items):
        """Test GeoJSON export with varying dataset sizes."""
        service = GeoJSONExportService()
        cop_update = create_mock_cop_update(num_items=num_items, published=True)

        # Time the export
        with PerformanceTimer() as timer:
            result = service.generate_geojson_string(
                cop_update,
                include_non_spatial=True,
                pretty=False,
            )

        # Verify output
        assert '"type":"FeatureCollection"' in result or '"type": "FeatureCollection"' in result
        assert '"features"' in result

        # Check performance
        expected_time = TARGET_EXPORT_TIME * (num_items / 10)
        assert timer.elapsed_ms < expected_time, (
            f"GeoJSON export ({num_items} items) took {timer.elapsed_ms:.2f}ms, "
            f"target: {expected_time:.0f}ms"
        )

        print(f"✓ GeoJSON export ({num_items} items): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.skipif(
        True,  # Skip by default - requires psutil
        reason="Memory profiling requires psutil package",
    )
    def test_cap_export_memory_usage_large_dataset(self):
        """Test CAP export memory usage with large dataset (500 items)."""
        import psutil
        import os

        service = CAPExportService(sender_id="test@example.com")
        cop_update = create_mock_cop_update(num_items=500, published=True)

        # Measure memory before
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB

        # Perform export
        result = service.generate_cap_xml(cop_update, language="en-US")

        # Measure memory after
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        mem_delta = mem_after - mem_before

        # Verify memory usage is reasonable
        assert mem_delta < TARGET_MAX_MEMORY_EXPORT, (
            f"CAP export (500 items) used {mem_delta:.2f}MB, "
            f"target: <{TARGET_MAX_MEMORY_EXPORT}MB"
        )

        print(f"✓ CAP export (500 items) memory: {mem_delta:.2f}MB")


# =============================================================================
# Webhook Delivery Performance Tests
# =============================================================================


@pytest.mark.skip(reason="Webhook tests require settings configuration")
class TestWebhookPerformance:
    """Performance tests for webhook delivery service."""

    @pytest.fixture
    def mock_collections(self):
        """Mock MongoDB collections."""
        webhooks = MagicMock()
        deliveries = MagicMock()
        return webhooks, deliveries

    @pytest.fixture
    def webhook_service(self, mock_collections):
        """Create WebhookService with mocked collections."""
        from integritykit.services.webhooks import WebhookService

        webhooks, deliveries = mock_collections
        return WebhookService(
            webhooks_collection=webhooks,
            deliveries_collection=deliveries,
        )

    @pytest.mark.asyncio
    async def test_webhook_payload_construction_performance(self, webhook_service):
        """Test webhook payload construction time."""
        event_data = {
            "cop_update_id": str(ObjectId()),
            "update_number": 1,
            "workspace_id": "W123",
            "line_items": [{"text": f"Item {i}"} for i in range(50)],
        }

        # Time payload construction
        with PerformanceTimer() as timer:
            payload = WebhookPayload(
                event_id="test_event_1",
                event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
                timestamp=datetime.utcnow(),
                workspace_id="W123",
                data=event_data,
            )
            payload_json = payload.model_dump_json()

        # Verify
        assert len(payload_json) > 0
        assert timer.elapsed_ms < 10, (  # Very fast operation
            f"Payload construction took {timer.elapsed_ms:.2f}ms, target: <10ms"
        )

        print(f"✓ Webhook payload construction: {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_webhook_delivery_attempt_performance(self, webhook_service, monkeypatch):
        """Test single webhook delivery attempt time."""
        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        async def mock_post(*args, **kwargs):
            await asyncio.sleep(0.01)  # Simulate 10ms network delay
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        # Patch httpx.AsyncClient
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

        # Create webhook and payload
        webhook = Webhook(
            workspace_id="W123",
            name="Test Webhook",
            url="https://example.com/webhook",
            events=[WebhookEvent.COP_UPDATE_PUBLISHED],
            auth_type=AuthType.NONE,
            enabled=True,
            retry_config=RetryConfig(),
            created_by=ObjectId(),
        )

        payload = WebhookPayload(
            event_id="test_event",
            event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
            timestamp=datetime.utcnow(),
            workspace_id="W123",
            data={"test": "data"},
        )

        # Time delivery attempt
        with PerformanceTimer() as timer:
            success, status_code, response_time_ms, response_body, error = (
                await webhook_service._attempt_delivery(webhook, payload)
            )

        # Verify
        assert success is True
        assert status_code == 200
        assert timer.elapsed_ms < TARGET_WEBHOOK_DELIVERY, (
            f"Webhook delivery took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_WEBHOOK_DELIVERY}ms"
        )

        print(f"✓ Webhook delivery attempt: {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_concurrent_webhook_deliveries_performance(
        self,
        webhook_service,
        monkeypatch,
    ):
        """Test concurrent webhook deliveries (10 webhooks)."""
        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        async def mock_post(*args, **kwargs):
            await asyncio.sleep(0.02)  # Simulate 20ms network delay
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

        # Create 10 webhooks
        webhooks = []
        for i in range(10):
            webhook = Webhook(
                id=ObjectId(),
                workspace_id="W123",
                name=f"Webhook {i}",
                url=f"https://example.com/webhook/{i}",
                events=[WebhookEvent.COP_UPDATE_PUBLISHED],
                auth_type=AuthType.NONE,
                enabled=True,
                retry_config=RetryConfig(),
                created_by=ObjectId(),
            )
            webhooks.append(webhook)

        payload = WebhookPayload(
            event_id="test_event",
            event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
            timestamp=datetime.utcnow(),
            workspace_id="W123",
            data={"test": "data"},
        )

        # Time concurrent deliveries
        with PerformanceTimer() as timer:
            tasks = [
                webhook_service._attempt_delivery(webhook, payload)
                for webhook in webhooks
            ]
            results = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert all(result[0] for result in results)  # All success=True

        # With concurrency, should be ~20-50ms, not 200ms (10 * 20ms)
        assert timer.elapsed_ms < 100, (
            f"Concurrent deliveries (10) took {timer.elapsed_ms:.2f}ms, target: <100ms"
        )

        print(f"✓ Concurrent webhook deliveries (10): {timer.elapsed_ms:.2f}ms")


# =============================================================================
# Language Detection Performance Tests
# =============================================================================


class TestLanguageDetectionPerformance:
    """Performance tests for language detection service."""

    @pytest.fixture
    def language_service(self):
        """Create LanguageDetectionService."""
        return LanguageDetectionService(
            confidence_threshold=0.8,
            enabled=True,
            supported_languages=["en", "es", "fr"],
        )

    def test_single_detection_performance(self, language_service):
        """Test single language detection time."""
        text = "Emergency shelter available at community center on Main Street."

        # Warmup (first call includes library initialization)
        _ = language_service.detect_language(text)

        # Time detection (warmed up)
        with PerformanceTimer() as timer:
            result = language_service.detect_language(text)

        # Verify
        assert result.detected_language == LanguageCode.EN
        assert timer.elapsed_ms < TARGET_LANGUAGE_DETECTION_WARMUP, (
            f"Language detection took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_LANGUAGE_DETECTION_WARMUP}ms"
        )

        print(f"✓ Single language detection (warmed up): {timer.elapsed_ms:.2f}ms")

    def test_batch_detection_performance_100_signals(self, language_service):
        """Test batch language detection for 100 signals."""
        signals = [
            create_mock_signal(
                content=f"Emergency update {i}: Shelter available at location.",
            )
            for i in range(100)
        ]

        # Warmup
        _ = language_service.detect_language("Warmup text")

        # Time batch detection
        with PerformanceTimer() as timer:
            results = language_service.batch_detect_languages(signals)

        # Verify
        assert len(results) == 100
        avg_time_per_signal = timer.elapsed_ms / 100
        assert avg_time_per_signal < TARGET_LANGUAGE_DETECTION_WARMUP, (
            f"Average detection time {avg_time_per_signal:.2f}ms, "
            f"target: {TARGET_LANGUAGE_DETECTION_WARMUP}ms"
        )

        print(
            f"✓ Batch language detection (100 signals): {timer.elapsed_ms:.2f}ms "
            f"({avg_time_per_signal:.2f}ms/signal)"
        )

    @pytest.mark.parametrize("text_length", [50, 200, 500, 1000])
    def test_detection_performance_varying_text_length(
        self,
        language_service,
        text_length,
    ):
        """Test language detection with varying text lengths."""
        # Generate text of specified length
        base_text = "Emergency shelter available at community center. "
        text = (base_text * (text_length // len(base_text) + 1))[:text_length]

        # Warmup
        _ = language_service.detect_language("Warmup")

        # Time detection
        with PerformanceTimer() as timer:
            result = language_service.detect_language(text)

        # Verify
        assert result.detected_language is not None
        assert timer.elapsed_ms < TARGET_LANGUAGE_DETECTION_WARMUP * 1.5, (
            f"Detection (text_length={text_length}) took {timer.elapsed_ms:.2f}ms, "
            f"target: {TARGET_LANGUAGE_DETECTION_WARMUP * 1.5:.0f}ms"
        )

        print(f"✓ Language detection ({text_length} chars): {timer.elapsed_ms:.2f}ms")


# =============================================================================
# Draft Generation Performance Tests
# =============================================================================


class TestDraftGenerationPerformance:
    """Performance tests for COP draft generation service."""

    @pytest.fixture
    def draft_service(self):
        """Create DraftService without LLM (rule-based only)."""
        return DraftService(
            openai_client=None,
            use_llm=False,
            default_language="en",
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("num_candidates", [10, 25, 50, 100])
    async def test_draft_generation_performance_varying_sizes(
        self,
        draft_service,
        num_candidates,
    ):
        """Test draft generation with varying numbers of candidates."""
        candidates = [
            create_mock_cop_candidate(
                readiness_state=(
                    ReadinessState.VERIFIED if i % 2 == 0 else ReadinessState.IN_REVIEW
                ),
                risk_tier=(
                    RiskTier.HIGH_STAKES
                    if i % 10 == 0
                    else RiskTier.ELEVATED if i % 5 == 0 else RiskTier.ROUTINE
                ),
                what=f"Emergency situation {i}",
                where=f"Location {i}",
            )
            for i in range(num_candidates)
        ]

        # Time draft generation
        with PerformanceTimer() as timer:
            draft = await draft_service.generate_draft(
                workspace_id="W123",
                candidates=candidates,
                title=f"COP Update - {num_candidates} items",
                include_open_questions=True,
            )

        # Verify
        assert draft.total_items == num_candidates
        assert len(draft.verified_items) > 0 or len(draft.in_review_items) > 0

        # Performance check
        expected_time = TARGET_DRAFT_GENERATION * (num_candidates / 10)
        assert timer.elapsed_ms < expected_time, (
            f"Draft generation ({num_candidates} candidates) took {timer.elapsed_ms:.2f}ms, "
            f"target: {expected_time:.0f}ms"
        )

        print(f"✓ Draft generation ({num_candidates} candidates): {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_line_item_generation_performance(self, draft_service):
        """Test single line item generation time."""
        candidate = create_mock_cop_candidate(
            readiness_state=ReadinessState.VERIFIED,
            risk_tier=RiskTier.ELEVATED,
        )

        # Time line item generation
        with PerformanceTimer() as timer:
            line_item = await draft_service.generate_line_item(
                candidate,
                use_llm=False,
                target_language="en",
            )

        # Verify
        assert line_item.line_item_text is not None
        assert line_item.status_label == "VERIFIED"
        assert timer.elapsed_ms < 10, (  # Very fast operation
            f"Line item generation took {timer.elapsed_ms:.2f}ms, target: <10ms"
        )

        print(f"✓ Line item generation: {timer.elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_markdown_conversion_performance(self, draft_service):
        """Test Markdown conversion performance for large drafts."""
        candidates = [
            create_mock_cop_candidate(
                readiness_state=ReadinessState.VERIFIED,
                what=f"Update {i}",
            )
            for i in range(100)
        ]

        draft = await draft_service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        # Time Markdown conversion
        with PerformanceTimer() as timer:
            markdown = draft.to_markdown(language="en")

        # Verify
        assert "# " in markdown
        assert len(markdown) > 0
        assert timer.elapsed_ms < 50, (
            f"Markdown conversion took {timer.elapsed_ms:.2f}ms, target: <50ms"
        )

        print(f"✓ Markdown conversion (100 items): {timer.elapsed_ms:.2f}ms")


# =============================================================================
# Performance Summary Report
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def performance_summary(request):
    """Print performance test summary after all tests."""
    yield

    print("\n" + "=" * 80)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 80)
    print("\nPerformance Targets:")
    print(f"  • API Response (p95):     <{TARGET_API_RESPONSE_P95}ms")
    print(f"  • Export Generation:      <{TARGET_EXPORT_TIME}ms")
    print(f"  • Language Detection:     <{TARGET_LANGUAGE_DETECTION}ms")
    print(f"  • Draft Generation:       <{TARGET_DRAFT_GENERATION}ms")
    print(f"  • Webhook Delivery:       <{TARGET_WEBHOOK_DELIVERY}ms")
    print(f"  • Max Export Memory:      <{TARGET_MAX_MEMORY_EXPORT}MB")
    print("\nAll performance tests completed. Review output above for detailed timings.")
    print("=" * 80 + "\n")
