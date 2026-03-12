"""Unit tests for after-action report export service (S8-14).

Tests:
- Report data aggregation
- PDF generation
- DOCX generation
- Recommendations generation
- Model validation
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from integritykit.models.report import (
    AfterActionReportData,
    AfterActionReportRequest,
    CandidateSummary,
    ConflictSummary,
    FacilitatorSummary,
    ReportFormat,
    ReportSection,
    SignalSummary,
    TimelineEvent,
    TopicSummary,
)
from integritykit.services.report_export import ReportExportService


class AsyncIterator:
    """Helper class for mocking async iterators."""

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


class TestReportExportService:
    """Test suite for ReportExportService."""

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
    def report_service(self, mock_collections):
        """Create ReportExportService with mocked collections."""
        signals, candidates, audit_log, clusters, users = mock_collections
        return ReportExportService(
            signals_collection=signals,
            candidates_collection=candidates,
            audit_log_collection=audit_log,
            clusters_collection=clusters,
            users_collection=users,
        )

    @pytest.fixture
    def sample_request(self):
        """Create a sample report request."""
        return AfterActionReportRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            title="Test After-Action Report",
            incident_name="Test Incident",
            format=ReportFormat.PDF,
            sections=list(ReportSection),
            include_charts=True,
        )

    @pytest.mark.asyncio
    async def test_aggregate_signal_summary_empty(
        self,
        report_service,
        mock_collections,
    ):
        """Test signal aggregation with no data."""
        signals, _, _, _, _ = mock_collections
        signals.aggregate.return_value = AsyncIterator([])

        result = await report_service._aggregate_signal_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_signals == 0
        assert result.signals_by_channel == {}
        signals.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggregate_signal_summary_with_data(
        self,
        report_service,
        mock_collections,
    ):
        """Test signal aggregation with mock data."""
        signals, _, _, _, _ = mock_collections

        mock_data = [
            {
                "total": 100,
                "by_channel": ["C123", "C123", "C456", "C123"],
            }
        ]
        signals.aggregate.return_value = AsyncIterator(mock_data)

        result = await report_service._aggregate_signal_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_signals == 100
        assert result.signals_by_channel == {"C123": 3, "C456": 1}
        assert result.avg_signals_per_day > 0

    @pytest.mark.asyncio
    async def test_aggregate_candidate_summary_empty(
        self,
        report_service,
        mock_collections,
    ):
        """Test candidate aggregation with no data."""
        _, candidates, _, _, _ = mock_collections
        candidates.aggregate.return_value = AsyncIterator([])

        result = await report_service._aggregate_candidate_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_candidates == 0
        assert result.verified_count == 0
        assert result.verification_rate == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_candidate_summary_with_data(
        self,
        report_service,
        mock_collections,
    ):
        """Test candidate aggregation with mock data."""
        _, candidates, _, _, _ = mock_collections

        mock_data = [
            {"_id": "VERIFIED", "count": 15},
            {"_id": "BLOCKED", "count": 3},
            {"_id": "IN_REVIEW", "count": 7},
        ]
        candidates.aggregate.return_value = AsyncIterator(mock_data)

        result = await report_service._aggregate_candidate_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_candidates == 25
        assert result.verified_count == 15
        assert result.blocked_count == 3
        assert result.in_review_count == 7
        assert result.verification_rate == 0.6  # 15/25

    @pytest.mark.asyncio
    async def test_build_timeline_empty(
        self,
        report_service,
        mock_collections,
    ):
        """Test timeline building with no events."""
        _, _, audit_log, _, _ = mock_collections
        audit_log.aggregate.return_value = AsyncIterator([])

        result = await report_service._build_timeline(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_build_timeline_with_events(
        self,
        report_service,
        mock_collections,
    ):
        """Test timeline building with mock events."""
        _, _, audit_log, _, _ = mock_collections

        mock_events = [
            {
                "timestamp": datetime(2026, 3, 2, 10, 0, 0),
                "action_type": "cop_candidate.verify",
                "target_id": "123",
            },
            {
                "timestamp": datetime(2026, 3, 3, 14, 0, 0),
                "action_type": "cop_update.publish",
                "target_id": "456",
            },
        ]
        audit_log.aggregate.return_value = AsyncIterator(mock_events)

        result = await report_service._build_timeline(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert len(result) == 2
        assert isinstance(result[0], TimelineEvent)
        assert result[0].event_type == "cop_candidate.verify"
        assert result[1].event_type == "cop_update.publish"
        assert result[1].significance == "notable"

    @pytest.mark.asyncio
    async def test_aggregate_facilitator_summaries_empty(
        self,
        report_service,
        mock_collections,
    ):
        """Test facilitator aggregation with no data."""
        _, _, audit_log, _, _ = mock_collections
        audit_log.aggregate.return_value = AsyncIterator([])

        result = await report_service._aggregate_facilitator_summaries(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_aggregate_facilitator_summaries_with_data(
        self,
        report_service,
        mock_collections,
    ):
        """Test facilitator aggregation with mock data."""
        _, _, audit_log, _, users = mock_collections

        mock_data = [
            {
                "_id": "U123",
                "total_actions": 25,
                "candidates": ["C1", "C2", "C3"],
                "action_types": [
                    "cop_candidate.verify",
                    "cop_candidate.verify",
                    "conflict.resolve",
                ],
            },
        ]
        audit_log.aggregate.return_value = AsyncIterator(mock_data)
        users.find_one = AsyncMock(return_value={"name": "John Doe"})

        result = await report_service._aggregate_facilitator_summaries(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert len(result) == 1
        assert isinstance(result[0], FacilitatorSummary)
        assert result[0].user_id == "U123"
        assert result[0].user_name == "John Doe"
        assert result[0].total_actions == 25
        assert result[0].candidates_processed == 3
        assert result[0].verification_actions == 2
        assert result[0].conflict_resolutions == 1

    @pytest.mark.asyncio
    async def test_aggregate_conflict_summary_empty(
        self,
        report_service,
        mock_collections,
    ):
        """Test conflict aggregation with no data."""
        _, _, _, clusters, _ = mock_collections
        clusters.aggregate.return_value = AsyncIterator([])

        result = await report_service._aggregate_conflict_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_conflicts == 0
        assert result.resolved_conflicts == 0
        assert result.resolution_rate == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_conflict_summary_with_data(
        self,
        report_service,
        mock_collections,
    ):
        """Test conflict aggregation with mock data."""
        _, _, _, clusters, _ = mock_collections

        mock_data = [
            {
                "_id": "routine",
                "total": 10,
                "resolved": 8,
                "resolution_methods": ["merged", "merged", "one_correct"],
            },
            {
                "_id": "elevated",
                "total": 5,
                "resolved": 3,
                "resolution_methods": ["merged", "deferred"],
            },
        ]
        clusters.aggregate.return_value = AsyncIterator(mock_data)

        result = await report_service._aggregate_conflict_summary(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert result.total_conflicts == 15
        assert result.resolved_conflicts == 11
        assert result.resolution_rate == round(11 / 15, 3)
        assert result.by_risk_tier == {"routine": 10, "elevated": 5}
        assert "merged" in result.by_resolution_method

    def test_generate_recommendations_no_data(self, report_service):
        """Test recommendations with no data."""
        report_data = AfterActionReportData(
            workspace_id="W123",
            title="Test",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        recommendations = report_service._generate_recommendations(report_data)

        assert len(recommendations) >= 1
        assert "normal parameters" in recommendations[0].lower()

    def test_generate_recommendations_low_verification_rate(self, report_service):
        """Test recommendations for low verification rate."""
        report_data = AfterActionReportData(
            workspace_id="W123",
            title="Test",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            candidate_summary=CandidateSummary(
                total_candidates=20,
                verified_count=5,
                blocked_count=10,
                verification_rate=0.25,
            ),
        )

        recommendations = report_service._generate_recommendations(report_data)

        assert any("verification rate" in r.lower() for r in recommendations)
        assert any("blocked" in r.lower() for r in recommendations)

    def test_generate_recommendations_low_conflict_resolution(self, report_service):
        """Test recommendations for low conflict resolution rate."""
        report_data = AfterActionReportData(
            workspace_id="W123",
            title="Test",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            conflict_summary=ConflictSummary(
                total_conflicts=10,
                resolved_conflicts=5,
                resolution_rate=0.5,
            ),
        )

        recommendations = report_service._generate_recommendations(report_data)

        assert any("conflict resolution" in r.lower() for r in recommendations)

    def test_generate_recommendations_uneven_workload(self, report_service):
        """Test recommendations for uneven facilitator workload."""
        report_data = AfterActionReportData(
            workspace_id="W123",
            title="Test",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
            facilitator_summaries=[
                FacilitatorSummary(user_id="U1", total_actions=100),
                FacilitatorSummary(user_id="U2", total_actions=10),
            ],
        )

        recommendations = report_service._generate_recommendations(report_data)

        assert any("workload" in r.lower() for r in recommendations)

    @pytest.mark.asyncio
    async def test_generate_report_invalid_time_range(
        self,
        report_service,
    ):
        """Test report generation with invalid time range."""
        request = AfterActionReportRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 7),  # After end date
            end_date=datetime(2026, 3, 1),
            title="Test",
        )

        with pytest.raises(ValueError, match="End date must be after start date"):
            await report_service.generate_report(request)

    @pytest.mark.asyncio
    async def test_generate_report_exceeds_max_range(
        self,
        report_service,
    ):
        """Test report generation with time range exceeding max."""
        request = AfterActionReportRequest(
            workspace_id="W123",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 6, 1),  # 151 days
            title="Test",
        )

        with pytest.raises(ValueError, match="cannot exceed 90 days"):
            await report_service.generate_report(request)

    @pytest.mark.asyncio
    async def test_generate_pdf_report(
        self,
        report_service,
        mock_collections,
        sample_request,
    ):
        """Test PDF report generation."""
        signals, candidates, audit_log, clusters, users = mock_collections

        # Mock empty responses
        signals.aggregate.return_value = AsyncIterator([])
        candidates.aggregate.return_value = AsyncIterator([])
        audit_log.aggregate.return_value = AsyncIterator([])
        clusters.aggregate.return_value = AsyncIterator([])

        sample_request.format = ReportFormat.PDF
        content, content_type = await report_service.generate_report(sample_request)

        assert content_type == "application/pdf"
        assert len(content) > 0
        # PDF files start with %PDF
        assert content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_generate_docx_report(
        self,
        report_service,
        mock_collections,
        sample_request,
    ):
        """Test DOCX report generation."""
        signals, candidates, audit_log, clusters, users = mock_collections

        # Mock empty responses
        signals.aggregate.return_value = AsyncIterator([])
        candidates.aggregate.return_value = AsyncIterator([])
        audit_log.aggregate.return_value = AsyncIterator([])
        clusters.aggregate.return_value = AsyncIterator([])

        sample_request.format = ReportFormat.DOCX
        content, content_type = await report_service.generate_report(sample_request)

        assert content_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert len(content) > 0
        # DOCX files are ZIP archives starting with PK
        assert content[:2] == b"PK"


class TestReportModels:
    """Test report Pydantic models."""

    def test_signal_summary_model(self):
        """Test SignalSummary model validation."""
        summary = SignalSummary(
            total_signals=100,
            signals_by_channel={"C123": 60, "C456": 40},
            avg_signals_per_day=14.3,
        )

        assert summary.total_signals == 100
        assert summary.signals_by_channel["C123"] == 60
        assert summary.avg_signals_per_day == 14.3

    def test_candidate_summary_model(self):
        """Test CandidateSummary model validation."""
        summary = CandidateSummary(
            total_candidates=50,
            verified_count=30,
            blocked_count=10,
            in_review_count=10,
            verification_rate=0.6,
        )

        assert summary.total_candidates == 50
        assert summary.verification_rate == 0.6

    def test_facilitator_summary_model(self):
        """Test FacilitatorSummary model validation."""
        summary = FacilitatorSummary(
            user_id="U123",
            user_name="Jane Doe",
            total_actions=50,
            candidates_processed=25,
            verification_actions=20,
            conflict_resolutions=5,
        )

        assert summary.user_id == "U123"
        assert summary.user_name == "Jane Doe"
        assert summary.total_actions == 50

    def test_timeline_event_model(self):
        """Test TimelineEvent model validation."""
        event = TimelineEvent(
            timestamp=datetime(2026, 3, 10, 14, 30, 0),
            event_type="cop_update.publish",
            description="COP update published",
            significance="notable",
            related_ids=["123", "456"],
        )

        assert event.timestamp == datetime(2026, 3, 10, 14, 30, 0)
        assert event.event_type == "cop_update.publish"
        assert event.significance == "notable"
        assert len(event.related_ids) == 2

    def test_topic_summary_model(self):
        """Test TopicSummary model validation."""
        summary = TopicSummary(
            topic="Water shortage in Region A",
            topic_type="need",
            signal_count=45,
            trend_direction="emerging",
            first_seen=datetime(2026, 3, 1),
        )

        assert summary.topic == "Water shortage in Region A"
        assert summary.topic_type == "need"
        assert summary.signal_count == 45
        assert summary.trend_direction == "emerging"

    def test_after_action_report_request_defaults(self):
        """Test AfterActionReportRequest defaults."""
        request = AfterActionReportRequest(
            workspace_id="W123",
            start_date=datetime(2026, 3, 1),
            end_date=datetime(2026, 3, 7),
        )

        assert request.title == "After-Action Report"
        assert request.format == ReportFormat.PDF
        assert request.include_charts is True
        assert len(request.sections) == len(ReportSection)

    def test_report_format_enum(self):
        """Test ReportFormat enum values."""
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.DOCX.value == "docx"

    def test_report_section_enum(self):
        """Test ReportSection enum values."""
        assert ReportSection.EXECUTIVE_SUMMARY.value == "executive_summary"
        assert ReportSection.TIMELINE.value == "timeline"
        assert ReportSection.RECOMMENDATIONS.value == "recommendations"
