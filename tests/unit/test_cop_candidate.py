"""
Unit tests for COP candidate model and promotion functionality.

Tests:
- FR-BACKLOG-002: Promote cluster to COP candidate
- COP candidate model and state management
"""

import pytest
from bson import ObjectId
from datetime import datetime

from integritykit.models.cluster import (
    Cluster,
    ConflictRecord,
    ConflictSeverity,
    PriorityScores,
)
from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    BlockingIssueSeverity,
    CandidateConflict,
    COPCandidate,
    COPCandidateCreate,
    COPFields,
    COPWhen,
    ConfidenceLevel,
    DraftWording,
    Evidence,
    FacilitatorNote,
    ReadinessState,
    RecommendedAction,
    RiskTier,
    RiskTierOverride,
    SlackPermalink,
    Verification,
    VerificationMethod,
)


# ============================================================================
# COP Candidate Model Tests
# ============================================================================


@pytest.mark.unit
class TestCOPCandidateModel:
    """Test COPCandidate model."""

    def test_create_basic_candidate(self) -> None:
        """Create a basic COP candidate."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
        )

        assert candidate.readiness_state == ReadinessState.IN_REVIEW
        assert candidate.risk_tier == RiskTier.ROUTINE
        assert candidate.is_verified is False
        assert candidate.is_blocked is False

    def test_candidate_with_fields(self) -> None:
        """Create candidate with COP fields."""
        fields = COPFields(
            what="Power outage reported",
            where="Downtown district",
            when=COPWhen(
                timestamp=datetime.utcnow(),
                timezone="America/New_York",
                is_approximate=False,
                description="Reported at 2:30 PM EST",
            ),
            who="Approximately 5,000 residents",
            so_what="Emergency shelters may be needed",
        )

        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            fields=fields,
        )

        assert candidate.fields.what == "Power outage reported"
        assert candidate.fields.where == "Downtown district"
        assert candidate.fields.when.is_approximate is False

    def test_candidate_with_evidence(self) -> None:
        """Create candidate with evidence pack."""
        evidence = Evidence(
            slack_permalinks=[
                SlackPermalink(
                    url="https://slack.com/archives/C01/p123",
                    signal_id=ObjectId(),
                    description="Initial report",
                ),
            ],
        )

        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            evidence=evidence,
        )

        assert len(candidate.evidence.slack_permalinks) == 1
        assert "C01" in candidate.evidence.slack_permalinks[0].url

    def test_verified_candidate(self) -> None:
        """Create a verified candidate."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            readiness_state=ReadinessState.VERIFIED,
            verifications=[
                Verification(
                    verified_by=ObjectId(),
                    verification_method=VerificationMethod.AUTHORITATIVE_SOURCE,
                    verification_notes="Confirmed via FEMA alert",
                    confidence_level=ConfidenceLevel.HIGH,
                ),
            ],
        )

        assert candidate.is_verified is True
        assert len(candidate.verifications) == 1

    def test_blocked_candidate(self) -> None:
        """Create a blocked candidate."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            readiness_state=ReadinessState.BLOCKED,
            blocking_issues=[
                BlockingIssue(
                    issue_type="missing_field",
                    description="Missing location information",
                    severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
                ),
            ],
        )

        assert candidate.is_blocked is True
        assert candidate.is_publishable is False
        assert len(candidate.blocking_issues) == 1


# ============================================================================
# Readiness State Tests
# ============================================================================


@pytest.mark.unit
class TestReadinessState:
    """Test COP candidate readiness states."""

    def test_in_review_state(self) -> None:
        """In review is the default state."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
        )

        assert candidate.readiness_state == ReadinessState.IN_REVIEW
        assert candidate.is_verified is False
        assert candidate.is_blocked is False

    def test_verified_state_properties(self) -> None:
        """Verified state properties."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            readiness_state=ReadinessState.VERIFIED,
        )

        assert candidate.is_verified is True
        assert candidate.is_publishable is True

    def test_blocked_state_not_publishable(self) -> None:
        """Blocked candidates are not publishable."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            readiness_state=ReadinessState.BLOCKED,
        )

        assert candidate.is_blocked is True
        assert candidate.is_publishable is False

    def test_verified_but_has_issues_not_publishable(self) -> None:
        """Verified but with issues is not publishable."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            readiness_state=ReadinessState.VERIFIED,
            blocking_issues=[
                BlockingIssue(
                    issue_type="conflict",
                    description="Unresolved conflict",
                    severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
                ),
            ],
        )

        assert candidate.is_verified is True
        assert candidate.is_publishable is False


# ============================================================================
# Risk Tier Tests
# ============================================================================


@pytest.mark.unit
class TestRiskTier:
    """Test risk tier classification."""

    def test_routine_is_default(self) -> None:
        """Routine is the default risk tier."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
        )

        assert candidate.risk_tier == RiskTier.ROUTINE

    def test_elevated_risk(self) -> None:
        """Elevated risk tier."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            risk_tier=RiskTier.ELEVATED,
        )

        assert candidate.risk_tier == RiskTier.ELEVATED

    def test_high_stakes_risk(self) -> None:
        """High stakes risk tier."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            risk_tier=RiskTier.HIGH_STAKES,
        )

        assert candidate.risk_tier == RiskTier.HIGH_STAKES

    def test_risk_tier_override(self) -> None:
        """Risk tier can be overridden."""
        override = RiskTierOverride(
            previous_tier=RiskTier.ROUTINE,
            new_tier=RiskTier.HIGH_STAKES,
            overridden_by=ObjectId(),
            reason="Potential mass casualty situation",
        )

        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            risk_tier=RiskTier.HIGH_STAKES,
            risk_tier_override=override,
        )

        assert candidate.risk_tier == RiskTier.HIGH_STAKES
        assert candidate.risk_tier_override.previous_tier == RiskTier.ROUTINE


# ============================================================================
# Conflict Tracking Tests
# ============================================================================


@pytest.mark.unit
class TestCandidateConflicts:
    """Test conflict tracking in COP candidates."""

    def test_no_conflicts(self) -> None:
        """Candidate without conflicts."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            conflicts=[],
        )

        assert candidate.has_unresolved_conflicts is False

    def test_has_unresolved_conflicts(self) -> None:
        """Candidate with unresolved conflicts."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            conflicts=[
                CandidateConflict(
                    conflict_id="c1",
                    status="unresolved",
                ),
            ],
        )

        assert candidate.has_unresolved_conflicts is True

    def test_all_conflicts_resolved(self) -> None:
        """Candidate with all conflicts resolved."""
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            conflicts=[
                CandidateConflict(
                    conflict_id="c1",
                    status="resolved",
                    resolution_notes="Verified location was correct",
                ),
            ],
        )

        assert candidate.has_unresolved_conflicts is False


# ============================================================================
# Draft Wording Tests
# ============================================================================


@pytest.mark.unit
class TestDraftWording:
    """Test draft COP wording."""

    def test_basic_draft(self) -> None:
        """Create basic draft wording."""
        draft = DraftWording(
            headline="Power Outage Downtown",
            body="A power outage affecting 5,000 residents...",
        )

        assert draft.headline == "Power Outage Downtown"
        assert draft.hedging_applied is False

    def test_draft_with_hedging(self) -> None:
        """Draft with hedging language."""
        draft = DraftWording(
            headline="Reported Power Outage",
            body="Unconfirmed reports suggest a power outage...",
            hedging_applied=True,
            next_verification_step="Contact utility company",
        )

        assert draft.hedging_applied is True
        assert draft.next_verification_step is not None


# ============================================================================
# Facilitator Notes Tests
# ============================================================================


@pytest.mark.unit
class TestFacilitatorNotes:
    """Test facilitator notes on candidates."""

    def test_add_note(self) -> None:
        """Add facilitator note."""
        note = FacilitatorNote(
            author_id=ObjectId(),
            content="Waiting for verification from field team",
        )

        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            facilitator_notes=[note],
        )

        assert len(candidate.facilitator_notes) == 1
        assert "field team" in candidate.facilitator_notes[0].content


# ============================================================================
# COP Candidate Create Tests
# ============================================================================


@pytest.mark.unit
class TestCOPCandidateCreate:
    """Test COPCandidateCreate schema."""

    def test_create_from_cluster(self) -> None:
        """Create candidate creation data from cluster."""
        cluster_id = ObjectId()
        signal_ids = [ObjectId(), ObjectId()]
        user_id = ObjectId()

        create_data = COPCandidateCreate(
            cluster_id=cluster_id,
            primary_signal_ids=signal_ids,
            created_by=user_id,
        )

        assert create_data.cluster_id == cluster_id
        assert len(create_data.primary_signal_ids) == 2
        assert create_data.created_by == user_id
        assert create_data.risk_tier == RiskTier.ROUTINE

    def test_create_with_initial_fields(self) -> None:
        """Create with initial COP fields."""
        fields = COPFields(
            what="Test situation",
            where="Test location",
        )

        create_data = COPCandidateCreate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            fields=fields,
        )

        assert create_data.fields.what == "Test situation"


# ============================================================================
# Recommended Action Tests
# ============================================================================


@pytest.mark.unit
class TestRecommendedAction:
    """Test recommended action generation."""

    def test_assign_verification_action(self) -> None:
        """Recommend verification assignment."""
        action = RecommendedAction(
            action_type=ActionType.ASSIGN_VERIFICATION,
            reason="Candidate is ready for verification",
            alternatives=[],
        )

        assert action.action_type == ActionType.ASSIGN_VERIFICATION

    def test_resolve_conflict_action(self) -> None:
        """Recommend conflict resolution."""
        action = RecommendedAction(
            action_type=ActionType.RESOLVE_CONFLICT,
            reason="Conflicting information about location",
            alternatives=["add_evidence", "assign_verification"],
        )

        assert action.action_type == ActionType.RESOLVE_CONFLICT
        assert len(action.alternatives) == 2

    def test_ready_to_publish_action(self) -> None:
        """Ready to publish action."""
        action = RecommendedAction(
            action_type=ActionType.READY_TO_PUBLISH,
            reason="All verifications complete, no conflicts",
            alternatives=[],
        )

        assert action.action_type == ActionType.READY_TO_PUBLISH


# ============================================================================
# Promotion Tests
# ============================================================================


@pytest.mark.unit
class TestPromotion:
    """Test promotion from cluster to COP candidate."""

    def test_cluster_promotion_fields(self) -> None:
        """Cluster has fields for tracking promotion."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Test",
            summary="Test summary",
            promoted_to_candidate=False,
            cop_candidate_id=None,
        )

        assert cluster.promoted_to_candidate is False
        assert cluster.cop_candidate_id is None

    def test_promoted_cluster(self) -> None:
        """Cluster marked as promoted."""
        candidate_id = ObjectId()
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T123",
            topic="Test",
            summary="Test summary",
            promoted_to_candidate=True,
            cop_candidate_id=candidate_id,
        )

        assert cluster.promoted_to_candidate is True
        assert cluster.cop_candidate_id == candidate_id

    def test_candidate_links_to_cluster(self) -> None:
        """COP candidate links back to source cluster."""
        cluster_id = ObjectId()
        candidate = COPCandidate(
            cluster_id=cluster_id,
            created_by=ObjectId(),
        )

        assert candidate.cluster_id == cluster_id

    def test_candidate_inherits_signals(self) -> None:
        """Candidate references primary signals from cluster."""
        signal_ids = [ObjectId(), ObjectId(), ObjectId()]
        candidate = COPCandidate(
            cluster_id=ObjectId(),
            created_by=ObjectId(),
            primary_signal_ids=signal_ids,
        )

        assert len(candidate.primary_signal_ids) == 3
