"""Time-series analytics models for Sprint 8.

Implements:
- FR-ANALYTICS-001: Time-series analysis of signal volume and readiness
- S8-9: Time-series analytics service
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Granularity(StrEnum):
    """Time granularity for analytics aggregation."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


class MetricType(StrEnum):
    """Types of time-series metrics."""

    SIGNAL_VOLUME = "signal_volume"
    READINESS_TRANSITIONS = "readiness_transitions"
    FACILITATOR_ACTIONS = "facilitator_actions"


class TrendDirection(StrEnum):
    """Trend direction indicators for topic analysis."""

    EMERGING = "emerging"
    DECLINING = "declining"
    STABLE = "stable"
    NEW = "new"
    PEAKED = "peaked"


class TimeSeriesDataPoint(BaseModel):
    """Single data point in a time-series."""

    model_config = ConfigDict(use_enum_values=True)

    timestamp: datetime = Field(
        ...,
        description="Time bucket for this data point",
    )
    metric_type: str = Field(
        ...,
        description="Type of metric (signal_volume, readiness_transitions, facilitator_actions)",
    )
    value: float = Field(
        ...,
        description="Numeric value for this time bucket",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., breakdown by state, action type)",
    )


class SignalVolumeDataPoint(BaseModel):
    """Time-series data point for signal volume."""

    timestamp: datetime = Field(
        ...,
        description="Time bucket for this data point",
    )
    signal_count: int = Field(
        ...,
        description="Number of signals ingested in this time bucket",
    )
    by_channel: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown by channel ID",
    )


class ReadinessTransitionDataPoint(BaseModel):
    """Time-series data point for readiness state transitions."""

    timestamp: datetime = Field(
        ...,
        description="Time bucket for this data point",
    )
    transitions: dict[str, int] = Field(
        default_factory=dict,
        description="Count of transitions by state (e.g., IN_REVIEW->VERIFIED: 5)",
    )
    total_transitions: int = Field(
        ...,
        description="Total transitions in this time bucket",
    )


class FacilitatorActionDataPoint(BaseModel):
    """Time-series data point for facilitator actions."""

    timestamp: datetime = Field(
        ...,
        description="Time bucket for this data point",
    )
    total_actions: int = Field(
        ...,
        description="Total facilitator actions in this time bucket",
    )
    by_action_type: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown by action type",
    )
    by_facilitator: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown by facilitator user ID",
    )
    action_velocity: float = Field(
        ...,
        description="Actions per hour (normalized rate)",
    )


class TimeSeriesAnalyticsRequest(BaseModel):
    """Request parameters for time-series analytics query."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_date: datetime = Field(
        ...,
        description="Start date for time-series query",
    )
    end_date: datetime = Field(
        ...,
        description="End date for time-series query",
    )
    granularity: Granularity = Field(
        default=Granularity.DAY,
        description="Time bucket granularity (hour, day, week)",
    )
    metrics: list[MetricType] = Field(
        default_factory=lambda: [MetricType.SIGNAL_VOLUME],
        description="List of metrics to compute",
    )
    facilitator_id: str | None = Field(
        default=None,
        description="Filter by specific facilitator (optional)",
    )


class TimeSeriesAnalyticsResponse(BaseModel):
    """Response containing time-series analytics data."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_date: datetime = Field(
        ...,
        description="Start date of analysis period",
    )
    end_date: datetime = Field(
        ...,
        description="End date of analysis period",
    )
    granularity: str = Field(
        ...,
        description="Time bucket granularity used",
    )
    signal_volume: list[SignalVolumeDataPoint] | None = Field(
        default=None,
        description="Signal volume time-series (if requested)",
    )
    readiness_transitions: list[ReadinessTransitionDataPoint] | None = Field(
        default=None,
        description="Readiness transition time-series (if requested)",
    )
    facilitator_actions: list[FacilitatorActionDataPoint] | None = Field(
        default=None,
        description="Facilitator action time-series (if requested)",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics for the period",
    )


class AnalyticsAggregationConfig(BaseModel):
    """Configuration for analytics aggregation queries."""

    max_time_range_days: int = Field(
        default=90,
        description="Maximum time range for single query (days)",
    )
    retention_days: int = Field(
        default=365,
        description="How long to retain analytics data (days)",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Cache TTL for analytics queries",
    )


class TopicTrend(BaseModel):
    """Topic trend analysis result.

    Represents a topic identified through clustering with its trend characteristics.
    """

    model_config = ConfigDict(use_enum_values=True)

    topic: str = Field(
        ...,
        description="Topic name or keyword cluster",
    )
    topic_type: str = Field(
        ...,
        description="Type of topic (incident, need, resource_offer, etc.)",
    )
    direction: TrendDirection = Field(
        ...,
        description="Trend direction (emerging, declining, stable, new, peaked)",
    )
    signal_count: int = Field(
        ...,
        description="Total signals in this topic during time range",
    )
    volume_change_pct: float = Field(
        ...,
        description="Percentage change in signal volume (positive = increase)",
    )
    first_seen: datetime = Field(
        ...,
        description="First signal timestamp for this topic",
    )
    peak_time: datetime | None = Field(
        default=None,
        description="Timestamp of maximum signal volume",
    )
    peak_volume: int = Field(
        default=0,
        description="Maximum signals in a single time bucket",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Representative keywords for this topic",
    )
    related_clusters: list[str] = Field(
        default_factory=list,
        description="Cluster IDs associated with this topic",
    )
    velocity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Rate of change indicator (0 = stable, 1 = rapid change)",
    )


class TopicTrendsResponse(BaseModel):
    """Response containing topic trend analysis results."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_date: datetime = Field(
        ...,
        description="Start date of analysis period",
    )
    end_date: datetime = Field(
        ...,
        description="End date of analysis period",
    )
    trends: list[TopicTrend] = Field(
        default_factory=list,
        description="List of detected topic trends",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics (total_topics, emerging_count, etc.)",
    )


class FacilitatorWorkload(BaseModel):
    """Facilitator workload metrics for a single facilitator.

    Tracks performance and workload distribution metrics for workload
    balancing and training needs identification.
    """

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
        ...,
        description="Total actions performed in time range",
    )
    actions_by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown by action type (promote, verify, publish, merge, etc.)",
    )
    average_time_per_candidate_hours: float = Field(
        default=0.0,
        description="Average time from first to last action on candidates (hours)",
    )
    candidates_processed: int = Field(
        default=0,
        description="Number of unique candidates touched",
    )
    conflict_resolution_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of conflicts resolved to conflicts encountered",
    )
    high_stakes_override_count: int = Field(
        default=0,
        description="Number of high-stakes approval overrides performed",
    )
    workload_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized workload indicator relative to team average (0=light, 1=heavy)",
    )


class FacilitatorWorkloadResponse(BaseModel):
    """Response containing facilitator workload analytics."""

    workspace_id: str = Field(
        ...,
        description="Slack workspace ID",
    )
    start_date: datetime = Field(
        ...,
        description="Start date of analysis period",
    )
    end_date: datetime = Field(
        ...,
        description="End date of analysis period",
    )
    facilitators: list[FacilitatorWorkload] = Field(
        default_factory=list,
        description="Workload metrics by facilitator",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics (total_facilitators, total_actions, avg_actions, etc.)",
    )
