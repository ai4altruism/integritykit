"""Operational metrics models for exercise evaluation.

Implements:
- FR-METRICS-001: Five operational metrics
- FR-METRICS-002: Metrics export capability
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricType(StrEnum):
    """Types of operational metrics (FR-METRICS-001)."""

    TIME_TO_VALIDATED_UPDATE = "time_to_validated_update"
    CONFLICTING_REPORT_RATE = "conflicting_report_rate"
    MODERATOR_BURDEN = "moderator_burden"
    PROVENANCE_COVERAGE = "provenance_coverage"
    READINESS_DISTRIBUTION = "readiness_distribution"


class TimeToValidatedUpdateMetric(BaseModel):
    """Time from signal ingestion to COP publication.

    Measures the latency of the verification pipeline.
    """

    model_config = ConfigDict(use_enum_values=True)

    metric_type: str = Field(
        default=MetricType.TIME_TO_VALIDATED_UPDATE.value,
        description="Type of metric",
    )
    average_seconds: float = Field(
        ...,
        description="Average time in seconds from signal to publication",
    )
    median_seconds: float = Field(
        ...,
        description="Median time in seconds",
    )
    min_seconds: float = Field(
        ...,
        description="Minimum time observed",
    )
    max_seconds: float = Field(
        ...,
        description="Maximum time observed",
    )
    p90_seconds: float = Field(
        ...,
        description="90th percentile time",
    )
    sample_count: int = Field(
        ...,
        description="Number of COP updates measured",
    )
    breakdown_by_risk_tier: dict[str, float] = Field(
        default_factory=dict,
        description="Average time broken down by risk tier",
    )


class ConflictingReportRateMetric(BaseModel):
    """Rate of conflicting information detected.

    Measures information quality and verification burden.
    """

    model_config = ConfigDict(use_enum_values=True)

    metric_type: str = Field(
        default=MetricType.CONFLICTING_REPORT_RATE.value,
        description="Type of metric",
    )
    total_clusters: int = Field(
        ...,
        description="Total clusters analyzed",
    )
    clusters_with_conflicts: int = Field(
        ...,
        description="Clusters containing conflicts",
    )
    conflict_rate: float = Field(
        ...,
        description="Percentage of clusters with conflicts (0-100)",
    )
    total_conflicts_detected: int = Field(
        ...,
        description="Total number of conflicts detected",
    )
    conflicts_resolved: int = Field(
        ...,
        description="Number of conflicts resolved",
    )
    resolution_rate: float = Field(
        ...,
        description="Percentage of conflicts resolved (0-100)",
    )
    average_resolution_time_seconds: float | None = Field(
        default=None,
        description="Average time to resolve conflicts",
    )


class ModeratorBurdenMetric(BaseModel):
    """Facilitator workload metrics.

    Measures actions required per COP update.
    """

    model_config = ConfigDict(use_enum_values=True)

    metric_type: str = Field(
        default=MetricType.MODERATOR_BURDEN.value,
        description="Type of metric",
    )
    total_facilitator_actions: int = Field(
        ...,
        description="Total actions taken by facilitators",
    )
    actions_per_cop_update: float = Field(
        ...,
        description="Average actions per published COP update",
    )
    actions_by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Actions broken down by type",
    )
    unique_facilitators_active: int = Field(
        ...,
        description="Number of unique facilitators who took actions",
    )
    actions_per_facilitator: float = Field(
        ...,
        description="Average actions per active facilitator",
    )
    high_stakes_overrides: int = Field(
        default=0,
        description="Number of high-stakes publish overrides",
    )
    edits_to_ai_drafts: int = Field(
        default=0,
        description="Number of edits made to AI-generated drafts",
    )


class ProvenanceCoverageMetric(BaseModel):
    """Citation and evidence coverage metrics.

    Measures provenance quality of published COP updates.
    """

    model_config = ConfigDict(use_enum_values=True)

    metric_type: str = Field(
        default=MetricType.PROVENANCE_COVERAGE.value,
        description="Type of metric",
    )
    total_published_line_items: int = Field(
        ...,
        description="Total line items across all COP updates",
    )
    line_items_with_citations: int = Field(
        ...,
        description="Line items with at least one citation",
    )
    coverage_rate: float = Field(
        ...,
        description="Percentage with citations (0-100)",
    )
    average_citations_per_item: float = Field(
        ...,
        description="Average citations per line item",
    )
    slack_permalink_citations: int = Field(
        default=0,
        description="Total Slack message citations",
    )
    external_source_citations: int = Field(
        default=0,
        description="Total external source citations",
    )


class ReadinessDistributionMetric(BaseModel):
    """Distribution of COP candidates across readiness states.

    Shows pipeline health and verification bottlenecks.
    """

    model_config = ConfigDict(use_enum_values=True)

    metric_type: str = Field(
        default=MetricType.READINESS_DISTRIBUTION.value,
        description="Type of metric",
    )
    total_candidates: int = Field(
        ...,
        description="Total COP candidates",
    )
    in_review_count: int = Field(
        ...,
        description="Candidates in IN_REVIEW state",
    )
    verified_count: int = Field(
        ...,
        description="Candidates in VERIFIED state",
    )
    blocked_count: int = Field(
        ...,
        description="Candidates in BLOCKED state",
    )
    archived_count: int = Field(
        ...,
        description="Candidates in ARCHIVED state",
    )
    in_review_percentage: float = Field(
        ...,
        description="Percentage in IN_REVIEW (0-100)",
    )
    verified_percentage: float = Field(
        ...,
        description="Percentage VERIFIED (0-100)",
    )
    blocked_percentage: float = Field(
        ...,
        description="Percentage BLOCKED (0-100)",
    )
    archived_percentage: float = Field(
        ...,
        description="Percentage ARCHIVED (0-100)",
    )
    by_risk_tier: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Distribution breakdown by risk tier",
    )


class MetricsSnapshot(BaseModel):
    """Complete metrics snapshot for a time period.

    Combines all five operational metrics (FR-METRICS-001).
    """

    model_config = ConfigDict(use_enum_values=True)

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    period_start: datetime = Field(
        ...,
        description="Start of measurement period",
    )
    period_end: datetime = Field(
        ...,
        description="End of measurement period",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this snapshot was generated",
    )
    time_to_validated_update: TimeToValidatedUpdateMetric = Field(
        ...,
        description="Time-to-validated-update metric",
    )
    conflicting_report_rate: ConflictingReportRateMetric = Field(
        ...,
        description="Conflicting report rate metric",
    )
    moderator_burden: ModeratorBurdenMetric = Field(
        ...,
        description="Moderator burden metric",
    )
    provenance_coverage: ProvenanceCoverageMetric = Field(
        ...,
        description="Provenance coverage metric",
    )
    readiness_distribution: ReadinessDistributionMetric = Field(
        ...,
        description="Readiness distribution metric",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics and highlights",
    )


class MetricsExportFormat(StrEnum):
    """Export formats for metrics (FR-METRICS-002)."""

    JSON = "json"
    CSV = "csv"


class MetricsExportRequest(BaseModel):
    """Request for metrics export."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_time: datetime = Field(
        ...,
        description="Start of period to export",
    )
    end_time: datetime = Field(
        ...,
        description="End of period to export",
    )
    format: MetricsExportFormat = Field(
        default=MetricsExportFormat.JSON,
        description="Export format",
    )
    include_raw_data: bool = Field(
        default=False,
        description="Include raw data points for detailed analysis",
    )
