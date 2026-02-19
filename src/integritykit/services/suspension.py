"""User suspension service with audit logging.

Implements:
- S7-4: Facilitator permission suspension by admin
- NFR-ABUSE-002: Permission suspension
"""

from typing import Optional

import structlog
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.user import Permission, User, UserRole
from integritykit.services.audit import AuditService, get_audit_service
from integritykit.services.rbac import (
    AccessDeniedError,
    InvalidRoleError,
    RBACService,
    get_rbac_service,
)

logger = structlog.get_logger(__name__)


class SuspensionError(Exception):
    """Base exception for suspension operations."""

    pass


class SelfSuspensionError(SuspensionError):
    """Raised when attempting to suspend oneself."""

    def __init__(self):
        super().__init__("Cannot suspend yourself")


class SuspendAdminError(SuspensionError):
    """Raised when attempting to suspend another admin."""

    def __init__(self):
        super().__init__("Cannot suspend another admin")


class SuspensionService:
    """Service for suspending and reinstating user permissions.

    Implements S7-4: Facilitator permission suspension by admin
    with full audit logging.
    """

    def __init__(
        self,
        rbac_service: Optional[RBACService] = None,
        audit_service: Optional[AuditService] = None,
    ):
        """Initialize SuspensionService.

        Args:
            rbac_service: RBAC service for permission operations
            audit_service: Audit service for logging
        """
        self.rbac_service = rbac_service or get_rbac_service()
        self.audit_service = audit_service or get_audit_service()

    def _check_suspend_permission(self, admin: User) -> None:
        """Verify admin has suspension permission.

        Args:
            admin: User attempting to suspend

        Raises:
            AccessDeniedError: If admin lacks permission
        """
        self.rbac_service.require_permission(admin, Permission.SUSPEND_USER)

    def _validate_suspension_target(self, admin: User, target: User) -> None:
        """Validate the suspension target.

        Args:
            admin: Admin performing suspension
            target: User being suspended

        Raises:
            SelfSuspensionError: If trying to suspend self
            SuspendAdminError: If trying to suspend another admin
        """
        # Cannot suspend yourself
        if admin.id == target.id:
            raise SelfSuspensionError()

        # Cannot suspend another admin (protect admin accounts)
        if target.has_role(UserRole.WORKSPACE_ADMIN):
            raise SuspendAdminError()

    async def suspend_user(
        self,
        admin: User,
        target: User,
        reason: str,
    ) -> User:
        """Suspend a user's permissions.

        A suspended user loses all permissions except viewing published COPs.
        Only workspace admins can suspend users.

        Args:
            admin: Admin user performing the suspension
            target: User to suspend
            reason: Justification for suspension (min 10 chars)

        Returns:
            Updated suspended user

        Raises:
            AccessDeniedError: If admin lacks permission
            SelfSuspensionError: If trying to suspend self
            SuspendAdminError: If trying to suspend another admin
            InvalidRoleError: If user is already suspended
        """
        # Verify permissions
        self._check_suspend_permission(admin)

        # Validate target
        self._validate_suspension_target(admin, target)

        # Capture state before
        was_suspended = target.is_suspended
        previous_roles = [
            r.value if hasattr(r, 'value') else r
            for r in target.roles
        ]

        # Perform suspension
        suspended_user = self.rbac_service.suspend_user(
            user=target,
            suspended_by=admin.id,
            reason=reason,
        )

        # Audit log the suspension
        await self.audit_service.log_action(
            actor=admin,
            action_type=AuditActionType.USER_SUSPEND,
            target_type=AuditTargetType.USER,
            target_id=target.id,
            changes_before={
                "is_suspended": was_suspended,
                "roles": previous_roles,
            },
            changes_after={
                "is_suspended": True,
                "roles": previous_roles,  # Roles preserved but inactive
                "suspension_reason": reason,
            },
            justification=reason,
            system_context={
                "action": "user_suspension",
                "target_slack_id": target.slack_user_id,
                "target_display_name": target.slack_display_name,
            },
        )

        logger.warning(
            "User suspended",
            admin_id=str(admin.id),
            target_id=str(target.id),
            target_slack_id=target.slack_user_id,
            reason=reason,
        )

        return suspended_user

    async def reinstate_user(
        self,
        admin: User,
        target: User,
        reason: Optional[str] = None,
    ) -> User:
        """Reinstate a suspended user's permissions.

        Restores all previously assigned roles.

        Args:
            admin: Admin user performing the reinstatement
            target: User to reinstate
            reason: Optional reason for reinstatement

        Returns:
            Updated reinstated user

        Raises:
            AccessDeniedError: If admin lacks permission
            InvalidRoleError: If user is not suspended
        """
        # Verify permissions
        self._check_suspend_permission(admin)

        # Capture state before
        was_suspended = target.is_suspended
        roles = [
            r.value if hasattr(r, 'value') else r
            for r in target.roles
        ]

        # Get suspension record before reinstatement
        suspension_reason = None
        if target.suspension_history:
            for record in reversed(target.suspension_history):
                if record.reinstated_at is None:
                    suspension_reason = record.suspension_reason
                    break

        # Perform reinstatement
        reinstated_user = self.rbac_service.reinstate_user(
            user=target,
            reinstated_by=admin.id,
            reason=reason,
        )

        # Audit log the reinstatement
        await self.audit_service.log_action(
            actor=admin,
            action_type=AuditActionType.USER_REINSTATE,
            target_type=AuditTargetType.USER,
            target_id=target.id,
            changes_before={
                "is_suspended": was_suspended,
                "suspension_reason": suspension_reason,
            },
            changes_after={
                "is_suspended": False,
                "roles": roles,
            },
            justification=reason,
            system_context={
                "action": "user_reinstatement",
                "target_slack_id": target.slack_user_id,
                "target_display_name": target.slack_display_name,
            },
        )

        logger.info(
            "User reinstated",
            admin_id=str(admin.id),
            target_id=str(target.id),
            target_slack_id=target.slack_user_id,
            reason=reason,
        )

        return reinstated_user

    async def get_suspension_status(self, user: User) -> dict:
        """Get suspension status for a user.

        Args:
            user: User to check

        Returns:
            Dict with suspension status and details
        """
        status = {
            "is_suspended": user.is_suspended,
            "suspension_count": len(user.suspension_history),
            "current_suspension": None,
            "suspension_history": [],
        }

        if user.suspension_history:
            # Get current suspension (if any)
            for record in reversed(user.suspension_history):
                if record.reinstated_at is None:
                    status["current_suspension"] = {
                        "suspended_at": record.suspended_at.isoformat(),
                        "suspended_by": str(record.suspended_by),
                        "reason": record.suspension_reason,
                    }
                    break

            # Build history
            for record in user.suspension_history:
                entry = {
                    "suspended_at": record.suspended_at.isoformat(),
                    "suspended_by": str(record.suspended_by),
                    "reason": record.suspension_reason,
                    "is_active": record.reinstated_at is None,
                }
                if record.reinstated_at:
                    entry["reinstated_at"] = record.reinstated_at.isoformat()
                    entry["reinstated_by"] = str(record.reinstated_by)
                    entry["reinstatement_reason"] = record.reinstatement_reason
                status["suspension_history"].append(entry)

        return status

    def can_be_suspended(self, admin: User, target: User) -> tuple[bool, str]:
        """Check if a user can be suspended by an admin.

        Args:
            admin: Admin attempting suspension
            target: User to potentially suspend

        Returns:
            Tuple of (can_suspend, reason_if_not)
        """
        # Check admin permission
        if not admin.has_permission(Permission.SUSPEND_USER):
            return False, "Admin lacks SUSPEND_USER permission"

        # Check self-suspension
        if admin.id == target.id:
            return False, "Cannot suspend yourself"

        # Check admin protection
        if target.has_role(UserRole.WORKSPACE_ADMIN):
            return False, "Cannot suspend another admin"

        # Check already suspended
        if target.is_suspended:
            return False, "User is already suspended"

        return True, ""


# Singleton instance
_suspension_service: Optional[SuspensionService] = None


def get_suspension_service() -> SuspensionService:
    """Get the suspension service singleton.

    Returns:
        SuspensionService instance
    """
    global _suspension_service
    if _suspension_service is None:
        _suspension_service = SuspensionService()
    return _suspension_service
