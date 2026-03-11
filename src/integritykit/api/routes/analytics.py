"""Time-series analytics API routes for Sprint 8.

Implements:
- FR-ANALYTICS-001: Time-series analysis endpoints
- S8-9: Analytics API routes
"""

from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from integritykit.api.dependencies import (
    CurrentUser,
    RequireViewMetrics,
)
from integritykit.models.analytics import (
    ConflictResolutionMetricsResponse,
    FacilitatorWorkloadResponse,
    Granularity,
    MetricType,
    TimeSeriesAnalyticsRequest,
    TimeSeriesAnalyticsResponse,
    TopicTrendsResponse,
)
from integritykit.services.analytics import (
    AnalyticsService,
    get_analytics_service_dependency,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/time-series", response_model=TimeSeriesAnalyticsResponse)
async def get_time_series_analytics(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime | None = Query(
        default=None,
        description="Start date for time-series (defaults to 7 days ago)",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End date for time-series (defaults to now)",
    ),
    granularity: Granularity = Query(
        default=Granularity.DAY,
        description="Time bucket granularity (hour, day, week)",
    ),
    metrics: list[MetricType] = Query(
        default=[MetricType.SIGNAL_VOLUME],
        description="List of metrics to compute (signal_volume, readiness_transitions, facilitator_actions)",
    ),
    facilitator_id: str | None = Query(
        default=None,
        description="Filter facilitator actions by specific user (optional)",
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> TimeSeriesAnalyticsResponse:
    """Get time-series analytics for specified metrics.

    Supports multiple metrics in a single query:
    - signal_volume: Signal ingestion volume over time
    - readiness_transitions: COP candidate state transitions
    - facilitator_actions: Facilitator action velocity and breakdown

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start date (defaults to 7 days ago)
        end_date: End date (defaults to now)
        granularity: Time bucket granularity
        metrics: List of metrics to compute
        facilitator_id: Filter by facilitator (optional)
        analytics_service: Analytics service

    Returns:
        TimeSeriesAnalyticsResponse with requested metrics

    Raises:
        HTTPException: If time range is invalid or exceeds maximum
    """
    now = datetime.utcnow()

    if end_date is None:
        end_date = now

    if start_date is None:
        start_date = end_date - timedelta(days=7)

    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before end_date",
        )

    # Validate that end_date is not in the future
    if end_date > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be in the future",
        )

    # Create request object
    request = TimeSeriesAnalyticsRequest(
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        metrics=metrics,
        facilitator_id=facilitator_id,
    )

    try:
        response = await analytics_service.compute_time_series_analytics(request)
        return response
    except ValueError as e:
        logger.warning(
            "Invalid time-series analytics request",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to compute time-series analytics",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute analytics",
        )


@router.get("/signal-volume")
async def get_signal_volume_time_series(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    granularity: Granularity = Query(default=Granularity.DAY),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> dict:
    """Get signal volume time-series.

    Convenience endpoint for signal volume only.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start date
        end_date: End date
        granularity: Time granularity
        analytics_service: Analytics service

    Returns:
        dict with signal volume time-series data
    """
    now = datetime.utcnow()
    end_date = end_date or now
    start_date = start_date or (end_date - timedelta(days=7))

    signal_volume = await analytics_service.compute_signal_volume_time_series(
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )

    return {
        "workspace_id": workspace_id,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity.value,
        "data": [dp.model_dump() for dp in signal_volume],
        "total_signals": sum(dp.signal_count for dp in signal_volume),
    }


@router.get("/readiness-transitions")
async def get_readiness_transitions_time_series(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    granularity: Granularity = Query(default=Granularity.DAY),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> dict:
    """Get readiness state transitions time-series.

    Convenience endpoint for readiness transitions only.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start date
        end_date: End date
        granularity: Time granularity
        analytics_service: Analytics service

    Returns:
        dict with readiness transitions time-series data
    """
    now = datetime.utcnow()
    end_date = end_date or now
    start_date = start_date or (end_date - timedelta(days=7))

    transitions = await analytics_service.compute_readiness_transitions_time_series(
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )

    return {
        "workspace_id": workspace_id,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity.value,
        "data": [dp.model_dump() for dp in transitions],
        "total_transitions": sum(dp.total_transitions for dp in transitions),
    }


@router.get("/facilitator-actions")
async def get_facilitator_actions_time_series(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    granularity: Granularity = Query(default=Granularity.DAY),
    facilitator_id: str | None = Query(default=None),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> dict:
    """Get facilitator actions time-series.

    Convenience endpoint for facilitator actions only.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start date
        end_date: End date
        granularity: Time granularity
        facilitator_id: Filter by facilitator
        analytics_service: Analytics service

    Returns:
        dict with facilitator actions time-series data
    """
    now = datetime.utcnow()
    end_date = end_date or now
    start_date = start_date or (end_date - timedelta(days=7))

    actions = await analytics_service.compute_facilitator_actions_time_series(
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        facilitator_id=facilitator_id,
    )

    return {
        "workspace_id": workspace_id,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity.value,
        "facilitator_id": facilitator_id,
        "data": [dp.model_dump() for dp in actions],
        "total_actions": sum(dp.total_actions for dp in actions),
        "avg_velocity": (
            sum(dp.action_velocity for dp in actions) / len(actions) if actions else 0
        ),
    }


@router.get("/trends", response_model=TopicTrendsResponse)
async def get_topic_trends(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime | None = Query(
        default=None,
        description="Start date for trend analysis (defaults to 30 days ago)",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End date for trend analysis (defaults to now)",
    ),
    min_signals: int = Query(
        default=5,
        ge=1,
        description="Minimum signal count for topic to be included",
    ),
    direction: str | None = Query(
        default=None,
        description="Filter by trend direction (emerging, declining, stable, new, peaked, all)",
    ),
    topic_type: str | None = Query(
        default=None,
        description="Filter by topic type (incident, need, resource_offer, etc.)",
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> TopicTrendsResponse:
    """Get topic trend analysis.

    Analyzes topic clustering trends over time to identify emerging topics
    (increasing signal volume) and declining topics (decreasing activity).

    Uses LLM-based topic clustering to detect thematic shifts in signal content.

    Trend indicators:
    - emerging: Significant increase in signal volume for topic (>20%)
    - declining: Significant decrease in signal volume for topic (>20%)
    - stable: Consistent signal volume (within ±20%)
    - new: Topic first appeared in time range
    - peaked: Topic reached maximum volume and now declining

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start date (defaults to 30 days ago)
        end_date: End date (defaults to now)
        min_signals: Minimum signal count for inclusion
        direction: Filter by trend direction (optional)
        topic_type: Filter by topic type (optional)
        analytics_service: Analytics service

    Returns:
        TopicTrendsResponse with detected trends and summary

    Raises:
        HTTPException: If time range is invalid or exceeds maximum
    """
    now = datetime.utcnow()

    if end_date is None:
        end_date = now

    if start_date is None:
        start_date = end_date - timedelta(days=30)

    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before end_date",
        )

    # Validate that end_date is not in the future
    if end_date > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be in the future",
        )

    # Validate direction filter
    valid_directions = ["emerging", "declining", "stable", "new", "peaked", "all"]
    if direction and direction not in valid_directions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid direction filter. Must be one of: {', '.join(valid_directions)}",
        )

    try:
        response = await analytics_service.compute_topic_trends(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            min_signals=min_signals,
            direction_filter=direction,
            topic_type_filter=topic_type,
        )
        return response
    except ValueError as e:
        logger.warning(
            "Invalid topic trends request",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to compute topic trends",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute topic trends",
        )


@router.get("/facilitator-workload", response_model=FacilitatorWorkloadResponse)
async def get_facilitator_workload(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime = Query(
        ...,
        description="Start of time range for analysis",
    ),
    end_date: datetime = Query(
        ...,
        description="End of time range for analysis",
    ),
    facilitator_id: str | None = Query(
        default=None,
        description="Filter by specific facilitator (default: all)",
    ),
    include_inactive: bool = Query(
        default=False,
        description="Include facilitators with zero actions in time range",
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> FacilitatorWorkloadResponse:
    """Get facilitator workload analytics.

    Analyzes facilitator performance and workload distribution metrics including:
    - Total actions by facilitator
    - Average time per candidate
    - Actions by type (promote, verify, publish, merge, etc.)
    - Readiness state transition velocity
    - Conflict resolution rate
    - High-stakes override frequency

    Useful for:
    - Workload balancing
    - Training needs identification
    - Performance benchmarking
    - Bottleneck detection

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start of time range
        end_date: End of time range
        facilitator_id: Filter by specific facilitator (optional)
        include_inactive: Include facilitators with zero actions
        analytics_service: Analytics service

    Returns:
        FacilitatorWorkloadResponse with workload metrics

    Raises:
        HTTPException: If time range is invalid or exceeds maximum
    """
    now = datetime.utcnow()

    # Validate date range
    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before end_date",
        )

    # Validate that end_date is not in the future
    if end_date > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be in the future",
        )

    try:
        response = await analytics_service.compute_facilitator_workload(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            facilitator_id=facilitator_id,
            include_inactive=include_inactive,
        )
        return response
    except ValueError as e:
        logger.warning(
            "Invalid facilitator workload request",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to compute facilitator workload",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute facilitator workload analytics",
        )


@router.get("/conflict-resolution", response_model=ConflictResolutionMetricsResponse)
async def get_conflict_resolution_metrics(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_date: datetime = Query(
        ...,
        description="Start of time range for analysis",
    ),
    end_date: datetime = Query(
        ...,
        description="End of time range for analysis",
    ),
    risk_tier: str | None = Query(
        default=None,
        description="Filter by risk tier (routine, elevated, high_stakes) - optional",
    ),
    resolved_only: bool = Query(
        default=False,
        description="Only include resolved conflicts (default: False)",
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service_dependency),
) -> ConflictResolutionMetricsResponse:
    """Get conflict resolution time analysis metrics (S8-12).

    Analyzes conflict detection and resolution patterns including:
    - Resolution times from detection to resolution
    - Resolution rates by risk tier
    - Resolution method distribution (merged, one_correct, both_valid, deferred)
    - Time statistics (avg, median, min, max) by risk tier

    Useful for:
    - Process optimization
    - Workload planning
    - Identifying bottlenecks in conflict resolution
    - Training needs assessment

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_date: Start of time range
        end_date: End of time range
        risk_tier: Filter by specific risk tier (optional)
        resolved_only: Only include resolved conflicts
        analytics_service: Analytics service

    Returns:
        ConflictResolutionMetricsResponse with metrics grouped by risk tier

    Raises:
        HTTPException: If time range is invalid or exceeds maximum
    """
    now = datetime.utcnow()

    # Validate date range
    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before end_date",
        )

    # Validate that end_date is not in the future
    if end_date > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be in the future",
        )

    # Validate risk_tier if provided
    if risk_tier:
        valid_tiers = ["routine", "elevated", "high_stakes"]
        if risk_tier not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid risk_tier. Must be one of: {', '.join(valid_tiers)}",
            )

    try:
        response = await analytics_service.compute_conflict_resolution_metrics(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            risk_tier=risk_tier,
            resolved_only=resolved_only,
        )
        return response
    except ValueError as e:
        logger.warning(
            "Invalid conflict resolution metrics request",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to compute conflict resolution metrics",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute conflict resolution metrics",
        )
