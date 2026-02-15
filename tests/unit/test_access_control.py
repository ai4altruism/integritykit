"""
Unit tests for access control and access-denied scenarios.

Tests:
- FR-ROLE-002: Role-based access enforcement
- Non-facilitators cannot access backlog or search
"""

import pytest
from bson import ObjectId
from fastapi import HTTPException

from integritykit.models.user import Permission, User, UserRole
from integritykit.services.rbac import (
    AccessDeniedError,
    RBACService,
    UserSuspendedError,
)


# ============================================================================
# Access Denied for Backlog Tests
# ============================================================================


@pytest.mark.unit
class TestBacklogAccessDenied:
    """Test that non-facilitators cannot access backlog."""

    def test_general_participant_denied_backlog(self) -> None:
        """General participant cannot view backlog."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],  # General participant
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError) as exc_info:
            service.require_permission(user, Permission.VIEW_BACKLOG)

        assert "VIEW_BACKLOG" in str(exc_info.value.message)

    def test_general_participant_cannot_promote(self) -> None:
        """General participant cannot promote clusters."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.PROMOTE_CLUSTER)

    def test_verifier_can_view_backlog(self) -> None:
        """Verifier can view backlog."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.VIEW_BACKLOG)

    def test_facilitator_can_view_backlog(self) -> None:
        """Facilitator can view backlog."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.VIEW_BACKLOG)


# ============================================================================
# Access Denied for Search Tests
# ============================================================================


@pytest.mark.unit
class TestSearchAccessDenied:
    """Test that non-facilitators cannot access search."""

    def test_general_participant_denied_search(self) -> None:
        """General participant cannot use search."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError) as exc_info:
            service.require_permission(user, Permission.SEARCH)

        assert "SEARCH" in str(exc_info.value.message)

    def test_verifier_can_search(self) -> None:
        """Verifier can use search."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.SEARCH)

    def test_facilitator_can_search(self) -> None:
        """Facilitator can use search."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.SEARCH)


# ============================================================================
# Access Denied for Promote Tests
# ============================================================================


@pytest.mark.unit
class TestPromoteAccessDenied:
    """Test that only authorized users can promote clusters."""

    def test_general_participant_denied_promote(self) -> None:
        """General participant cannot promote clusters."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.PROMOTE_CLUSTER)

    def test_verifier_denied_promote(self) -> None:
        """Verifier cannot promote clusters."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.PROMOTE_CLUSTER)

    def test_facilitator_can_promote(self) -> None:
        """Facilitator can promote clusters."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.PROMOTE_CLUSTER)


# ============================================================================
# Access Denied for Admin Actions Tests
# ============================================================================


@pytest.mark.unit
class TestAdminAccessDenied:
    """Test that only admins can perform admin actions."""

    def test_general_participant_denied_manage_roles(self) -> None:
        """General participant cannot manage roles."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.MANAGE_ROLES)

    def test_facilitator_denied_manage_roles(self) -> None:
        """Facilitator cannot manage roles."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.MANAGE_ROLES)

    def test_admin_can_manage_roles(self) -> None:
        """Admin can manage roles."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.MANAGE_ROLES)

    def test_general_participant_denied_suspend(self) -> None:
        """General participant cannot suspend users."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.SUSPEND_USER)

    def test_admin_can_suspend(self) -> None:
        """Admin can suspend users."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.SUSPEND_USER)


# ============================================================================
# Suspended User Tests
# ============================================================================


@pytest.mark.unit
class TestSuspendedUserAccess:
    """Test that suspended users are denied all access."""

    def test_suspended_facilitator_denied_backlog(self) -> None:
        """Suspended facilitator cannot view backlog."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
            is_suspended=True,
        )

        service = RBACService()

        with pytest.raises(UserSuspendedError):
            service.require_permission(user, Permission.VIEW_BACKLOG)

    def test_suspended_admin_denied_manage_roles(self) -> None:
        """Suspended admin cannot manage roles."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
            is_suspended=True,
        )

        service = RBACService()

        with pytest.raises(UserSuspendedError):
            service.require_permission(user, Permission.MANAGE_ROLES)

    def test_suspended_user_denied_search(self) -> None:
        """Suspended user cannot use search."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
            is_suspended=True,
        )

        service = RBACService()

        with pytest.raises(UserSuspendedError):
            service.require_permission(user, Permission.SEARCH)


# ============================================================================
# Role Requirement Tests
# ============================================================================


@pytest.mark.unit
class TestRoleRequirements:
    """Test role requirement checks."""

    def test_require_facilitator_role(self) -> None:
        """Require facilitator role."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError) as exc_info:
            service.require_role(user, UserRole.FACILITATOR)

        assert "FACILITATOR" in str(exc_info.value.message)

    def test_require_any_role_fails(self) -> None:
        """Require any of multiple roles fails when user has none."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_any_role(
                user,
                [UserRole.FACILITATOR, UserRole.VERIFIER],
            )

    def test_require_any_role_succeeds(self) -> None:
        """Require any of multiple roles succeeds when user has one."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = RBACService()

        # Should not raise
        service.require_any_role(
            user,
            [UserRole.FACILITATOR, UserRole.VERIFIER],
        )


# ============================================================================
# Permission Check Method Tests
# ============================================================================


@pytest.mark.unit
class TestPermissionChecks:
    """Test permission check methods."""

    def test_check_permission_returns_false(self) -> None:
        """check_permission returns False for denied permissions."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        result = service.check_permission(user, Permission.VIEW_BACKLOG)

        assert result is False

    def test_check_permission_returns_true(self) -> None:
        """check_permission returns True for granted permissions."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        result = service.check_permission(user, Permission.VIEW_BACKLOG)

        assert result is True

    def test_check_permission_suspended_returns_false(self) -> None:
        """check_permission returns False for suspended users."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
            is_suspended=True,
        )

        service = RBACService()

        result = service.check_permission(user, Permission.VIEW_BACKLOG)

        assert result is False


# ============================================================================
# Audit Log Access Tests
# ============================================================================


@pytest.mark.unit
class TestAuditLogAccess:
    """Test audit log access controls."""

    def test_general_participant_denied_audit_log(self) -> None:
        """General participant cannot view audit log."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.VIEW_AUDIT_LOG)

    def test_facilitator_denied_audit_log(self) -> None:
        """Facilitator cannot view audit log."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.VIEW_AUDIT_LOG)

    def test_admin_can_view_audit_log(self) -> None:
        """Admin can view audit log."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.VIEW_AUDIT_LOG)


# ============================================================================
# COP Publish Access Tests
# ============================================================================


@pytest.mark.unit
class TestCOPPublishAccess:
    """Test COP publish access controls."""

    def test_general_participant_denied_publish(self) -> None:
        """General participant cannot publish COP."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.PUBLISH_COP)

    def test_verifier_denied_publish(self) -> None:
        """Verifier cannot publish COP."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = RBACService()

        with pytest.raises(AccessDeniedError):
            service.require_permission(user, Permission.PUBLISH_COP)

    def test_facilitator_can_publish(self) -> None:
        """Facilitator can publish COP."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        service = RBACService()

        # Should not raise
        service.require_permission(user, Permission.PUBLISH_COP)
