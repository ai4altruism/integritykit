"""COP Candidate model for items in the verification workflow.

Implements:
- FR-BACKLOG-002: Promote cluster to COP candidate
- FR-VER-001: Verification workflow states
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class ReadinessState(str, Enum):
    """Workflow states for COP candidate readiness."""

    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class RiskTier(str, Enum):
    """Risk classification for COP candidates."""

    ROUTINE = "routine"
    ELEVATED = "elevated"
    HIGH_STAKES = "high_stakes"


class VerificationMethod(str, Enum):
    """Methods used to verify information."""

    AUTHORITATIVE_SOURCE = "authoritative_source"
    MULTIPLE_INDEPENDENT = "multiple_independent"
    DIRECT_OBSERVATION = "direct_observation"
    EXPERT_CONFIRMATION = "expert_confirmation"


class ConfidenceLevel(str, Enum):
    """Confidence level for verifications."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BlockingIssueSeverity(str, Enum):
    """Severity of blocking issues."""

    BLOCKS_PUBLISHING = "blocks_publishing"
    REQUIRES_ATTENTION = "requires_attention"
    WARNING = "warning"


class ActionType(str, Enum):
    """Recommended action types for candidates."""

    ASSIGN_VERIFICATION = "assign_verification"
    RESOLVE_CONFLICT = "resolve_conflict"
    ADD_EVIDENCE = "add_evidence"
    READY_TO_PUBLISH = "ready_to_publish"
    MERGE_CANDIDATES = "merge_candidates"


class COPWhen(BaseModel):
    """Temporal information for COP candidate."""

    timestamp: Optional[datetime] = Field(
        default=None,
        description="Specific timestamp if known",
    )
    timezone: str = Field(
        default="UTC",
        description="Timezone for the timestamp",
    )
    is_approximate: bool = Field(
        default=True,
        description="Whether the time is approximate",
    )
    description: str = Field(
        default="",
        description="Human-readable time description",
    )


class COPFields(BaseModel):
    """Structured COP content fields (5W framework)."""

    what: str = Field(
        default="",
        description="What is happening/happened",
    )
    where: str = Field(
        default="",
        description="Location of the event/situation",
    )
    when: COPWhen = Field(
        default_factory=COPWhen,
        description="Temporal information",
    )
    who: str = Field(
        default="",
        description="Who is affected or involved",
    )
    so_what: str = Field(
        default="",
        description="Operational relevance and implications",
    )


class SlackPermalink(BaseModel):
    """Reference to a Slack message as evidence."""

    url: str = Field(
        ...,
        description="Slack permalink URL",
    )
    signal_id: Optional[PyObjectId] = Field(
        default=None,
        description="Associated signal ID if available",
    )
    description: str = Field(
        default="",
        description="Brief description of what this evidence supports",
    )


class ExternalSource(BaseModel):
    """External source reference for evidence."""

    url: str = Field(
        ...,
        description="URL of external source",
    )
    source_name: str = Field(
        default="",
        description="Name of the source (e.g., 'FEMA', 'Local News')",
    )
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the source was accessed",
    )
    description: str = Field(
        default="",
        description="What information this source provides",
    )


class Evidence(BaseModel):
    """Evidence pack for COP candidate."""

    slack_permalinks: list[SlackPermalink] = Field(
        default_factory=list,
        description="Links to supporting Slack messages",
    )
    external_sources: list[ExternalSource] = Field(
        default_factory=list,
        description="External source references",
    )


class Verification(BaseModel):
    """Record of a verification action."""

    verified_by: PyObjectId = Field(
        ...,
        description="User who performed verification",
    )
    verified_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When verification was performed",
    )
    verification_method: VerificationMethod = Field(
        ...,
        description="Method used to verify",
    )
    verification_notes: str = Field(
        default="",
        description="Notes about the verification",
    )
    confidence_level: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Confidence in the verification",
    )


class BlockingIssue(BaseModel):
    """Issue blocking candidate from publishing."""

    issue_type: str = Field(
        ...,
        description="Type of issue (missing_field, conflict, etc.)",
    )
    description: str = Field(
        ...,
        description="Description of the issue",
    )
    severity: BlockingIssueSeverity = Field(
        default=BlockingIssueSeverity.REQUIRES_ATTENTION,
        description="How severe this issue is",
    )


class RecommendedAction(BaseModel):
    """AI-recommended next action for candidate."""

    action_type: ActionType = Field(
        ...,
        description="Type of recommended action",
    )
    reason: str = Field(
        ...,
        description="Why this action is recommended",
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative actions to consider",
    )


class CandidateConflict(BaseModel):
    """Conflict record specific to COP candidate."""

    conflict_id: str = Field(
        ...,
        description="Reference to cluster conflict ID",
    )
    status: str = Field(
        default="unresolved",
        description="Resolution status (unresolved, resolved, deferred)",
    )
    resolution_notes: Optional[str] = Field(
        default=None,
        description="Notes on how conflict was resolved",
    )


class DraftWording(BaseModel):
    """Draft COP text generated by LLM."""

    headline: str = Field(
        default="",
        description="Headline for the COP update",
    )
    body: str = Field(
        default="",
        description="Body text for the COP update",
    )
    hedging_applied: bool = Field(
        default=False,
        description="Whether hedging language was applied",
    )
    recheck_time: Optional[datetime] = Field(
        default=None,
        description="When this info should be rechecked",
    )
    next_verification_step: Optional[str] = Field(
        default=None,
        description="Suggested next step for verification",
    )


class FacilitatorNote(BaseModel):
    """Note added by a facilitator."""

    author_id: PyObjectId = Field(
        ...,
        description="User who wrote the note",
    )
    content: str = Field(
        ...,
        description="Note content",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When note was created",
    )


class RiskTierOverride(BaseModel):
    """Record of manual risk tier override."""

    previous_tier: RiskTier = Field(
        ...,
        description="Tier before override",
    )
    new_tier: RiskTier = Field(
        ...,
        description="Tier after override",
    )
    overridden_by: PyObjectId = Field(
        ...,
        description="User who performed override",
    )
    overridden_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When override occurred",
    )
    reason: str = Field(
        ...,
        description="Justification for override",
    )


class COPCandidateCreate(BaseModel):
    """Schema for creating a COP candidate from a cluster."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cluster_id: PyObjectId = Field(
        ...,
        description="Source cluster ID",
    )
    primary_signal_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="Key supporting signal IDs",
    )
    created_by: PyObjectId = Field(
        ...,
        description="User promoting the cluster",
    )
    fields: Optional[COPFields] = Field(
        default=None,
        description="Initial COP fields (can be populated from cluster)",
    )
    risk_tier: RiskTier = Field(
        default=RiskTier.ROUTINE,
        description="Initial risk classification",
    )


class COPCandidate(BaseModel):
    """COP Candidate in verification workflow (FR-BACKLOG-002).

    Represents a cluster that has been promoted from the backlog
    and is being prepared for publication as a COP update.
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
    cluster_id: PyObjectId = Field(
        ...,
        description="Source cluster reference",
    )
    primary_signal_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="Key supporting signals from cluster",
    )

    # Workflow state
    readiness_state: ReadinessState = Field(
        default=ReadinessState.IN_REVIEW,
        description="Current workflow state",
    )
    readiness_updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When state was last changed",
    )
    readiness_updated_by: Optional[PyObjectId] = Field(
        default=None,
        description="User who last changed state",
    )

    # Risk classification
    risk_tier: RiskTier = Field(
        default=RiskTier.ROUTINE,
        description="Risk classification",
    )
    risk_tier_override: Optional[RiskTierOverride] = Field(
        default=None,
        description="Manual override if applicable",
    )

    # Content
    fields: COPFields = Field(
        default_factory=COPFields,
        description="Structured COP fields",
    )
    evidence: Evidence = Field(
        default_factory=Evidence,
        description="Evidence pack",
    )

    # Verification
    verifications: list[Verification] = Field(
        default_factory=list,
        description="Verification records",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields that still need to be filled",
    )
    blocking_issues: list[BlockingIssue] = Field(
        default_factory=list,
        description="Issues blocking publication",
    )
    recommended_action: Optional[RecommendedAction] = Field(
        default=None,
        description="AI-recommended next action",
    )

    # Conflict handling
    conflicts: list[CandidateConflict] = Field(
        default_factory=list,
        description="Conflicts from source cluster",
    )

    # Draft output
    draft_wording: Optional[DraftWording] = Field(
        default=None,
        description="LLM-generated draft text",
    )

    # Facilitator collaboration
    facilitator_notes: list[FacilitatorNote] = Field(
        default_factory=list,
        description="Notes from facilitators",
    )

    # Publication tracking
    published_in_cop_update_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="COP updates containing this candidate",
    )

    # Merge tracking
    merged_into_candidate_id: Optional[PyObjectId] = Field(
        default=None,
        description="If merged, the target candidate ID",
    )
    merged_at: Optional[datetime] = Field(
        default=None,
        description="When merge occurred",
    )
    merged_by: Optional[PyObjectId] = Field(
        default=None,
        description="User who performed merge",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When candidate was created",
    )
    created_by: PyObjectId = Field(
        ...,
        description="User who promoted cluster to candidate",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When candidate was last updated",
    )

    @property
    def is_verified(self) -> bool:
        """Check if candidate is verified."""
        return self.readiness_state == ReadinessState.VERIFIED

    @property
    def is_blocked(self) -> bool:
        """Check if candidate is blocked."""
        return self.readiness_state == ReadinessState.BLOCKED

    @property
    def is_publishable(self) -> bool:
        """Check if candidate can be published."""
        return (
            self.readiness_state == ReadinessState.VERIFIED
            and len(self.blocking_issues) == 0
            and len(self.missing_fields) == 0
        )

    @property
    def has_unresolved_conflicts(self) -> bool:
        """Check for unresolved conflicts."""
        return any(c.status == "unresolved" for c in self.conflicts)
