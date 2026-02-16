"""
Unit tests for COP update publishing service.

Tests:
- FR-COP-PUB-001: Human-approved publishing (no automated publishing)
- NFR-TRANSPARENCY-001: Full audit trail for publish actions
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
    SlackPermalink,
    Verification,
)
from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateStatus,
    PublishedLineItem,
)
from integritykit.models.user import User, UserRole
from integritykit.services.draft import COPDraft, COPLineItem, COPSection, WordingStyle
from integritykit.services.publish import (
    CLARIFICATION_TEMPLATES,
    COPUpdateRepository,
    PublishService,
    get_clarification_template,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_user(
    *,
    roles: list[UserRole] | None = None,
) -> User:
    """Create a test user."""
    return User(
        id=ObjectId(),
        slack_user_id="U123456",
        slack_team_id="T123456",
        slack_display_name="Test User",
        roles=roles or [UserRole.FACILITATOR],
        created_at=datetime.now(timezone.utc),
    )


def make_candidate(
    *,
    readiness_state: ReadinessState = ReadinessState.VERIFIED,
    what: str = "Bridge closure confirmed",
) -> COPCandidate:
    """Create a test candidate."""
    return COPCandidate(
        id=ObjectId(),
        cluster_id=ObjectId(),
        primary_signal_ids=[ObjectId()],
        readiness_state=readiness_state,
        readiness_updated_at=datetime.now(timezone.utc),
        readiness_updated_by=ObjectId(),
        risk_tier=RiskTier.ROUTINE,
        fields=COPFields(
            what=what,
            where="123 Main St",
            when=COPWhen(
                timestamp=datetime.now(timezone.utc),
                timezone="America/Chicago",
                is_approximate=False,
                description="As of 2pm",
            ),
            who="City Department",
            so_what="Traffic rerouted",
        ),
        evidence=Evidence(
            slack_permalinks=[
                SlackPermalink(
                    url="https://workspace.slack.com/archives/C123/p100",
                    signal_id=ObjectId(),
                    description="Source",
                )
            ],
            external_sources=[],
        ),
        verifications=[
            Verification(
                verified_by=ObjectId(),
                verified_at=datetime.now(timezone.utc),
                verification_method="authoritative_source",
                verification_notes="Confirmed",
            )
        ],
        conflicts=[],
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


def make_update(
    *,
    status: COPUpdateStatus = COPUpdateStatus.DRAFT,
    approved_by: ObjectId | None = None,
) -> COPUpdate:
    """Create a test COP update."""
    return COPUpdate(
        id=ObjectId(),
        workspace_id="T123456",
        update_number=1,
        title="Test COP Update",
        status=status,
        line_items=[
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="verified",
                status_label="VERIFIED",
                text="Bridge closure confirmed at Main St",
                citations=["https://example.com"],
                was_edited=False,
            )
        ],
        open_questions=["What is the expected reopening time?"],
        candidate_ids=[ObjectId()],
        draft_generated_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc) if approved_by else None,
        created_at=datetime.now(timezone.utc),
    )


# ============================================================================
# Human Approval Requirement Tests (FR-COP-PUB-001 / S4-5)
# ============================================================================


def make_publish_service(
    *,
    update_repo: AsyncMock | None = None,
    candidate_repo: AsyncMock | None = None,
    audit_service: AsyncMock | None = None,
    draft_service: AsyncMock | None = None,
    slack_client: AsyncMock | None = None,
) -> PublishService:
    """Create a PublishService with mocked dependencies."""
    return PublishService(
        update_repo=update_repo or AsyncMock(spec=COPUpdateRepository),
        candidate_repo=candidate_repo or AsyncMock(),
        audit_service=audit_service or AsyncMock(),
        draft_service=draft_service or AsyncMock(),
        slack_client=slack_client,
    )


@pytest.mark.unit
class TestHumanApprovalRequired:
    """Verify no automated publishing without human approval."""

    @pytest.mark.asyncio
    async def test_publish_requires_approved_status(self) -> None:
        """Publishing must fail if update is not in APPROVED status."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)

        # Mock repository
        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        # Mock Slack client
        mock_slack = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            slack_client=mock_slack,
        )

        with pytest.raises(ValueError) as exc_info:
            await service.publish_to_slack(
                update_id=update.id,
                channel_id="C123",
                user=user,
            )

        assert "must be approved" in str(exc_info.value).lower()
        mock_slack.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_requires_explicit_approval_action(self) -> None:
        """Cannot bypass approval by setting status directly."""
        user = make_user()
        # Update with PENDING_APPROVAL status
        update = make_update(status=COPUpdateStatus.PENDING_APPROVAL)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        mock_slack = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            slack_client=mock_slack,
        )

        with pytest.raises(ValueError) as exc_info:
            await service.publish_to_slack(
                update_id=update.id,
                channel_id="C123",
                user=user,
            )

        assert "must be approved" in str(exc_info.value).lower()
        mock_slack.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_update_can_be_published(self) -> None:
        """Only APPROVED updates can be published."""
        user = make_user()
        approver_id = ObjectId()
        update = make_update(
            status=COPUpdateStatus.APPROVED,
            approved_by=approver_id,
        )

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update
        mock_repo.update.return_value = update
        mock_repo.get_latest_published.return_value = None

        mock_slack = AsyncMock()
        mock_slack.chat_postMessage.return_value = {"ts": "123.456"}
        mock_slack.chat_getPermalink.return_value = {"permalink": "https://slack.com/msg"}

        mock_audit = AsyncMock()
        mock_candidate_repo = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            candidate_repo=mock_candidate_repo,
            audit_service=mock_audit,
            slack_client=mock_slack,
        )

        result = await service.publish_to_slack(
            update_id=update.id,
            channel_id="C123",
            user=user,
        )

        # Verify Slack was called
        mock_slack.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_sets_approver_and_timestamp(self) -> None:
        """Approval action must record who approved and when."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        # Capture the update call
        updated_fields = {}

        async def capture_update(update_id, fields):
            updated_fields.update(fields)
            update.status = COPUpdateStatus.APPROVED
            update.approved_by = fields.get("approved_by")
            update.approved_at = fields.get("approved_at")
            return update

        mock_repo.update.side_effect = capture_update

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            audit_service=mock_audit,
        )

        await service.approve(
            update_id=update.id,
            user=user,
            notes="Looks good",
        )

        # Verify approval fields were set
        assert updated_fields.get("approved_by") == user.id
        assert updated_fields.get("approved_at") is not None
        assert updated_fields.get("status") == COPUpdateStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_cannot_publish_superseded_update(self) -> None:
        """Cannot publish an update that has been superseded."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.SUPERSEDED)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        service = make_publish_service(update_repo=mock_repo)

        with pytest.raises(ValueError) as exc_info:
            await service.approve(
                update_id=update.id,
                user=user,
            )

        assert "superseded" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cannot_publish_already_published_update(self) -> None:
        """Cannot publish an update that is already published."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.PUBLISHED)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        service = make_publish_service(update_repo=mock_repo)

        with pytest.raises(ValueError) as exc_info:
            await service.approve(
                update_id=update.id,
                user=user,
            )

        assert "already published" in str(exc_info.value).lower()


# ============================================================================
# Draft Creation Tests
# ============================================================================


def make_draft(candidate_id: str) -> COPDraft:
    """Create a mock COPDraft."""
    return COPDraft(
        draft_id="draft-123",
        workspace_id="T123456",
        title="Test COP Update",
        generated_at=datetime.now(timezone.utc),
        verified_items=[
            COPLineItem(
                candidate_id=candidate_id,
                status_label="VERIFIED",
                line_item_text="Bridge closure confirmed at Main St",
                citations=["https://example.com"],
                wording_style=WordingStyle.DIRECT_FACTUAL,
                section=COPSection.VERIFIED,
            )
        ],
        in_review_items=[],
        disproven_items=[],
        open_questions=["What is the expected reopening time?"],
    )


@pytest.mark.unit
class TestDraftCreation:
    """Test draft creation from candidates."""

    @pytest.mark.asyncio
    async def test_draft_starts_in_draft_status(self) -> None:
        """New drafts must start in DRAFT status."""
        user = make_user()
        candidate = make_candidate()

        mock_candidate_repo = AsyncMock()
        mock_candidate_repo.get_by_id.return_value = candidate

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)

        created_update = None

        async def capture_create(update_data):
            nonlocal created_update
            created_update = COPUpdate(
                id=ObjectId(),
                workspace_id=update_data.workspace_id,
                update_number=1,
                title=update_data.title,
                status=COPUpdateStatus.DRAFT,
                line_items=update_data.line_items,
                open_questions=update_data.open_questions,
                created_by=update_data.created_by,
                created_at=datetime.now(timezone.utc),
            )
            return created_update

        mock_update_repo.create.side_effect = capture_create
        mock_update_repo.collection = AsyncMock()
        mock_update_repo.collection.find_one.return_value = None

        # Mock draft service to return a proper draft
        mock_draft_service = AsyncMock()
        mock_draft_service.generate_draft.return_value = make_draft(str(candidate.id))

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_update_repo,
            candidate_repo=mock_candidate_repo,
            draft_service=mock_draft_service,
            audit_service=mock_audit,
        )

        result = await service.create_draft_from_candidates(
            workspace_id="T123456",
            candidate_ids=[candidate.id],
            user=user,
        )

        assert result.status == COPUpdateStatus.DRAFT

    @pytest.mark.asyncio
    async def test_draft_records_creator(self) -> None:
        """Draft must record who created it."""
        user = make_user()
        candidate = make_candidate()

        mock_candidate_repo = AsyncMock()
        mock_candidate_repo.get_by_id.return_value = candidate

        created_data = None

        async def capture_create(update_data):
            nonlocal created_data
            created_data = update_data
            return COPUpdate(
                id=ObjectId(),
                workspace_id=update_data.workspace_id,
                update_number=1,
                title=update_data.title,
                status=COPUpdateStatus.DRAFT,
                line_items=update_data.line_items,
                open_questions=update_data.open_questions,
                created_by=update_data.created_by,
                created_at=datetime.now(timezone.utc),
            )

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_update_repo.create.side_effect = capture_create
        mock_update_repo.collection = AsyncMock()
        mock_update_repo.collection.find_one.return_value = None

        # Mock draft service to return a proper draft
        mock_draft_service = AsyncMock()
        mock_draft_service.generate_draft.return_value = make_draft(str(candidate.id))

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_update_repo,
            candidate_repo=mock_candidate_repo,
            draft_service=mock_draft_service,
            audit_service=mock_audit,
        )

        await service.create_draft_from_candidates(
            workspace_id="T123456",
            candidate_ids=[candidate.id],
            user=user,
        )

        assert created_data.created_by == user.id


# ============================================================================
# Edit Tracking Tests
# ============================================================================


@pytest.mark.unit
class TestEditTracking:
    """Test line item edit tracking."""

    @pytest.mark.asyncio
    async def test_edit_preserves_original_text(self) -> None:
        """Edits must preserve original auto-generated text."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)
        original_text = update.line_items[0].text

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        updated_items = None

        async def capture_update(update_id, fields):
            nonlocal updated_items
            updated_items = fields.get("line_items")
            return update

        mock_repo.update.side_effect = capture_update

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            audit_service=mock_audit,
        )

        await service.edit_line_item(
            update_id=update.id,
            item_index=0,
            new_text="Edited text here",
            user=user,
        )

        # Verify original text was preserved
        assert updated_items[0]["original_text"] == original_text
        assert updated_items[0]["was_edited"] is True

    @pytest.mark.asyncio
    async def test_edit_increments_edit_count(self) -> None:
        """Each edit must increment the edit counter."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)
        update.edit_count = 0

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        update_fields = {}

        async def capture_update(update_id, fields):
            update_fields.update(fields)
            return update

        mock_repo.update.side_effect = capture_update

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            audit_service=mock_audit,
        )

        await service.edit_line_item(
            update_id=update.id,
            item_index=0,
            new_text="First edit",
            user=user,
        )

        assert update_fields.get("edit_count") == 1

    @pytest.mark.asyncio
    async def test_cannot_edit_published_update(self) -> None:
        """Cannot edit a published update."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.PUBLISHED)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update

        service = make_publish_service(update_repo=mock_repo)

        with pytest.raises(ValueError) as exc_info:
            await service.edit_line_item(
                update_id=update.id,
                item_index=0,
                new_text="Attempted edit",
                user=user,
            )

        assert "cannot edit" in str(exc_info.value).lower()


# ============================================================================
# Audit Logging Tests
# ============================================================================


@pytest.mark.unit
class TestAuditLogging:
    """Test audit logging for publish actions."""

    @pytest.mark.asyncio
    async def test_approval_is_audited(self) -> None:
        """Approval action must be recorded in audit log."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update
        mock_repo.update.return_value = update

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            audit_service=mock_audit,
        )

        await service.approve(
            update_id=update.id,
            user=user,
            notes="Approved for publishing",
        )

        # Verify audit was called
        mock_audit.log_action.assert_called()
        call_kwargs = mock_audit.log_action.call_args.kwargs

        assert call_kwargs["actor"] == user
        assert call_kwargs["target_id"] == update.id
        assert "approve" in str(call_kwargs.get("system_context", {})).lower()

    @pytest.mark.asyncio
    async def test_edit_is_audited_with_before_after(self) -> None:
        """Edit action must record before and after text in audit."""
        user = make_user()
        update = make_update(status=COPUpdateStatus.DRAFT)
        original_text = update.line_items[0].text
        new_text = "Edited text"

        mock_repo = AsyncMock(spec=COPUpdateRepository)
        mock_repo.get_by_id.return_value = update
        mock_repo.update.return_value = update

        mock_audit = AsyncMock()

        service = make_publish_service(
            update_repo=mock_repo,
            audit_service=mock_audit,
        )

        await service.edit_line_item(
            update_id=update.id,
            item_index=0,
            new_text=new_text,
            user=user,
        )

        # Verify audit captured before/after
        mock_audit.log_action.assert_called()
        call_kwargs = mock_audit.log_action.call_args.kwargs

        assert call_kwargs["changes_before"]["text"] == original_text
        assert call_kwargs["changes_after"]["text"] == new_text


# ============================================================================
# Clarification Template Tests (S4-4)
# ============================================================================


@pytest.mark.unit
class TestClarificationTemplates:
    """Test clarification request templates."""

    def test_location_template(self) -> None:
        """Location template should mention location details."""
        template = get_clarification_template("location", "bridge closure")

        assert "bridge closure" in template
        assert "location" in template.lower()

    def test_time_template(self) -> None:
        """Time template should ask about timing."""
        template = get_clarification_template("time", "power outage")

        assert "power outage" in template
        assert "when" in template.lower() or "time" in template.lower()

    def test_source_template(self) -> None:
        """Source template should ask about verification."""
        template = get_clarification_template("source", "shelter opening")

        assert "shelter opening" in template
        assert "source" in template.lower() or "witness" in template.lower()

    def test_general_template_fallback(self) -> None:
        """Unknown template type should use general template."""
        template = get_clarification_template("unknown_type", "some topic")

        assert "some topic" in template
        assert len(template) > 20  # Should be a meaningful template

    def test_all_templates_have_topic_placeholder(self) -> None:
        """All templates must include the topic."""
        for template_type in CLARIFICATION_TEMPLATES.keys():
            template = get_clarification_template(template_type, "TEST_TOPIC")
            assert "TEST_TOPIC" in template


# ============================================================================
# Slack Block Kit Formatting Tests (S4-2)
# ============================================================================


@pytest.mark.unit
class TestSlackBlockFormatting:
    """Test Slack Block Kit output formatting."""

    def test_blocks_have_header(self) -> None:
        """Published update blocks should have header."""
        update = make_update(status=COPUpdateStatus.APPROVED)
        service = make_publish_service()

        blocks = service._build_slack_blocks(update)

        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) >= 1
        assert "COP Update" in header_blocks[0]["text"]["text"]

    def test_blocks_have_section_headers(self) -> None:
        """Blocks should have section headers for each category."""
        update = make_update(status=COPUpdateStatus.APPROVED)
        service = make_publish_service()

        blocks = service._build_slack_blocks(update)

        block_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b.get("type") == "section"
        ]

        # Should have verified section
        assert any("Verified" in t for t in block_texts)

    def test_blocks_include_citations(self) -> None:
        """Line items with citations should show citation links."""
        update = make_update(status=COPUpdateStatus.APPROVED)
        update.line_items[0].citations = ["https://example.com/source1"]
        service = make_publish_service()

        blocks = service._build_slack_blocks(update)

        # Find the section with the line item
        all_text = str(blocks)
        assert "[1]" in all_text or "example.com" in all_text

    def test_blocks_have_footer(self) -> None:
        """Blocks should have footer with IntegrityKit attribution."""
        update = make_update(status=COPUpdateStatus.APPROVED)
        service = make_publish_service()

        blocks = service._build_slack_blocks(update)

        context_blocks = [b for b in blocks if b.get("type") == "context"]
        context_text = str(context_blocks)

        assert "IntegrityKit" in context_text or "facilitator" in context_text.lower()
