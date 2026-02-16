"""Unit tests for delta summary generation.

Tests:
- FR-COPDRAFT-003: "What changed since last COP" delta summary
"""

from datetime import datetime

import pytest
from bson import ObjectId

from integritykit.services.draft import (
    ChangeType,
    COPDraft,
    COPLineItem,
    COPSection,
    COPDeltaSummary,
    DeltaChange,
    DeltaSummaryService,
    WordingStyle,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_line_item(
    candidate_id: str = None,
    headline: str = "Test headline",
    section: COPSection = COPSection.IN_REVIEW,
    status_label: str = "IN REVIEW",
) -> COPLineItem:
    """Create a test line item."""
    return COPLineItem(
        candidate_id=candidate_id or str(ObjectId()),
        status_label=status_label,
        line_item_text=headline,
        citations=["https://example.com/1"],
        wording_style=WordingStyle.HEDGED_UNCERTAIN,
        section=section,
    )


def make_draft(
    draft_id: str = None,
    verified_items: list[COPLineItem] = None,
    in_review_items: list[COPLineItem] = None,
    disproven_items: list[COPLineItem] = None,
    open_questions: list[str] = None,
) -> COPDraft:
    """Create a test draft."""
    return COPDraft(
        draft_id=draft_id or str(ObjectId()),
        workspace_id="T123",
        title="Test COP Update",
        generated_at=datetime.utcnow(),
        verified_items=verified_items or [],
        in_review_items=in_review_items or [],
        disproven_items=disproven_items or [],
        open_questions=open_questions or [],
    )


# ============================================================================
# First Draft Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestFirstDraftDelta:
    """Test delta summary for first draft (no previous)."""

    def test_first_draft_all_items_new(self) -> None:
        """First draft should mark all items as new."""
        service = DeltaSummaryService()

        draft = make_draft(
            verified_items=[make_line_item(section=COPSection.VERIFIED)],
            in_review_items=[make_line_item(), make_line_item()],
        )

        delta = service.compare_drafts(draft, previous_draft=None)

        assert delta.previous_draft_id is None
        assert len(delta.changes) == 3
        assert all(c.change_type == ChangeType.NEW for c in delta.changes)

    def test_first_draft_summary_text(self) -> None:
        """First draft should have appropriate summary text."""
        service = DeltaSummaryService()

        draft = make_draft(
            verified_items=[make_line_item(section=COPSection.VERIFIED)],
            in_review_items=[make_line_item()],
        )

        delta = service.compare_drafts(draft, previous_draft=None)

        assert "Initial COP draft" in delta.summary_text
        assert "1 verified item" in delta.summary_text
        assert "1 in-review item" in delta.summary_text


# ============================================================================
# New Items Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestNewItemsDetection:
    """Test detection of new items between drafts."""

    def test_detects_new_verified_item(self) -> None:
        """Should detect newly added verified items."""
        service = DeltaSummaryService()

        cid1 = str(ObjectId())
        cid2 = str(ObjectId())

        previous = make_draft(
            verified_items=[make_line_item(candidate_id=cid1, section=COPSection.VERIFIED)],
        )
        current = make_draft(
            verified_items=[
                make_line_item(candidate_id=cid1, section=COPSection.VERIFIED),
                make_line_item(candidate_id=cid2, section=COPSection.VERIFIED),
            ],
        )

        delta = service.compare_drafts(current, previous)

        new_items = [c for c in delta.changes if c.change_type == ChangeType.NEW]
        assert len(new_items) == 1
        assert new_items[0].candidate_id == cid2

    def test_detects_new_in_review_item(self) -> None:
        """Should detect newly added in-review items."""
        service = DeltaSummaryService()

        cid_new = str(ObjectId())

        previous = make_draft(in_review_items=[])
        current = make_draft(
            in_review_items=[make_line_item(candidate_id=cid_new)],
        )

        delta = service.compare_drafts(current, previous)

        new_items = [c for c in delta.changes if c.change_type == ChangeType.NEW]
        assert len(new_items) == 1
        assert new_items[0].new_section == COPSection.IN_REVIEW.value


# ============================================================================
# Removed Items Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestRemovedItemsDetection:
    """Test detection of removed items between drafts."""

    def test_detects_removed_item(self) -> None:
        """Should detect items removed from draft."""
        service = DeltaSummaryService()

        cid_removed = str(ObjectId())

        previous = make_draft(
            in_review_items=[make_line_item(candidate_id=cid_removed)],
        )
        current = make_draft(in_review_items=[])

        delta = service.compare_drafts(current, previous)

        removed_items = [c for c in delta.changes if c.change_type == ChangeType.REMOVED]
        assert len(removed_items) == 1
        assert removed_items[0].candidate_id == cid_removed

    def test_removed_item_includes_previous_section(self) -> None:
        """Removed items should include their previous section."""
        service = DeltaSummaryService()

        cid = str(ObjectId())

        previous = make_draft(
            verified_items=[make_line_item(candidate_id=cid, section=COPSection.VERIFIED)],
        )
        current = make_draft()

        delta = service.compare_drafts(current, previous)

        removed = [c for c in delta.changes if c.change_type == ChangeType.REMOVED][0]
        assert removed.previous_section == COPSection.VERIFIED.value


# ============================================================================
# Status Change Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestStatusChangeDetection:
    """Test detection of status changes between drafts."""

    def test_detects_verification_status_change(self) -> None:
        """Should detect when item status changes."""
        service = DeltaSummaryService()

        cid = str(ObjectId())

        previous = make_draft(
            in_review_items=[
                make_line_item(candidate_id=cid, status_label="IN REVIEW")
            ],
        )
        # Same section, different status
        item = make_line_item(candidate_id=cid, status_label="PENDING VERIFICATION")
        current = make_draft(in_review_items=[item])

        delta = service.compare_drafts(current, previous)

        status_changes = [
            c for c in delta.changes
            if c.change_type == ChangeType.STATUS_CHANGE
        ]
        assert len(status_changes) == 1
        assert status_changes[0].previous_status == "IN REVIEW"
        assert status_changes[0].new_status == "PENDING VERIFICATION"


# ============================================================================
# Section Move Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestSectionMoveDetection:
    """Test detection of section moves between drafts."""

    def test_detects_move_to_verified(self) -> None:
        """Should detect item moving to verified section."""
        service = DeltaSummaryService()

        cid = str(ObjectId())

        previous = make_draft(
            in_review_items=[make_line_item(candidate_id=cid)],
        )
        current = make_draft(
            verified_items=[
                make_line_item(
                    candidate_id=cid,
                    section=COPSection.VERIFIED,
                    status_label="VERIFIED",
                )
            ],
        )

        delta = service.compare_drafts(current, previous)

        moves = [c for c in delta.changes if c.change_type == ChangeType.SECTION_MOVE]
        assert len(moves) == 1
        assert moves[0].previous_section == COPSection.IN_REVIEW.value
        assert moves[0].new_section == COPSection.VERIFIED.value

    def test_detects_move_to_disproven(self) -> None:
        """Should detect item moving to disproven section."""
        service = DeltaSummaryService()

        cid = str(ObjectId())

        previous = make_draft(
            in_review_items=[make_line_item(candidate_id=cid)],
        )
        current = make_draft(
            disproven_items=[
                make_line_item(
                    candidate_id=cid,
                    section=COPSection.DISPROVEN,
                    status_label="DISPROVEN",
                )
            ],
        )

        delta = service.compare_drafts(current, previous)

        moves = [c for c in delta.changes if c.change_type == ChangeType.SECTION_MOVE]
        assert len(moves) == 1
        assert moves[0].new_section == COPSection.DISPROVEN.value


# ============================================================================
# Content Update Tests (FR-COPDRAFT-003)
# ============================================================================


@pytest.mark.unit
class TestContentUpdateDetection:
    """Test detection of content updates between drafts."""

    def test_detects_text_change(self) -> None:
        """Should detect when line item text changes."""
        service = DeltaSummaryService()

        cid = str(ObjectId())

        previous = make_draft(
            in_review_items=[
                make_line_item(candidate_id=cid, headline="Original text")
            ],
        )
        current = make_draft(
            in_review_items=[
                make_line_item(candidate_id=cid, headline="Updated text with more details")
            ],
        )

        delta = service.compare_drafts(current, previous)

        updates = [c for c in delta.changes if c.change_type == ChangeType.CONTENT_UPDATE]
        assert len(updates) == 1


# ============================================================================
# Delta Summary Properties Tests
# ============================================================================


@pytest.mark.unit
class TestDeltaSummaryProperties:
    """Test delta summary computed properties."""

    def test_has_changes_true(self) -> None:
        """has_changes should be True when changes exist."""
        delta = COPDeltaSummary(
            current_draft_id="current",
            previous_draft_id="previous",
            generated_at=datetime.utcnow(),
            changes=[
                DeltaChange(
                    change_type=ChangeType.NEW,
                    candidate_id="123",
                    headline="Test",
                )
            ],
            summary_text="Test",
        )

        assert delta.has_changes is True

    def test_has_changes_false(self) -> None:
        """has_changes should be False when no changes."""
        delta = COPDeltaSummary(
            current_draft_id="current",
            previous_draft_id="previous",
            generated_at=datetime.utcnow(),
            changes=[],
            summary_text="No changes",
        )

        assert delta.has_changes is False

    def test_count_properties(self) -> None:
        """Count properties should correctly count change types."""
        delta = COPDeltaSummary(
            current_draft_id="current",
            previous_draft_id="previous",
            generated_at=datetime.utcnow(),
            changes=[
                DeltaChange(change_type=ChangeType.NEW, candidate_id="1", headline="A"),
                DeltaChange(change_type=ChangeType.NEW, candidate_id="2", headline="B"),
                DeltaChange(change_type=ChangeType.REMOVED, candidate_id="3", headline="C"),
                DeltaChange(change_type=ChangeType.STATUS_CHANGE, candidate_id="4", headline="D"),
            ],
            summary_text="Test",
        )

        assert delta.new_items_count == 2
        assert delta.removed_items_count == 1
        assert delta.status_changes_count == 1


# ============================================================================
# Markdown Output Tests
# ============================================================================


@pytest.mark.unit
class TestDeltaMarkdownOutput:
    """Test markdown output generation."""

    def test_markdown_includes_sections(self) -> None:
        """Markdown should include sections for each change type."""
        service = DeltaSummaryService()

        cid_new = str(ObjectId())
        cid_removed = str(ObjectId())

        previous = make_draft(
            in_review_items=[make_line_item(candidate_id=cid_removed)],
        )
        current = make_draft(
            verified_items=[make_line_item(candidate_id=cid_new, section=COPSection.VERIFIED)],
        )

        delta = service.compare_drafts(current, previous)
        markdown = delta.to_markdown()

        assert "New Items" in markdown
        assert "Removed Items" in markdown

    def test_markdown_no_changes_message(self) -> None:
        """Markdown should show no changes message when empty."""
        delta = COPDeltaSummary(
            current_draft_id="current",
            previous_draft_id="previous",
            generated_at=datetime.utcnow(),
            changes=[],
            summary_text="No changes",
        )

        markdown = delta.to_markdown()

        assert "No changes" in markdown
