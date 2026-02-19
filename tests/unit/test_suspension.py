"""Unit tests for user suspension service.

Tests:
- S7-4: Facilitator permission suspension by admin
- NFR-ABUSE-002: Permission suspension
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from integritykit.models.user import (
    Permission,
    SuspensionRecord,
    User,
    UserRole,
)
from integritykit.services.rbac import AccessDeniedError, InvalidRoleError
from integritykit.services.suspension import (
    SelfSuspensionError,
    SuspendAdminError,
    SuspensionService,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_user(
    *,
    user_id: ObjectId | None = None,
    roles: list[UserRole] | None = None,
    is_suspended: bool = False,
    suspension_history: list | None = None,
) -> User:
    """Create a test user."""
    return User(
        id=user_id or ObjectId(),
        slack_user_id="U123456",
        slack_team_id="T123456",
        slack_display_name="Test User",
        roles=roles or [UserRole.GENERAL_PARTICIPANT],
        is_suspended=is_suspended,
        suspension_history=suspension_history or [],
        created_at=datetime.now(timezone.utc),
    )


def make_admin(user_id: ObjectId | None = None) -> User:
    """Create a test admin user."""
    return User(
        id=user_id or ObjectId(),
        slack_user_id="U_ADMIN",
        slack_team_id="T123456",
        slack_display_name="Admin User",
        roles=[UserRole.WORKSPACE_ADMIN],
        created_at=datetime.now(timezone.utc),
    )


def make_facilitator(user_id: ObjectId | None = None) -> User:
    """Create a test facilitator user."""
    return User(
        id=user_id or ObjectId(),
        slack_user_id="U_FACILITATOR",
        slack_team_id="T123456",
        slack_display_name="Facilitator User",
        roles=[UserRole.FACILITATOR],
        created_at=datetime.now(timezone.utc),
    )


def make_mock_audit_service():
    """Create mock audit service."""
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


# ============================================================================
# SuspensionService Tests
# ============================================================================


@pytest.mark.unit
class TestSuspensionService:
    """Test SuspensionService functionality."""

    @pytest.mark.asyncio
    async def test_admin_can_suspend_facilitator(self) -> None:
        """Admin can suspend a facilitator."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        facilitator = make_facilitator()

        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Abuse detected in override patterns",
        )

        assert suspended.is_suspended is True
        assert len(suspended.suspension_history) == 1
        assert suspended.suspension_history[0].suspension_reason == "Abuse detected in override patterns"

    @pytest.mark.asyncio
    async def test_suspended_user_loses_permissions(self) -> None:
        """Suspended user loses all permissions."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        facilitator = make_facilitator()

        # Before suspension, facilitator has permissions
        assert facilitator.has_permission(Permission.PUBLISH_COP) is True
        assert facilitator.has_permission(Permission.VIEW_BACKLOG) is True

        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Abuse detected",
        )

        # After suspension, all permissions revoked
        assert suspended.has_permission(Permission.PUBLISH_COP) is False
        assert suspended.has_permission(Permission.VIEW_BACKLOG) is False
        assert suspended.has_permission(Permission.VIEW_SIGNALS) is False

    @pytest.mark.asyncio
    async def test_cannot_suspend_self(self) -> None:
        """Admin cannot suspend themselves."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()

        with pytest.raises(SelfSuspensionError):
            await service.suspend_user(
                admin=admin,
                target=admin,  # Same user
                reason="Self-suspension attempt",
            )

    @pytest.mark.asyncio
    async def test_cannot_suspend_another_admin(self) -> None:
        """Admin cannot suspend another admin."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin1 = make_admin()
        admin2 = make_admin()

        with pytest.raises(SuspendAdminError):
            await service.suspend_user(
                admin=admin1,
                target=admin2,
                reason="Trying to suspend admin",
            )

    @pytest.mark.asyncio
    async def test_non_admin_cannot_suspend(self) -> None:
        """Non-admin users cannot suspend others."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        facilitator = make_facilitator()
        other_user = make_user()

        with pytest.raises(AccessDeniedError):
            await service.suspend_user(
                admin=facilitator,  # Not an admin
                target=other_user,
                reason="Unauthorized suspension attempt",
            )

    @pytest.mark.asyncio
    async def test_cannot_suspend_already_suspended(self) -> None:
        """Cannot suspend an already suspended user."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        already_suspended = make_facilitator()
        already_suspended.is_suspended = True

        with pytest.raises(InvalidRoleError):
            await service.suspend_user(
                admin=admin,
                target=already_suspended,
                reason="Already suspended",
            )


@pytest.mark.unit
class TestReinstatement:
    """Test user reinstatement functionality."""

    @pytest.mark.asyncio
    async def test_admin_can_reinstate_user(self) -> None:
        """Admin can reinstate a suspended user."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin.id,
            suspension_reason="Test suspension",
        )
        suspended_user = make_facilitator()
        suspended_user.is_suspended = True
        suspended_user.suspension_history = [suspension]

        reinstated = await service.reinstate_user(
            admin=admin,
            target=suspended_user,
            reason="Issue resolved",
        )

        assert reinstated.is_suspended is False
        assert reinstated.suspension_history[0].reinstated_at is not None
        assert reinstated.suspension_history[0].reinstatement_reason == "Issue resolved"

    @pytest.mark.asyncio
    async def test_reinstated_user_regains_permissions(self) -> None:
        """Reinstated user regains their permissions."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin.id,
            suspension_reason="Test suspension",
        )
        suspended_user = make_facilitator()
        suspended_user.is_suspended = True
        suspended_user.suspension_history = [suspension]

        # While suspended, no permissions
        assert suspended_user.has_permission(Permission.PUBLISH_COP) is False

        reinstated = await service.reinstate_user(
            admin=admin,
            target=suspended_user,
        )

        # After reinstatement, permissions restored
        assert reinstated.has_permission(Permission.PUBLISH_COP) is True
        assert reinstated.has_permission(Permission.VIEW_BACKLOG) is True

    @pytest.mark.asyncio
    async def test_cannot_reinstate_non_suspended_user(self) -> None:
        """Cannot reinstate a user who is not suspended."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        active_user = make_facilitator()

        with pytest.raises(InvalidRoleError):
            await service.reinstate_user(
                admin=admin,
                target=active_user,
                reason="Not suspended",
            )


@pytest.mark.unit
class TestSuspensionAuditLogging:
    """Test that suspension actions are properly logged."""

    @pytest.mark.asyncio
    async def test_suspension_is_audit_logged(self) -> None:
        """Suspension creates audit log entry."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        facilitator = make_facilitator()

        await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Audit test suspension",
        )

        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args.kwargs
        assert call_kwargs["action_type"].value == "user.suspend"
        assert call_kwargs["target_id"] == facilitator.id
        assert call_kwargs["changes_after"]["is_suspended"] is True

    @pytest.mark.asyncio
    async def test_reinstatement_is_audit_logged(self) -> None:
        """Reinstatement creates audit log entry."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin.id,
            suspension_reason="Test suspension",
        )
        suspended_user = make_facilitator()
        suspended_user.is_suspended = True
        suspended_user.suspension_history = [suspension]

        await service.reinstate_user(
            admin=admin,
            target=suspended_user,
            reason="Audit test reinstatement",
        )

        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args.kwargs
        assert call_kwargs["action_type"].value == "user.reinstate"
        assert call_kwargs["target_id"] == suspended_user.id
        assert call_kwargs["changes_after"]["is_suspended"] is False


@pytest.mark.unit
class TestSuspensionStatus:
    """Test suspension status checking."""

    @pytest.mark.asyncio
    async def test_get_status_for_active_user(self) -> None:
        """Get status returns correct info for active user."""
        service = SuspensionService(audit_service=make_mock_audit_service())
        user = make_facilitator()

        status = await service.get_suspension_status(user)

        assert status["is_suspended"] is False
        assert status["suspension_count"] == 0
        assert status["current_suspension"] is None

    @pytest.mark.asyncio
    async def test_get_status_for_suspended_user(self) -> None:
        """Get status returns correct info for suspended user."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin_id = ObjectId()
        suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin_id,
            suspension_reason="Test reason",
        )
        user = make_facilitator()
        user.is_suspended = True
        user.suspension_history = [suspension]

        status = await service.get_suspension_status(user)

        assert status["is_suspended"] is True
        assert status["suspension_count"] == 1
        assert status["current_suspension"]["reason"] == "Test reason"

    @pytest.mark.asyncio
    async def test_get_status_with_history(self) -> None:
        """Get status includes full suspension history."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin_id = ObjectId()
        past_suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin_id,
            suspension_reason="First suspension",
            reinstated_at=datetime.now(timezone.utc),
            reinstated_by=admin_id,
            reinstatement_reason="Resolved",
        )
        current_suspension = SuspensionRecord(
            suspended_at=datetime.now(timezone.utc),
            suspended_by=admin_id,
            suspension_reason="Second suspension",
        )
        user = make_facilitator()
        user.is_suspended = True
        user.suspension_history = [past_suspension, current_suspension]

        status = await service.get_suspension_status(user)

        assert status["suspension_count"] == 2
        assert len(status["suspension_history"]) == 2
        assert status["suspension_history"][0]["is_active"] is False
        assert status["suspension_history"][1]["is_active"] is True


@pytest.mark.unit
class TestCanBeSuspended:
    """Test the can_be_suspended check."""

    def test_facilitator_can_be_suspended_by_admin(self) -> None:
        """Facilitator can be suspended by admin."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin = make_admin()
        facilitator = make_facilitator()

        can_suspend, reason = service.can_be_suspended(admin, facilitator)

        assert can_suspend is True
        assert reason == ""

    def test_admin_cannot_be_suspended(self) -> None:
        """Admin cannot be suspended."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin1 = make_admin()
        admin2 = make_admin()

        can_suspend, reason = service.can_be_suspended(admin1, admin2)

        assert can_suspend is False
        assert "admin" in reason.lower()

    def test_self_cannot_be_suspended(self) -> None:
        """Cannot suspend yourself."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin = make_admin()

        can_suspend, reason = service.can_be_suspended(admin, admin)

        assert can_suspend is False
        assert "yourself" in reason.lower()

    def test_already_suspended_cannot_be_suspended(self) -> None:
        """Already suspended user cannot be suspended again."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        admin = make_admin()
        suspended_user = make_facilitator()
        suspended_user.is_suspended = True

        can_suspend, reason = service.can_be_suspended(admin, suspended_user)

        assert can_suspend is False
        assert "already" in reason.lower()

    def test_non_admin_cannot_suspend(self) -> None:
        """Non-admin lacks permission to suspend."""
        service = SuspensionService(audit_service=make_mock_audit_service())

        facilitator = make_facilitator()
        other_user = make_user()

        can_suspend, reason = service.can_be_suspended(facilitator, other_user)

        assert can_suspend is False
        assert "permission" in reason.lower()


@pytest.mark.unit
class TestSuspensionPreservesRoles:
    """Test that suspension preserves roles for later reinstatement."""

    @pytest.mark.asyncio
    async def test_roles_preserved_during_suspension(self) -> None:
        """User roles are preserved during suspension."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()
        facilitator = make_facilitator()
        original_roles = list(facilitator.roles)

        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Temporary suspension",
        )

        # Roles are still on the user object (just inactive)
        suspended_roles = [
            r.value if hasattr(r, 'value') else r
            for r in suspended.roles
        ]
        original_role_values = [
            r.value if hasattr(r, 'value') else r
            for r in original_roles
        ]
        assert suspended_roles == original_role_values

    @pytest.mark.asyncio
    async def test_roles_active_after_reinstatement(self) -> None:
        """User roles are active after reinstatement."""
        mock_audit = make_mock_audit_service()
        service = SuspensionService(audit_service=mock_audit)

        admin = make_admin()

        # Create and suspend facilitator
        facilitator = make_facilitator()
        suspended = await service.suspend_user(
            admin=admin,
            target=facilitator,
            reason="Temporary suspension",
        )

        # Reinstate
        reinstated = await service.reinstate_user(
            admin=admin,
            target=suspended,
            reason="Issue resolved",
        )

        # Roles are now active again
        assert reinstated.has_role(UserRole.FACILITATOR) is True
        assert reinstated.has_permission(Permission.PUBLISH_COP) is True
