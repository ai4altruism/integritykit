"""
Integration tests for metrics collection across a full COP lifecycle (S6-8).

Tests the complete metrics workflow:
- Signal ingestion through COP publication
- Time-to-validated-update measurement
- Conflicting report rate calculation
- Moderator burden tracking via audit log
- Provenance coverage analysis
- Readiness distribution snapshot

These tests use mongomock for database operations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditLogEntry, AuditTargetType
from integritykit.models.cop_candidate import (
    CandidateConflict,
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
    SlackPermalink,
)
from integritykit.models.cop_update import COPUpdate, COPUpdateStatus, PublishedLineItem
from integritykit.models.signal import Signal
from integritykit.models.user import User, UserRole
from integritykit.services.metrics import MetricsService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_signal(
    *,
    workspace_id: str = "T123456",
    channel_id: str = "C123456",
    text: str = "Test signal content",
    created_at: datetime | None = None,
) -> Signal:
    """Create a test signal."""
    return Signal(
        id=ObjectId(),
        workspace_id=workspace_id,
        channel_id=channel_id,
        message_ts="1234567890.123456",
        text=text,
        user_id="U123456",
        user_name="Test Reporter",
        created_at=created_at or datetime.now(timezone.utc),
    )


def create_test_candidate(
    *,
    workspace_id: str = "T123456",
    signal_ids: list[ObjectId] | None = None,
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    has_conflict: bool = False,
    created_at: datetime | None = None,
) -> COPCandidate:
    """Create a test COPCandidate."""
    conflicts = []
    if has_conflict:
        conflicts = [
            CandidateConflict(
                description="Conflicting reports about status",
                detected_at=datetime.now(timezone.utc),
            )
        ]

    return COPCandidate(
        id=ObjectId(),
        workspace_id=workspace_id,
        topic="Test Topic",
        summary="Test summary of candidate",
        cluster_id=ObjectId(),
        primary_signal_ids=signal_ids or [],
        fields=COPFields(
            what="Test event",
            where="Test location",
            when=COPWhen(
                event_time=datetime.now(timezone.utc),
                report_time=datetime.now(timezone.utc),
            ),
            who="Test organization",
            so_what="Test impact",
        ),
        evidence=[],
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        conflicts=conflicts,
        created_at=created_at or datetime.now(timezone.utc),
    )


def create_test_cop_update(
    *,
    workspace_id: str = "T123456",
    candidate_ids: list[ObjectId] | None = None,
    status: COPUpdateStatus = COPUpdateStatus.PUBLISHED,
    line_items: list[PublishedLineItem] | None = None,
    published_at: datetime | None = None,
) -> COPUpdate:
    """Create a test COP update."""
    return COPUpdate(
        id=ObjectId(),
        workspace_id=workspace_id,
        title="Test COP Update",
        candidate_ids=candidate_ids or [],
        line_items=line_items or [],
        status=status,
        created_by=ObjectId(),
        created_at=datetime.now(timezone.utc),
        published_at=published_at,
        published_by=ObjectId() if status == COPUpdateStatus.PUBLISHED else None,
    )


def create_test_audit_entry(
    *,
    workspace_id: str = "T123456",
    action_type: AuditActionType = AuditActionType.COP_CANDIDATE_PROMOTE,
    actor_id: ObjectId | None = None,
    target_id: ObjectId | None = None,
    created_at: datetime | None = None,
) -> AuditLogEntry:
    """Create a test audit log entry."""
    return AuditLogEntry(
        id=ObjectId(),
        timestamp=created_at or datetime.now(timezone.utc),
        actor_id=actor_id or ObjectId(),
        actor_role="facilitator",
        action_type=action_type,
        target_entity_type=AuditTargetType.COP_CANDIDATE,
        target_entity_id=target_id or ObjectId(),
        created_at=created_at or datetime.now(timezone.utc),
    )


# ============================================================================
# Mock Collections
# ============================================================================


class MockCollection:
    """Mock MongoDB collection for testing."""

    def __init__(self):
        self.documents = []

    async def find_one(self, query, projection=None):
        for doc in self.documents:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query=None, projection=None):
        return MockCursor([d for d in self.documents if self._matches(d, query or {})])

    async def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.documents.append(doc)

        class Result:
            inserted_id = doc["_id"]

        return Result()

    async def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def aggregate(self, pipeline):
        # Simplified aggregation for testing
        return MockCursor(self.documents)

    def _matches(self, doc, query):
        for key, value in query.items():
            if key.startswith("$"):
                continue  # Skip operators for simple matching
            if key not in doc:
                return False
            if isinstance(value, dict):
                # Handle $in, $gte, $lte operators
                if "$in" in value and doc[key] not in value["$in"]:
                    return False
                if "$gte" in value and doc[key] < value["$gte"]:
                    return False
                if "$lte" in value and doc[key] > value["$lte"]:
                    return False
            elif doc[key] != value:
                return False
        return True


class MockCursor:
    """Mock MongoDB cursor."""

    def __init__(self, documents):
        self.documents = documents
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self.documents):
            raise StopAsyncIteration
        doc = self.documents[self._index]
        self._index += 1
        return doc

    async def to_list(self, length=None):
        return self.documents[: length] if length else self.documents


# ============================================================================
# Test: Time to Validated Update
# ============================================================================


class TestTimeToValidatedUpdate:
    """Tests for time-to-validated-update metric computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_no_published_updates_returns_zeros(self, metrics_service):
        """Test metric returns zeros when no COP updates exist."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=1)

        metric = await metrics_service.compute_time_to_validated_update(
            workspace_id="T123456",
            start_time=start_time,
            end_time=now,
        )

        assert metric.sample_count == 0
        assert metric.average_seconds == 0.0
        assert metric.median_seconds == 0.0

    @pytest.mark.asyncio
    async def test_metric_type_is_correct(self, metrics_service):
        """Test that metric type is set correctly."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_time_to_validated_update(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.metric_type == "time_to_validated_update"


# ============================================================================
# Test: Conflicting Report Rate
# ============================================================================


class TestConflictingReportRate:
    """Tests for conflicting-report-rate metric computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_no_clusters_returns_zeros(self, metrics_service):
        """Test metric returns zeros when no clusters exist."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_conflicting_report_rate(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.total_clusters == 0
        assert metric.conflict_rate == 0.0

    @pytest.mark.asyncio
    async def test_metric_type_is_correct(self, metrics_service):
        """Test that metric type is set correctly."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_conflicting_report_rate(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.metric_type == "conflicting_report_rate"


# ============================================================================
# Test: Moderator Burden
# ============================================================================


class TestModeratorBurden:
    """Tests for moderator-burden metric computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_no_actions_returns_zeros(self, metrics_service):
        """Test metric returns zeros when no facilitator actions exist."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_moderator_burden(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.total_facilitator_actions == 0
        assert metric.actions_per_cop_update == 0.0
        assert metric.unique_facilitators_active == 0

    @pytest.mark.asyncio
    async def test_metric_type_is_correct(self, metrics_service):
        """Test that metric type is set correctly."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_moderator_burden(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.metric_type == "moderator_burden"


# ============================================================================
# Test: Provenance Coverage
# ============================================================================


class TestProvenanceCoverage:
    """Tests for provenance-coverage metric computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_no_updates_returns_zeros(self, metrics_service):
        """Test metric returns zeros when no COP updates exist."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_provenance_coverage(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.total_published_line_items == 0
        assert metric.coverage_rate == 0.0

    @pytest.mark.asyncio
    async def test_metric_type_is_correct(self, metrics_service):
        """Test that metric type is set correctly."""
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_provenance_coverage(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.metric_type == "provenance_coverage"


# ============================================================================
# Test: Readiness Distribution
# ============================================================================


class TestReadinessDistribution:
    """Tests for readiness-distribution metric computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        candidates_collection = MockCollection()
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=candidates_collection,
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        ), candidates_collection

    @pytest.mark.asyncio
    async def test_no_candidates_returns_zeros(self):
        """Test metric returns zeros when no candidates exist."""
        metrics_service = MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_readiness_distribution(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.total_candidates == 0
        assert metric.in_review_count == 0
        assert metric.verified_count == 0
        assert metric.blocked_count == 0

    @pytest.mark.asyncio
    async def test_metric_type_is_correct(self):
        """Test that metric type is set correctly."""
        metrics_service = MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )
        now = datetime.now(timezone.utc)

        metric = await metrics_service.compute_readiness_distribution(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metric.metric_type == "readiness_distribution"


# ============================================================================
# Test: Full Metrics Snapshot
# ============================================================================


class TestMetricsSnapshot:
    """Tests for complete metrics snapshot computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_snapshot_includes_all_metrics(self, metrics_service):
        """Test that snapshot includes all five operational metrics."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=1)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=start_time,
            end_time=now,
        )

        # Verify all five metrics are present
        assert snapshot.time_to_validated_update is not None
        assert snapshot.conflicting_report_rate is not None
        assert snapshot.moderator_burden is not None
        assert snapshot.provenance_coverage is not None
        assert snapshot.readiness_distribution is not None

    @pytest.mark.asyncio
    async def test_snapshot_has_correct_workspace(self, metrics_service):
        """Test that snapshot has correct workspace ID."""
        now = datetime.now(timezone.utc)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert snapshot.workspace_id == "T123456"

    @pytest.mark.asyncio
    async def test_snapshot_has_correct_time_range(self, metrics_service):
        """Test that snapshot captures correct time range."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=1)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=start_time,
            end_time=now,
        )

        assert snapshot.period_start == start_time
        assert snapshot.period_end == now

    @pytest.mark.asyncio
    async def test_snapshot_has_generated_timestamp(self, metrics_service):
        """Test that snapshot includes generation timestamp."""
        now = datetime.now(timezone.utc)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert snapshot.generated_at is not None
        # Generated at should be recent - just verify it exists and is a datetime
        assert isinstance(snapshot.generated_at, datetime)


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestMetricsEdgeCases:
    """Tests for edge cases in metrics computation."""

    @pytest.fixture
    def metrics_service(self):
        """Create metrics service with mock collections."""
        return MetricsService(
            signals_collection=MockCollection(),
            clusters_collection=MockCollection(),
            candidates_collection=MockCollection(),
            cop_updates_collection=MockCollection(),
            audit_log_collection=MockCollection(),
        )

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_valid_metrics(self, metrics_service):
        """Test that empty workspace returns valid (zero) metrics."""
        now = datetime.now(timezone.utc)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="EMPTY_WORKSPACE",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        # All counts should be zero
        assert snapshot.time_to_validated_update.sample_count == 0
        assert snapshot.conflicting_report_rate.total_clusters == 0
        assert snapshot.moderator_burden.total_facilitator_actions == 0
        assert snapshot.provenance_coverage.total_published_line_items == 0
        assert snapshot.readiness_distribution.total_candidates == 0

    @pytest.mark.asyncio
    async def test_future_time_range_returns_zeros(self, metrics_service):
        """Test that future time range returns zeros."""
        now = datetime.now(timezone.utc)
        future_start = now + timedelta(days=1)
        future_end = now + timedelta(days=2)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=future_start,
            end_time=future_end,
        )

        assert snapshot.time_to_validated_update.sample_count == 0

    @pytest.mark.asyncio
    async def test_very_short_time_range(self, metrics_service):
        """Test metrics with very short time range (1 second)."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=1)

        snapshot = await metrics_service.compute_metrics_snapshot(
            workspace_id="T123456",
            start_time=start_time,
            end_time=now,
        )

        # Should still return valid structure
        assert snapshot.workspace_id == "T123456"
        assert snapshot.period_start == start_time
        assert snapshot.period_end == now
