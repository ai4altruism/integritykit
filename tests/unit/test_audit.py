"""
Unit tests for audit logging functionality.

Tests:
- FR-AUD-001: Immutable audit log
- FR-ROLE-003: Role-change audit logging
- NFR-ABUSE-001: Abuse detection signals
"""

import pytest
from bson import ObjectId

from integritykit.models.audit import (
    AuditActionType,
    AuditChanges,
    AuditLogCreate,
    AuditLogEntry,
    AuditLogResponse,
    AuditTargetType,
)
from integritykit.models.user import User, UserRole
from integritykit.services.audit import AuditService


# ============================================================================
# Audit Model Tests
# ============================================================================


@pytest.mark.unit
class TestAuditLogEntry:
    """Test AuditLogEntry model."""

    def test_create_audit_entry(self) -> None:
        """Create a basic audit log entry."""
        entry = AuditLogEntry(
            actor_id=ObjectId(),
            action_type=AuditActionType.USER_ROLE_CHANGE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=ObjectId(),
        )

        assert entry.action_type == AuditActionType.USER_ROLE_CHANGE
        assert entry.target_entity_type == AuditTargetType.USER
        assert entry.timestamp is not None
        assert entry.created_at is not None

    def test_audit_entry_with_changes(self) -> None:
        """Create audit entry with before/after changes."""
        changes = AuditChanges(
            before={"roles": ["general_participant"]},
            after={"roles": ["general_participant", "facilitator"]},
        )

        entry = AuditLogEntry(
            actor_id=ObjectId(),
            action_type=AuditActionType.USER_ROLE_CHANGE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=ObjectId(),
            changes=changes,
        )

        assert entry.changes.before == {"roles": ["general_participant"]}
        assert entry.changes.after == {"roles": ["general_participant", "facilitator"]}

    def test_audit_entry_with_justification(self) -> None:
        """Create audit entry with justification."""
        entry = AuditLogEntry(
            actor_id=ObjectId(),
            action_type=AuditActionType.USER_SUSPEND,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=ObjectId(),
            justification="Policy violation - repeated abuse",
        )

        assert entry.justification == "Policy violation - repeated abuse"

    def test_audit_entry_flagged(self) -> None:
        """Create flagged audit entry for abuse detection."""
        entry = AuditLogEntry(
            actor_id=ObjectId(),
            action_type=AuditActionType.COP_UPDATE_OVERRIDE,
            target_entity_type=AuditTargetType.COP_UPDATE,
            target_entity_id=ObjectId(),
            is_flagged=True,
            flag_reason="Multiple overrides in short period",
        )

        assert entry.is_flagged is True
        assert entry.flag_reason == "Multiple overrides in short period"


@pytest.mark.unit
class TestAuditLogCreate:
    """Test AuditLogCreate schema."""

    def test_create_role_change_entry(self) -> None:
        """Create role change audit entry data."""
        data = AuditLogCreate(
            actor_id=ObjectId(),
            actor_role="workspace_admin",
            action_type=AuditActionType.USER_ROLE_CHANGE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=ObjectId(),
            changes=AuditChanges(
                before={"roles": ["general_participant"]},
                after={"roles": ["general_participant", "facilitator"]},
            ),
            justification="Promoted for crisis exercise",
        )

        assert data.action_type == AuditActionType.USER_ROLE_CHANGE
        assert data.actor_role == "workspace_admin"

    def test_create_access_denied_entry(self) -> None:
        """Create access denied audit entry data."""
        data = AuditLogCreate(
            actor_id=ObjectId(),
            actor_role="general_participant",
            action_type=AuditActionType.ACCESS_DENIED,
            target_entity_type=AuditTargetType.COP_CANDIDATE,
            target_entity_id=ObjectId(),
            system_context={
                "required_permission": "VIEW_BACKLOG",
                "actor_roles": ["general_participant"],
            },
        )

        assert data.action_type == AuditActionType.ACCESS_DENIED
        assert data.system_context["required_permission"] == "VIEW_BACKLOG"


@pytest.mark.unit
class TestAuditLogResponse:
    """Test AuditLogResponse."""

    def test_from_entry(self) -> None:
        """Convert AuditLogEntry to response."""
        entry = AuditLogEntry(
            id=ObjectId(),
            actor_id=ObjectId(),
            actor_role="workspace_admin",
            action_type=AuditActionType.USER_ROLE_CHANGE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=ObjectId(),
            justification="Test promotion",
        )

        response = AuditLogResponse.from_entry(entry)

        assert response.action_type == "user.role_change"
        assert response.actor_role == "workspace_admin"
        assert response.justification == "Test promotion"


# ============================================================================
# Audit Action Type Tests
# ============================================================================


@pytest.mark.unit
class TestAuditActionTypes:
    """Test audit action type enumeration."""

    def test_user_action_types(self) -> None:
        """Verify user-related action types."""
        assert AuditActionType.USER_ROLE_CHANGE.value == "user.role_change"
        assert AuditActionType.USER_SUSPEND.value == "user.suspend"
        assert AuditActionType.USER_REINSTATE.value == "user.reinstate"

    def test_cop_action_types(self) -> None:
        """Verify COP-related action types."""
        assert AuditActionType.COP_CANDIDATE_PROMOTE.value == "cop_candidate.promote"
        assert AuditActionType.COP_UPDATE_PUBLISH.value == "cop_update.publish"
        assert AuditActionType.COP_UPDATE_OVERRIDE.value == "cop_update.override"

    def test_access_control_action_types(self) -> None:
        """Verify access control action types."""
        assert AuditActionType.ACCESS_DENIED.value == "access.denied"


# ============================================================================
# Audit Service Tests
# ============================================================================


@pytest.mark.unit
class TestAuditService:
    """Test AuditService high-level methods."""

    def test_get_highest_role_admin(self) -> None:
        """Get highest role for admin user."""
        admin = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        service = AuditService(repository=None)
        role = service._get_highest_role(admin)

        assert role == "workspace_admin"

    def test_get_highest_role_facilitator(self) -> None:
        """Get highest role for facilitator user."""
        facilitator = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR, UserRole.VERIFIER],
        )

        service = AuditService(repository=None)
        role = service._get_highest_role(facilitator)

        assert role == "facilitator"

    def test_get_highest_role_verifier(self) -> None:
        """Get highest role for verifier user."""
        verifier = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        service = AuditService(repository=None)
        role = service._get_highest_role(verifier)

        assert role == "verifier"

    def test_get_highest_role_participant(self) -> None:
        """Get highest role for general participant."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
        )

        service = AuditService(repository=None)
        role = service._get_highest_role(user)

        assert role == "general_participant"


# ============================================================================
# Audit Target Type Tests
# ============================================================================


@pytest.mark.unit
class TestAuditTargetTypes:
    """Test audit target type enumeration."""

    def test_entity_types(self) -> None:
        """Verify all entity types are defined."""
        assert AuditTargetType.SIGNAL.value == "signal"
        assert AuditTargetType.CLUSTER.value == "cluster"
        assert AuditTargetType.COP_CANDIDATE.value == "cop_candidate"
        assert AuditTargetType.COP_UPDATE.value == "cop_update"
        assert AuditTargetType.USER.value == "user"


# ============================================================================
# Audit Changes Tests
# ============================================================================


@pytest.mark.unit
class TestAuditChanges:
    """Test AuditChanges model."""

    def test_empty_changes(self) -> None:
        """Create empty changes (for read-only actions)."""
        changes = AuditChanges()

        assert changes.before is None
        assert changes.after is None

    def test_create_changes(self) -> None:
        """Create changes for entity creation."""
        changes = AuditChanges(
            before=None,
            after={"slack_user_id": "U123", "roles": ["general_participant"]},
        )

        assert changes.before is None
        assert changes.after is not None
        assert changes.after["slack_user_id"] == "U123"

    def test_update_changes(self) -> None:
        """Create changes for entity update."""
        changes = AuditChanges(
            before={"is_suspended": False},
            after={"is_suspended": True},
        )

        assert changes.before["is_suspended"] is False
        assert changes.after["is_suspended"] is True

    def test_role_change_tracking(self) -> None:
        """Track role changes for FR-ROLE-003."""
        changes = AuditChanges(
            before={"roles": ["general_participant"]},
            after={"roles": ["general_participant", "facilitator", "verifier"]},
        )

        old_roles = set(changes.before["roles"])
        new_roles = set(changes.after["roles"])
        added_roles = new_roles - old_roles
        removed_roles = old_roles - new_roles

        assert added_roles == {"facilitator", "verifier"}
        assert removed_roles == set()
