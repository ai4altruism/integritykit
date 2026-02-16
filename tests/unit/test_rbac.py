"""
Unit tests for role-based access control (RBAC) logic.

Tests permission checks for different user roles:
- general_participant: Can view signals and clusters
- facilitator: Can promote clusters, update candidates, publish COPs
- verifier: Can verify candidates
- workspace_admin: Can manage user roles and system settings

These are pure unit tests testing business logic without database dependencies.
"""

import pytest
from bson import ObjectId

from integritykit.models.user import (
    Permission,
    ROLE_PERMISSIONS,
    User,
    UserCreate,
    UserRole,
)
from integritykit.services.rbac import (
    AccessDeniedError,
    InvalidRoleError,
    RBACService,
    UserSuspendedError,
)
from tests.factories import create_admin, create_facilitator, create_user


# ============================================================================
# User Model Tests
# ============================================================================


@pytest.mark.unit
class TestUserModel:
    """Test User model behavior."""

    def test_user_has_base_role_by_default(self) -> None:
        """All users should have general_participant role by default."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
        )
        assert user.has_role(UserRole.GENERAL_PARTICIPANT)

    def test_user_roles_always_include_base_role(self) -> None:
        """Even when setting other roles, general_participant is included."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        assert user.has_role(UserRole.GENERAL_PARTICIPANT)
        assert user.has_role(UserRole.FACILITATOR)

    def test_user_has_permission_checks_role_permissions(self) -> None:
        """has_permission should check role-based permissions."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        assert facilitator.has_permission(Permission.VIEW_BACKLOG)
        assert facilitator.has_permission(Permission.PUBLISH_COP)
        assert not facilitator.has_permission(Permission.MANAGE_ROLES)

    def test_suspended_user_has_no_permissions(self) -> None:
        """Suspended users should have no permissions."""
        suspended_user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
            is_suspended=True,
        )

        assert not suspended_user.has_permission(Permission.VIEW_BACKLOG)
        assert suspended_user.get_permissions() == set()

    def test_get_permissions_returns_all_role_permissions(self) -> None:
        """get_permissions should return all permissions from all roles."""
        admin = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        permissions = admin.get_permissions()
        assert Permission.MANAGE_ROLES in permissions
        assert Permission.VIEW_BACKLOG in permissions
        assert Permission.PUBLISH_COP in permissions

    def test_is_facilitator_property(self) -> None:
        """is_facilitator property should work correctly."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        regular = User(
            slack_user_id="U456",
            slack_team_id="T123",
        )

        assert facilitator.is_facilitator
        assert not regular.is_facilitator

    def test_is_admin_property(self) -> None:
        """is_admin property should work correctly."""
        admin = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )
        facilitator = User(
            slack_user_id="U456",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        assert admin.is_admin
        assert not facilitator.is_admin


# ============================================================================
# Role Permissions Mapping Tests
# ============================================================================


@pytest.mark.unit
class TestRolePermissions:
    """Test role-to-permission mappings."""

    def test_general_participant_has_limited_permissions(self) -> None:
        """General participants have read-only access to signals."""
        perms = ROLE_PERMISSIONS[UserRole.GENERAL_PARTICIPANT]

        assert Permission.VIEW_SIGNALS in perms
        assert Permission.VIEW_BACKLOG not in perms
        assert Permission.PUBLISH_COP not in perms

    def test_verifier_has_verification_permissions(self) -> None:
        """Verifiers can view backlog and verify candidates."""
        perms = ROLE_PERMISSIONS[UserRole.VERIFIER]

        assert Permission.VIEW_BACKLOG in perms
        assert Permission.VERIFY_CANDIDATE in perms
        assert Permission.PUBLISH_COP not in perms

    def test_facilitator_has_full_workflow_permissions(self) -> None:
        """Facilitators have full backlog and candidate management."""
        perms = ROLE_PERMISSIONS[UserRole.FACILITATOR]

        assert Permission.VIEW_BACKLOG in perms
        assert Permission.PROMOTE_CLUSTER in perms
        assert Permission.PUBLISH_COP in perms
        assert Permission.SEARCH in perms
        assert Permission.MANAGE_ROLES not in perms

    def test_admin_has_all_permissions(self) -> None:
        """Workspace admins have all permissions including user management."""
        perms = ROLE_PERMISSIONS[UserRole.WORKSPACE_ADMIN]

        assert Permission.MANAGE_ROLES in perms
        assert Permission.SUSPEND_USER in perms
        assert Permission.VIEW_USERS in perms
        assert Permission.PUBLISH_COP in perms


# ============================================================================
# RBAC Service Tests
# ============================================================================


@pytest.mark.unit
class TestRBACService:
    """Test RBACService permission checking."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.rbac = RBACService()

    def test_check_permission_returns_true_for_allowed(self) -> None:
        """check_permission returns True when user has permission."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        assert self.rbac.check_permission(user, Permission.VIEW_BACKLOG)

    def test_check_permission_returns_false_for_denied(self) -> None:
        """check_permission returns False when user lacks permission."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.GENERAL_PARTICIPANT],
        )

        assert not self.rbac.check_permission(user, Permission.VIEW_BACKLOG)

    def test_check_permission_raises_for_suspended_user(self) -> None:
        """check_permission raises UserSuspendedError for suspended users."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
            is_suspended=True,
        )

        with pytest.raises(UserSuspendedError):
            self.rbac.check_permission(user, Permission.VIEW_BACKLOG)

    def test_require_permission_raises_for_denied(self) -> None:
        """require_permission raises AccessDeniedError when permission denied."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.GENERAL_PARTICIPANT],
        )

        with pytest.raises(AccessDeniedError) as exc_info:
            self.rbac.require_permission(user, Permission.VIEW_BACKLOG)

        assert exc_info.value.required_permission == Permission.VIEW_BACKLOG

    def test_require_role_raises_for_missing_role(self) -> None:
        """require_role raises AccessDeniedError when role is missing."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.GENERAL_PARTICIPANT],
        )

        with pytest.raises(AccessDeniedError) as exc_info:
            self.rbac.require_role(user, UserRole.FACILITATOR)

        assert exc_info.value.required_role == UserRole.FACILITATOR

    def test_require_any_role_passes_with_one_match(self) -> None:
        """require_any_role passes when user has any of the roles."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        # Should not raise
        self.rbac.require_any_role(user, [UserRole.VERIFIER, UserRole.FACILITATOR])

    def test_require_any_role_raises_with_no_match(self) -> None:
        """require_any_role raises when user has none of the roles."""
        user = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.GENERAL_PARTICIPANT],
        )

        with pytest.raises(AccessDeniedError):
            self.rbac.require_any_role(user, [UserRole.VERIFIER, UserRole.FACILITATOR])


# ============================================================================
# Role Assignment Tests
# ============================================================================


@pytest.mark.unit
class TestRoleAssignment:
    """Test role assignment and revocation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.rbac = RBACService()
        self.admin_id = ObjectId()

    def test_assign_role_adds_role(self) -> None:
        """assign_role adds the role to user."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        updated = self.rbac.assign_role(
            user, UserRole.FACILITATOR, self.admin_id, "Promoted to facilitator"
        )

        assert updated.has_role(UserRole.FACILITATOR)

    def test_assign_role_creates_history_entry(self) -> None:
        """assign_role creates role history entry."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        updated = self.rbac.assign_role(
            user, UserRole.FACILITATOR, self.admin_id, "Promoted to facilitator"
        )

        assert len(updated.role_history) == 1
        assert UserRole.FACILITATOR in updated.role_history[0].new_roles
        assert updated.role_history[0].changed_by == self.admin_id

    def test_assign_role_raises_if_already_assigned(self) -> None:
        """assign_role raises InvalidRoleError if role already assigned."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        with pytest.raises(InvalidRoleError):
            self.rbac.assign_role(user, UserRole.FACILITATOR, self.admin_id)

    def test_revoke_role_removes_role(self) -> None:
        """revoke_role removes the role from user."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        updated = self.rbac.revoke_role(
            user, UserRole.FACILITATOR, self.admin_id, "Demoted"
        )

        assert not updated.has_role(UserRole.FACILITATOR)

    def test_revoke_role_cannot_remove_base_role(self) -> None:
        """revoke_role cannot remove general_participant role."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        with pytest.raises(InvalidRoleError):
            self.rbac.revoke_role(user, UserRole.GENERAL_PARTICIPANT, self.admin_id)

    def test_revoke_role_raises_if_not_assigned(self) -> None:
        """revoke_role raises InvalidRoleError if role not assigned."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        with pytest.raises(InvalidRoleError):
            self.rbac.revoke_role(user, UserRole.FACILITATOR, self.admin_id)


# ============================================================================
# User Suspension Tests
# ============================================================================


@pytest.mark.unit
class TestUserSuspension:
    """Test user suspension and reinstatement."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.rbac = RBACService()
        self.admin_id = ObjectId()

    def test_suspend_user_sets_suspended_flag(self) -> None:
        """suspend_user sets is_suspended to True."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        suspended = self.rbac.suspend_user(
            user, self.admin_id, "Policy violation"
        )

        assert suspended.is_suspended

    def test_suspend_user_creates_suspension_record(self) -> None:
        """suspend_user creates suspension history entry."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        suspended = self.rbac.suspend_user(
            user, self.admin_id, "Policy violation"
        )

        assert len(suspended.suspension_history) == 1
        assert suspended.suspension_history[0].suspended_by == self.admin_id
        assert suspended.suspension_history[0].suspension_reason == "Policy violation"

    def test_suspend_user_raises_if_already_suspended(self) -> None:
        """suspend_user raises InvalidRoleError if already suspended."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            is_suspended=True,
        )

        with pytest.raises(InvalidRoleError):
            self.rbac.suspend_user(user, self.admin_id, "Policy violation")

    def test_reinstate_user_clears_suspended_flag(self) -> None:
        """reinstate_user sets is_suspended to False."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            is_suspended=True,
        )
        # Add a suspension record
        from integritykit.models.user import SuspensionRecord
        user.suspension_history.append(
            SuspensionRecord(
                suspended_at=user.created_at,
                suspended_by=self.admin_id,
                suspension_reason="Test suspension reason",
            )
        )

        reinstated = self.rbac.reinstate_user(
            user, self.admin_id, "Cleared of violations"
        )

        assert not reinstated.is_suspended

    def test_reinstate_user_raises_if_not_suspended(self) -> None:
        """reinstate_user raises InvalidRoleError if not suspended."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            is_suspended=False,
        )

        with pytest.raises(InvalidRoleError):
            self.rbac.reinstate_user(user, self.admin_id)


# ============================================================================
# Activity Tracking Tests
# ============================================================================


@pytest.mark.unit
class TestActivityTracking:
    """Test activity statistics tracking."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.rbac = RBACService()

    def test_record_action_increments_total(self) -> None:
        """record_action increments total_actions."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        updated = self.rbac.record_action(user)

        assert updated.activity_stats.total_actions == 1

    def test_record_publish_increments_publish_count(self) -> None:
        """record_publish increments publish_count."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        updated = self.rbac.record_publish(user)

        assert updated.activity_stats.publish_count == 1
        assert updated.activity_stats.total_actions == 1

    def test_record_high_stakes_override_increments_count(self) -> None:
        """record_high_stakes_override increments override count."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        updated = self.rbac.record_high_stakes_override(user)

        assert updated.activity_stats.high_stakes_overrides_count == 1
        assert updated.activity_stats.total_actions == 1


# ============================================================================
# Convenience Method Tests
# ============================================================================


@pytest.mark.unit
class TestConvenienceMethods:
    """Test RBAC convenience methods."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.rbac = RBACService()

    def test_can_access_backlog(self) -> None:
        """can_access_backlog returns correct values."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        regular = User(
            slack_user_id="U456",
            slack_team_id="T123",
        )

        assert self.rbac.can_access_backlog(facilitator)
        assert not self.rbac.can_access_backlog(regular)

    def test_can_promote_cluster(self) -> None:
        """can_promote_cluster returns correct values."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        verifier = User(
            slack_user_id="U456",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        assert self.rbac.can_promote_cluster(facilitator)
        assert not self.rbac.can_promote_cluster(verifier)

    def test_can_publish_cop(self) -> None:
        """can_publish_cop returns correct values."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        verifier = User(
            slack_user_id="U456",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        assert self.rbac.can_publish_cop(facilitator)
        assert not self.rbac.can_publish_cop(verifier)

    def test_can_manage_roles(self) -> None:
        """can_manage_roles returns correct values."""
        admin = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )
        facilitator = User(
            slack_user_id="U456",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        assert self.rbac.can_manage_roles(admin)
        assert not self.rbac.can_manage_roles(facilitator)

    def test_can_search(self) -> None:
        """can_search returns correct values."""
        facilitator = User(
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )
        regular = User(
            slack_user_id="U456",
            slack_team_id="T123",
        )

        assert self.rbac.can_search(facilitator)
        assert not self.rbac.can_search(regular)


# ============================================================================
# Factory-Based Tests (Backwards Compatibility)
# ============================================================================


@pytest.mark.unit
class TestRoleAssignmentWithFactories:
    """Test role assignment and validation using factories."""

    def test_general_participant_has_base_role(self) -> None:
        """All users should have general_participant role."""
        user = create_user(roles=["general_participant"])
        assert "general_participant" in user["roles"]

    def test_facilitator_has_multiple_roles(self) -> None:
        """Facilitator should have participant, facilitator, and verifier roles."""
        facilitator = create_facilitator()
        assert "general_participant" in facilitator["roles"]
        assert "facilitator" in facilitator["roles"]
        assert "verifier" in facilitator["roles"]

    def test_admin_has_all_roles(self) -> None:
        """Admin should have all roles including workspace_admin."""
        admin = create_admin()
        assert "general_participant" in admin["roles"]
        assert "facilitator" in admin["roles"]
        assert "verifier" in admin["roles"]
        assert "workspace_admin" in admin["roles"]


@pytest.mark.unit
class TestPermissionChecksWithFactories:
    """Test permission checking logic using factories."""

    def test_general_participant_can_view_signals(self) -> None:
        """General participants can read signals."""
        user = create_user(roles=["general_participant"])
        can_view_signals = "general_participant" in user["roles"]
        assert can_view_signals is True

    def test_general_participant_cannot_publish_cop(self) -> None:
        """General participants cannot publish COP updates."""
        user = create_user(roles=["general_participant"])
        can_publish_cop = "facilitator" in user["roles"]
        assert can_publish_cop is False

    def test_facilitator_can_publish_cop(self) -> None:
        """Facilitators can publish COP updates."""
        facilitator = create_facilitator()
        can_publish_cop = "facilitator" in facilitator["roles"]
        assert can_publish_cop is True

    def test_admin_can_change_user_roles(self) -> None:
        """Admins can change user roles."""
        admin = create_admin()
        can_manage_roles = "workspace_admin" in admin["roles"]
        assert can_manage_roles is True


@pytest.mark.unit
class TestUserSuspensionWithFactories:
    """Test user suspension logic using factories."""

    def test_active_user_is_not_suspended(self) -> None:
        """Active user should have is_suspended=False."""
        user = create_user(is_suspended=False)
        assert user["is_suspended"] is False

    def test_suspended_user_cannot_act(self) -> None:
        """Suspended user should have is_suspended=True."""
        user = create_user(is_suspended=True)
        is_allowed = not user["is_suspended"]
        assert is_allowed is False


@pytest.mark.unit
class TestActivityStatsWithFactories:
    """Test user activity statistics tracking using factories."""

    def test_new_user_has_zero_actions(self) -> None:
        """Newly created user should have zero total_actions."""
        user = create_user()
        assert user["activity_stats"]["total_actions"] == 0
        assert user["activity_stats"]["high_stakes_overrides_count"] == 0
        assert user["activity_stats"]["publish_count"] == 0
