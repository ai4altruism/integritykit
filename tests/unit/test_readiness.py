"""
Unit tests for readiness computation logic.

Tests the business logic for determining COP candidate readiness states
(verified, in_review, blocked) based on field completeness, verification
status, and risk tier.

Tests:
- FR-COP-READ-001: Readiness states (Ready-Verified / Ready-In Review / Blocked)
- FR-COP-READ-002: Missing/weak fields identification
- FR-COP-READ-003: Best next action recommendation
- NFR-CONFLICT-001: Conflict blocking enforcement
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssueSeverity,
    CandidateConflict,
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
    SlackPermalink,
    Verification,
)
from integritykit.services.readiness import (
    FieldEvaluation,
    FieldStatus,
    ReadinessEvaluation,
    ReadinessService,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candidate(
    *,
    fields: dict | None = None,
    evidence_count: int = 1,
    verifications: list | None = None,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    has_conflicts: bool = False,
) -> COPCandidate:
    """Create a COPCandidate for testing."""
    default_fields = {
        "what": "Bridge closure on Main Street",
        "where": "123 Main St, Springfield, IL",
        "when": COPWhen(
            timestamp=datetime.now(timezone.utc),
            timezone="America/Chicago",
            is_approximate=False,
            description="As of 2pm today",
        ),
        "who": "City Public Works Department",
        "so_what": "Traffic rerouted via Oak Avenue",
    }
    if fields:
        default_fields.update(fields)

    # Build evidence
    evidence = Evidence(
        slack_permalinks=[
            SlackPermalink(
                url=f"https://workspace.slack.com/archives/C123/p{i}",
                signal_id=ObjectId(),
                description="Source message",
            )
            for i in range(evidence_count)
        ],
        external_sources=[],
    )

    # Build verifications
    verification_list = []
    if verifications is not None:
        verification_list = verifications

    # Build conflicts
    conflicts = []
    if has_conflicts:
        conflicts = [
            CandidateConflict(
                conflict_id=str(ObjectId()),
                status="unresolved",
            )
        ]

    return COPCandidate(
        id=ObjectId(),
        cluster_id=ObjectId(),
        primary_signal_ids=[ObjectId()],
        readiness_state=ReadinessState.IN_REVIEW,
        readiness_updated_at=datetime.now(timezone.utc),
        readiness_updated_by=ObjectId(),
        risk_tier=risk_tier,
        fields=COPFields(**default_fields),
        evidence=evidence,
        verifications=verification_list,
        conflicts=conflicts,
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# ReadinessService Field Evaluation Tests (FR-COP-READ-002)
# ============================================================================


@pytest.mark.unit
class TestFieldEvaluation:
    """Test field evaluation logic in ReadinessService."""

    def test_complete_field_status(self) -> None:
        """Well-specified field should have COMPLETE status."""
        service = ReadinessService(use_llm=False)
        status = service._assess_field_status("Bridge closure on Main Street")
        assert status == FieldStatus.COMPLETE

    def test_empty_field_is_missing(self) -> None:
        """Empty string field should have MISSING status."""
        service = ReadinessService(use_llm=False)
        status = service._assess_field_status("")
        assert status == FieldStatus.MISSING

    def test_none_field_is_missing(self) -> None:
        """None field should have MISSING status."""
        service = ReadinessService(use_llm=False)
        status = service._assess_field_status(None)
        assert status == FieldStatus.MISSING

    def test_vague_field_is_partial(self) -> None:
        """Vague indicator values should have PARTIAL status."""
        service = ReadinessService(use_llm=False)
        vague_values = ["unknown", "TBD", "unclear", "N/A", "?"]
        for value in vague_values:
            status = service._assess_field_status(value)
            assert status == FieldStatus.PARTIAL, f"Expected PARTIAL for '{value}'"

    def test_short_field_is_partial(self) -> None:
        """Very short values should have PARTIAL status."""
        service = ReadinessService(use_llm=False)
        status = service._assess_field_status("Hi")  # < 5 chars
        assert status == FieldStatus.PARTIAL

    def test_evaluate_fields_all_complete(self) -> None:
        """Candidate with all fields should have all COMPLETE evaluations."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate()

        evaluations = service._evaluate_fields(candidate)

        # Core fields should be complete
        field_statuses = {e.field: e.status for e in evaluations}
        assert field_statuses["what"] == FieldStatus.COMPLETE
        assert field_statuses["where"] == FieldStatus.COMPLETE
        assert field_statuses["when"] == FieldStatus.COMPLETE
        assert field_statuses["who"] == FieldStatus.COMPLETE
        assert field_statuses["so_what"] == FieldStatus.COMPLETE

    def test_evaluate_fields_missing_where(self) -> None:
        """Candidate missing 'where' should show MISSING for that field."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(fields={"where": ""})

        evaluations = service._evaluate_fields(candidate)

        field_statuses = {e.field: e.status for e in evaluations}
        assert field_statuses["where"] == FieldStatus.MISSING

    def test_evidence_evaluation_complete(self) -> None:
        """Candidate with 2+ evidence sources should have COMPLETE evidence."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(evidence_count=2)

        evaluations = service._evaluate_fields(candidate)

        evidence_eval = next(e for e in evaluations if e.field == "evidence")
        assert evidence_eval.status == FieldStatus.COMPLETE

    def test_evidence_evaluation_partial(self) -> None:
        """Candidate with 1 evidence source should have PARTIAL evidence."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(evidence_count=1)

        evaluations = service._evaluate_fields(candidate)

        evidence_eval = next(e for e in evaluations if e.field == "evidence")
        assert evidence_eval.status == FieldStatus.PARTIAL

    def test_evidence_evaluation_missing(self) -> None:
        """Candidate with no evidence should have MISSING evidence."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(evidence_count=0)

        evaluations = service._evaluate_fields(candidate)

        evidence_eval = next(e for e in evaluations if e.field == "evidence")
        assert evidence_eval.status == FieldStatus.MISSING


# ============================================================================
# Readiness State Computation Tests (FR-COP-READ-001)
# ============================================================================


@pytest.mark.unit
class TestReadinessStateComputation:
    """Test readiness state computation in ReadinessService."""

    @pytest.mark.asyncio
    async def test_verified_state_with_verification_and_all_fields(self) -> None:
        """Candidate with verification and all fields should be VERIFIED."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(
            verifications=[
                Verification(
                    verified_by=ObjectId(),
                    verified_at=datetime.now(timezone.utc),
                    verification_method="authoritative_source",
                    verification_notes="Confirmed via official source",
                )
            ]
        )

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.readiness_state == ReadinessState.VERIFIED
        assert len(evaluation.missing_fields) == 0

    @pytest.mark.asyncio
    async def test_in_review_state_without_verification(self) -> None:
        """Candidate without verification should be IN_REVIEW."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(verifications=[])

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.readiness_state == ReadinessState.IN_REVIEW

    @pytest.mark.asyncio
    async def test_blocked_state_missing_critical_field(self) -> None:
        """Candidate missing critical field (what/where/when) should be BLOCKED."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(fields={"what": ""})  # Critical field missing

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.readiness_state == ReadinessState.BLOCKED
        assert "what" in evaluation.missing_fields
        # Should have blocking issue
        blocking = [bi for bi in evaluation.blocking_issues
                    if bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING]
        assert len(blocking) > 0

    @pytest.mark.asyncio
    async def test_blocked_state_high_stakes_unverified(self) -> None:
        """High-stakes candidate without verification should be BLOCKED."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(
            risk_tier=RiskTier.HIGH_STAKES,
            verifications=[],
        )

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.readiness_state == ReadinessState.BLOCKED
        # Should have blocking issue about verification required
        blocking_descriptions = [bi.description for bi in evaluation.blocking_issues]
        assert any("verification" in desc.lower() for desc in blocking_descriptions)


# ============================================================================
# Conflict Blocking Tests (NFR-CONFLICT-001)
# ============================================================================


@pytest.mark.unit
class TestConflictBlocking:
    """Test conflict blocking enforcement."""

    @pytest.mark.asyncio
    async def test_unresolved_conflict_blocks_candidate(self) -> None:
        """Candidate with unresolved conflict should be BLOCKED."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(has_conflicts=True)

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.readiness_state == ReadinessState.BLOCKED
        # Should have conflict blocking issue
        conflict_issues = [
            bi for bi in evaluation.blocking_issues
            if "conflict" in bi.issue_type.lower()
        ]
        assert len(conflict_issues) > 0

    @pytest.mark.asyncio
    async def test_resolved_conflict_does_not_block(self) -> None:
        """Candidate without unresolved conflicts should not be blocked by conflicts."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(has_conflicts=False)

        evaluation = await service.evaluate_readiness(candidate)

        # Should not have conflict blocking issue
        conflict_issues = [
            bi for bi in evaluation.blocking_issues
            if "conflict" in bi.issue_type.lower()
        ]
        assert len(conflict_issues) == 0


# ============================================================================
# Recommended Action Tests (FR-COP-READ-003)
# ============================================================================


@pytest.mark.unit
class TestRecommendedActions:
    """Test next action recommendation generation."""

    @pytest.mark.asyncio
    async def test_high_stakes_recommends_verification(self) -> None:
        """High-stakes unverified item should recommend assign_verification."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(
            risk_tier=RiskTier.HIGH_STAKES,
            verifications=[],
        )

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.recommended_action is not None
        assert evaluation.recommended_action.action_type == ActionType.ASSIGN_VERIFICATION

    @pytest.mark.asyncio
    async def test_conflict_recommends_resolution(self) -> None:
        """Candidate with conflict should recommend resolve_conflict."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(has_conflicts=True)

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.recommended_action is not None
        assert evaluation.recommended_action.action_type == ActionType.RESOLVE_CONFLICT

    @pytest.mark.asyncio
    async def test_missing_critical_recommends_add_evidence(self) -> None:
        """Candidate missing critical field should recommend add_evidence."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(fields={"where": ""})

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.recommended_action is not None
        assert evaluation.recommended_action.action_type == ActionType.ADD_EVIDENCE

    @pytest.mark.asyncio
    async def test_verified_recommends_ready_to_publish(self) -> None:
        """Verified candidate should recommend ready_to_publish."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate(
            verifications=[
                Verification(
                    verified_by=ObjectId(),
                    verified_at=datetime.now(timezone.utc),
                    verification_method="authoritative_source",
                    verification_notes="Confirmed",
                )
            ]
        )

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.recommended_action is not None
        assert evaluation.recommended_action.action_type == ActionType.READY_TO_PUBLISH


# ============================================================================
# Clarification Template Tests
# ============================================================================


@pytest.mark.unit
class TestClarificationTemplates:
    """Test clarification message template generation."""

    def test_where_clarification_template(self) -> None:
        """Should return location clarification template for 'where'."""
        service = ReadinessService(use_llm=False)
        template = service.get_clarification_template("where")

        assert template is not None
        assert len(template) > 10  # Should be a meaningful template

    def test_when_clarification_template(self) -> None:
        """Should return time clarification template for 'when'."""
        service = ReadinessService(use_llm=False)
        template = service.get_clarification_template("when")

        assert template is not None
        assert len(template) > 10

    def test_unknown_field_gets_generic_template(self) -> None:
        """Unknown field should get generic clarification template."""
        service = ReadinessService(use_llm=False)
        template = service.get_clarification_template("unknown_field")

        assert template is not None
        assert "unknown field" in template.lower() or "details" in template.lower()


# ============================================================================
# Apply Evaluation Tests
# ============================================================================


@pytest.mark.unit
class TestApplyEvaluation:
    """Test applying evaluation results to candidates."""

    @pytest.mark.asyncio
    async def test_apply_evaluation_updates_candidate_state(self) -> None:
        """Applying evaluation should update candidate's readiness state."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate()

        evaluation = await service.evaluate_readiness(candidate)
        updated = await service.apply_evaluation(candidate, evaluation)

        assert updated.readiness_state == evaluation.readiness_state
        assert updated.missing_fields == evaluation.missing_fields
        assert updated.blocking_issues == evaluation.blocking_issues

    @pytest.mark.asyncio
    async def test_apply_evaluation_sets_recommended_action(self) -> None:
        """Applying evaluation should set recommended action."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate()

        evaluation = await service.evaluate_readiness(candidate)
        updated = await service.apply_evaluation(candidate, evaluation)

        assert updated.recommended_action == evaluation.recommended_action


# ============================================================================
# Evaluation Method Tests
# ============================================================================


@pytest.mark.unit
class TestEvaluationMethod:
    """Test evaluation method selection."""

    @pytest.mark.asyncio
    async def test_rule_based_when_llm_disabled(self) -> None:
        """Should use rule-based when LLM is disabled."""
        service = ReadinessService(use_llm=False)
        candidate = make_candidate()

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.evaluation_method == "rule_based"

    @pytest.mark.asyncio
    async def test_rule_based_when_no_client(self) -> None:
        """Should use rule-based when no OpenAI client provided."""
        service = ReadinessService(openai_client=None, use_llm=True)
        candidate = make_candidate()

        evaluation = await service.evaluate_readiness(candidate)

        assert evaluation.evaluation_method == "rule_based"

    @pytest.mark.asyncio
    async def test_override_use_llm_parameter(self) -> None:
        """Should respect use_llm parameter override."""
        service = ReadinessService(use_llm=True)  # Instance defaults to LLM
        candidate = make_candidate()

        # Override to use rule-based
        evaluation = await service.evaluate_readiness(candidate, use_llm=False)

        assert evaluation.evaluation_method == "rule_based"
