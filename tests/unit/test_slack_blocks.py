"""Unit tests for Slack Block Kit UI builders.

Tests:
- build_fields_checklist_blocks: Missing/weak fields checklist UI
- build_readiness_summary_blocks: Readiness status display
- build_next_action_blocks: Recommended action display
- build_candidate_detail_blocks: Full candidate detail view
- build_candidate_list_item_blocks: Compact list item view
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    BlockingIssueSeverity,
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RecommendedAction,
    RiskTier,
    Verification,
    VerificationMethod,
)
from integritykit.services.readiness import (
    FieldEvaluation,
    FieldStatus,
    ReadinessEvaluation,
)
from integritykit.slack.blocks import (
    build_candidate_detail_blocks,
    build_candidate_list_item_blocks,
    build_fields_checklist_blocks,
    build_next_action_blocks,
    build_readiness_summary_blocks,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cop_candidate(
    *,
    candidate_id: ObjectId | None = None,
    what: str = "Test event",
    where: str = "Test location",
    when_description: str = "Today",
    who: str = "Test people",
    so_what: str = "Test impact",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    verifications: list[Verification] | None = None,
    blocking_issues: list[BlockingIssue] | None = None,
) -> COPCandidate:
    """Create a test COP candidate.

    Note: Due to use_enum_values=True in the model config, enum fields are
    automatically converted to their string values.
    """
    candidate = COPCandidate(
        id=candidate_id or ObjectId(),
        cluster_id=ObjectId(),
        created_by=ObjectId(),
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(description=when_description),
            who=who,
            so_what=so_what,
        ),
        evidence=Evidence(),
        verifications=verifications or [],
        blocking_issues=blocking_issues or [],
    )
    # Model automatically converts enums to strings via use_enum_values=True
    return candidate


def make_field_evaluation(
    field: str,
    status: FieldStatus,
    value: str | None = None,
    notes: str = "",
) -> FieldEvaluation:
    """Create a test field evaluation."""
    return FieldEvaluation(
        field=field,
        status=status,
        value=value,
        notes=notes,
    )


def make_readiness_evaluation(
    candidate: COPCandidate,
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    field_evaluations: list[FieldEvaluation] | None = None,
    missing_fields: list[str] | None = None,
    blocking_issues: list[BlockingIssue] | None = None,
    recommended_action: RecommendedAction | None = None,
    explanation: str = "Test evaluation",
) -> ReadinessEvaluation:
    """Create a test readiness evaluation."""
    return ReadinessEvaluation(
        candidate_id=str(candidate.id),
        readiness_state=readiness_state,
        field_evaluations=field_evaluations or [],
        missing_fields=missing_fields or [],
        blocking_issues=blocking_issues or [],
        recommended_action=recommended_action,
        explanation=explanation,
        evaluated_at=datetime.now(timezone.utc),
        evaluation_method="rule_based",
    )


# ============================================================================
# build_fields_checklist_blocks() Tests
# ============================================================================


@pytest.mark.unit
class TestFieldsChecklistBlocks:
    """Test build_fields_checklist_blocks() function."""

    def test_all_fields_complete(self) -> None:
        """Checklist shows all complete when all fields are good."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
            make_field_evaluation("where", FieldStatus.COMPLETE, "Test location"),
            make_field_evaluation("when", FieldStatus.COMPLETE, "Today"),
            make_field_evaluation("who", FieldStatus.COMPLETE, "Test people"),
            make_field_evaluation("so_what", FieldStatus.COMPLETE, "Test impact"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Should have header, summary, divider, and 5 field sections
        assert len(blocks) >= 7
        assert blocks[0]["type"] == "header"
        assert "Field Completeness Checklist" in blocks[0]["text"]["text"]

        # Summary should be positive
        summary_text = blocks[1]["text"]["text"]
        assert ":white_check_mark:" in summary_text
        assert "All fields are complete" in summary_text

    def test_missing_fields_shown(self) -> None:
        """Checklist shows missing fields with warning."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
            make_field_evaluation("where", FieldStatus.MISSING, None),
            make_field_evaluation("when", FieldStatus.MISSING, None),
            make_field_evaluation("who", FieldStatus.PARTIAL, "Partial info"),
            make_field_evaluation("so_what", FieldStatus.COMPLETE, "Test impact"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Summary should indicate issues
        summary_text = blocks[1]["text"]["text"]
        assert ":warning:" in summary_text
        assert "2 missing" in summary_text
        assert "1 need improvement" in summary_text

    def test_partial_fields_shown(self) -> None:
        """Checklist shows partial fields needing improvement."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
            make_field_evaluation("where", FieldStatus.PARTIAL, "Vague location"),
            make_field_evaluation("when", FieldStatus.PARTIAL, "Sometime"),
            make_field_evaluation("who", FieldStatus.COMPLETE, "Test people"),
            make_field_evaluation("so_what", FieldStatus.COMPLETE, "Test impact"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Summary should indicate partial fields
        summary_text = blocks[1]["text"]["text"]
        assert ":hourglass:" in summary_text
        assert "2 fields need improvement" in summary_text

    def test_field_icons_correct(self) -> None:
        """Each field has correct status icon."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Complete"),
            make_field_evaluation("where", FieldStatus.PARTIAL, "Partial"),
            make_field_evaluation("when", FieldStatus.MISSING, None),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Find field sections (after header, summary, divider)
        field_blocks = [b for b in blocks if b["type"] == "section"][1:]

        # Complete field
        assert ":white_check_mark:" in field_blocks[0]["text"]["text"]
        assert "What" in field_blocks[0]["text"]["text"]

        # Partial field
        assert ":warning:" in field_blocks[1]["text"]["text"]
        assert "Where" in field_blocks[1]["text"]["text"]

        # Missing field
        assert ":x:" in field_blocks[2]["text"]["text"]
        assert "When" in field_blocks[2]["text"]["text"]

    def test_field_notes_shown_for_incomplete_fields(self) -> None:
        """Notes are displayed for partial/missing fields."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation(
                "what",
                FieldStatus.PARTIAL,
                "Vague",
                notes="Be more specific about the event type",
            ),
            make_field_evaluation(
                "where",
                FieldStatus.MISSING,
                None,
                notes="Need to specify location",
            ),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Should have context blocks with notes
        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 2
        assert "Be more specific" in context_blocks[0]["elements"][0]["text"]
        assert "Need to specify location" in context_blocks[1]["elements"][0]["text"]

    def test_field_notes_not_shown_for_complete_fields(self) -> None:
        """Notes are not displayed for complete fields."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation(
                "what",
                FieldStatus.COMPLETE,
                "Complete info",
                notes="This is complete",
            ),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Should not have context blocks
        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 0

    def test_field_value_preview_truncated(self) -> None:
        """Long field values are truncated in preview."""
        candidate = make_cop_candidate()
        long_value = "A" * 100
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, long_value),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Find the field section
        field_sections = [b for b in blocks if b["type"] == "section"][1:]
        field_text = field_sections[0]["text"]["text"]

        # Should be truncated to 50 chars with ellipsis
        assert "A" * 50 in field_text
        assert "..." in field_text
        assert len(long_value) > 50  # Verify test setup


# ============================================================================
# build_readiness_summary_blocks() Tests
# ============================================================================


@pytest.mark.unit
class TestReadinessSummaryBlocks:
    """Test build_readiness_summary_blocks() function."""

    def test_verified_state_display(self) -> None:
        """Verified state shows correct icon and text."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.VERIFIED)
        evaluation = make_readiness_evaluation(
            candidate,
            readiness_state=ReadinessState.VERIFIED,
        )

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        # First block should show readiness state
        assert blocks[0]["type"] == "section"
        state_text = blocks[0]["text"]["text"]
        assert ":white_check_mark:" in state_text
        assert "Ready - Verified" in state_text

    def test_in_review_state_display(self) -> None:
        """In review state shows correct icon and text."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.IN_REVIEW)
        evaluation = make_readiness_evaluation(
            candidate,
            readiness_state=ReadinessState.IN_REVIEW,
        )

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        state_text = blocks[0]["text"]["text"]
        assert ":hourglass:" in state_text
        assert "Ready - In Review" in state_text

    def test_blocked_state_display(self) -> None:
        """Blocked state shows correct icon and text."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.BLOCKED)
        evaluation = make_readiness_evaluation(
            candidate,
            readiness_state=ReadinessState.BLOCKED,
        )

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        state_text = blocks[0]["text"]["text"]
        assert ":no_entry:" in state_text
        assert "Blocked" in state_text

    def test_risk_tier_display(self) -> None:
        """Risk tier is displayed with correct icon."""
        candidate = make_cop_candidate(risk_tier=RiskTier.HIGH_STAKES)
        evaluation = make_readiness_evaluation(candidate)

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        # Second block should show risk tier
        risk_text = blocks[1]["text"]["text"]
        assert ":red_circle:" in risk_text
        assert "High Stakes" in risk_text

    def test_blocking_issues_displayed(self) -> None:
        """Blocking issues are shown with severity indicators."""
        candidate = make_cop_candidate()
        blocking_issues = [
            BlockingIssue(
                issue_type="missing_field",
                description="Missing critical information",
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            ),
            BlockingIssue(
                issue_type="weak_field",
                description="Needs more detail",
                severity=BlockingIssueSeverity.REQUIRES_ATTENTION,
            ),
        ]
        evaluation = make_readiness_evaluation(
            candidate,
            blocking_issues=blocking_issues,
        )

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        # Should have divider, header, and issue blocks
        divider_count = sum(1 for b in blocks if b["type"] == "divider")
        assert divider_count >= 1

        # Find blocking issues section
        blocking_header = None
        for block in blocks:
            if block["type"] == "section" and "Blocking Issues" in str(block):
                blocking_header = block
                break
        assert blocking_header is not None

        # Check issue severity icons
        issue_blocks = [
            b for b in blocks
            if b["type"] == "section" and "Missing critical" in str(b)
        ]
        assert len(issue_blocks) >= 1
        assert ":red_circle:" in issue_blocks[0]["text"]["text"]

    def test_no_blocking_issues_section_when_none(self) -> None:
        """No blocking issues section when list is empty."""
        candidate = make_cop_candidate()
        evaluation = make_readiness_evaluation(candidate, blocking_issues=[])

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        # Should not contain blocking issues text
        block_text = str(blocks)
        assert "Blocking Issues" not in block_text

    def test_explanation_shown_in_context(self) -> None:
        """Explanation is shown in context block."""
        candidate = make_cop_candidate()
        evaluation = make_readiness_evaluation(
            candidate,
            explanation="This candidate needs verification from experts",
        )

        blocks = build_readiness_summary_blocks(candidate, evaluation)

        # Find context block with explanation
        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) >= 1
        context_text = context_blocks[0]["elements"][0]["text"]
        assert ":information_source:" in context_text
        assert "needs verification from experts" in context_text


# ============================================================================
# build_next_action_blocks() Tests
# ============================================================================


@pytest.mark.unit
class TestNextActionBlocks:
    """Test build_next_action_blocks() function."""

    def test_no_action_required(self) -> None:
        """Shows positive message when no action needed."""
        candidate = make_cop_candidate()

        blocks = build_next_action_blocks(candidate, recommended_action=None)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert ":thumbsup:" in blocks[0]["text"]["text"]
        assert "No action required" in blocks[0]["text"]["text"]

    def test_assign_verification_action(self) -> None:
        """Assign verification action displays correctly."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ASSIGN_VERIFICATION,
            reason="This candidate needs expert verification",
        )

        blocks = build_next_action_blocks(candidate, action)

        # Should have header
        assert blocks[0]["type"] == "header"
        assert "Recommended Next Action" in blocks[0]["text"]["text"]

        # Should have action description
        assert blocks[1]["type"] == "section"
        action_text = blocks[1]["text"]["text"]
        assert ":clipboard:" in action_text
        assert "Assign Verification" in action_text
        assert "needs expert verification" in action_text

        # Should have button
        assert blocks[2]["type"] == "actions"
        button = blocks[2]["elements"][0]
        assert button["type"] == "button"
        assert button["text"]["text"] == "Assign Verifier"
        assert f"assign_verification_{candidate.id}" in button["action_id"]

    def test_resolve_conflict_action(self) -> None:
        """Resolve conflict action displays correctly."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.RESOLVE_CONFLICT,
            reason="Conflicting information detected",
        )

        blocks = build_next_action_blocks(candidate, action)

        action_text = blocks[1]["text"]["text"]
        assert ":scales:" in action_text
        assert "Resolve Conflict" in action_text

        button = blocks[2]["elements"][0]
        assert button["text"]["text"] == "View Conflicts"

    def test_add_evidence_action(self) -> None:
        """Add evidence action displays correctly."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ADD_EVIDENCE,
            reason="More evidence needed",
        )

        blocks = build_next_action_blocks(candidate, action)

        action_text = blocks[1]["text"]["text"]
        assert ":mag:" in action_text
        assert "Add Evidence" in action_text

        button = blocks[2]["elements"][0]
        assert button["text"]["text"] == "Request Info"

    def test_ready_to_publish_action(self) -> None:
        """Ready to publish action displays correctly."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.READY_TO_PUBLISH,
            reason="All requirements met",
        )

        blocks = build_next_action_blocks(candidate, action)

        action_text = blocks[1]["text"]["text"]
        assert ":rocket:" in action_text
        assert "Ready To Publish" in action_text

        button = blocks[2]["elements"][0]
        assert button["text"]["text"] == "Publish"

    def test_clarification_template_shown(self) -> None:
        """Clarification template is shown when provided."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ADD_EVIDENCE,
            reason="Need more info",
        )
        template = "Can you provide more details about the location?"

        blocks = build_next_action_blocks(candidate, action, template)

        # Find the template section
        template_found = False
        for block in blocks:
            if block["type"] == "section" and "Suggested Message" in str(block):
                template_found = True
                break

        assert template_found
        # Should contain the template in code block
        assert any("```" in str(b) for b in blocks)

    def test_alternatives_shown(self) -> None:
        """Alternative actions are shown when present."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ASSIGN_VERIFICATION,
            reason="Needs verification",
            alternatives=["add_evidence", "request_clarification"],
        )

        blocks = build_next_action_blocks(candidate, action)

        # Find alternatives in context block
        alternatives_found = False
        for block in blocks:
            if block["type"] == "context":
                context_text = str(block)
                if "Alternatives" in context_text:
                    alternatives_found = True
                    assert "Add Evidence" in context_text
                    break

        assert alternatives_found


# ============================================================================
# build_candidate_detail_blocks() Tests
# ============================================================================


@pytest.mark.unit
class TestCandidateDetailBlocks:
    """Test build_candidate_detail_blocks() function."""

    def test_header_and_status_summary(self) -> None:
        """Detail view has header and status summary."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Event"),
        ]
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation
        )

        # Should have header
        assert blocks[0]["type"] == "header"
        assert "COP Candidate Details" in blocks[0]["text"]["text"]

        # Should have status summary with fields
        status_block = blocks[1]
        assert status_block["type"] == "section"
        assert "fields" in status_block
        fields = status_block["fields"]
        # Should have Status, Verifications, Risk Tier, Evidence
        assert len(fields) == 4

    def test_cop_fields_displayed(self) -> None:
        """All COP fields are displayed with status icons."""
        candidate = make_cop_candidate(
            what="Major incident",
            where="City Center",
            when_description="2pm today",
            who="Residents",
            so_what="Evacuations needed",
        )
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Major incident"),
            make_field_evaluation("where", FieldStatus.COMPLETE, "City Center"),
            make_field_evaluation("when", FieldStatus.COMPLETE, "2pm today"),
            make_field_evaluation("who", FieldStatus.COMPLETE, "Residents"),
            make_field_evaluation("so_what", FieldStatus.COMPLETE, "Evacuations needed"),
        ]
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation
        )

        # Find COP Information section
        cop_info_found = False
        for block in blocks:
            if block["type"] == "section" and "COP Information" in str(block):
                cop_info_found = True
                break
        assert cop_info_found

        # All fields should be present
        blocks_text = str(blocks)
        assert "Major incident" in blocks_text
        assert "City Center" in blocks_text
        assert "2pm today" in blocks_text
        assert "Residents" in blocks_text
        assert "Evacuations needed" in blocks_text

    def test_includes_readiness_summary(self) -> None:
        """Detail view includes readiness summary."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.VERIFIED)
        field_evaluations = []
        evaluation = make_readiness_evaluation(
            candidate,
            readiness_state=ReadinessState.VERIFIED,
            field_evaluations=field_evaluations,
        )

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation
        )

        # Should contain readiness state
        blocks_text = str(blocks)
        assert "Ready - Verified" in blocks_text

    def test_includes_next_action(self) -> None:
        """Detail view includes next action recommendation."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ASSIGN_VERIFICATION,
            reason="Needs verification",
        )
        field_evaluations = []
        evaluation = make_readiness_evaluation(
            candidate,
            recommended_action=action,
            field_evaluations=field_evaluations,
        )

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation
        )

        # Should contain action
        blocks_text = str(blocks)
        assert "Recommended Next Action" in blocks_text
        assert "Assign Verification" in blocks_text

    def test_action_buttons_present(self) -> None:
        """Detail view has action buttons at bottom."""
        candidate = make_cop_candidate()
        field_evaluations = []
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation
        )

        # Find actions block at end
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        # Should have at least one actions block (the final buttons)
        assert len(actions_blocks) >= 1

        # Last actions block should have View Full Details and Re-evaluate
        final_actions = actions_blocks[-1]
        buttons = final_actions["elements"]
        assert len(buttons) == 2
        assert any("View Full Details" in str(b) for b in buttons)
        assert any("Re-evaluate" in str(b) for b in buttons)


# ============================================================================
# build_candidate_list_item_blocks() Tests
# ============================================================================


@pytest.mark.unit
class TestCandidateListItemBlocks:
    """Test build_candidate_list_item_blocks() function."""

    def test_compact_list_item_structure(self) -> None:
        """List item has compact structure with key info."""
        candidate = make_cop_candidate(
            what="Test incident",
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.ELEVATED,
        )

        blocks = build_candidate_list_item_blocks(candidate)

        # Should be compact (1-2 blocks)
        assert len(blocks) <= 2

        # First block should be section with accessory button
        assert blocks[0]["type"] == "section"
        assert "accessory" in blocks[0]
        assert blocks[0]["accessory"]["type"] == "button"
        assert blocks[0]["accessory"]["text"]["text"] == "View"

    def test_readiness_state_icon_shown(self) -> None:
        """List item shows readiness state icon."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.VERIFIED)

        blocks = build_candidate_list_item_blocks(candidate)

        section_text = blocks[0]["text"]["text"]
        assert ":white_check_mark:" in section_text

    def test_risk_tier_icon_shown(self) -> None:
        """List item shows risk tier icon."""
        candidate = make_cop_candidate(risk_tier=RiskTier.HIGH_STAKES)

        blocks = build_candidate_list_item_blocks(candidate)

        section_text = blocks[0]["text"]["text"]
        assert ":red_circle:" in section_text
        assert "High Stakes" in section_text

    def test_verification_count_shown(self) -> None:
        """List item shows verification count."""
        verifications = [
            Verification(
                verified_by=ObjectId(),
                verification_method=VerificationMethod.AUTHORITATIVE_SOURCE,
            ),
            Verification(
                verified_by=ObjectId(),
                verification_method=VerificationMethod.EXPERT_CONFIRMATION,
            ),
        ]
        candidate = make_cop_candidate(verifications=verifications)

        blocks = build_candidate_list_item_blocks(candidate)

        section_text = blocks[0]["text"]["text"]
        assert "2 verifications" in section_text

    def test_what_field_truncated_if_long(self) -> None:
        """Long 'what' field is truncated in list view."""
        long_what = "A" * 100
        candidate = make_cop_candidate(what=long_what)

        blocks = build_candidate_list_item_blocks(candidate)

        section_text = blocks[0]["text"]["text"]
        # Should be truncated to 80 chars with ellipsis
        assert "..." in section_text
        # The full long_what should not appear in the text
        assert long_what not in section_text

    def test_blocking_issues_indicator_shown(self) -> None:
        """Blocking issues are indicated in list item."""
        blocking_issues = [
            BlockingIssue(
                issue_type="conflict",
                description="Data conflict",
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            ),
            BlockingIssue(
                issue_type="missing_field",
                description="Missing info",
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            ),
        ]
        candidate = make_cop_candidate(blocking_issues=blocking_issues)

        blocks = build_candidate_list_item_blocks(candidate)

        # Should have context block showing blocking count
        assert len(blocks) == 2
        assert blocks[1]["type"] == "context"
        context_text = blocks[1]["elements"][0]["text"]
        assert ":no_entry:" in context_text
        assert "2 blocking issue" in context_text

    def test_no_blocking_indicator_when_none(self) -> None:
        """No blocking indicator when no blocking issues."""
        candidate = make_cop_candidate(blocking_issues=[])

        blocks = build_candidate_list_item_blocks(candidate)

        # Should only have main section, no context block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_view_button_has_correct_action_id(self) -> None:
        """View button action ID includes candidate ID."""
        candidate_id = ObjectId()
        candidate = make_cop_candidate(candidate_id=candidate_id)

        blocks = build_candidate_list_item_blocks(candidate)

        button = blocks[0]["accessory"]
        assert button["action_id"] == f"view_candidate_{candidate_id}"
        assert button["value"] == str(candidate_id)

    def test_untitled_when_what_is_empty(self) -> None:
        """Shows 'Untitled' when what field is empty."""
        candidate = make_cop_candidate(what="")

        blocks = build_candidate_list_item_blocks(candidate)

        section_text = blocks[0]["text"]["text"]
        assert "Untitled" in section_text
