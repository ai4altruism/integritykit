"""Unit tests for time-series analytics service (S8-9).

Tests:
- Signal volume aggregation
- Readiness state transitions tracking
- Facilitator action velocity calculation
- MongoDB aggregation pipeline correctness
- Time bucketing for different granularities
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.analytics import (
    FacilitatorActionDataPoint,
    FacilitatorWorkload,
    Granularity,
    MetricType,
    ReadinessTransitionDataPoint,
    SignalVolumeDataPoint,
    TimeSeriesAnalyticsRequest,
    TopicTrend,
    TrendDirection,
)
from integritykit.services.analytics import AnalyticsService


class TestAnalyticsService:
    """Test suite for AnalyticsService."""

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
            max_time_range_days=90,
            retention_days=365,
        )

    def test_get_date_format_string_hour(self, analytics_service):
        """Test date format for hour granularity."""
        fmt = analytics_service._get_date_format_string(Granularity.HOUR)
        assert fmt == "%Y-%m-%d %H:00:00"

    def test_get_date_format_string_day(self, analytics_service):
        """Test date format for day granularity."""
        fmt = analytics_service._get_date_format_string(Granularity.DAY)
        assert fmt == "%Y-%m-%d"

    def test_get_date_format_string_week(self, analytics_service):
        """Test date format for week granularity."""
        fmt = analytics_service._get_date_format_string(Granularity.WEEK)
        assert fmt == "%Y-W%V"

    def test_parse_bucket_timestamp_hour(self, analytics_service):
        """Test parsing hour bucket timestamp."""
        bucket_str = "2026-03-10 14:00:00"
        result = analytics_service._parse_bucket_timestamp(bucket_str, Granularity.HOUR)
        assert result == datetime(2026, 3, 10, 14, 0, 0)

    def test_parse_bucket_timestamp_day(self, analytics_service):
        """Test parsing day bucket timestamp."""
        bucket_str = "2026-03-10"
        result = analytics_service._parse_bucket_timestamp(bucket_str, Granularity.DAY)
        assert result == datetime(2026, 3, 10, 0, 0, 0)

    def test_parse_bucket_timestamp_week(self, analytics_service):
        """Test parsing week bucket timestamp."""
        bucket_str = "2026-W11"
        result = analytics_service._parse_bucket_timestamp(bucket_str, Granularity.WEEK)
        # Should return Monday of week 11
        assert result.weekday() == 0  # Monday
        assert result.year == 2026

    @pytest.mark.asyncio
    async def test_compute_signal_volume_time_series_empty(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test signal volume computation with no data."""
        signals, _, _, _, _ = mock_collections

        # Mock empty aggregation result
        async def mock_aggregate(*args, **kwargs):
            return AsyncIterator([])

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator([])

        result = await analytics_service.compute_signal_volume_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            granularity=Granularity.DAY,
        )

        assert result == []
        signals.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_compute_signal_volume_time_series_with_data(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test signal volume computation with mock data."""
        signals, _, _, _, _ = mock_collections

        # Mock aggregation result
        mock_data = [
            {
                "_id": "2026-03-10",
                "total_count": 15,
                "by_channel": [
                    {"k": "C123", "v": 10},
                    {"k": "C456", "v": 5},
                ],
            },
            {
                "_id": "2026-03-11",
                "total_count": 8,
                "by_channel": [
                    {"k": "C123", "v": 8},
                ],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator(mock_data)

        result = await analytics_service.compute_signal_volume_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 11),
            granularity=Granularity.DAY,
        )

        assert len(result) == 2
        assert isinstance(result[0], SignalVolumeDataPoint)
        assert result[0].signal_count == 15
        assert result[0].by_channel == {"C123": 10, "C456": 5}
        assert result[1].signal_count == 8
        assert result[1].by_channel == {"C123": 8}

    @pytest.mark.asyncio
    async def test_compute_readiness_transitions_no_clusters(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test readiness transitions with no clusters."""
        _, _, _, clusters, _ = mock_collections

        class AsyncIterator:
            def __init__(self, items):
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

        clusters.find.return_value = AsyncIterator([])

        result = await analytics_service.compute_readiness_transitions_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            granularity=Granularity.DAY,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_compute_readiness_transitions_with_data(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test readiness transitions computation with mock data."""
        _, _, audit_log, clusters, _ = mock_collections

        # Mock clusters
        class AsyncIterator:
            def __init__(self, items):
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

        clusters.find.return_value = AsyncIterator([
            {"_id": ObjectId()},
            {"_id": ObjectId()},
        ])

        # Mock audit log aggregation
        mock_transitions = [
            {
                "_id": "2026-03-10",
                "total_transitions": 12,
                "transitions": [
                    {"k": "IN_REVIEW->VERIFIED", "v": 8},
                    {"k": "VERIFIED->BLOCKED", "v": 2},
                    {"k": "BLOCKED->IN_REVIEW", "v": 2},
                ],
            },
        ]

        audit_log.aggregate.return_value = AsyncIterator(mock_transitions)

        result = await analytics_service.compute_readiness_transitions_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 11),
            granularity=Granularity.DAY,
        )

        assert len(result) == 1
        assert isinstance(result[0], ReadinessTransitionDataPoint)
        assert result[0].total_transitions == 12
        assert result[0].transitions["IN_REVIEW->VERIFIED"] == 8
        assert result[0].transitions["VERIFIED->BLOCKED"] == 2

    @pytest.mark.asyncio
    async def test_compute_facilitator_actions_with_data(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator actions computation with mock data."""
        _, _, audit_log, _, _ = mock_collections

        # Mock audit log aggregation
        mock_actions = [
            {
                "_id": "2026-03-10",
                "total_actions": 24,
                "by_action_type": [
                    {"k": "cop_candidate.promote", "v": 10},
                    {"k": "cop_update.publish", "v": 8},
                    {"k": "cop_candidate.verify", "v": 6},
                ],
                "by_facilitator": [
                    {"k": "U123", "v": 15},
                    {"k": "U456", "v": 9},
                ],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        audit_log.aggregate.return_value = AsyncIterator(mock_actions)

        result = await analytics_service.compute_facilitator_actions_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 11),
            granularity=Granularity.DAY,
        )

        assert len(result) == 1
        assert isinstance(result[0], FacilitatorActionDataPoint)
        assert result[0].total_actions == 24
        assert result[0].by_action_type["cop_candidate.promote"] == 10
        assert result[0].by_facilitator["U123"] == 15
        # Day granularity: actions per hour = total / 24
        assert result[0].action_velocity == 24 / 24.0

    @pytest.mark.asyncio
    async def test_compute_facilitator_actions_hourly_velocity(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator action velocity calculation for hourly granularity."""
        _, _, audit_log, _, _ = mock_collections

        mock_actions = [
            {
                "_id": "2026-03-10 14:00:00",
                "total_actions": 10,
                "by_action_type": [],
                "by_facilitator": [],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        audit_log.aggregate.return_value = AsyncIterator(mock_actions)

        result = await analytics_service.compute_facilitator_actions_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10, 14),
            end_date=datetime(2026, 3, 10, 15),
            granularity=Granularity.HOUR,
        )

        assert len(result) == 1
        # Hour granularity: velocity = total actions (already per hour)
        assert result[0].action_velocity == 10.0

    @pytest.mark.asyncio
    async def test_compute_facilitator_actions_filter_by_facilitator(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test filtering facilitator actions by specific user."""
        _, _, audit_log, _, _ = mock_collections

        mock_actions = [
            {
                "_id": "2026-03-10",
                "total_actions": 15,
                "by_action_type": [],
                "by_facilitator": [{"k": "U123", "v": 15}],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        audit_log.aggregate.return_value = AsyncIterator(mock_actions)

        result = await analytics_service.compute_facilitator_actions_time_series(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 11),
            granularity=Granularity.DAY,
            facilitator_id="U123",
        )

        assert len(result) == 1
        assert result[0].total_actions == 15

        # Verify facilitator filter was passed to pipeline
        call_args = audit_log.aggregate.call_args
        pipeline = call_args[0][0]
        match_stage = pipeline[0]["$match"]
        assert match_stage["actor_id"] == "U123"

    @pytest.mark.asyncio
    async def test_compute_time_series_analytics_multiple_metrics(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test computing multiple metrics in single query."""
        signals, _, audit_log, clusters, _ = mock_collections

        # Setup mocks for all metric types
        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator([
            {
                "_id": "2026-03-10",
                "total_count": 10,
                "by_channel": [],
            }
        ])

        clusters.find.return_value = AsyncIterator([{"_id": ObjectId()}])

        audit_log.aggregate.return_value = AsyncIterator([])

        request = TimeSeriesAnalyticsRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 11),
            granularity=Granularity.DAY,
            metrics=[
                MetricType.SIGNAL_VOLUME,
                MetricType.READINESS_TRANSITIONS,
                MetricType.FACILITATOR_ACTIONS,
            ],
        )

        result = await analytics_service.compute_time_series_analytics(request)

        assert result.workspace_id == "W123"
        assert result.granularity == "day"
        assert result.signal_volume is not None
        assert result.readiness_transitions is not None
        assert result.facilitator_actions is not None
        assert result.summary["time_range_days"] == 1
        assert "total_signals" in result.summary

    @pytest.mark.asyncio
    async def test_compute_time_series_analytics_exceeds_max_range(
        self,
        analytics_service,
    ):
        """Test that exceeding max time range raises ValueError."""
        request = TimeSeriesAnalyticsRequest(
            workspace_id="W123",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 5, 1),  # 120 days
            granularity=Granularity.DAY,
            metrics=[MetricType.SIGNAL_VOLUME],
        )

        with pytest.raises(ValueError, match="exceeds maximum"):
            await analytics_service.compute_time_series_analytics(request)

    @pytest.mark.asyncio
    async def test_compute_time_series_analytics_summary_stats(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test summary statistics computation."""
        signals, _, _, _, _ = mock_collections

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator([
            {"_id": "2026-03-10", "total_count": 10, "by_channel": []},
            {"_id": "2026-03-11", "total_count": 15, "by_channel": []},
            {"_id": "2026-03-12", "total_count": 8, "by_channel": []},
        ])

        request = TimeSeriesAnalyticsRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 10),
            end_date=datetime(2026, 3, 12),
            granularity=Granularity.DAY,
            metrics=[MetricType.SIGNAL_VOLUME],
        )

        result = await analytics_service.compute_time_series_analytics(request)

        assert result.summary["total_signals"] == 33  # 10 + 15 + 8
        assert result.summary["avg_signals_per_bucket"] == 11.0  # 33 / 3
        assert result.summary["time_range_days"] == 2

    @pytest.mark.asyncio
    async def test_compute_facilitator_workload_empty(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator workload computation with no data."""
        signals, candidates, audit_log, clusters, users = mock_collections

        # Mock empty aggregation result
        class AsyncIterator:
            def __init__(self, items):
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

        audit_log.aggregate.return_value = AsyncIterator([])

        result = await analytics_service.compute_facilitator_workload(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.workspace_id == "W123"
        assert len(result.facilitators) == 0
        assert result.summary["total_facilitators"] == 0
        assert result.summary["total_actions"] == 0
        audit_log.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_compute_facilitator_workload_with_data(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator workload computation with mock data."""
        signals, candidates, audit_log, clusters, users = mock_collections

        # Helper class
        class AsyncIterator:
            def __init__(self, items):
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

        # Mock aggregation result
        mock_data = [
            {
                "_id": "user123",
                "total_actions": 25,
                "actions_by_type": [
                    "cop_candidate.promote",
                    "cop_candidate.verify",
                    "cop_candidate.promote",
                    "cop_update.publish",
                ],
                "candidates": [
                    ObjectId(),
                    ObjectId(),
                    ObjectId(),
                ],
                "timestamps": [
                    datetime(2026, 3, 1, 10, 0, 0),
                    datetime(2026, 3, 2, 14, 0, 0),
                ],
                "high_stakes_overrides": 2,
            },
            {
                "_id": "user456",
                "total_actions": 15,
                "actions_by_type": [
                    "cop_candidate.verify",
                    "cop_candidate.merge",
                ],
                "candidates": [ObjectId()],
                "timestamps": [
                    datetime(2026, 3, 3, 10, 0, 0),
                ],
                "high_stakes_overrides": 0,
            },
        ]

        # Set up mock responses
        call_count = [0]

        def get_aggregate_iterator(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: main aggregation
                return AsyncIterator(mock_data)
            else:
                # Subsequent calls: avg time and conflict rate calculations
                return AsyncIterator([])

        audit_log.aggregate.side_effect = get_aggregate_iterator

        # Mock users collection
        async def mock_find_one(query):
            if query.get("_id") == "user123":
                return {"_id": "user123", "name": "John Doe"}
            elif query.get("_id") == "user456":
                return {"_id": "user456", "name": "Jane Smith"}
            return None

        analytics_service.users.find_one = AsyncMock(side_effect=mock_find_one)

        result = await analytics_service.compute_facilitator_workload(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        # Verify result structure
        assert result.workspace_id == "W123"
        assert len(result.facilitators) == 2

        # Check facilitators are sorted by total_actions (descending)
        assert result.facilitators[0].total_actions == 25
        assert result.facilitators[1].total_actions == 15

        # Check first facilitator details
        facilitator1 = result.facilitators[0]
        assert facilitator1.user_id == "user123"
        assert facilitator1.user_name == "John Doe"
        assert facilitator1.total_actions == 25
        assert facilitator1.candidates_processed == 3
        assert facilitator1.high_stakes_override_count == 2
        assert 0.0 <= facilitator1.workload_score <= 1.0

        # Check actions_by_type
        assert "promote" in facilitator1.actions_by_type
        assert "verify" in facilitator1.actions_by_type
        assert "publish" in facilitator1.actions_by_type

        # Check summary statistics
        assert result.summary["total_facilitators"] == 2
        assert result.summary["total_actions"] == 40
        assert result.summary["average_actions_per_facilitator"] == 20.0
        assert result.summary["most_active_facilitator"] == "John Doe"

        # Check workload distribution
        dist = result.summary["workload_distribution"]
        assert dist["min"] == 15
        assert dist["max"] == 25
        assert dist["median"] == 20.0

    @pytest.mark.asyncio
    async def test_compute_facilitator_workload_filter_by_id(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test facilitator workload computation filtered by facilitator_id."""
        signals, candidates, audit_log, clusters, users = mock_collections

        class AsyncIterator:
            def __init__(self, items):
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

        mock_data = [
            {
                "_id": "user123",
                "total_actions": 25,
                "actions_by_type": ["cop_candidate.promote"],
                "candidates": [ObjectId()],
                "timestamps": [datetime(2026, 3, 1, 10, 0, 0)],
                "high_stakes_overrides": 0,
            },
        ]

        call_count = [0]

        def get_aggregate_iterator(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return AsyncIterator(mock_data)
            else:
                return AsyncIterator([])

        audit_log.aggregate.side_effect = get_aggregate_iterator
        analytics_service.users.find_one = AsyncMock(return_value=None)

        result = await analytics_service.compute_facilitator_workload(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            facilitator_id="user123",
        )

        assert len(result.facilitators) == 1
        assert result.facilitators[0].user_id == "user123"

        # Verify match stage included facilitator_id filter
        call_args = audit_log.aggregate.call_args_list[0]
        pipeline = call_args[0][0]
        assert pipeline[0]["$match"]["actor_id"] == "user123"

    @pytest.mark.asyncio
    async def test_compute_facilitator_workload_time_range_validation(
        self,
        analytics_service,
    ):
        """Test time range validation for facilitator workload."""
        # Test time range exceeds maximum
        with pytest.raises(ValueError, match="exceeds maximum"):
            await analytics_service.compute_facilitator_workload(
                workspace_id="W123",
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 6, 1),  # 151 days, exceeds 90 day max
            )

    def test_simplify_action_type(self, analytics_service):
        """Test action type simplification."""
        assert (
            analytics_service._simplify_action_type("cop_candidate.promote")
            == "promote"
        )
        assert (
            analytics_service._simplify_action_type("cop_candidate.verify") == "verify"
        )
        assert (
            analytics_service._simplify_action_type("cop_update.publish") == "publish"
        )
        assert (
            analytics_service._simplify_action_type("cop_update.override")
            == "override"
        )

    def test_calculate_workload_summary_empty(self, analytics_service):
        """Test workload summary calculation with no facilitators."""
        summary = analytics_service._calculate_workload_summary(
            facilitators=[],
            total_actions=0,
        )

        assert summary["total_facilitators"] == 0
        assert summary["total_actions"] == 0
        assert summary["average_actions_per_facilitator"] == 0.0
        assert summary["workload_distribution"]["min"] == 0
        assert summary["workload_distribution"]["max"] == 0

    def test_calculate_workload_summary_with_data(self, analytics_service):
        """Test workload summary calculation with facilitator data."""
        facilitators = [
            FacilitatorWorkload(
                user_id="user1",
                user_name="User 1",
                total_actions=30,
                actions_by_type={},
            ),
            FacilitatorWorkload(
                user_id="user2",
                user_name="User 2",
                total_actions=20,
                actions_by_type={},
            ),
            FacilitatorWorkload(
                user_id="user3",
                user_name="User 3",
                total_actions=10,
                actions_by_type={},
            ),
        ]

        summary = analytics_service._calculate_workload_summary(
            facilitators=facilitators,
            total_actions=60,
        )

        assert summary["total_facilitators"] == 3
        assert summary["total_actions"] == 60
        assert summary["average_actions_per_facilitator"] == 20.0
        assert summary["most_active_facilitator"] == "User 1"
        assert summary["workload_distribution"]["min"] == 10
        assert summary["workload_distribution"]["max"] == 30
        assert summary["workload_distribution"]["median"] == 20.0


class TestAnalyticsModels:
    """Test analytics Pydantic models."""

    def test_time_series_data_point_validation(self):
        """Test TimeSeriesDataPoint model validation."""
        from integritykit.models.analytics import TimeSeriesDataPoint

        dp = TimeSeriesDataPoint(
            timestamp=datetime(2026, 3, 10),
            metric_type=MetricType.SIGNAL_VOLUME.value,
            value=15.0,
            metadata={"channel": "C123"},
        )

        assert dp.timestamp == datetime(2026, 3, 10)
        assert dp.metric_type == "signal_volume"
        assert dp.value == 15.0
        assert dp.metadata["channel"] == "C123"

    def test_signal_volume_data_point(self):
        """Test SignalVolumeDataPoint model."""
        dp = SignalVolumeDataPoint(
            timestamp=datetime(2026, 3, 10),
            signal_count=20,
            by_channel={"C123": 15, "C456": 5},
        )

        assert dp.signal_count == 20
        assert dp.by_channel["C123"] == 15

    def test_readiness_transition_data_point(self):
        """Test ReadinessTransitionDataPoint model."""
        dp = ReadinessTransitionDataPoint(
            timestamp=datetime(2026, 3, 10),
            transitions={"IN_REVIEW->VERIFIED": 10},
            total_transitions=10,
        )

        assert dp.total_transitions == 10
        assert dp.transitions["IN_REVIEW->VERIFIED"] == 10

    def test_facilitator_action_data_point(self):
        """Test FacilitatorActionDataPoint model."""
        dp = FacilitatorActionDataPoint(
            timestamp=datetime(2026, 3, 10),
            total_actions=25,
            by_action_type={"promote": 10, "verify": 15},
            by_facilitator={"U123": 25},
            action_velocity=1.04,
        )

        assert dp.total_actions == 25
        assert dp.action_velocity == 1.04
        assert dp.by_facilitator["U123"] == 25

    def test_time_series_analytics_request(self):
        """Test TimeSeriesAnalyticsRequest model."""
        request = TimeSeriesAnalyticsRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            granularity=Granularity.DAY,
            metrics=[MetricType.SIGNAL_VOLUME, MetricType.FACILITATOR_ACTIONS],
            facilitator_id="U123",
        )

        assert request.workspace_id == "W123"
        assert request.granularity == Granularity.DAY
        assert len(request.metrics) == 2
        assert MetricType.SIGNAL_VOLUME in request.metrics

    def test_granularity_enum_values(self):
        """Test Granularity enum values."""
        assert Granularity.HOUR.value == "hour"
        assert Granularity.DAY.value == "day"
        assert Granularity.WEEK.value == "week"

    def test_metric_type_enum_values(self):
        """Test MetricType enum values."""
        assert MetricType.SIGNAL_VOLUME.value == "signal_volume"
        assert MetricType.READINESS_TRANSITIONS.value == "readiness_transitions"
        assert MetricType.FACILITATOR_ACTIONS.value == "facilitator_actions"


class TestTopicTrendAnalytics:
    """Test suite for topic trend detection (S8-10)."""

    @pytest.fixture
    def mock_collections(self):
        """Mock MongoDB collections for trends."""
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
            max_time_range_days=90,
            retention_days=365,
        )

    def test_classify_trend_direction_emerging(self, analytics_service):
        """Test trend classification for emerging topics."""
        direction = analytics_service._classify_trend_direction(
            previous_count=10,
            current_count=15,
            volume_change_pct=50.0,
            first_seen=datetime(2026, 3, 1),
            start_date=datetime(2026, 3, 1),
        )
        assert direction == TrendDirection.EMERGING

    def test_classify_trend_direction_declining(self, analytics_service):
        """Test trend classification for declining topics."""
        direction = analytics_service._classify_trend_direction(
            previous_count=20,
            current_count=10,
            volume_change_pct=-50.0,
            first_seen=datetime(2026, 3, 1),
            start_date=datetime(2026, 3, 1),
        )
        assert direction == TrendDirection.PEAKED

    def test_classify_trend_direction_stable(self, analytics_service):
        """Test trend classification for stable topics."""
        direction = analytics_service._classify_trend_direction(
            previous_count=10,
            current_count=11,
            volume_change_pct=10.0,
            first_seen=datetime(2026, 3, 1),
            start_date=datetime(2026, 3, 1),
        )
        assert direction == TrendDirection.STABLE

    def test_classify_trend_direction_new(self, analytics_service):
        """Test trend classification for new topics."""
        direction = analytics_service._classify_trend_direction(
            previous_count=0,
            current_count=10,
            volume_change_pct=100.0,
            first_seen=datetime(2026, 3, 15),
            start_date=datetime(2026, 3, 1),
        )
        assert direction == TrendDirection.NEW

    def test_classify_trend_direction_peaked(self, analytics_service):
        """Test trend classification for peaked topics."""
        direction = analytics_service._classify_trend_direction(
            previous_count=30,
            current_count=10,
            volume_change_pct=-66.7,
            first_seen=datetime(2026, 2, 1),
            start_date=datetime(2026, 3, 1),
        )
        assert direction == TrendDirection.PEAKED

    @pytest.mark.asyncio
    async def test_compute_topic_trends_empty(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test topic trends computation with no data."""
        signals, _, _, _, _ = mock_collections

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator([])

        result = await analytics_service.compute_topic_trends(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 31),
            min_signals=5,
        )

        assert result.workspace_id == "W123"
        assert len(result.trends) == 0
        assert result.summary["total_topics"] == 0
        assert result.summary["emerging_count"] == 0

    @pytest.mark.asyncio
    async def test_compute_topic_trends_with_data(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test topic trends computation with mock data."""
        signals, _, _, _, _ = mock_collections

        # Mock aggregation result with trending topics
        mock_data = [
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Flood in Northern Region",
                    "topic_type": "incident",
                },
                "periods": [
                    {
                        "period": "previous",
                        "count": 5,
                        "first_seen": datetime(2026, 3, 1),
                        "last_seen": datetime(2026, 3, 15),
                    },
                    {
                        "period": "current",
                        "count": 15,
                        "first_seen": datetime(2026, 3, 16),
                        "last_seen": datetime(2026, 3, 31),
                    },
                ],
                "total_signals": 20,
                "keywords": ["flood", "northern"],
            },
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Food Distribution Center",
                    "topic_type": "resource_offer",
                },
                "periods": [
                    {
                        "period": "previous",
                        "count": 10,
                        "first_seen": datetime(2026, 3, 1),
                        "last_seen": datetime(2026, 3, 15),
                    },
                    {
                        "period": "current",
                        "count": 9,
                        "first_seen": datetime(2026, 3, 16),
                        "last_seen": datetime(2026, 3, 31),
                    },
                ],
                "total_signals": 19,
                "keywords": ["food", "distribution"],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator(mock_data)

        result = await analytics_service.compute_topic_trends(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 31),
            min_signals=5,
        )

        assert result.workspace_id == "W123"
        assert len(result.trends) == 2

        # First trend should be emerging (5 -> 15 = 200% increase)
        trend1 = result.trends[0]
        assert trend1.topic == "Flood in Northern Region"
        assert trend1.direction == TrendDirection.EMERGING
        assert trend1.signal_count == 20
        assert trend1.volume_change_pct == 200.0

        # Second trend should be stable (10 -> 9 = -10% decrease)
        trend2 = result.trends[1]
        assert trend2.topic == "Food Distribution Center"
        assert trend2.direction == TrendDirection.STABLE
        assert trend2.signal_count == 19

        # Summary statistics
        assert result.summary["total_topics"] == 2
        assert result.summary["emerging_count"] == 1
        assert result.summary["stable_count"] == 1
        assert result.summary["most_active_topic"] == "Flood in Northern Region"

    @pytest.mark.asyncio
    async def test_compute_topic_trends_filter_by_direction(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test filtering trends by direction."""
        signals, _, _, _, _ = mock_collections

        mock_data = [
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Emerging Topic",
                    "topic_type": "incident",
                },
                "periods": [
                    {"period": "previous", "count": 5, "first_seen": datetime(2026, 3, 1), "last_seen": datetime(2026, 3, 15)},
                    {"period": "current", "count": 15, "first_seen": datetime(2026, 3, 16), "last_seen": datetime(2026, 3, 31)},
                ],
                "total_signals": 20,
                "keywords": ["emerging"],
            },
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Stable Topic",
                    "topic_type": "need",
                },
                "periods": [
                    {"period": "previous", "count": 10, "first_seen": datetime(2026, 3, 1), "last_seen": datetime(2026, 3, 15)},
                    {"period": "current", "count": 11, "first_seen": datetime(2026, 3, 16), "last_seen": datetime(2026, 3, 31)},
                ],
                "total_signals": 21,
                "keywords": ["stable"],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator(mock_data)

        # Filter for emerging only
        result = await analytics_service.compute_topic_trends(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 31),
            min_signals=5,
            direction_filter="emerging",
        )

        assert len(result.trends) == 1
        assert result.trends[0].topic == "Emerging Topic"
        assert result.trends[0].direction == TrendDirection.EMERGING

    @pytest.mark.asyncio
    async def test_compute_topic_trends_filter_by_topic_type(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test filtering trends by topic type."""
        signals, _, _, _, _ = mock_collections

        mock_data = [
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Incident Topic",
                    "topic_type": "incident",
                },
                "periods": [
                    {"period": "previous", "count": 5, "first_seen": datetime(2026, 3, 1), "last_seen": datetime(2026, 3, 15)},
                    {"period": "current", "count": 10, "first_seen": datetime(2026, 3, 16), "last_seen": datetime(2026, 3, 31)},
                ],
                "total_signals": 15,
                "keywords": ["incident"],
            },
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Resource Topic",
                    "topic_type": "resource_offer",
                },
                "periods": [
                    {"period": "previous", "count": 8, "first_seen": datetime(2026, 3, 1), "last_seen": datetime(2026, 3, 15)},
                    {"period": "current", "count": 12, "first_seen": datetime(2026, 3, 16), "last_seen": datetime(2026, 3, 31)},
                ],
                "total_signals": 20,
                "keywords": ["resource"],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator(mock_data)

        # Filter for incidents only
        result = await analytics_service.compute_topic_trends(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 31),
            min_signals=5,
            topic_type_filter="incident",
        )

        assert len(result.trends) == 1
        assert result.trends[0].topic == "Incident Topic"
        assert result.trends[0].topic_type == "incident"

    @pytest.mark.asyncio
    async def test_compute_topic_trends_min_signals_filter(
        self,
        analytics_service,
        mock_collections,
    ):
        """Test minimum signals filter."""
        signals, _, _, _, _ = mock_collections

        # This should be filtered out by the pipeline's $match on min_signals
        mock_data = [
            {
                "_id": {
                    "cluster_id": ObjectId(),
                    "topic": "Large Topic",
                    "topic_type": "incident",
                },
                "periods": [
                    {"period": "previous", "count": 5, "first_seen": datetime(2026, 3, 1), "last_seen": datetime(2026, 3, 15)},
                    {"period": "current", "count": 10, "first_seen": datetime(2026, 3, 16), "last_seen": datetime(2026, 3, 31)},
                ],
                "total_signals": 15,
                "keywords": ["large"],
            },
        ]

        class AsyncIterator:
            def __init__(self, items):
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

        signals.aggregate.return_value = AsyncIterator(mock_data)

        result = await analytics_service.compute_topic_trends(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 31),
            min_signals=10,  # Only topics with >= 10 signals
        )

        assert len(result.trends) == 1
        assert result.trends[0].signal_count >= 10

    @pytest.mark.asyncio
    async def test_compute_topic_trends_exceeds_max_range(
        self,
        analytics_service,
    ):
        """Test that exceeding max time range raises ValueError."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            await analytics_service.compute_topic_trends(
                workspace_id="W123",
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 5, 1),  # 120 days
                min_signals=5,
            )

    def test_topic_trend_model(self):
        """Test TopicTrend model validation."""
        trend = TopicTrend(
            topic="Water Shortage",
            topic_type="need",
            direction=TrendDirection.EMERGING,
            signal_count=25,
            volume_change_pct=150.0,
            first_seen=datetime(2026, 3, 1),
            peak_time=datetime(2026, 3, 15),
            peak_volume=15,
            keywords=["water", "shortage", "emergency"],
            related_clusters=["507f1f77bcf86cd799439011"],
            velocity_score=0.85,
        )

        assert trend.topic == "Water Shortage"
        assert trend.direction == TrendDirection.EMERGING
        assert trend.signal_count == 25
        assert trend.velocity_score == 0.85
        assert len(trend.keywords) == 3

    def test_trend_direction_enum_values(self):
        """Test TrendDirection enum values."""
        assert TrendDirection.EMERGING.value == "emerging"
        assert TrendDirection.DECLINING.value == "declining"
        assert TrendDirection.STABLE.value == "stable"
        assert TrendDirection.NEW.value == "new"
        assert TrendDirection.PEAKED.value == "peaked"
