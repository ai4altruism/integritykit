"""Metrics API routes for operational metrics.

Implements:
- FR-METRICS-001: Five operational metrics
- FR-METRICS-002: Metrics export (JSON/CSV)
"""

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequireViewMetrics,
)
from integritykit.models.metrics import (
    MetricsExportFormat,
    MetricsSnapshot,
)
from integritykit.services.metrics import MetricsService, get_metrics_service_dependency

router = APIRouter(prefix="/metrics", tags=["Metrics"])


class MetricsResponse(BaseModel):
    """Response wrapper for metrics snapshot."""

    data: MetricsSnapshot
    export_formats: list[str] = Field(
        default=["json", "csv"],
        description="Available export formats",
    )


class SingleMetricResponse(BaseModel):
    """Response for single metric endpoint."""

    metric_type: str
    data: dict
    period_start: datetime
    period_end: datetime


@router.get("", response_model=MetricsResponse)
async def get_metrics_snapshot(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(
        default=None,
        description="Period start (defaults to 24 hours ago)",
    ),
    end_time: datetime | None = Query(
        default=None,
        description="Period end (defaults to now)",
    ),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> MetricsResponse:
    """Get complete metrics snapshot for a time period.

    Returns all five operational metrics (FR-METRICS-001):
    - Time-to-validated-update
    - Conflicting report rate
    - Moderator burden
    - Provenance coverage
    - Readiness distribution

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start (defaults to 24h ago)
        end_time: Period end (defaults to now)
        metrics_service: Metrics service

    Returns:
        MetricsResponse with complete snapshot
    """
    now = datetime.utcnow()

    if end_time is None:
        end_time = now

    if start_time is None:
        start_time = end_time - timedelta(hours=24)

    if start_time >= end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be before end_time",
        )

    snapshot = await metrics_service.compute_metrics_snapshot(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return MetricsResponse(data=snapshot)


@router.get("/time-to-validated-update", response_model=SingleMetricResponse)
async def get_time_to_validated_update(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> SingleMetricResponse:
    """Get time-to-validated-update metric.

    Measures time from signal ingestion to COP publication.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Time-to-validated-update metric data
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    metric = await metrics_service.compute_time_to_validated_update(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return SingleMetricResponse(
        metric_type="time_to_validated_update",
        data=metric.model_dump(),
        period_start=start_time,
        period_end=end_time,
    )


@router.get("/conflicting-report-rate", response_model=SingleMetricResponse)
async def get_conflicting_report_rate(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> SingleMetricResponse:
    """Get conflicting report rate metric.

    Measures rate of conflicts detected in clusters.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Conflicting report rate metric data
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    metric = await metrics_service.compute_conflicting_report_rate(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return SingleMetricResponse(
        metric_type="conflicting_report_rate",
        data=metric.model_dump(),
        period_start=start_time,
        period_end=end_time,
    )


@router.get("/moderator-burden", response_model=SingleMetricResponse)
async def get_moderator_burden(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> SingleMetricResponse:
    """Get moderator burden metric.

    Measures facilitator workload and actions.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Moderator burden metric data
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    metric = await metrics_service.compute_moderator_burden(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return SingleMetricResponse(
        metric_type="moderator_burden",
        data=metric.model_dump(),
        period_start=start_time,
        period_end=end_time,
    )


@router.get("/provenance-coverage", response_model=SingleMetricResponse)
async def get_provenance_coverage(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> SingleMetricResponse:
    """Get provenance coverage metric.

    Measures citation coverage in published COP updates.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Provenance coverage metric data
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    metric = await metrics_service.compute_provenance_coverage(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return SingleMetricResponse(
        metric_type="provenance_coverage",
        data=metric.model_dump(),
        period_start=start_time,
        period_end=end_time,
    )


@router.get("/readiness-distribution", response_model=SingleMetricResponse)
async def get_readiness_distribution(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> SingleMetricResponse:
    """Get readiness distribution metric.

    Measures distribution of COP candidates across readiness states.

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Readiness distribution metric data
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    metric = await metrics_service.compute_readiness_distribution(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    return SingleMetricResponse(
        metric_type="readiness_distribution",
        data=metric.model_dump(),
        period_start=start_time,
        period_end=end_time,
    )


@router.get("/export")
async def export_metrics(
    user: CurrentUser,
    _: None = RequireViewMetrics,
    workspace_id: str = Query(..., description="Slack workspace ID"),
    format: MetricsExportFormat = Query(
        default=MetricsExportFormat.JSON,
        description="Export format (json or csv)",
    ),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    metrics_service: MetricsService = Depends(get_metrics_service_dependency),
) -> Response:
    """Export metrics in JSON or CSV format (FR-METRICS-002).

    Args:
        user: Current authenticated user
        workspace_id: Slack workspace ID
        format: Export format (json or csv)
        start_time: Period start
        end_time: Period end
        metrics_service: Metrics service

    Returns:
        Response with exported metrics
    """
    now = datetime.utcnow()
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))

    snapshot = await metrics_service.compute_metrics_snapshot(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
    )

    if format == MetricsExportFormat.JSON:
        return Response(
            content=snapshot.model_dump_json(indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="metrics_{workspace_id}_{start_time.date()}_{end_time.date()}.json"'
            },
        )

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Metric",
        "Category",
        "Value",
        "Unit",
        "Period Start",
        "Period End",
    ])

    # Time to validated update
    ttv = snapshot.time_to_validated_update
    writer.writerow(["time_to_validated_update", "average", ttv.average_seconds, "seconds", start_time, end_time])
    writer.writerow(["time_to_validated_update", "median", ttv.median_seconds, "seconds", start_time, end_time])
    writer.writerow(["time_to_validated_update", "min", ttv.min_seconds, "seconds", start_time, end_time])
    writer.writerow(["time_to_validated_update", "max", ttv.max_seconds, "seconds", start_time, end_time])
    writer.writerow(["time_to_validated_update", "p90", ttv.p90_seconds, "seconds", start_time, end_time])
    writer.writerow(["time_to_validated_update", "sample_count", ttv.sample_count, "count", start_time, end_time])

    # Conflicting report rate
    crr = snapshot.conflicting_report_rate
    writer.writerow(["conflicting_report_rate", "total_clusters", crr.total_clusters, "count", start_time, end_time])
    writer.writerow(["conflicting_report_rate", "clusters_with_conflicts", crr.clusters_with_conflicts, "count", start_time, end_time])
    writer.writerow(["conflicting_report_rate", "conflict_rate", crr.conflict_rate, "percent", start_time, end_time])
    writer.writerow(["conflicting_report_rate", "total_conflicts", crr.total_conflicts_detected, "count", start_time, end_time])
    writer.writerow(["conflicting_report_rate", "conflicts_resolved", crr.conflicts_resolved, "count", start_time, end_time])
    writer.writerow(["conflicting_report_rate", "resolution_rate", crr.resolution_rate, "percent", start_time, end_time])

    # Moderator burden
    mb = snapshot.moderator_burden
    writer.writerow(["moderator_burden", "total_actions", mb.total_facilitator_actions, "count", start_time, end_time])
    writer.writerow(["moderator_burden", "actions_per_update", mb.actions_per_cop_update, "ratio", start_time, end_time])
    writer.writerow(["moderator_burden", "unique_facilitators", mb.unique_facilitators_active, "count", start_time, end_time])
    writer.writerow(["moderator_burden", "high_stakes_overrides", mb.high_stakes_overrides, "count", start_time, end_time])
    writer.writerow(["moderator_burden", "edits_to_ai_drafts", mb.edits_to_ai_drafts, "count", start_time, end_time])

    # Provenance coverage
    pc = snapshot.provenance_coverage
    writer.writerow(["provenance_coverage", "total_line_items", pc.total_published_line_items, "count", start_time, end_time])
    writer.writerow(["provenance_coverage", "items_with_citations", pc.line_items_with_citations, "count", start_time, end_time])
    writer.writerow(["provenance_coverage", "coverage_rate", pc.coverage_rate, "percent", start_time, end_time])
    writer.writerow(["provenance_coverage", "avg_citations_per_item", pc.average_citations_per_item, "ratio", start_time, end_time])

    # Readiness distribution
    rd = snapshot.readiness_distribution
    writer.writerow(["readiness_distribution", "total_candidates", rd.total_candidates, "count", start_time, end_time])
    writer.writerow(["readiness_distribution", "in_review_count", rd.in_review_count, "count", start_time, end_time])
    writer.writerow(["readiness_distribution", "verified_count", rd.verified_count, "count", start_time, end_time])
    writer.writerow(["readiness_distribution", "blocked_count", rd.blocked_count, "count", start_time, end_time])
    writer.writerow(["readiness_distribution", "in_review_percentage", rd.in_review_percentage, "percent", start_time, end_time])
    writer.writerow(["readiness_distribution", "verified_percentage", rd.verified_percentage, "percent", start_time, end_time])
    writer.writerow(["readiness_distribution", "blocked_percentage", rd.blocked_percentage, "percent", start_time, end_time])

    csv_content = output.getvalue()
    output.close()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="metrics_{workspace_id}_{start_time.date()}_{end_time.date()}.csv"'
        },
    )
