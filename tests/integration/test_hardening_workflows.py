"""
End-to-end integration tests for Sprint 7 hardening features.

Tests the critical workflows for:
- S7-1: Two-person rule for high-stakes overrides
- S7-3: Anti-abuse detection (rapid-fire override alerts)
- S7-4: Facilitator permission suspension by admin
- S7-5: Data retention TTL and purge

These tests verify complete workflows from user action through audit logging.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import TwoPersonApprovalStatus
from integritykit.models.user import Permission, User, UserRole
from integritykit.services.abuse_detection import AbuseDetectionService
from integritykit.services.suspension import SuspensionService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_user(
    *,
    user_id: ObjectId | None = None,
    roles: list[UserRole] | None = None,
    slack_user_id: str = "U123456",
    display_name: str = "Test User",
) -> User:
    """Create a test user."""
    return User(
        id=user_id or ObjectId(),
        slack_user_id=slack_user_id,
        slack_team_id="T123456",
        slack_display_name=display_name,
        roles=roles or [UserRole.GENERAL_PARTICIPANT],
        created_at=datetime.now(timezone.utc),
    )


def create_facilitator(
    user_id: ObjectId | None = None,
    display_name: str = "Facilitator",
) -> User:
    """Create a facilitator user."""
    return create_test_user(
        user_id=user_id,
        roles=[UserRole.FACILITATOR],
        slack_user_id=f"U_FAC_{ObjectId()}",
        display_name=display_name,
    )


def create_admin(
    user_id: ObjectId | None = None,
    display_name: str = "Admin",
) -> User:
    """Create an admin user."""
    return create_test_user(
        user_id=user_id,
        roles=[UserRole.WORKSPACE_ADMIN],
        slack_user_id=f"U_ADMIN_{ObjectId()}",
        display_name=display_name,
    )


def create_mock_high_stakes_candidate() -> MagicMock:
    """Create a mock high-stakes COP candidate for testing."""
    candidate = MagicMock()
    candidate.id = ObjectId()
    candidate.risk_tier = "high_stakes"
    candidate.readiness_state = "blocked"
    candidate.topic_label = "Emergency Shelter Closure"
    return candidate


def make_mock_settings(
    two_person_enabled: bool = True,
    abuse_enabled: bool = True,
    abuse_threshold: int = 5,
    abuse_window: int = 30,
):
    """Create mock settings for tests."""
    mock = MagicMock()
    mock.two_person_rule_enabled = two_person_enabled
    mock.two_person_rule_timeout_hours = 24
    mock.abuse_detection_enabled = abuse_enabled
    mock.abuse_override_threshold = abuse_threshold
    mock.abuse_override_window_minutes = abuse_window
    mock.abuse_alert_slack_channel = None
    mock.default_retention_days = 90
    return mock


def make_mock_audit_service():
    """Create mock audit service."""
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


# ============================================================================
# Two-Person Rule E2E Tests (S7-1)
# ============================================================================


@pytest.mark.integration
class TestTwoPersonRuleWorkflow:
    """End-to-end tests for two-person approval workflow."""

    @pytest.mark.asyncio
    async def test_complete_two_person_approval_workflow(self) -> None:
        """Test complete workflow: request -> grant -> override succeeds."""
        from integritykit.services.risk_classification import TwoPersonApprovalService

        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.risk_classification._get_settings",
            return_value=make_mock_settings(two_person_enabled=True),
        ):
            service = TwoPersonApprovalService(audit_service=mock_audit)
            candidate = create_mock_high_stakes_candidate()
            requestor = create_facilitator(display_name="Requestor")
            approver = create_facilitator(display_name="Approver")

            # Step 1: Requestor asks for two-person approval
            approval = await service.request_approval(
                candidate=candidate,
                override_type="high_stakes_publish",
                requester=requestor,
                justification="Urgent shelter situation requires immediate action for community safety",
            )

            assert approval.status == TwoPersonApprovalStatus.PENDING
            assert approval.requested_by == requestor.id

            # Step 2: Different facilitator grants approval
            updated_approval = await service.grant_approval(
                candidate_id=candidate.id,
                override_type="high_stakes_publish",
                approver=approver,
            )

            assert updated_approval.status == TwoPersonApprovalStatus.APPROVED
            assert updated_approval.second_approver_id == approver.id
            assert updated_approval.second_approval_at is not None

            # Step 3: Verify audit was logged
            assert mock_audit.log_action.call_count >= 1

    @pytest.mark.asyncio
    async def test_self_approval_prevented(self) -> None:
        """Test that same user cannot approve their own request."""
        from integritykit.services.risk_classification import TwoPersonApprovalService

        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.risk_classification._get_settings",
            return_value=make_mock_settings(two_person_enabled=True),
        ):
            service = TwoPersonApprovalService(audit_service=mock_audit)
            candidate = create_mock_high_stakes_candidate()
            facilitator = create_facilitator()

            # Request approval
            approval = await service.request_approval(
                candidate=candidate,
                override_type="high_stakes_publish",
                requester=facilitator,
                justification="Test request for approval workflow validation",
            )

            # Try to self-approve
            with pytest.raises(ValueError, match="must be different"):
                await service.grant_approval(
                    candidate_id=candidate.id,
                    override_type="high_stakes_publish",
                    approver=facilitator,  # Same user
                )

    @pytest.mark.asyncio
    async def test_denial_workflow(self) -> None:
        """Test that denial blocks the override."""
        from integritykit.services.risk_classification import TwoPersonApprovalService

        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.risk_classification._get_settings",
            return_value=make_mock_settings(two_person_enabled=True),
        ):
            service = TwoPersonApprovalService(audit_service=mock_audit)
            candidate = create_mock_high_stakes_candidate()
            requestor = create_facilitator(display_name="Requestor")
            denier = create_facilitator(display_name="Denier")

            # Request approval
            approval = await service.request_approval(
                candidate=candidate,
                override_type="high_stakes_publish",
                requester=requestor,
                justification="Test request for denial workflow validation",
            )

            # Deny approval
            denied_approval = await service.deny_approval(
                candidate_id=candidate.id,
                override_type="high_stakes_publish",
                denier=denier,
                reason="Insufficient evidence",
            )

            assert denied_approval.status == TwoPersonApprovalStatus.DENIED
            assert denied_approval.denial_reason == "Insufficient evidence"


# ============================================================================
# Abuse Detection E2E Tests (S7-3)
# ============================================================================


@pytest.mark.integration
class TestAbuseDetectionWorkflow:
    """End-to-end tests for abuse detection workflow."""

    @pytest.mark.asyncio
    async def test_rapid_fire_override_triggers_alert(self) -> None:
        """Test that rapid overrides trigger abuse alert."""
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(
                abuse_enabled=True,
                abuse_threshold=3,  # Low threshold for testing
                abuse_window=30,
            ),
        ):
            service = AbuseDetectionService(audit_service=mock_audit)
            facilitator = create_facilitator()

            # Perform rapid overrides
            alerts = []
            for i in range(3):
                alert = await service.record_override(
                    user=facilitator,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                if alert:
                    alerts.append(alert)

            # Should have triggered an alert
            assert len(alerts) == 1
            assert alerts[0].alert_type == "rapid_fire_overrides"
            assert alerts[0].override_count >= 3

            # Audit should be flagged
            mock_audit.log_action.assert_called()
            call_kwargs = mock_audit.log_action.call_args.kwargs
            assert call_kwargs["is_flagged"] is True

    @pytest.mark.asyncio
    async def test_alert_flood_prevention(self) -> None:
        """Test that duplicate alerts are suppressed within cooldown period."""
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(
                abuse_enabled=True,
                abuse_threshold=2,
                abuse_window=60,
            ),
        ):
            service = AbuseDetectionService(audit_service=mock_audit)
            facilitator = create_facilitator()

            # First batch - triggers alert
            for i in range(2):
                await service.record_override(
                    user=facilitator,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )

            # Second batch - should be suppressed
            alerts_second_batch = []
            for i in range(3):
                alert = await service.record_override(
                    user=facilitator,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                if alert:
                    alerts_second_batch.append(alert)

            # No new alerts due to flood prevention
            assert len(alerts_second_batch) == 0

            # Only one audit log call (from first alert)
            assert mock_audit.log_action.call_count == 1

    @pytest.mark.asyncio
    async def test_disabled_abuse_detection_no_tracking(self) -> None:
        """Test that disabled abuse detection doesn't track or alert."""
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(abuse_enabled=False),
        ):
            service = AbuseDetectionService(audit_service=mock_audit)
            facilitator = create_facilitator()

            # Many overrides - should not trigger anything
            for i in range(20):
                alert = await service.record_override(
                    user=facilitator,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                assert alert is None

            # No audit calls
            mock_audit.log_action.assert_not_called()


# ============================================================================
# User Suspension E2E Tests (S7-4)
# ============================================================================


@pytest.mark.integration
class TestUserSuspensionWorkflow:
    """End-to-end tests for user suspension workflow."""

    @pytest.mark.asyncio
    async def test_complete_suspension_reinstatement_cycle(self) -> None:
        """Test full cycle: suspend -> verify blocked -> reinstate -> verify active."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = create_admin()
        facilitator = create_facilitator()

        # Verify facilitator has permissions before suspension
        assert facilitator.has_permission(Permission.PUBLISH_COP) is True
        assert facilitator.has_permission(Permission.VIEW_BACKLOG) is True

        # Step 1: Admin suspends facilitator
        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Detected abuse pattern in override behavior",
        )

        # Verify suspension
        assert suspended.is_suspended is True
        assert suspended.has_permission(Permission.PUBLISH_COP) is False
        assert suspended.has_permission(Permission.VIEW_BACKLOG) is False
        assert len(suspended.suspension_history) == 1

        # Step 2: Admin reinstates facilitator
        reinstated = await service.reinstate_user(
            admin=admin,
            target=suspended,
            reason="Issue resolved after review",
        )

        # Verify reinstatement
        assert reinstated.is_suspended is False
        assert reinstated.has_permission(Permission.PUBLISH_COP) is True
        assert reinstated.has_permission(Permission.VIEW_BACKLOG) is True
        assert reinstated.suspension_history[0].reinstated_at is not None

        # Verify audit trail
        assert mock_audit.log_action.call_count == 2  # suspend + reinstate

    @pytest.mark.asyncio
    async def test_suspension_protects_admin_accounts(self) -> None:
        """Test that admin accounts cannot be suspended."""
        from integritykit.services.suspension import SuspendAdminError

        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin1 = create_admin(display_name="Admin 1")
        admin2 = create_admin(display_name="Admin 2")

        # Try to suspend another admin
        with pytest.raises(SuspendAdminError):
            await service.suspend_user(
                admin=admin1,
                target=admin2,
                reason="Attempted admin suspension",
            )

    @pytest.mark.asyncio
    async def test_suspension_status_tracking(self) -> None:
        """Test that suspension status is properly tracked."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = create_admin()
        facilitator = create_facilitator()

        # Check initial status
        initial_status = await service.get_suspension_status(facilitator)
        assert initial_status["is_suspended"] is False
        assert initial_status["suspension_count"] == 0

        # Suspend
        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Test suspension",
        )

        # Check suspended status
        suspended_status = await service.get_suspension_status(suspended)
        assert suspended_status["is_suspended"] is True
        assert suspended_status["suspension_count"] == 1
        assert suspended_status["current_suspension"] is not None
        assert "Test suspension" in suspended_status["current_suspension"]["reason"]


# ============================================================================
# Data Retention E2E Tests (S7-5)
# ============================================================================


@pytest.mark.integration
class TestDataRetentionWorkflow:
    """End-to-end tests for data retention workflow."""

    @pytest.mark.asyncio
    async def test_expiration_calculation(self) -> None:
        """Test that expiration dates are calculated correctly."""
        from integritykit.services.data_retention import DataRetentionService

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: getattr(mock_db, key)
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=mock_audit,
            )

            # Default retention
            now = datetime.utcnow()
            expires = service.calculate_expiration_date()
            expected = now + timedelta(days=90)

            # Should be approximately 90 days from now
            diff = abs((expires - expected).total_seconds())
            assert diff < 5  # Within 5 seconds

    @pytest.mark.asyncio
    async def test_dry_run_purge_counts_without_deleting(self) -> None:
        """Test that dry run reports counts without deleting."""
        from integritykit.services.data_retention import DataRetentionService

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: getattr(mock_db, key)
        mock_db.signals.count_documents = AsyncMock(return_value=42)
        mock_db.signals.delete_many = AsyncMock()
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=mock_audit,
            )

            result = await service.purge_expired_signals(dry_run=True)

            assert result.deleted_count == 42
            mock_db.signals.delete_many.assert_not_called()


# ============================================================================
# Combined Workflow Tests
# ============================================================================


@pytest.mark.integration
class TestCombinedHardeningWorkflows:
    """Tests combining multiple hardening features."""

    @pytest.mark.asyncio
    async def test_abuse_detection_triggers_suspension_workflow(self) -> None:
        """Test that abuse detection can lead to user suspension."""
        abuse_audit = make_mock_audit_service()
        suspension_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(
                abuse_enabled=True,
                abuse_threshold=3,
            ),
        ):
            abuse_service = AbuseDetectionService(audit_service=abuse_audit)
            suspension_service = SuspensionService(audit_service=suspension_audit)

            admin = create_admin()
            facilitator = create_facilitator()

            # Step 1: Facilitator triggers abuse alert
            alert = None
            for i in range(3):
                alert = await abuse_service.record_override(
                    user=facilitator,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )

            assert alert is not None

            # Step 2: Admin suspends based on alert
            suspended = await suspension_service.suspend_user(
                admin=admin,
                target=facilitator,
                reason=f"Suspended due to abuse alert: {alert.override_count} overrides in {alert.window_minutes} minutes",
            )

            # Verify complete workflow
            assert suspended.is_suspended is True
            assert suspended.has_permission(Permission.PUBLISH_COP) is False

            # Verify audit trail for both services
            abuse_audit.log_action.assert_called()
            suspension_audit.log_action.assert_called()
