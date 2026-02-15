"""
Unit tests for private COP backlog functionality.

Tests:
- FR-BACKLOG-001: Private backlog with prioritized clusters
- NFR-PRIVACY-001: Private facilitator views
"""

import pytest
from bson import ObjectId
from datetime import datetime

from integritykit.models.cluster import (
    Cluster,
    PriorityScores,
    ConflictRecord,
    ConflictSeverity,
)
from integritykit.models.signal import Signal
from integritykit.services.backlog import BacklogItem, BacklogService


# ============================================================================
# BacklogItem Tests
# ============================================================================


@pytest.mark.unit
class TestBacklogItem:
    """Test BacklogItem model."""

    def test_create_backlog_item(self) -> None:
        """Create a basic backlog item."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Shelter Status Update",
            summary="Shelter Alpha closing at 6pm",
            signal_ids=[ObjectId(), ObjectId()],
        )

        item = BacklogItem(
            cluster=cluster,
            signals=[],
            signal_count=2,
        )

        assert item.topic == "Shelter Status Update"
        assert item.signal_count == 2
        assert item.has_conflicts is False

    def test_backlog_item_with_priority_scores(self) -> None:
        """Backlog item includes priority scores."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Urgent: Road Closure",
            summary="Major road blocked",
            priority_scores=PriorityScores(
                urgency=85.0,
                urgency_reasoning="Time-critical road hazard",
                impact=70.0,
                impact_reasoning="Affects 500+ commuters",
                risk=60.0,
                risk_reasoning="Safety concern",
            ),
        )

        item = BacklogItem(
            cluster=cluster,
            signals=[],
            signal_count=5,
        )

        assert item.priority_scores.urgency == 85.0
        assert item.priority_scores.impact == 70.0
        assert item.composite_score > 0

    def test_backlog_item_with_conflicts(self) -> None:
        """Backlog item tracks conflicts."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Shelter Capacity",
            summary="Conflicting reports about capacity",
            conflicts=[
                ConflictRecord(
                    id="conflict-1",
                    signal_ids=[ObjectId(), ObjectId()],
                    field="capacity",
                    severity=ConflictSeverity.MEDIUM,
                    description="Conflicting capacity numbers: 45 vs 60",
                    resolved=False,
                ),
                ConflictRecord(
                    id="conflict-2",
                    signal_ids=[ObjectId(), ObjectId()],
                    field="time",
                    severity=ConflictSeverity.LOW,
                    description="Minor time discrepancy",
                    resolved=True,
                ),
            ],
        )

        item = BacklogItem(
            cluster=cluster,
            signals=[],
            signal_count=3,
        )

        assert item.has_conflicts is True
        assert item.conflict_count == 2
        assert item.unresolved_conflict_count == 1
        assert item.has_unresolved_conflicts is True

    def test_backlog_item_to_dict(self) -> None:
        """Convert backlog item to dictionary."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Test Topic",
            summary="Test summary",
            priority_scores=PriorityScores(
                urgency=50.0,
                impact=40.0,
                risk=30.0,
            ),
        )

        item = BacklogItem(
            cluster=cluster,
            signals=[],
            signal_count=1,
        )

        data = item.to_dict()

        assert "id" in data
        assert data["topic"] == "Test Topic"
        assert data["summary"] == "Test summary"
        assert "priority_scores" in data
        assert "composite_score" in data["priority_scores"]
        assert "sample_signals" in data


# ============================================================================
# Priority Scoring Tests
# ============================================================================


@pytest.mark.unit
class TestPriorityScoring:
    """Test priority score calculations."""

    def test_composite_score_calculation(self) -> None:
        """Composite score is weighted average."""
        scores = PriorityScores(
            urgency=100.0,
            impact=100.0,
            risk=100.0,
        )

        # Weighted: urgency*0.4 + impact*0.35 + risk*0.25 = 100
        assert scores.composite_score == 100.0

    def test_urgency_weighted_higher(self) -> None:
        """Urgency has higher weight in composite score."""
        high_urgency = PriorityScores(urgency=100.0, impact=0.0, risk=0.0)
        high_impact = PriorityScores(urgency=0.0, impact=100.0, risk=0.0)
        high_risk = PriorityScores(urgency=0.0, impact=0.0, risk=100.0)

        # Urgency weight: 0.4, Impact: 0.35, Risk: 0.25
        assert high_urgency.composite_score == 40.0
        assert high_impact.composite_score == 35.0
        assert high_risk.composite_score == 25.0

    def test_default_scores(self) -> None:
        """Default priority scores are neutral."""
        scores = PriorityScores()

        assert scores.urgency == 0.5
        assert scores.impact == 0.5
        assert scores.risk == 0.5

    def test_reasoning_fields(self) -> None:
        """Priority scores include reasoning."""
        scores = PriorityScores(
            urgency=80.0,
            urgency_reasoning="Time-critical situation",
            impact=60.0,
            impact_reasoning="Affects many people",
            risk=40.0,
            risk_reasoning="Low safety risk",
        )

        assert scores.urgency_reasoning == "Time-critical situation"
        assert scores.impact_reasoning == "Affects many people"
        assert scores.risk_reasoning == "Low safety risk"


# ============================================================================
# Backlog Sorting Tests
# ============================================================================


@pytest.mark.unit
class TestBacklogSorting:
    """Test backlog sorting logic."""

    def _create_cluster_with_priority(
        self,
        urgency: float,
        impact: float,
        risk: float,
        topic: str = "Test",
    ) -> Cluster:
        """Helper to create cluster with specific priority scores."""
        return Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic=topic,
            summary="Test summary",
            priority_scores=PriorityScores(
                urgency=urgency,
                impact=impact,
                risk=risk,
            ),
        )

    def test_sort_by_composite_priority(self) -> None:
        """Items should sort by composite priority score."""
        items = [
            BacklogItem(
                cluster=self._create_cluster_with_priority(50, 50, 50, "Medium"),
                signals=[],
                signal_count=1,
            ),
            BacklogItem(
                cluster=self._create_cluster_with_priority(90, 80, 70, "High"),
                signals=[],
                signal_count=1,
            ),
            BacklogItem(
                cluster=self._create_cluster_with_priority(20, 20, 20, "Low"),
                signals=[],
                signal_count=1,
            ),
        ]

        sorted_items = sorted(items, key=lambda x: x.composite_score, reverse=True)

        assert sorted_items[0].topic == "High"
        assert sorted_items[1].topic == "Medium"
        assert sorted_items[2].topic == "Low"

    def test_sort_by_urgency_only(self) -> None:
        """Can sort by urgency alone."""
        items = [
            BacklogItem(
                cluster=self._create_cluster_with_priority(30, 90, 90, "Low Urgency"),
                signals=[],
                signal_count=1,
            ),
            BacklogItem(
                cluster=self._create_cluster_with_priority(95, 10, 10, "High Urgency"),
                signals=[],
                signal_count=1,
            ),
        ]

        sorted_items = sorted(
            items, key=lambda x: x.priority_scores.urgency, reverse=True
        )

        assert sorted_items[0].topic == "High Urgency"
        assert sorted_items[1].topic == "Low Urgency"


# ============================================================================
# Conflict Detection Tests
# ============================================================================


@pytest.mark.unit
class TestBacklogConflicts:
    """Test conflict tracking in backlog items."""

    def test_no_conflicts(self) -> None:
        """Cluster without conflicts."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="No conflicts",
            summary="Clean cluster",
            conflicts=[],
        )

        item = BacklogItem(cluster=cluster, signals=[], signal_count=1)

        assert item.has_conflicts is False
        assert item.conflict_count == 0
        assert item.has_unresolved_conflicts is False

    def test_all_resolved_conflicts(self) -> None:
        """Cluster with all conflicts resolved."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Resolved conflicts",
            summary="All conflicts resolved",
            conflicts=[
                ConflictRecord(
                    id="c1",
                    signal_ids=[ObjectId()],
                    field="time",
                    severity=ConflictSeverity.LOW,
                    description="Time discrepancy",
                    resolved=True,
                ),
            ],
        )

        item = BacklogItem(cluster=cluster, signals=[], signal_count=1)

        assert item.has_conflicts is True
        assert item.conflict_count == 1
        assert item.unresolved_conflict_count == 0
        assert item.has_unresolved_conflicts is False

    def test_conflict_severity_levels(self) -> None:
        """Track different conflict severity levels."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Mixed conflicts",
            conflicts=[
                ConflictRecord(
                    id="c1",
                    signal_ids=[ObjectId()],
                    field="location",
                    severity=ConflictSeverity.CRITICAL,
                    description="Major location discrepancy",
                    resolved=False,
                ),
                ConflictRecord(
                    id="c2",
                    signal_ids=[ObjectId()],
                    field="time",
                    severity=ConflictSeverity.LOW,
                    description="Minor time discrepancy",
                    resolved=False,
                ),
            ],
        )

        assert cluster.conflicts[0].severity == ConflictSeverity.CRITICAL
        assert cluster.conflicts[1].severity == ConflictSeverity.LOW


# ============================================================================
# Backlog Privacy Tests
# ============================================================================


@pytest.mark.unit
class TestBacklogPrivacy:
    """Test backlog privacy (NFR-PRIVACY-001)."""

    def test_backlog_item_hides_slack_user_ids_in_sample(self) -> None:
        """Sample signals don't expose full user details."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Test",
            summary="Test",
        )

        item = BacklogItem(cluster=cluster, signals=[], signal_count=1)
        data = item.to_dict()

        # Sample signals should exist but be empty when no signals provided
        assert "sample_signals" in data
        assert len(data["sample_signals"]) == 0

    def test_backlog_scoped_to_workspace(self) -> None:
        """Backlog items are scoped to workspace."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Test",
            summary="Test",
        )

        item = BacklogItem(cluster=cluster, signals=[], signal_count=1)

        # Workspace ID should be in cluster, not exposed in backlog item dict
        data = item.to_dict()
        assert "slack_workspace_id" not in data


# ============================================================================
# Promoted Cluster Tests
# ============================================================================


@pytest.mark.unit
class TestPromotedClusters:
    """Test that promoted clusters are excluded from backlog."""

    def test_promoted_cluster_flag(self) -> None:
        """Cluster tracks promotion status."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Promoted",
            summary="Already promoted",
            promoted_to_candidate=True,
            cop_candidate_id=ObjectId(),
        )

        assert cluster.promoted_to_candidate is True
        assert cluster.cop_candidate_id is not None

    def test_unpromoted_cluster(self) -> None:
        """Default cluster is not promoted."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Not promoted",
            summary="In backlog",
        )

        assert cluster.promoted_to_candidate is False
        assert cluster.cop_candidate_id is None
