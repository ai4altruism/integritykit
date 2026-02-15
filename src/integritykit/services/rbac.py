"""Role-Based Access Control (RBAC) service.

Implements:
- FR-ROLE-001: Three configurable roles (General Participant, Facilitator, Verifier)
- FR-ROLE-002: Role-based access enforcement
- FR-ROLE-003: Role-change audit logging
- NFR-ABUSE-002: Permission suspension by admin
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId

from integritykit.models.user import (
    ActivityStats,
    Permission,
    RoleChange,
    SuspensionRecord,
    User,
    UserCreate,
    UserRole,
)


class RBACError(Exception):
    """Base exception for RBAC errors."""

    pass


class AccessDeniedError(RBACError):
    """Raised when access is denied due to insufficient permissions."""

    def __init__(
        self,
        message: str = "Access denied",
        required_permission: Optional[Permission] = None,
        required_role: Optional[UserRole] = None,
    ):
        super().__init__(message)
        self.message = message
        self.required_permission = required_permission
        self.required_role = required_role


class UserSuspendedError(RBACError):
    """Raised when a suspended user attempts an action."""

    def __init__(self, message: str = "User account is suspended"):
        super().__init__(message)
        self.message = message


class InvalidRoleError(RBACError):
    """Raised when an invalid role operation is attempted."""

    pass


class RBACService:
    """Service for role-based access control operations.

    This service handles:
    - Permission checking
    - Role assignment and revocation
    - User suspension and reinstatement
    - Activity tracking
    """

    def check_permission(self, user: User, permission: Permission) -> bool:
        """Check if user has a specific permission.

        Args:
            user: User to check
            permission: Permission to verify

        Returns:
            True if user has the permission

        Raises:
            UserSuspendedError: If user is suspended
        """
        if user.is_suspended:
            raise UserSuspendedError()
        return user.has_permission(permission)

    def require_permission(self, user: User, permission: Permission) -> None:
        """Require user to have a specific permission.

        Args:
            user: User to check
            permission: Required permission

        Raises:
            AccessDeniedError: If user lacks the permission
            UserSuspendedError: If user is suspended
        """
        if user.is_suspended:
            raise UserSuspendedError()
        if not user.has_permission(permission):
            raise AccessDeniedError(
                message=f"Permission denied: {permission.value}",
                required_permission=permission,
            )

    def require_role(self, user: User, role: UserRole) -> None:
        """Require user to have a specific role.

        Args:
            user: User to check
            role: Required role

        Raises:
            AccessDeniedError: If user lacks the role
            UserSuspendedError: If user is suspended
        """
        if user.is_suspended:
            raise UserSuspendedError()
        if not user.has_role(role):
            raise AccessDeniedError(
                message=f"Role required: {role.value}",
                required_role=role,
            )

    def require_any_role(self, user: User, roles: list[UserRole]) -> None:
        """Require user to have at least one of the specified roles.

        Args:
            user: User to check
            roles: List of acceptable roles

        Raises:
            AccessDeniedError: If user lacks all roles
            UserSuspendedError: If user is suspended
        """
        if user.is_suspended:
            raise UserSuspendedError()
        if not any(user.has_role(role) for role in roles):
            role_names = ", ".join(r.value for r in roles)
            raise AccessDeniedError(
                message=f"One of these roles required: {role_names}",
            )

    def assign_role(
        self,
        user: User,
        role: UserRole,
        assigned_by: ObjectId,
        reason: Optional[str] = None,
    ) -> User:
        """Assign a role to a user.

        Creates a role change record for audit trail (FR-ROLE-003).

        Args:
            user: User to modify
            role: Role to assign
            assigned_by: User ID performing the assignment
            reason: Justification for the change

        Returns:
            Updated user with new role

        Raises:
            InvalidRoleError: If role is already assigned
        """
        # Check if role already exists
        if user.has_role(role):
            raise InvalidRoleError(f"User already has role: {role.value}")

        # Record old roles for audit
        old_roles = list(user.roles)

        # Add new role
        new_roles = list(user.roles)
        new_roles.append(role)

        # Create role change record
        role_change = RoleChange(
            changed_at=datetime.utcnow(),
            changed_by=assigned_by,
            old_roles=[UserRole(r) if isinstance(r, str) else r for r in old_roles],
            new_roles=[UserRole(r) if isinstance(r, str) else r for r in new_roles],
            reason=reason,
        )

        # Update user
        user.roles = new_roles
        user.role_history.append(role_change)
        user.updated_at = datetime.utcnow()

        return user

    def revoke_role(
        self,
        user: User,
        role: UserRole,
        revoked_by: ObjectId,
        reason: Optional[str] = None,
    ) -> User:
        """Revoke a role from a user.

        Creates a role change record for audit trail (FR-ROLE-003).

        Args:
            user: User to modify
            role: Role to revoke
            revoked_by: User ID performing the revocation
            reason: Justification for the change

        Returns:
            Updated user without the role

        Raises:
            InvalidRoleError: If role not assigned or is base role
        """
        # Cannot remove base role
        if role == UserRole.GENERAL_PARTICIPANT:
            raise InvalidRoleError("Cannot revoke base role: general_participant")

        # Check if role exists
        if not user.has_role(role):
            raise InvalidRoleError(f"User does not have role: {role.value}")

        # Record old roles for audit
        old_roles = list(user.roles)

        # Remove role
        new_roles = [r for r in user.roles if r != role and r != role.value]

        # Create role change record
        role_change = RoleChange(
            changed_at=datetime.utcnow(),
            changed_by=revoked_by,
            old_roles=[UserRole(r) if isinstance(r, str) else r for r in old_roles],
            new_roles=[UserRole(r) if isinstance(r, str) else r for r in new_roles],
            reason=reason,
        )

        # Update user
        user.roles = new_roles
        user.role_history.append(role_change)
        user.updated_at = datetime.utcnow()

        return user

    def suspend_user(
        self,
        user: User,
        suspended_by: ObjectId,
        reason: str,
    ) -> User:
        """Suspend a user's permissions (NFR-ABUSE-002).

        Args:
            user: User to suspend
            suspended_by: Admin user ID performing suspension
            reason: Reason for suspension

        Returns:
            Updated suspended user

        Raises:
            InvalidRoleError: If user is already suspended
        """
        if user.is_suspended:
            raise InvalidRoleError("User is already suspended")

        suspension = SuspensionRecord(
            suspended_at=datetime.utcnow(),
            suspended_by=suspended_by,
            suspension_reason=reason,
        )

        user.is_suspended = True
        user.suspension_history.append(suspension)
        user.updated_at = datetime.utcnow()

        return user

    def reinstate_user(
        self,
        user: User,
        reinstated_by: ObjectId,
        reason: Optional[str] = None,
    ) -> User:
        """Reinstate a suspended user.

        Args:
            user: User to reinstate
            reinstated_by: Admin user ID performing reinstatement
            reason: Reason for reinstatement

        Returns:
            Updated reinstated user

        Raises:
            InvalidRoleError: If user is not suspended
        """
        if not user.is_suspended:
            raise InvalidRoleError("User is not suspended")

        # Update the most recent suspension record
        for record in reversed(user.suspension_history):
            if record.reinstated_at is None:
                record.reinstated_at = datetime.utcnow()
                record.reinstated_by = reinstated_by
                record.reinstatement_reason = reason
                break

        user.is_suspended = False
        user.updated_at = datetime.utcnow()

        return user

    def record_action(self, user: User) -> User:
        """Record that a user performed an action.

        Used for activity tracking and abuse detection.

        Args:
            user: User who performed action

        Returns:
            Updated user with activity stats
        """
        now = datetime.utcnow()
        user.activity_stats.last_action_at = now
        user.activity_stats.total_actions += 1
        return user

    def record_publish(self, user: User) -> User:
        """Record that a user published a COP update.

        Args:
            user: User who published

        Returns:
            Updated user with publish count incremented
        """
        user = self.record_action(user)
        user.activity_stats.publish_count += 1
        return user

    def record_high_stakes_override(self, user: User) -> User:
        """Record that a user performed a high-stakes override.

        Args:
            user: User who overrode

        Returns:
            Updated user with override count incremented
        """
        user = self.record_action(user)
        user.activity_stats.high_stakes_overrides_count += 1
        return user

    def can_access_backlog(self, user: User) -> bool:
        """Check if user can access the facilitator backlog.

        Args:
            user: User to check

        Returns:
            True if user can view backlog
        """
        return self.check_permission(user, Permission.VIEW_BACKLOG)

    def can_promote_cluster(self, user: User) -> bool:
        """Check if user can promote clusters to candidates.

        Args:
            user: User to check

        Returns:
            True if user can promote
        """
        return self.check_permission(user, Permission.PROMOTE_CLUSTER)

    def can_publish_cop(self, user: User) -> bool:
        """Check if user can publish COP updates.

        Args:
            user: User to check

        Returns:
            True if user can publish
        """
        return self.check_permission(user, Permission.PUBLISH_COP)

    def can_manage_roles(self, user: User) -> bool:
        """Check if user can manage other users' roles.

        Args:
            user: User to check

        Returns:
            True if user can manage roles
        """
        return self.check_permission(user, Permission.MANAGE_ROLES)

    def can_search(self, user: User) -> bool:
        """Check if user can use facilitator search.

        Args:
            user: User to check

        Returns:
            True if user can search
        """
        return self.check_permission(user, Permission.SEARCH)


# Global singleton instance
_rbac_service: Optional[RBACService] = None


def get_rbac_service() -> RBACService:
    """Get the global RBAC service instance.

    Returns:
        RBACService singleton
    """
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService()
    return _rbac_service
