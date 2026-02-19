"""COP Update model for published Common Operating Picture updates.

Implements:
- FR-COP-PUB-001: Human-approved publishing
- NFR-TRANSPARENCY-001: Full provenance tracking
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class COPUpdateStatus(str, Enum):
    """Status of a COP update."""

    DRAFT = "draft"  # Being edited, not yet approved
    PENDING_APPROVAL = "pending_approval"  # Awaiting facilitator approval
    APPROVED = "approved"  # Approved but not yet posted
    PUBLISHED = "published"  # Posted to Slack
    SUPERSEDED = "superseded"  # Replaced by newer update


class VersionChangeType(str, Enum):
    """Types of changes between versions."""

    ADDED = "added"  # New line item added
    REMOVED = "removed"  # Line item removed
    MODIFIED = "modified"  # Line item text changed
    STATUS_CHANGED = "status_changed"  # Item moved between sections
    PROMOTED = "promoted"  # Item promoted from in_review to verified
    DEMOTED = "demoted"  # Item demoted from verified to in_review


class VersionChange(BaseModel):
    """Record of a single change between versions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    change_type: VersionChangeType = Field(
        ...,
        description="Type of change",
    )
    candidate_id: Optional[PyObjectId] = Field(
        default=None,
        description="Affected candidate ID",
    )
    field: Optional[str] = Field(
        default=None,
        description="Field that changed (text, section, etc.)",
    )
    old_value: Optional[str] = Field(
        default=None,
        description="Previous value",
    )
    new_value: Optional[str] = Field(
        default=None,
        description="New value",
    )
    description: str = Field(
        default="",
        description="Human-readable change description",
    )


class EvidenceSnapshot(BaseModel):
    """Frozen evidence state at time of publication (S7-2).

    Preserves evidence exactly as it existed when COP was published,
    ensuring accountability and preventing post-hoc modifications.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    candidate_id: PyObjectId = Field(
        ...,
        description="COP candidate this evidence belongs to",
    )
    slack_permalinks: list[dict] = Field(
        default_factory=list,
        description="Frozen Slack permalink references",
    )
    external_sources: list[dict] = Field(
        default_factory=list,
        description="Frozen external source references",
    )
    verifications: list[dict] = Field(
        default_factory=list,
        description="Frozen verification records",
    )
    risk_tier: str = Field(
        default="routine",
        description="Risk tier at time of publication",
    )
    readiness_state: str = Field(
        default="in_review",
        description="Readiness state at time of publication",
    )
    fields_snapshot: dict = Field(
        default_factory=dict,
        description="COP fields (what/where/when/who/so_what) at publication",
    )
    captured_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this snapshot was captured",
    )


class PublishedLineItem(BaseModel):
    """A line item as published in the COP update."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    candidate_id: PyObjectId = Field(
        ...,
        description="Source COP candidate ID",
    )
    section: str = Field(
        ...,
        description="Section (verified/in_review/disproven/open_questions)",
    )
    status_label: str = Field(
        ...,
        description="Display status (VERIFIED, IN REVIEW, etc.)",
    )
    text: str = Field(
        ...,
        description="Published line item text",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Citation URLs",
    )
    was_edited: bool = Field(
        default=False,
        description="True if facilitator edited from auto-generated text",
    )
    original_text: Optional[str] = Field(
        default=None,
        description="Auto-generated text before edit (if edited)",
    )


class COPUpdateCreate(BaseModel):
    """Schema for creating a COP update."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    title: str = Field(
        ...,
        description="Update title",
    )
    line_items: list[PublishedLineItem] = Field(
        default_factory=list,
        description="Line items included in update",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Open questions section",
    )
    created_by: PyObjectId = Field(
        ...,
        description="Facilitator who created the draft",
    )


class COPUpdate(BaseModel):
    """COP Update model (FR-COP-PUB-001).

    Represents a published COP update with full provenance.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    update_number: int = Field(
        default=1,
        description="Sequential update number for workspace",
    )
    title: str = Field(
        ...,
        description="Update title",
    )
    status: COPUpdateStatus = Field(
        default=COPUpdateStatus.DRAFT,
        description="Current status",
    )
    line_items: list[PublishedLineItem] = Field(
        default_factory=list,
        description="Line items in update",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Open questions section",
    )

    # Version tracking (S7-2)
    version: str = Field(
        default="1.0",
        description="Semantic version (major.minor)",
    )
    previous_version_id: Optional[PyObjectId] = Field(
        default=None,
        description="ID of the previous version (for version chain)",
    )
    version_changes: list[VersionChange] = Field(
        default_factory=list,
        description="Changes from previous version",
    )
    change_summary: Optional[str] = Field(
        default=None,
        description="Human-readable summary of changes",
    )

    # Evidence preservation (S7-2)
    evidence_snapshots: list[EvidenceSnapshot] = Field(
        default_factory=list,
        description="Frozen evidence state at publication time",
    )

    # Provenance tracking (NFR-TRANSPARENCY-001)
    candidate_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="All COP candidate IDs included",
    )
    draft_generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When draft was first generated",
    )
    created_by: PyObjectId = Field(
        ...,
        description="Facilitator who created draft",
    )

    # Approval tracking (FR-COP-PUB-001)
    approved_by: Optional[PyObjectId] = Field(
        default=None,
        description="Facilitator who approved for publishing",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="When approved",
    )
    approval_notes: Optional[str] = Field(
        default=None,
        description="Notes from approver",
    )

    # Publishing tracking
    published_at: Optional[datetime] = Field(
        default=None,
        description="When posted to Slack",
    )
    slack_channel_id: Optional[str] = Field(
        default=None,
        description="Channel where posted",
    )
    slack_message_ts: Optional[str] = Field(
        default=None,
        description="Slack message timestamp",
    )
    slack_permalink: Optional[str] = Field(
        default=None,
        description="Permalink to posted message",
    )

    # Edit tracking
    edit_count: int = Field(
        default=0,
        description="Number of edits made to draft",
    )
    last_edited_by: Optional[PyObjectId] = Field(
        default=None,
        description="Last user to edit",
    )
    last_edited_at: Optional[datetime] = Field(
        default=None,
        description="When last edited",
    )

    # Supersession tracking
    superseded_by: Optional[PyObjectId] = Field(
        default=None,
        description="ID of newer update that supersedes this",
    )
    superseded_at: Optional[datetime] = Field(
        default=None,
        description="When superseded",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last update timestamp",
    )

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class COPUpdateResponse(BaseModel):
    """API response for COP update."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    workspace_id: str
    update_number: int
    title: str
    status: str
    verified_count: int
    in_review_count: int
    disproven_count: int
    open_questions_count: int
    created_by: str
    created_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    slack_permalink: Optional[str] = None

    @classmethod
    def from_model(cls, update: COPUpdate) -> "COPUpdateResponse":
        """Create response from COPUpdate model."""
        verified = [li for li in update.line_items if li.section == "verified"]
        in_review = [li for li in update.line_items if li.section == "in_review"]
        disproven = [li for li in update.line_items if li.section == "disproven"]

        return cls(
            id=str(update.id),
            workspace_id=update.workspace_id,
            update_number=update.update_number,
            title=update.title,
            status=update.status.value,
            verified_count=len(verified),
            in_review_count=len(in_review),
            disproven_count=len(disproven),
            open_questions_count=len(update.open_questions),
            created_by=str(update.created_by),
            created_at=update.created_at,
            approved_by=str(update.approved_by) if update.approved_by else None,
            approved_at=update.approved_at,
            published_at=update.published_at,
            slack_permalink=update.slack_permalink,
        )
