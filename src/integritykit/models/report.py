"""After-action report models for Sprint 8.

Implements:
- S8-14: After-action report export (PDF/DOCX)
- Aggregated analytics data for post-incident analysis
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportFormat(StrEnum):
    """Supported report export formats."""

    PDF = "pdf"
    DOCX = "docx"


class ReportSection(StrEnum):
    """Sections included in after-action reports."""

    EXECUTIVE_SUMMARY = "executive_summary"
    TIMELINE = "timeline"
    SIGNAL_ANALYSIS = "signal_analysis"
    FACILITATOR_PERFORMANCE = "facilitator_performance"
    CONFLICT_RESOLUTION = "conflict_resolution"
    TOPIC_TRENDS = "topic_trends"
    RECOMMENDATIONS = "recommendations"


class SignalSummary(BaseModel):
    """Summary of signal ingestion and processing."""

    model_config = ConfigDict(use_enum_values=True)

    total_signals: int = Field(
        ...,
        description="Total signals ingested during the period",
    )
    signals_by_channel: dict[str, int] = Field(
        default_factory=dict,
        description="Signal count by channel",
    )
    peak_volume_hour: datetime | None = Field(
        default=None,
        description="Hour with highest signal volume",
    )
    peak_volume_count: int = Field(
        default=0,
        description="Signal count during peak hour",
    )
    avg_signals_per_day: float = Field(
        default=0.0,
        description="Average signals per day",
    )


class CandidateSummary(BaseModel):
    """Summary of COP candidate processing."""

    model_config = ConfigDict(use_enum_values=True)

    total_candidates: int = Field(
        ...,
        description="Total candidates created",
    )
    verified_count: int = Field(
        default=0,
        description="Candidates that reached VERIFIED state",
    )
    blocked_count: int = Field(
        default=0,
        description="Candidates blocked by conflicts",
    )
    in_review_count: int = Field(
        default=0,
        description="Candidates still in review at end of period",
    )
    avg_time_to_verification_hours: float = Field(
        default=0.0,
        description="Average time from creation to verification",
    )
    verification_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of verified to total candidates",
    )


class FacilitatorSummary(BaseModel):
    """Summary of facilitator performance metrics."""

    model_config = ConfigDict(use_enum_values=True)

    user_id: str = Field(
        ...,
        description="Facilitator user ID",
    )
    user_name: str | None = Field(
        default=None,
        description="Facilitator display name",
    )
    total_actions: int = Field(
        default=0,
        description="Total actions performed",
    )
    candidates_processed: int = Field(
        default=0,
        description="Unique candidates touched",
    )
    verification_actions: int = Field(
        default=0,
        description="Number of verification actions",
    )
    conflict_resolutions: int = Field(
        default=0,
        description="Number of conflicts resolved",
    )
    avg_response_time_hours: float = Field(
        default=0.0,
        description="Average response time to candidate updates",
    )


class ConflictSummary(BaseModel):
    """Summary of conflict resolution metrics."""

    model_config = ConfigDict(use_enum_values=True)

    total_conflicts: int = Field(
        default=0,
        description="Total conflicts detected",
    )
    resolved_conflicts: int = Field(
        default=0,
        description="Conflicts successfully resolved",
    )
    resolution_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of resolved to total conflicts",
    )
    avg_resolution_time_hours: float = Field(
        default=0.0,
        description="Average time to resolve conflicts",
    )
    by_risk_tier: dict[str, int] = Field(
        default_factory=dict,
        description="Conflict count by risk tier",
    )
    by_resolution_method: dict[str, int] = Field(
        default_factory=dict,
        description="Count by resolution method",
    )


class TopicSummary(BaseModel):
    """Summary of a trending topic."""

    model_config = ConfigDict(use_enum_values=True)

    topic: str = Field(
        ...,
        description="Topic name",
    )
    topic_type: str = Field(
        ...,
        description="Type (incident, need, resource_offer, etc.)",
    )
    signal_count: int = Field(
        default=0,
        description="Total signals for this topic",
    )
    trend_direction: str = Field(
        default="stable",
        description="Trend direction (emerging, declining, stable, new, peaked)",
    )
    first_seen: datetime | None = Field(
        default=None,
        description="First appearance of topic",
    )
    peak_time: datetime | None = Field(
        default=None,
        description="Time of peak activity",
    )


class TimelineEvent(BaseModel):
    """Significant event in the incident timeline."""

    model_config = ConfigDict(use_enum_values=True)

    timestamp: datetime = Field(
        ...,
        description="Event timestamp",
    )
    event_type: str = Field(
        ...,
        description="Type of event (signal_surge, conflict_detected, verification, etc.)",
    )
    description: str = Field(
        ...,
        description="Human-readable event description",
    )
    significance: str = Field(
        default="normal",
        description="Event significance (normal, notable, critical)",
    )
    related_ids: list[str] = Field(
        default_factory=list,
        description="Related entity IDs (candidate_id, signal_id, etc.)",
    )


class AfterActionReportRequest(BaseModel):
    """Request parameters for after-action report generation."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_date: datetime = Field(
        ...,
        description="Start of reporting period",
    )
    end_date: datetime = Field(
        ...,
        description="End of reporting period",
    )
    title: str = Field(
        default="After-Action Report",
        description="Report title",
    )
    incident_name: str | None = Field(
        default=None,
        description="Optional incident/event name",
    )
    format: ReportFormat = Field(
        default=ReportFormat.PDF,
        description="Output format (pdf or docx)",
    )
    sections: list[ReportSection] = Field(
        default_factory=lambda: list(ReportSection),
        description="Sections to include in report",
    )
    include_charts: bool = Field(
        default=True,
        description="Include visual charts (PDF only)",
    )


class AfterActionReportData(BaseModel):
    """Aggregated data for after-action report generation."""

    model_config = ConfigDict(use_enum_values=True)

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    workspace_name: str | None = Field(
        default=None,
        description="Workspace display name",
    )
    title: str = Field(
        ...,
        description="Report title",
    )
    incident_name: str | None = Field(
        default=None,
        description="Incident/event name",
    )
    start_date: datetime = Field(
        ...,
        description="Start of reporting period",
    )
    end_date: datetime = Field(
        ...,
        description="End of reporting period",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Report generation timestamp",
    )

    # Executive summary metrics
    signal_summary: SignalSummary | None = Field(
        default=None,
        description="Signal ingestion summary",
    )
    candidate_summary: CandidateSummary | None = Field(
        default=None,
        description="Candidate processing summary",
    )

    # Detailed analytics
    timeline: list[TimelineEvent] = Field(
        default_factory=list,
        description="Significant events timeline",
    )
    facilitator_summaries: list[FacilitatorSummary] = Field(
        default_factory=list,
        description="Per-facilitator performance metrics",
    )
    conflict_summary: ConflictSummary | None = Field(
        default=None,
        description="Conflict resolution summary",
    )
    topic_summaries: list[TopicSummary] = Field(
        default_factory=list,
        description="Top trending topics",
    )

    # Recommendations
    recommendations: list[str] = Field(
        default_factory=list,
        description="Auto-generated recommendations based on metrics",
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional report metadata",
    )
