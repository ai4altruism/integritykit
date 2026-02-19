"""Audit log model for immutable action history.

Implements:
- FR-AUD-001: Immutable audit log of system actions
- FR-ROLE-003: Role-change audit logging
- NFR-ABUSE-001: Abuse detection signals
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class AuditActionType(str, Enum):
    """Action types for audit log entries."""

    # Signal actions
    SIGNAL_INGEST = "signal.ingest"

    # Cluster actions
    CLUSTER_CREATE = "cluster.create"
    CLUSTER_UPDATE = "cluster.update"

    # COP Candidate actions
    COP_CANDIDATE_PROMOTE = "cop_candidate.promote"
    COP_CANDIDATE_UPDATE_STATE = "cop_candidate.update_state"
    COP_CANDIDATE_UPDATE_RISK_TIER = "cop_candidate.update_risk_tier"
    COP_CANDIDATE_VERIFY = "cop_candidate.verify"
    COP_CANDIDATE_MERGE = "cop_candidate.merge"

    # COP Update actions
    COP_UPDATE_PUBLISH = "cop_update.publish"
    COP_UPDATE_OVERRIDE = "cop_update.override"

    # Two-person rule actions (FR-COP-GATE-002)
    TWO_PERSON_APPROVAL_REQUESTED = "two_person.approval_requested"
    TWO_PERSON_APPROVAL_GRANTED = "two_person.approval_granted"
    TWO_PERSON_APPROVAL_DENIED = "two_person.approval_denied"
    TWO_PERSON_APPROVAL_EXPIRED = "two_person.approval_expired"

    # User actions (FR-ROLE-003)
    USER_ROLE_CHANGE = "user.role_change"
    USER_SUSPEND = "user.suspend"
    USER_REINSTATE = "user.reinstate"

    # Access control (FR-ROLE-002)
    ACCESS_DENIED = "access.denied"

    # Redaction actions (NFR-PRIVACY-002)
    REDACTION_APPLIED = "redaction.applied"
    REDACTION_OVERRIDE = "redaction.override"


class AuditTargetType(str, Enum):
    """Target entity types for audit log entries."""

    SIGNAL = "signal"
    CLUSTER = "cluster"
    COP_CANDIDATE = "cop_candidate"
    COP_UPDATE = "cop_update"
    USER = "user"


class AuditChanges(BaseModel):
    """Change tracking for audit entries."""

    before: Optional[dict[str, Any]] = Field(
        default=None,
        description="State before action (for updates)",
    )
    after: Optional[dict[str, Any]] = Field(
        default=None,
        description="State after action (for updates/creates)",
    )


class AuditLogCreate(BaseModel):
    """Schema for creating a new audit log entry."""

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)

    actor_id: PyObjectId = Field(
        ...,
        description="User who performed action",
    )
    actor_role: Optional[str] = Field(
        default=None,
        description="Role at time of action",
    )
    actor_ip: Optional[str] = Field(
        default=None,
        description="IP address for security audit",
    )
    action_type: AuditActionType = Field(
        ...,
        description="Type of action performed",
    )
    target_entity_type: AuditTargetType = Field(
        ...,
        description="Type of entity affected",
    )
    target_entity_id: PyObjectId = Field(
        ...,
        description="ID of affected entity",
    )
    changes: AuditChanges = Field(
        default_factory=AuditChanges,
        description="Before/after state changes",
    )
    justification: Optional[str] = Field(
        default=None,
        description="User-provided reason (required for overrides)",
    )
    system_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="System state snapshot",
    )
    is_flagged: bool = Field(
        default=False,
        description="True if flagged by abuse detection",
    )
    flag_reason: Optional[str] = Field(
        default=None,
        description="Reason for flagging",
    )


class AuditLogEntry(BaseModel):
    """Audit log entry model (FR-AUD-001).

    Audit log entries are immutable after creation.
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
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When action occurred",
    )
    actor_id: PyObjectId = Field(
        ...,
        description="User who performed action",
    )
    actor_role: Optional[str] = Field(
        default=None,
        description="Role at time of action",
    )
    actor_ip: Optional[str] = Field(
        default=None,
        description="IP address for security audit",
    )
    action_type: AuditActionType = Field(
        ...,
        description="Type of action performed",
    )
    target_entity_type: AuditTargetType = Field(
        ...,
        description="Type of entity affected",
    )
    target_entity_id: PyObjectId = Field(
        ...,
        description="ID of affected entity",
    )
    changes: AuditChanges = Field(
        default_factory=AuditChanges,
        description="Before/after state changes",
    )
    justification: Optional[str] = Field(
        default=None,
        description="User-provided reason",
    )
    system_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="System state snapshot",
    )
    is_flagged: bool = Field(
        default=False,
        description="True if flagged by abuse detection",
    )
    flag_reason: Optional[str] = Field(
        default=None,
        description="Reason for flagging",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Immutable creation timestamp",
    )


class AuditLogResponse(BaseModel):
    """API response for audit log entry."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    id: str
    timestamp: datetime
    actor_id: str
    actor_role: Optional[str] = None
    action_type: str
    target_entity_type: str
    target_entity_id: str
    changes: AuditChanges
    justification: Optional[str] = None
    is_flagged: bool = False
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AuditLogEntry) -> "AuditLogResponse":
        """Create response from AuditLogEntry model."""
        return cls(
            id=str(entry.id),
            timestamp=entry.timestamp,
            actor_id=str(entry.actor_id),
            actor_role=entry.actor_role,
            action_type=entry.action_type,
            target_entity_type=entry.target_entity_type,
            target_entity_id=str(entry.target_entity_id),
            changes=entry.changes,
            justification=entry.justification,
            is_flagged=entry.is_flagged,
            created_at=entry.created_at,
        )
