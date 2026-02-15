"""User model for role-based access control (RBAC).

Implements FR-ROLE-001: Three configurable roles
- general_participant: Read-only access to published COPs
- facilitator: Full backlog and candidate management
- verifier: Verification actions on candidates
- workspace_admin: User and role management
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from integritykit.models.signal import PyObjectId


class UserRole(str, Enum):
    """User role enumeration (FR-ROLE-001)."""

    GENERAL_PARTICIPANT = "general_participant"
    FACILITATOR = "facilitator"
    VERIFIER = "verifier"
    WORKSPACE_ADMIN = "workspace_admin"


class Permission(str, Enum):
    """Permissions that can be checked for authorization."""

    # Signal permissions
    VIEW_SIGNALS = "view_signals"

    # Cluster/Backlog permissions
    VIEW_BACKLOG = "view_backlog"
    PROMOTE_CLUSTER = "promote_cluster"

    # COP Candidate permissions
    VIEW_CANDIDATES = "view_candidates"
    UPDATE_CANDIDATE = "update_candidate"
    VERIFY_CANDIDATE = "verify_candidate"
    MERGE_CANDIDATES = "merge_candidates"

    # COP Publishing permissions
    VIEW_COP_DRAFT = "view_cop_draft"
    EDIT_COP_DRAFT = "edit_cop_draft"
    PUBLISH_COP = "publish_cop"
    OVERRIDE_PUBLISH_GATE = "override_publish_gate"

    # Search permissions
    SEARCH = "search"

    # Metrics permissions
    VIEW_METRICS = "view_metrics"
    EXPORT_METRICS = "export_metrics"

    # Audit permissions
    VIEW_AUDIT_LOG = "view_audit_log"

    # User management permissions
    VIEW_USERS = "view_users"
    MANAGE_ROLES = "manage_roles"
    SUSPEND_USER = "suspend_user"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.GENERAL_PARTICIPANT: {
        Permission.VIEW_SIGNALS,
    },
    UserRole.VERIFIER: {
        Permission.VIEW_SIGNALS,
        Permission.VIEW_BACKLOG,
        Permission.VIEW_CANDIDATES,
        Permission.VERIFY_CANDIDATE,
        Permission.VIEW_COP_DRAFT,
        Permission.SEARCH,
        Permission.VIEW_METRICS,
    },
    UserRole.FACILITATOR: {
        Permission.VIEW_SIGNALS,
        Permission.VIEW_BACKLOG,
        Permission.PROMOTE_CLUSTER,
        Permission.VIEW_CANDIDATES,
        Permission.UPDATE_CANDIDATE,
        Permission.VERIFY_CANDIDATE,
        Permission.MERGE_CANDIDATES,
        Permission.VIEW_COP_DRAFT,
        Permission.EDIT_COP_DRAFT,
        Permission.PUBLISH_COP,
        Permission.OVERRIDE_PUBLISH_GATE,
        Permission.SEARCH,
        Permission.VIEW_METRICS,
        Permission.EXPORT_METRICS,
        Permission.VIEW_AUDIT_LOG,
    },
    UserRole.WORKSPACE_ADMIN: {
        Permission.VIEW_SIGNALS,
        Permission.VIEW_BACKLOG,
        Permission.PROMOTE_CLUSTER,
        Permission.VIEW_CANDIDATES,
        Permission.UPDATE_CANDIDATE,
        Permission.VERIFY_CANDIDATE,
        Permission.MERGE_CANDIDATES,
        Permission.VIEW_COP_DRAFT,
        Permission.EDIT_COP_DRAFT,
        Permission.PUBLISH_COP,
        Permission.OVERRIDE_PUBLISH_GATE,
        Permission.SEARCH,
        Permission.VIEW_METRICS,
        Permission.EXPORT_METRICS,
        Permission.VIEW_AUDIT_LOG,
        Permission.VIEW_USERS,
        Permission.MANAGE_ROLES,
        Permission.SUSPEND_USER,
    },
}


class RoleChange(BaseModel):
    """Record of a role change for audit trail (FR-ROLE-003)."""

    changed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the change occurred",
    )
    changed_by: PyObjectId = Field(
        ...,
        description="User ID who made the change",
    )
    old_roles: list[UserRole] = Field(
        default_factory=list,
        description="Roles before change",
    )
    new_roles: list[UserRole] = Field(
        ...,
        description="Roles after change",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Justification for the change",
    )


class SuspensionRecord(BaseModel):
    """Record of a user suspension (NFR-ABUSE-002)."""

    suspended_at: datetime = Field(
        ...,
        description="When suspension started",
    )
    suspended_by: PyObjectId = Field(
        ...,
        description="User ID who suspended",
    )
    suspension_reason: str = Field(
        ...,
        min_length=10,
        description="Reason for suspension",
    )
    reinstated_at: Optional[datetime] = Field(
        default=None,
        description="When reinstated (None if still suspended)",
    )
    reinstated_by: Optional[PyObjectId] = Field(
        default=None,
        description="User ID who reinstated",
    )
    reinstatement_reason: Optional[str] = Field(
        default=None,
        description="Reason for reinstatement",
    )


class UserPreferences(BaseModel):
    """User preferences and settings."""

    timezone: str = Field(
        default="UTC",
        description="IANA timezone for display",
    )
    notification_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="User-specific notification preferences",
    )


class ActivityStats(BaseModel):
    """Activity tracking for abuse detection (NFR-ABUSE-001)."""

    last_action_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last action",
    )
    total_actions: int = Field(
        default=0,
        ge=0,
        description="Total actions performed",
    )
    high_stakes_overrides_count: int = Field(
        default=0,
        ge=0,
        description="Number of high-stakes overrides",
    )
    publish_count: int = Field(
        default=0,
        ge=0,
        description="Number of COP publishes",
    )


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)

    slack_user_id: str = Field(
        ...,
        description="Unique Slack user ID",
    )
    slack_team_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    slack_email: Optional[str] = Field(
        default=None,
        description="User email from Slack profile",
    )
    slack_display_name: Optional[str] = Field(
        default=None,
        description="Display name from Slack",
    )
    slack_real_name: Optional[str] = Field(
        default=None,
        description="Real name from Slack",
    )
    roles: list[UserRole] = Field(
        default_factory=lambda: [UserRole.GENERAL_PARTICIPANT],
        description="Initial roles (defaults to general_participant)",
    )


class User(BaseModel):
    """User model with role-based access control.

    Implements:
    - FR-ROLE-001: Three configurable roles
    - FR-ROLE-002: Role-based access enforcement
    - FR-ROLE-003: Role-change audit logging
    - NFR-ABUSE-002: Permission suspension
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        use_enum_values=True,
    )

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    slack_user_id: str = Field(
        ...,
        description="Unique Slack user ID",
    )
    slack_team_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    slack_email: Optional[str] = Field(
        default=None,
        description="User email from Slack profile",
    )
    slack_display_name: Optional[str] = Field(
        default=None,
        description="Display name from Slack",
    )
    slack_real_name: Optional[str] = Field(
        default=None,
        description="Real name from Slack",
    )
    roles: list[UserRole] = Field(
        default_factory=lambda: [UserRole.GENERAL_PARTICIPANT],
        description="Assigned roles",
    )
    role_history: list[RoleChange] = Field(
        default_factory=list,
        description="Role change audit trail (FR-ROLE-003)",
    )
    is_suspended: bool = Field(
        default=False,
        description="Whether user is currently suspended",
    )
    suspension_history: list[SuspensionRecord] = Field(
        default_factory=list,
        description="Suspension records",
    )
    preferences: UserPreferences = Field(
        default_factory=UserPreferences,
        description="User preferences",
    )
    activity_stats: ActivityStats = Field(
        default_factory=ActivityStats,
        description="Activity tracking",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When user was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When user was last updated",
    )

    @field_validator("roles", mode="before")
    @classmethod
    def ensure_base_role(cls, v: list) -> list:
        """Ensure user always has general_participant role."""
        if not v:
            return [UserRole.GENERAL_PARTICIPANT]
        # Convert strings to enum if needed
        roles = []
        for role in v:
            if isinstance(role, str):
                roles.append(UserRole(role))
            else:
                roles.append(role)
        # Always include general_participant
        if UserRole.GENERAL_PARTICIPANT not in roles:
            roles.insert(0, UserRole.GENERAL_PARTICIPANT)
        return roles

    def has_role(self, role: UserRole) -> bool:
        """Check if user has a specific role.

        Args:
            role: Role to check

        Returns:
            True if user has the role
        """
        return role in self.roles or role.value in self.roles

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission (FR-ROLE-002).

        Permission is granted if ANY of the user's roles grant it.

        Args:
            permission: Permission to check

        Returns:
            True if user has the permission
        """
        if self.is_suspended:
            return False

        for role in self.roles:
            role_enum = UserRole(role) if isinstance(role, str) else role
            if permission in ROLE_PERMISSIONS.get(role_enum, set()):
                return True
        return False

    def get_permissions(self) -> set[Permission]:
        """Get all permissions for this user.

        Returns:
            Set of all permissions granted by user's roles
        """
        if self.is_suspended:
            return set()

        permissions = set()
        for role in self.roles:
            role_enum = UserRole(role) if isinstance(role, str) else role
            permissions.update(ROLE_PERMISSIONS.get(role_enum, set()))
        return permissions

    @property
    def is_facilitator(self) -> bool:
        """Check if user is a facilitator."""
        return self.has_role(UserRole.FACILITATOR)

    @property
    def is_verifier(self) -> bool:
        """Check if user is a verifier."""
        return self.has_role(UserRole.VERIFIER)

    @property
    def is_admin(self) -> bool:
        """Check if user is a workspace admin."""
        return self.has_role(UserRole.WORKSPACE_ADMIN)


class UserResponse(BaseModel):
    """API response for user data."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    id: str = Field(..., description="User ID")
    slack_user_id: str
    slack_team_id: str
    slack_email: Optional[str] = None
    slack_display_name: Optional[str] = None
    slack_real_name: Optional[str] = None
    roles: list[str]
    is_suspended: bool
    activity_stats: ActivityStats
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        """Create response from User model."""
        return cls(
            id=str(user.id),
            slack_user_id=user.slack_user_id,
            slack_team_id=user.slack_team_id,
            slack_email=user.slack_email,
            slack_display_name=user.slack_display_name,
            slack_real_name=user.slack_real_name,
            roles=[r.value if isinstance(r, UserRole) else r for r in user.roles],
            is_suspended=user.is_suspended,
            activity_stats=user.activity_stats,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
