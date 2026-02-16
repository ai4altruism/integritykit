"""
Unit tests for COP draft generation service.

Tests:
- FR-COPDRAFT-001: Generate COP line items with status labels and citations
- FR-COPDRAFT-002: Assemble drafts grouped by section
- FR-COP-WORDING-001: Wording guidance (hedged vs direct phrasing)
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ExternalSource,
    ReadinessState,
    RiskTier,
    SlackPermalink,
    Verification,
)
from integritykit.services.draft import (
    COPDraft,
    COPLineItem,
    COPSection,
    DraftService,
    WordingStyle,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candidate(
    *,
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    what: str = "Bridge closure on Main Street",
    where: str = "123 Main St, Springfield, IL",
    when_desc: str = "As of 2pm today",
    who: str = "City Public Works Department",
    so_what: str = "Traffic rerouted via Oak Avenue",
    evidence_count: int = 1,
    external_sources: int = 0,
    has_verification: bool = False,
) -> COPCandidate:
    """Create a COPCandidate for testing."""
    # Build evidence
    slack_permalinks = [
        SlackPermalink(
            url=f"https://workspace.slack.com/archives/C123/p{i}00000",
            signal_id=ObjectId(),
            description=f"Source message {i}",
        )
        for i in range(evidence_count)
    ]

    ext_sources = [
        ExternalSource(
            url=f"https://example.com/source{i}",
            source_name=f"Source {i}",
            description=f"External source {i}",
            retrieved_at=datetime.now(timezone.utc),
        )
        for i in range(external_sources)
    ]

    evidence = Evidence(
        slack_permalinks=slack_permalinks,
        external_sources=ext_sources,
    )

    # Build verifications
    verifications = []
    if has_verification:
        verifications = [
            Verification(
                verified_by=ObjectId(),
                verified_at=datetime.now(timezone.utc),
                verification_method="authoritative_source",
                verification_notes="Confirmed",
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
        evidence=evidence,
        verifications=verifications,
        conflicts=[],
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# Line Item Generation Tests (FR-COPDRAFT-001)
# ============================================================================


@pytest.mark.unit
class TestLineItemGeneration:
    """Test COP line item generation."""

    @pytest.mark.asyncio
    async def test_generate_line_item_verified(self) -> None:
        """Verified candidate should generate line item with VERIFIED label."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        )

        line_item = await service.generate_line_item(candidate)

        assert line_item.status_label == "VERIFIED"
        assert line_item.section == COPSection.VERIFIED
        assert line_item.wording_style == WordingStyle.DIRECT_FACTUAL

    @pytest.mark.asyncio
    async def test_generate_line_item_in_review(self) -> None:
        """In-review candidate should generate line item with IN REVIEW label."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(readiness_state=ReadinessState.IN_REVIEW)

        line_item = await service.generate_line_item(candidate)

        assert line_item.status_label == "IN REVIEW"
        assert line_item.section == COPSection.IN_REVIEW
        assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN

    @pytest.mark.asyncio
    async def test_generate_line_item_blocked(self) -> None:
        """Blocked candidate should generate line item for OPEN_QUESTIONS."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(readiness_state=ReadinessState.BLOCKED)

        line_item = await service.generate_line_item(candidate)

        assert line_item.status_label == "BLOCKED"
        assert line_item.section == COPSection.OPEN_QUESTIONS
        assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN

    @pytest.mark.asyncio
    async def test_line_item_has_candidate_id(self) -> None:
        """Line item should include candidate ID."""
        service = DraftService(use_llm=False)
        candidate = make_candidate()

        line_item = await service.generate_line_item(candidate)

        assert line_item.candidate_id == str(candidate.id)

    @pytest.mark.asyncio
    async def test_line_item_has_generated_at(self) -> None:
        """Line item should include generation timestamp."""
        service = DraftService(use_llm=False)
        candidate = make_candidate()

        line_item = await service.generate_line_item(candidate)

        assert line_item.generated_at is not None
        assert isinstance(line_item.generated_at, datetime)


# ============================================================================
# Citation Tests (FR-COPDRAFT-001)
# ============================================================================


@pytest.mark.unit
class TestCitations:
    """Test citation generation in line items."""

    @pytest.mark.asyncio
    async def test_citations_from_slack_permalinks(self) -> None:
        """Line item should include Slack permalink citations."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(evidence_count=2)

        line_item = await service.generate_line_item(candidate)

        assert len(line_item.citations) == 2
        assert all("slack.com" in url for url in line_item.citations)

    @pytest.mark.asyncio
    async def test_citations_from_external_sources(self) -> None:
        """Line item should include external source citations."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(evidence_count=0, external_sources=2)

        line_item = await service.generate_line_item(candidate)

        assert len(line_item.citations) == 2
        assert all("example.com" in url for url in line_item.citations)

    @pytest.mark.asyncio
    async def test_citations_combined(self) -> None:
        """Line item should combine Slack and external citations."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(evidence_count=1, external_sources=1)

        line_item = await service.generate_line_item(candidate)

        assert len(line_item.citations) == 2

    @pytest.mark.asyncio
    async def test_citation_markers_in_text(self) -> None:
        """Line item text should include citation markers."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(evidence_count=2)

        line_item = await service.generate_line_item(candidate)

        # Should have [1] [2] markers
        assert "[1]" in line_item.line_item_text
        assert "[2]" in line_item.line_item_text


# ============================================================================
# Wording Guidance Tests (FR-COP-WORDING-001)
# ============================================================================


@pytest.mark.unit
class TestWordingGuidance:
    """Test verification-aware wording guidance."""

    @pytest.mark.asyncio
    async def test_verified_uses_direct_phrasing(self) -> None:
        """Verified items should use direct, factual phrasing."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
            what="Bridge is closed",
            where="Main Street",
        )

        line_item = await service.generate_line_item(candidate)

        # Should NOT have hedging language
        assert "Unconfirmed" not in line_item.line_item_text
        assert "Reports indicate" not in line_item.line_item_text
        # Should have direct statement
        assert "Bridge is closed" in line_item.line_item_text

    @pytest.mark.asyncio
    async def test_in_review_uses_hedged_phrasing(self) -> None:
        """In-review items should use hedged, uncertain phrasing."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.IN_REVIEW,
            what="Bridge is closed",
            where="Main Street",
        )

        line_item = await service.generate_line_item(candidate)

        # Should have hedging language
        assert "Unconfirmed:" in line_item.line_item_text
        assert "Reports indicate" in line_item.line_item_text
        # Should use "may be" instead of "is"
        assert "may be" in line_item.line_item_text.lower()

    @pytest.mark.asyncio
    async def test_hedged_includes_conditional_so_what(self) -> None:
        """Hedged items should frame so_what conditionally."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.IN_REVIEW,
            so_what="Traffic rerouted via Oak Avenue",
        )

        line_item = await service.generate_line_item(candidate)

        # Should have conditional framing
        assert "If confirmed" in line_item.line_item_text

    @pytest.mark.asyncio
    async def test_verified_includes_source_attribution(self) -> None:
        """Verified items should include source attribution."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
            who="City Public Works Department",
        )

        line_item = await service.generate_line_item(candidate)

        # Should include source
        assert "Source:" in line_item.line_item_text
        assert "City Public Works" in line_item.line_item_text


# ============================================================================
# High-Stakes Line Item Tests
# ============================================================================


@pytest.mark.unit
class TestHighStakesLineItems:
    """Test high-stakes item handling in line items."""

    @pytest.mark.asyncio
    async def test_high_stakes_in_review_has_next_step(self) -> None:
        """High-stakes in-review items should include next verification step."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        line_item = await service.generate_line_item(candidate)

        assert line_item.next_verification_step is not None

    @pytest.mark.asyncio
    async def test_high_stakes_in_review_has_recheck_time(self) -> None:
        """High-stakes in-review items should include urgent recheck time."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        line_item = await service.generate_line_item(candidate)

        # High-stakes should have 30-minute recheck (FR-COP-WORDING-002)
        assert line_item.recheck_time is not None
        assert "30 minutes" in line_item.recheck_time.lower()
        # Should also have URGENT next step
        assert line_item.next_verification_step is not None
        assert "URGENT" in line_item.next_verification_step

    @pytest.mark.asyncio
    async def test_routine_in_review_has_optional_next_step(self) -> None:
        """Routine in-review items have optional next step and 4-hour recheck."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.ROUTINE,
        )

        line_item = await service.generate_line_item(candidate)

        # Routine items get 4-hour recheck (FR-COP-WORDING-002)
        assert line_item.recheck_time is not None
        assert "4 hours" in line_item.recheck_time.lower()
        # May or may not have next step depending on verifications
        # (no verifications = has next step, has verifications = may not)


# ============================================================================
# Draft Assembly Tests (FR-COPDRAFT-002)
# ============================================================================


@pytest.mark.unit
class TestDraftAssembly:
    """Test COP draft assembly from multiple candidates."""

    @pytest.mark.asyncio
    async def test_draft_groups_by_section(self) -> None:
        """Draft should group items by verification section."""
        service = DraftService(use_llm=False)
        candidates = [
            make_candidate(
                readiness_state=ReadinessState.VERIFIED,
                has_verification=True,
            ),
            make_candidate(readiness_state=ReadinessState.IN_REVIEW),
            make_candidate(readiness_state=ReadinessState.IN_REVIEW),
        ]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        assert len(draft.verified_items) == 1
        assert len(draft.in_review_items) == 2
        assert draft.total_items == 3

    @pytest.mark.asyncio
    async def test_draft_has_title(self) -> None:
        """Draft should have a title."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        assert draft.title is not None
        assert "COP Update" in draft.title

    @pytest.mark.asyncio
    async def test_draft_custom_title(self) -> None:
        """Draft should accept custom title."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
            title="Emergency Situation Update",
        )

        assert draft.title == "Emergency Situation Update"

    @pytest.mark.asyncio
    async def test_draft_has_workspace_id(self) -> None:
        """Draft should include workspace ID."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W12345",
            candidates=candidates,
        )

        assert draft.workspace_id == "W12345"

    @pytest.mark.asyncio
    async def test_draft_has_draft_id(self) -> None:
        """Draft should have unique ID."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        assert draft.draft_id is not None
        assert len(draft.draft_id) > 0

    @pytest.mark.asyncio
    async def test_draft_has_generated_at(self) -> None:
        """Draft should have generation timestamp."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        assert draft.generated_at is not None
        assert isinstance(draft.generated_at, datetime)


# ============================================================================
# Open Questions Section Tests
# ============================================================================


@pytest.mark.unit
class TestOpenQuestions:
    """Test open questions section in drafts."""

    @pytest.mark.asyncio
    async def test_blocked_items_create_open_questions(self) -> None:
        """Blocked items should create open questions entries."""
        service = DraftService(use_llm=False)
        candidates = [
            make_candidate(
                readiness_state=ReadinessState.BLOCKED,
                what="Shelter status unclear",
            ),
        ]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
            include_open_questions=True,
        )

        assert len(draft.open_questions) > 0

    @pytest.mark.asyncio
    async def test_exclude_open_questions(self) -> None:
        """Should be able to exclude open questions section."""
        service = DraftService(use_llm=False)
        candidates = [
            make_candidate(readiness_state=ReadinessState.BLOCKED),
        ]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
            include_open_questions=False,
        )

        # Should not have open questions from blocked items
        assert len(draft.open_questions) == 0

    @pytest.mark.asyncio
    async def test_empty_draft_adds_open_question(self) -> None:
        """Draft with no items should note the gap."""
        service = DraftService(use_llm=False)

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[],
            include_open_questions=True,
        )

        assert len(draft.open_questions) > 0
        assert any("no" in q.lower() and "item" in q.lower() for q in draft.open_questions)


# ============================================================================
# Draft Output Format Tests
# ============================================================================


@pytest.mark.unit
class TestDraftOutputFormats:
    """Test draft output format conversions."""

    @pytest.mark.asyncio
    async def test_to_markdown_has_sections(self) -> None:
        """Markdown output should have section headers."""
        service = DraftService(use_llm=False)
        candidates = [
            make_candidate(
                readiness_state=ReadinessState.VERIFIED,
                has_verification=True,
            ),
            make_candidate(readiness_state=ReadinessState.IN_REVIEW),
        ]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )
        markdown = draft.to_markdown()

        assert "# " in markdown  # Has header
        assert "## Verified Updates" in markdown
        assert "## In Review" in markdown

    @pytest.mark.asyncio
    async def test_to_markdown_has_title(self) -> None:
        """Markdown output should start with title."""
        service = DraftService(use_llm=False)
        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
            title="Test Update",
        )

        markdown = draft.to_markdown()

        assert markdown.startswith("# Test Update")

    @pytest.mark.asyncio
    async def test_to_markdown_has_timestamp(self) -> None:
        """Markdown output should include generation timestamp."""
        service = DraftService(use_llm=False)
        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
        )

        markdown = draft.to_markdown()

        assert "*Generated:" in markdown

    @pytest.mark.asyncio
    async def test_to_slack_blocks_is_list(self) -> None:
        """Slack blocks output should be a list."""
        service = DraftService(use_llm=False)
        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
        )

        blocks = draft.to_slack_blocks()

        assert isinstance(blocks, list)
        assert len(blocks) > 0

    @pytest.mark.asyncio
    async def test_to_slack_blocks_has_header(self) -> None:
        """Slack blocks should include header block."""
        service = DraftService(use_llm=False)
        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
        )

        blocks = draft.to_slack_blocks()

        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) > 0

    @pytest.mark.asyncio
    async def test_to_slack_blocks_has_sections(self) -> None:
        """Slack blocks should include section blocks."""
        service = DraftService(use_llm=False)
        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
        )

        blocks = draft.to_slack_blocks()

        section_blocks = [b for b in blocks if b.get("type") == "section"]
        assert len(section_blocks) > 0


# ============================================================================
# Draft Metadata Tests
# ============================================================================


@pytest.mark.unit
class TestDraftMetadata:
    """Test draft metadata tracking."""

    @pytest.mark.asyncio
    async def test_metadata_includes_candidate_count(self) -> None:
        """Metadata should include candidate count."""
        service = DraftService(use_llm=False)
        candidates = [make_candidate(), make_candidate()]

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=candidates,
        )

        assert draft.metadata.get("candidate_count") == 2

    @pytest.mark.asyncio
    async def test_metadata_includes_generator_model(self) -> None:
        """Metadata should indicate generator method."""
        service = DraftService(use_llm=False)

        draft = await service.generate_draft(
            workspace_id="W123",
            candidates=[make_candidate()],
        )

        assert draft.metadata.get("generator_model") == "rule_based"


# ============================================================================
# Save Draft Wording Tests
# ============================================================================


@pytest.mark.unit
class TestSaveDraftWording:
    """Test saving draft wording to candidate."""

    @pytest.mark.asyncio
    async def test_save_draft_wording_updates_candidate(self) -> None:
        """Saving draft wording should update candidate's draft_wording field."""
        service = DraftService(use_llm=False)
        candidate = make_candidate()
        line_item = await service.generate_line_item(candidate)

        updated = service.save_draft_wording(candidate, line_item)

        assert updated.draft_wording is not None
        assert updated.draft_wording.body == line_item.line_item_text

    @pytest.mark.asyncio
    async def test_save_draft_wording_tracks_hedging(self) -> None:
        """Saving draft wording should track if hedging was applied."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(readiness_state=ReadinessState.IN_REVIEW)
        line_item = await service.generate_line_item(candidate)

        updated = service.save_draft_wording(candidate, line_item)

        assert updated.draft_wording.hedging_applied is True

    @pytest.mark.asyncio
    async def test_save_draft_wording_no_hedging_for_verified(self) -> None:
        """Verified items should not have hedging applied."""
        service = DraftService(use_llm=False)
        candidate = make_candidate(
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        )
        line_item = await service.generate_line_item(candidate)

        updated = service.save_draft_wording(candidate, line_item)

        assert updated.draft_wording.hedging_applied is False
