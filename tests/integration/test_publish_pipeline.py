"""
End-to-end integration tests for COP update publish pipeline (S4-6).

Tests the complete workflow from signal ingestion through publishing:
- Signal creation and clustering
- COP candidate creation and readiness evaluation
- Draft generation and assembly
- Human approval workflow (FR-COP-PUB-001)
- Publish to Slack (mocked)
- Audit trail verification (NFR-TRANSPARENCY-001)

These tests use mongomock for database operations and mock Slack API.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditLogEntry, AuditTargetType
from integritykit.models.cop_candidate import (
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
from integritykit.models.cop_update import COPUpdate, COPUpdateStatus, PublishedLineItem
from integritykit.models.signal import Signal
from integritykit.models.user import User, UserRole
from integritykit.services.audit import AuditService
from integritykit.services.draft import COPDraft, COPLineItem, COPSection, DraftService, WordingStyle
from integritykit.services.publish import COPUpdateRepository, PublishService
from integritykit.services.readiness import ReadinessService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_user(
    *,
    roles: list[UserRole] | None = None,
    team_id: str = "T123456",
) -> User:
    """Create a test user."""
    return User(
        id=ObjectId(),
        slack_user_id="U123456",
        slack_team_id=team_id,
        slack_display_name="Test Facilitator",
        roles=roles or [UserRole.FACILITATOR],
        created_at=datetime.now(timezone.utc),
    )


def create_test_signal(
    *,
    text: str = "Bridge is closed on Main Street due to flooding",
    workspace_id: str = "T123456",
    channel_id: str = "C123456",
) -> Signal:
    """Create a test signal."""
    return Signal(
        id=ObjectId(),
        workspace_id=workspace_id,
        channel_id=channel_id,
        message_ts="1234567890.123456",
        text=text,
        user_id="U123456",
        user_name="John Reporter",
        created_at=datetime.now(timezone.utc),
    )


def create_test_candidate(
    *,
    what: str = "Bridge closure on Main Street",
    where: str = "123 Main St, Springfield, IL",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    has_verification: bool = False,
) -> COPCandidate:
    """Create a test COPCandidate."""
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
            where=where,
            when=COPWhen(
                timestamp=datetime.now(timezone.utc),
                timezone="America/Chicago",
                is_approximate=False,
                description="As of now",
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
        verifications=verifications,
        conflicts=[],
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


def create_mock_audit_service() -> tuple[AuditService, list[dict]]:
    """Create mock audit service that captures logged actions."""
    captured_logs = []

    mock_audit = AsyncMock(spec=AuditService)

    async def capture_log_action(**kwargs):
        captured_logs.append(kwargs)
        return AuditLogEntry(
            id=ObjectId(),
            timestamp=datetime.now(timezone.utc),
            action_type=kwargs.get("action_type", AuditActionType.COP_UPDATE_PUBLISH),
            target_entity_type=kwargs.get("target_type", AuditTargetType.COP_UPDATE),
            target_entity_id=kwargs.get("target_id") or ObjectId(),
            actor_id=kwargs.get("actor").id if kwargs.get("actor") else ObjectId(),
            actor_role="facilitator",
        )

    mock_audit.log_action.side_effect = capture_log_action

    return mock_audit, captured_logs


def create_mock_slack_client() -> AsyncMock:
    """Create mock Slack client for publish testing."""
    mock_slack = AsyncMock()
    mock_slack.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C123456",
    }
    mock_slack.chat_getPermalink.return_value = {
        "ok": True,
        "permalink": "https://workspace.slack.com/archives/C123456/p1234567890123456",
    }
    return mock_slack


# ============================================================================
# End-to-End Pipeline Tests
# ============================================================================


@pytest.mark.integration
class TestIngestToPublishPipeline:
    """Test complete pipeline from signal ingest to COP publish."""

    @pytest.mark.asyncio
    async def test_verified_candidate_to_published_cop(self) -> None:
        """Test full pipeline: verified candidate -> draft -> approve -> publish."""
        user = create_test_user()

        # 1. Create verified candidate (simulating post-clustering/extraction)
        candidate = create_test_candidate(
            what="Water main break repaired",
            where="456 Oak Avenue",
            has_verification=True,
        )

        # 2. Evaluate readiness
        readiness_service = ReadinessService(use_llm=False)
        evaluation = await readiness_service.evaluate_readiness(candidate)
        candidate = await readiness_service.apply_evaluation(candidate, evaluation)

        assert candidate.readiness_state == ReadinessState.VERIFIED

        # 3. Generate draft
        draft_service = DraftService(use_llm=False)
        draft = await draft_service.generate_draft(
            workspace_id="T123456",
            candidates=[candidate],
            title="Crisis Update #1",
        )

        assert len(draft.verified_items) == 1
        assert draft.verified_items[0].wording_style == WordingStyle.DIRECT_FACTUAL

        # 4. Create COP update from draft (simulating PublishService)
        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_candidate_repo = AsyncMock()
        mock_candidate_repo.get_by_id.return_value = candidate
        mock_audit, audit_logs = create_mock_audit_service()
        mock_slack = create_mock_slack_client()

        # Mock draft service
        mock_draft_service = AsyncMock()
        mock_draft_service.generate_draft.return_value = draft

        # Create update record
        update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=1,
            title=draft.title,
            status=COPUpdateStatus.DRAFT,
            line_items=[
                PublishedLineItem(
                    candidate_id=candidate.id,
                    section="verified",
                    status_label="VERIFIED",
                    text=draft.verified_items[0].line_item_text,
                    citations=draft.verified_items[0].citations,
                    was_edited=False,
                )
            ],
            open_questions=draft.open_questions,
            candidate_ids=[candidate.id],
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        mock_update_repo.create.return_value = update
        mock_update_repo.get_by_id.return_value = update
        mock_update_repo.update.return_value = update
        mock_update_repo.get_latest_published.return_value = None

        service = PublishService(
            update_repo=mock_update_repo,
            candidate_repo=mock_candidate_repo,
            draft_service=mock_draft_service,
            audit_service=mock_audit,
            slack_client=mock_slack,
        )

        # 5. Approve (human approval step - FR-COP-PUB-001)
        approved_update = await service.approve(
            update_id=update.id,
            user=user,
            notes="Looks good, ready to publish",
        )

        # Verify approval was audited
        approval_logs = [
            log for log in audit_logs
            if log.get("system_context", {}).get("action") == "approve"
        ]
        assert len(approval_logs) == 1
        assert approval_logs[0]["actor"] == user

        # 6. Update status for publish test
        update.status = COPUpdateStatus.APPROVED
        update.approved_by = user.id
        update.approved_at = datetime.now(timezone.utc)
        mock_update_repo.get_by_id.return_value = update

        # 7. Publish to Slack
        published_update = await service.publish_to_slack(
            update_id=update.id,
            channel_id="C123456",
            user=user,
        )

        # Verify Slack was called
        mock_slack.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "C123456"
        assert len(call_kwargs["blocks"]) > 0

        # Verify publish was audited
        publish_logs = [
            log for log in audit_logs
            if log.get("system_context", {}).get("action") == "publish_to_slack"
        ]
        assert len(publish_logs) == 1
        assert "slack_channel_id" in publish_logs[0]["changes_after"]

    @pytest.mark.asyncio
    async def test_unapproved_update_cannot_publish(self) -> None:
        """Test that unapproved updates cannot be published (FR-COP-PUB-001)."""
        user = create_test_user()

        # Create draft update (not approved)
        update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=1,
            title="Test Update",
            status=COPUpdateStatus.DRAFT,
            line_items=[],
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_update_repo.get_by_id.return_value = update

        mock_slack = create_mock_slack_client()

        service = PublishService(
            update_repo=mock_update_repo,
            candidate_repo=AsyncMock(),
            audit_service=AsyncMock(),
            draft_service=AsyncMock(),
            slack_client=mock_slack,
        )

        # Attempt to publish without approval
        with pytest.raises(ValueError) as exc_info:
            await service.publish_to_slack(
                update_id=update.id,
                channel_id="C123456",
                user=user,
            )

        assert "must be approved" in str(exc_info.value).lower()
        mock_slack.chat_postMessage.assert_not_called()


@pytest.mark.integration
class TestMultiCandidatePipeline:
    """Test pipeline with multiple candidates in different states."""

    @pytest.mark.asyncio
    async def test_mixed_readiness_draft_assembly(self) -> None:
        """Test draft assembly with verified, in-review, and blocked candidates."""
        readiness_service = ReadinessService(use_llm=False)
        draft_service = DraftService(use_llm=False)

        candidates = [
            create_test_candidate(what="Verified: Bridge closed", has_verification=True),
            create_test_candidate(what="In Review: Flooding reported", has_verification=False),
            create_test_candidate(what="In Review: Power issues", has_verification=False),
        ]

        # Evaluate all candidates
        for i, candidate in enumerate(candidates):
            evaluation = await readiness_service.evaluate_readiness(candidate)
            candidates[i] = await readiness_service.apply_evaluation(candidate, evaluation)

        # Verify states
        assert candidates[0].readiness_state == ReadinessState.VERIFIED
        assert candidates[1].readiness_state == ReadinessState.IN_REVIEW
        assert candidates[2].readiness_state == ReadinessState.IN_REVIEW

        # Generate draft
        draft = await draft_service.generate_draft(
            workspace_id="T123456",
            candidates=candidates,
            title="Multi-Item Update",
            include_open_questions=True,
        )

        # Verify section assignments
        assert len(draft.verified_items) == 1
        assert len(draft.in_review_items) == 2

        # Verify wording styles
        assert draft.verified_items[0].wording_style == WordingStyle.DIRECT_FACTUAL
        for item in draft.in_review_items:
            assert item.wording_style == WordingStyle.HEDGED_UNCERTAIN


@pytest.mark.integration
class TestAuditTrailPipeline:
    """Test audit trail through entire pipeline (NFR-TRANSPARENCY-001)."""

    @pytest.mark.asyncio
    async def test_full_audit_trail_captured(self) -> None:
        """Test that all workflow actions are captured in audit trail."""
        user = create_test_user()
        candidate = create_test_candidate(has_verification=True)

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_candidate_repo = AsyncMock()
        mock_candidate_repo.get_by_id.return_value = candidate
        mock_audit, audit_logs = create_mock_audit_service()
        mock_slack = create_mock_slack_client()

        # Create draft
        draft = COPDraft(
            draft_id="draft-123",
            workspace_id="T123456",
            title="Test Update",
            generated_at=datetime.now(timezone.utc),
            verified_items=[
                COPLineItem(
                    candidate_id=str(candidate.id),
                    status_label="VERIFIED",
                    line_item_text="Test item",
                    citations=[],
                    wording_style=WordingStyle.DIRECT_FACTUAL,
                    section=COPSection.VERIFIED,
                )
            ],
            in_review_items=[],
            disproven_items=[],
            open_questions=[],
        )

        mock_draft_service = AsyncMock()
        mock_draft_service.generate_draft.return_value = draft

        update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=1,
            title="Test Update",
            status=COPUpdateStatus.DRAFT,
            line_items=[
                PublishedLineItem(
                    candidate_id=candidate.id,
                    section="verified",
                    status_label="VERIFIED",
                    text="Test item",
                    citations=[],
                    was_edited=False,
                )
            ],
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        mock_update_repo.create.return_value = update
        mock_update_repo.get_by_id.return_value = update
        mock_update_repo.update.return_value = update
        mock_update_repo.get_latest_published.return_value = None

        service = PublishService(
            update_repo=mock_update_repo,
            candidate_repo=mock_candidate_repo,
            draft_service=mock_draft_service,
            audit_service=mock_audit,
            slack_client=mock_slack,
        )

        # 1. Create draft
        await service.create_draft_from_candidates(
            workspace_id="T123456",
            candidate_ids=[candidate.id],
            user=user,
        )

        # 2. Edit line item
        await service.edit_line_item(
            update_id=update.id,
            item_index=0,
            new_text="Edited text",
            user=user,
        )

        # 3. Approve
        await service.approve(
            update_id=update.id,
            user=user,
            notes="Approved",
        )

        # Update status for publish
        update.status = COPUpdateStatus.APPROVED
        update.approved_by = user.id

        # 4. Publish
        await service.publish_to_slack(
            update_id=update.id,
            channel_id="C123456",
            user=user,
        )

        # Verify audit trail captured all actions
        actions_logged = [
            log.get("system_context", {}).get("action")
            for log in audit_logs
        ]

        assert "create_draft" in actions_logged
        assert "edit_line_item" in actions_logged
        assert "approve" in actions_logged
        assert "publish_to_slack" in actions_logged

        # Verify all logs have actor
        for log in audit_logs:
            assert log["actor"] == user

        # Verify edit log has before/after
        edit_logs = [
            log for log in audit_logs
            if log.get("system_context", {}).get("action") == "edit_line_item"
        ]
        assert len(edit_logs) == 1
        assert "text" in edit_logs[0]["changes_before"]
        assert "text" in edit_logs[0]["changes_after"]


@pytest.mark.integration
class TestSlackBlockKitOutput:
    """Test Slack Block Kit formatting through pipeline."""

    @pytest.mark.asyncio
    async def test_published_update_has_correct_blocks(self) -> None:
        """Test that published updates have properly formatted Slack blocks."""
        user = create_test_user()

        update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=5,
            title="Flooding Response Update",
            status=COPUpdateStatus.APPROVED,
            line_items=[
                PublishedLineItem(
                    candidate_id=ObjectId(),
                    section="verified",
                    status_label="VERIFIED",
                    text="Main Street bridge is closed to traffic",
                    citations=["https://city.gov/alerts"],
                    was_edited=False,
                ),
                PublishedLineItem(
                    candidate_id=ObjectId(),
                    section="in_review",
                    status_label="IN REVIEW",
                    text="Unconfirmed reports of flooding on Oak Avenue",
                    citations=[],
                    was_edited=False,
                ),
            ],
            open_questions=["What is the expected reopening time for the bridge?"],
            approved_by=user.id,
            approved_at=datetime.now(timezone.utc),
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_update_repo.get_by_id.return_value = update
        mock_update_repo.update.return_value = update
        mock_update_repo.get_latest_published.return_value = None

        mock_slack = create_mock_slack_client()

        service = PublishService(
            update_repo=mock_update_repo,
            candidate_repo=AsyncMock(),
            audit_service=AsyncMock(),
            draft_service=AsyncMock(),
            slack_client=mock_slack,
        )

        await service.publish_to_slack(
            update_id=update.id,
            channel_id="C123456",
            user=user,
        )

        # Verify Slack blocks structure
        call_kwargs = mock_slack.chat_postMessage.call_args.kwargs
        blocks = call_kwargs["blocks"]

        # Should have header
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) >= 1
        assert "COP Update #5" in header_blocks[0]["text"]["text"]
        assert "Flooding Response" in header_blocks[0]["text"]["text"]

        # Should have section blocks for content
        section_blocks = [b for b in blocks if b.get("type") == "section"]
        section_texts = [b.get("text", {}).get("text", "") for b in section_blocks]

        # Verified section
        assert any("Verified" in t for t in section_texts)

        # In Review section
        assert any("In Review" in t for t in section_texts)

        # Open Questions section
        assert any("Open Questions" in t or "?" in t for t in section_texts)

        # Should have footer with IntegrityKit attribution
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        context_text = str(context_blocks)
        assert "IntegrityKit" in context_text or "facilitator" in context_text.lower()


@pytest.mark.integration
class TestSupersessionPipeline:
    """Test COP update supersession workflow."""

    @pytest.mark.asyncio
    async def test_new_publish_supersedes_previous(self) -> None:
        """Test that publishing new update supersedes previous one."""
        user = create_test_user()

        # Previous published update
        previous_update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=1,
            title="Previous Update",
            status=COPUpdateStatus.PUBLISHED,
            line_items=[],
            published_at=datetime.now(timezone.utc),
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        # New update to publish
        new_update = COPUpdate(
            id=ObjectId(),
            workspace_id="T123456",
            update_number=2,
            title="New Update",
            status=COPUpdateStatus.APPROVED,
            line_items=[],
            approved_by=user.id,
            approved_at=datetime.now(timezone.utc),
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )

        mock_update_repo = AsyncMock(spec=COPUpdateRepository)
        mock_update_repo.get_by_id.return_value = new_update
        mock_update_repo.update.return_value = new_update
        mock_update_repo.get_latest_published.return_value = previous_update

        mock_slack = create_mock_slack_client()

        supersession_captured = {}

        async def capture_update(update_id, fields):
            if update_id == previous_update.id:
                supersession_captured.update(fields)
            return new_update

        mock_update_repo.update.side_effect = capture_update

        service = PublishService(
            update_repo=mock_update_repo,
            candidate_repo=AsyncMock(),
            audit_service=AsyncMock(),
            draft_service=AsyncMock(),
            slack_client=mock_slack,
        )

        await service.publish_to_slack(
            update_id=new_update.id,
            channel_id="C123456",
            user=user,
        )

        # Verify previous update was superseded
        assert supersession_captured.get("status") == COPUpdateStatus.SUPERSEDED.value
        assert supersession_captured.get("superseded_by") == new_update.id
