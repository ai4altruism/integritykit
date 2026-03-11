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
