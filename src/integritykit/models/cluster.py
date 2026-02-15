"""Cluster model representing topic/incident groupings of related signals."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class ConflictSeverity(str, Enum):
    """Severity level of conflicts between signals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictResolutionType(str, Enum):
    """Type of resolution for a conflict."""

    MERGED = "merged"
    ONE_CORRECT = "one_correct"
    BOTH_VALID = "both_valid"
    DEFERRED = "deferred"


class ConflictResolution(BaseModel):
    """Resolution details for a conflict."""

    model_config = ConfigDict(use_enum_values=True)

    type: ConflictResolutionType = Field(
        ...,
        description="Type of resolution applied",
    )
    reasoning: str = Field(
        ...,
        description="Explanation for the resolution",
    )
    canonical_value: Optional[str] = Field(
        default=None,
        description="The canonical value if resolution type is merged or one_correct",
    )


class ConflictRecord(BaseModel):
    """Record of a detected conflict between signals in a cluster."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(
        ...,
        description="Unique identifier for this conflict",
    )
    signal_ids: list[PyObjectId] = Field(
        ...,
        description="Signal IDs involved in the conflict",
    )
    field: str = Field(
        ...,
        description="Field or dimension that conflicts (e.g., 'location', 'time', 'count')",
    )
    severity: ConflictSeverity = Field(
        ...,
        description="Severity level of the conflict",
    )
    description: str = Field(
        ...,
        description="Human-readable description of the conflict",
    )
    values: dict[str, str] = Field(
        default_factory=dict,
        description="The conflicting values from each signal (signal_id -> value)",
    )
    detected_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the conflict was detected",
    )
    resolved: bool = Field(
        default=False,
        description="Whether the conflict has been resolved",
    )
    resolution: Optional[ConflictResolution] = Field(
        default=None,
        description="Resolution details if conflict is resolved",
    )
    resolved_by: Optional[str] = Field(
        default=None,
        description="User who resolved the conflict",
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        description="When the conflict was resolved",
    )


class PriorityScores(BaseModel):
    """Priority scoring for cluster triage and backlog ordering."""

    urgency: float = Field(
        default=0.5,
        ge=0.0,
        le=100.0,
        description="Time-sensitive urgency score (0-100)",
    )
    urgency_reasoning: Optional[str] = Field(
        default=None,
        description="Explanation for urgency score",
    )
    impact: float = Field(
        default=0.5,
        ge=0.0,
        le=100.0,
        description="Estimated impact score - people affected, severity (0-100)",
    )
    impact_reasoning: Optional[str] = Field(
        default=None,
        description="Explanation for impact score",
    )
    risk: float = Field(
        default=0.5,
        ge=0.0,
        le=100.0,
        description="Safety/harm risk score (0-100)",
    )
    risk_reasoning: Optional[str] = Field(
        default=None,
        description="Explanation for risk score",
    )

    @property
    def composite_score(self) -> float:
        """Calculate composite priority score.

        Returns:
            Weighted average of urgency, impact, and risk (0-100)
        """
        # Weight urgency higher for crisis response
        return (self.urgency * 0.4 + self.impact * 0.35 + self.risk * 0.25)


class ClusterCreate(BaseModel):
    """Schema for creating a new cluster."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    slack_workspace_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    signal_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="Initial signal IDs in cluster",
    )
    topic: str = Field(
        ...,
        description="LLM-generated topic summary",
    )
    incident_type: Optional[str] = Field(
        default=None,
        description="Categorization of incident type",
    )
    summary: str = Field(
        default="",
        description="LLM-generated summary of cluster",
    )


class Cluster(BaseModel):
    """Cluster representing a group of related signals by topic/incident.

    Clusters group signals that discuss the same event, location, need, or situation.
    They are used for backlog prioritization and can be promoted to COP candidates.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    slack_workspace_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    signal_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="Signal IDs belonging to this cluster",
    )
    topic: str = Field(
        ...,
        description="LLM-generated topic summary",
    )
    incident_type: Optional[str] = Field(
        default=None,
        description="Categorization of incident type",
    )
    summary: str = Field(
        default="",
        description="LLM-generated summary of cluster content",
    )
    priority_scores: PriorityScores = Field(
        default_factory=PriorityScores,
        description="Priority scores for backlog triage",
    )
    conflicts: list[ConflictRecord] = Field(
        default_factory=list,
        description="Detected conflicts between signals in cluster",
    )
    promoted_to_candidate: bool = Field(
        default=False,
        description="Whether cluster has been promoted to COP candidate",
    )
    cop_candidate_id: Optional[PyObjectId] = Field(
        default=None,
        description="Reference to COP candidate if promoted",
    )
    ai_generated_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about AI processing (model used, generation timestamp, etc.)",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When cluster was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When cluster was last updated",
    )

    @property
    def signal_count(self) -> int:
        """Get count of signals in cluster.

        Returns:
            Number of signals in cluster
        """
        return len(self.signal_ids)

    @property
    def has_conflicts(self) -> bool:
        """Check if cluster has any conflicts.

        Returns:
            True if conflicts exist
        """
        return len(self.conflicts) > 0

    @property
    def has_unresolved_conflicts(self) -> bool:
        """Check if cluster has any unresolved conflicts.

        Returns:
            True if unresolved conflicts exist
        """
        return any(not conflict.resolved for conflict in self.conflicts)
