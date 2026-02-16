"""
Integration tests for COP candidate lifecycle through draft generation.

Tests the complete workflow from signal cluster to published COP draft,
including:
- Candidate creation from clusters
- Readiness evaluation and state transitions
- Draft generation with verification-aware wording
- Section assembly and output formatting

These tests use mongomock for database operations.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
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
from integritykit.services.draft import COPSection, DraftService, WordingStyle
from integritykit.services.readiness import ReadinessService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_candidate(
    *,
    what: str = "Bridge closure on Main Street",
    where: str = "123 Main St, Springfield, IL",
    when_desc: str = "As of 2pm today",
    who: str = "City Public Works Department",
    so_what: str = "Traffic rerouted via Oak Avenue",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    evidence_count: int = 1,
    has_verification: bool = False,
    has_conflicts: bool = False,
) -> COPCandidate:
    """Create a test COPCandidate with configurable state."""
    slack_permalinks = [
        SlackPermalink(
            url=f"https://workspace.slack.com/archives/C123/p{i}",
            signal_id=ObjectId(),
            description=f"Source {i}",
        )
        for i in range(evidence_count)
    ]

    verifications = []
    if has_verification:
        verifications = [
            Verification(
                verified_by=ObjectId(),
                verified_at=datetime.now(timezone.utc),
                verification_method="authoritative_source",
                verification_notes="Confirmed via official source",
            )
        ]

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
        readiness_state=readiness_state,
        readiness_updated_at=datetime.now(timezone.utc),
        readiness_updated_by=ObjectId(),
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(
                timestamp=datetime.now(timezone.utc),
                timezone="America/Chicago",
                is_approximate=False,
                description=when_desc,
            ),
            who=who,
            so_what=so_what,
        ),
        evidence=Evidence(
            slack_permalinks=slack_permalinks,
            external_sources=[],
        ),
        verifications=verifications,
        conflicts=conflicts,
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# Candidate Lifecycle Integration Tests
# ============================================================================


@pytest.mark.integration
class TestCandidateLifecycle:
    """Test complete candidate lifecycle from creation to draft."""

    @pytest.mark.asyncio
    async def test_new_candidate_evaluates_to_in_review(self) -> None:
        """New candidate with complete fields should evaluate to IN_REVIEW."""
        readiness_service = ReadinessService(use_llm=False)
        candidate = create_test_candidate()

        evaluation = await readiness_service.evaluate_readiness(candidate)
        updated = await readiness_service.apply_evaluation(candidate, evaluation)

        assert updated.readiness_state == ReadinessState.IN_REVIEW
        assert evaluation.recommended_action is not None
        assert evaluation.recommended_action.action_type == ActionType.ASSIGN_VERIFICATION

    @pytest.mark.asyncio
    async def test_verified_candidate_transitions_to_verified(self) -> None:
        """Candidate with verification record should evaluate to VERIFIED."""
        readiness_service = ReadinessService(use_llm=False)
        candidate = create_test_candidate(has_verification=True)

        evaluation = await readiness_service.evaluate_readiness(candidate)
        updated = await readiness_service.apply_evaluation(candidate, evaluation)

        assert updated.readiness_state == ReadinessState.VERIFIED
        assert evaluation.recommended_action.action_type == ActionType.READY_TO_PUBLISH

    @pytest.mark.asyncio
    async def test_conflict_blocks_candidate(self) -> None:
        """Candidate with unresolved conflict should be BLOCKED."""
        readiness_service = ReadinessService(use_llm=False)
        candidate = create_test_candidate(has_conflicts=True)

        evaluation = await readiness_service.evaluate_readiness(candidate)
        updated = await readiness_service.apply_evaluation(candidate, evaluation)

        assert updated.readiness_state == ReadinessState.BLOCKED
        assert evaluation.recommended_action.action_type == ActionType.RESOLVE_CONFLICT
        assert any(
            bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING
            for bi in updated.blocking_issues
        )

    @pytest.mark.asyncio
    async def test_high_stakes_requires_verification(self) -> None:
        """High-stakes candidate without verification should be BLOCKED."""
        readiness_service = ReadinessService(use_llm=False)
        candidate = create_test_candidate(
            risk_tier=RiskTier.HIGH_STAKES,
            has_verification=False,
        )

        evaluation = await readiness_service.evaluate_readiness(candidate)
        updated = await readiness_service.apply_evaluation(candidate, evaluation)

        assert updated.readiness_state == ReadinessState.BLOCKED
        assert evaluation.recommended_action.action_type == ActionType.ASSIGN_VERIFICATION


# ============================================================================
# Readiness to Draft Pipeline Tests
# ============================================================================


@pytest.mark.integration
class TestReadinessToDraftPipeline:
    """Test pipeline from readiness evaluation to draft generation."""

    @pytest.mark.asyncio
    async def test_verified_candidate_generates_direct_wording(self) -> None:
        """Verified candidate should generate direct wording in draft."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_verification=True)

        # Evaluate readiness
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate line item
        line_item = await draft_service.generate_line_item(candidate)

        assert candidate.readiness_state == ReadinessState.VERIFIED
        assert line_item.wording_style == WordingStyle.DIRECT_FACTUAL
        assert line_item.section == COPSection.VERIFIED
        assert "Unconfirmed" not in line_item.line_item_text

    @pytest.mark.asyncio
    async def test_in_review_candidate_generates_hedged_wording(self) -> None:
        """In-review candidate should generate hedged wording in draft."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_verification=False)

        # Evaluate readiness
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate line item
        line_item = await draft_service.generate_line_item(candidate)

        assert candidate.readiness_state == ReadinessState.IN_REVIEW
        assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN
        assert line_item.section == COPSection.IN_REVIEW
        assert "Unconfirmed" in line_item.line_item_text

    @pytest.mark.asyncio
    async def test_blocked_candidate_excluded_from_main_sections(self) -> None:
        """Blocked candidate should go to open questions, not main sections."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_conflicts=True)

        # Evaluate readiness
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate line item
        line_item = await draft_service.generate_line_item(candidate)

        assert candidate.readiness_state == ReadinessState.BLOCKED
        assert line_item.section == COPSection.OPEN_QUESTIONS


# ============================================================================
# Multi-Candidate Draft Assembly Tests
# ============================================================================


@pytest.mark.integration
class TestDraftAssemblyPipeline:
    """Test draft assembly with multiple candidates."""

    @pytest.mark.asyncio
    async def test_draft_separates_verified_and_in_review(self) -> None:
        """Draft should separate verified and in-review items."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidates = [
            create_test_candidate(
                what="Bridge closure confirmed",
                has_verification=True,
            ),
            create_test_candidate(
                what="Power outage reported",
                has_verification=False,
            ),
            create_test_candidate(
                what="Shelter status unclear",
                has_verification=False,
            ),
        ]

        # Evaluate and apply readiness for all
        for i, candidate in enumerate(candidates):
            evaluation = await readiness_service.evaluate_readiness(candidate)
            candidates[i] = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate draft
        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=candidates,
        )

        assert len(draft.verified_items) == 1
        assert len(draft.in_review_items) == 2
        assert draft.total_items == 3

    @pytest.mark.asyncio
    async def test_draft_markdown_has_all_sections(self) -> None:
        """Draft markdown should include all populated sections."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidates = [
            create_test_candidate(what="Verified situation", has_verification=True),
            create_test_candidate(what="Unverified report", has_verification=False),
        ]

        # Evaluate readiness
        for i, candidate in enumerate(candidates):
            evaluation = await readiness_service.evaluate_readiness(candidate)
            candidates[i] = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate draft
        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=candidates,
            title="Crisis Update #5",
        )

        markdown = draft.to_markdown()

        assert "# Crisis Update #5" in markdown
        assert "## Verified Updates" in markdown
        assert "## In Review" in markdown

    @pytest.mark.asyncio
    async def test_draft_slack_blocks_structure(self) -> None:
        """Draft Slack blocks should have proper structure."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_verification=True)
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=[candidate],
        )

        blocks = draft.to_slack_blocks()

        # Should have header
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1

        # Should have section blocks
        section_blocks = [b for b in blocks if b.get("type") == "section"]
        assert len(section_blocks) >= 1


# ============================================================================
# End-to-End Workflow Tests
# ============================================================================


@pytest.mark.integration
class TestEndToEndWorkflow:
    """Test complete end-to-end workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_verified_item(self) -> None:
        """Test full workflow: create -> evaluate -> draft for verified item."""
        # 1. Create candidate
        candidate = create_test_candidate(
            what="Water main break repaired",
            where="456 Oak Avenue",
            when_desc="Completed at 3pm",
            who="City Water Department",
            so_what="Water service restored to 200 homes",
            has_verification=True,
        )

        # 2. Evaluate readiness
        readiness_service = ReadinessService(use_llm=False)
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        # 3. Verify state
        assert candidate.readiness_state == ReadinessState.VERIFIED
        # May have warnings but no blocking issues
        blocking_issues = [
            bi for bi in candidate.blocking_issues
            if bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING
        ]
        assert len(blocking_issues) == 0
        assert candidate.recommended_action.action_type == ActionType.READY_TO_PUBLISH

        # 4. Generate line item
        draft_service = DraftService(use_llm=False)
        line_item = await draft_service.generate_line_item(candidate)

        # 5. Verify line item
        assert line_item.status_label == "VERIFIED"
        assert line_item.wording_style == WordingStyle.DIRECT_FACTUAL
        assert "Water main break repaired" in line_item.line_item_text
        assert "Source: City Water Department" in line_item.line_item_text
        assert len(line_item.citations) == 1

        # 6. Generate draft
        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=[candidate],
            title="Situation Update",
        )

        # 7. Verify draft
        assert len(draft.verified_items) == 1
        assert len(draft.in_review_items) == 0
        assert "Water main break repaired" in draft.to_markdown()

    @pytest.mark.asyncio
    async def test_full_workflow_blocked_item(self) -> None:
        """Test full workflow for blocked item with conflicts."""
        # 1. Create candidate with conflict
        candidate = create_test_candidate(
            what="Road status disputed",
            has_conflicts=True,
        )

        # 2. Evaluate readiness
        readiness_service = ReadinessService(use_llm=False)
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        # 3. Verify blocked state
        assert candidate.readiness_state == ReadinessState.BLOCKED
        assert len(candidate.blocking_issues) > 0
        assert candidate.recommended_action.action_type == ActionType.RESOLVE_CONFLICT

        # 4. Generate draft with blocked item
        draft_service = DraftService(use_llm=False)
        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=[candidate],
            include_open_questions=True,
        )

        # 5. Verify draft has open question
        assert len(draft.verified_items) == 0
        assert len(draft.in_review_items) == 0
        assert len(draft.open_questions) > 0

    @pytest.mark.asyncio
    async def test_mixed_candidates_workflow(self) -> None:
        """Test workflow with mix of verified, in-review, and blocked items."""
        candidates = [
            # Verified
            create_test_candidate(
                what="Hospital capacity normal",
                has_verification=True,
            ),
            # In-review
            create_test_candidate(
                what="Reports of flooding downtown",
                has_verification=False,
            ),
            # Blocked (missing field)
            create_test_candidate(
                what="",  # Missing critical field
                where="Unknown location",
            ),
            # Blocked (high-stakes without verification)
            create_test_candidate(
                what="Evacuation order possible",
                risk_tier=RiskTier.HIGH_STAKES,
                has_verification=False,
            ),
        ]

        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        # Evaluate all
        for i, candidate in enumerate(candidates):
            evaluation = await readiness_service.evaluate_readiness(candidate)
            candidates[i] = await readiness_service.apply_evaluation(candidate, evaluation)

        # Generate draft
        draft = await draft_service.generate_draft(
            workspace_id="W12345",
            candidates=candidates,
            include_open_questions=True,
        )

        # Should have 1 verified, 1 in-review, 2 blocked -> open questions
        assert len(draft.verified_items) == 1
        assert len(draft.in_review_items) == 1
        assert len(draft.open_questions) >= 2  # At least 2 blocked items

        # Verify wording styles
        assert draft.verified_items[0].wording_style == WordingStyle.DIRECT_FACTUAL
        assert draft.in_review_items[0].wording_style == WordingStyle.HEDGED_UNCERTAIN


# ============================================================================
# Draft Persistence Tests
# ============================================================================


@pytest.mark.integration
class TestDraftWordingPersistence:
    """Test saving draft wording back to candidates."""

    @pytest.mark.asyncio
    async def test_save_draft_wording_persists(self) -> None:
        """Draft wording should be saved to candidate."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_verification=True)

        # Evaluate and generate
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)
        line_item = await draft_service.generate_line_item(candidate)

        # Save wording
        candidate = draft_service.save_draft_wording(candidate, line_item)

        # Verify persisted
        assert candidate.draft_wording is not None
        assert candidate.draft_wording.body == line_item.line_item_text
        assert candidate.draft_wording.hedging_applied is False  # Verified = no hedging

    @pytest.mark.asyncio
    async def test_hedged_wording_marked_as_hedged(self) -> None:
        """In-review items should be marked as hedged."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidate = create_test_candidate(has_verification=False)

        # Evaluate and generate
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)
        line_item = await draft_service.generate_line_item(candidate)

        # Save wording
        candidate = draft_service.save_draft_wording(candidate, line_item)

        # Verify hedging marked
        assert candidate.draft_wording.hedging_applied is True
