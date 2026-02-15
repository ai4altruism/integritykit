"""Private COP backlog API routes.

Implements:
- FR-BACKLOG-001: Private backlog accessible to facilitators
- FR-BACKLOG-002: Support for promote to COP candidate
- NFR-PRIVACY-001: Private facilitator views
"""

from datetime import datetime
from typing import Any, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequirePromoteCluster,
    RequireViewBacklog,
)
from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.services.audit import AuditService, get_audit_service
from integritykit.services.backlog import BacklogService, get_backlog_service

router = APIRouter(prefix="/backlog", tags=["Backlog"])


class PriorityScoresResponse(BaseModel):
    """Priority scores for a backlog item."""

    urgency: float
    urgency_reasoning: Optional[str] = None
    impact: float
    impact_reasoning: Optional[str] = None
    risk: float
    risk_reasoning: Optional[str] = None
    composite_score: float


class SampleSignalResponse(BaseModel):
    """Sample signal for backlog item preview."""

    id: str
    content: str
    slack_permalink: str
    created_at: str


class BacklogItemResponse(BaseModel):
    """Response for a single backlog item."""

    id: str
    topic: str
    summary: str
    incident_type: Optional[str] = None
    signal_count: int
    priority_scores: PriorityScoresResponse
    has_conflicts: bool
    conflict_count: int
    unresolved_conflict_count: int
    sample_signals: list[SampleSignalResponse]
    created_at: str
    updated_at: str


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class BacklogListResponse(BaseModel):
    """Response for backlog list endpoint."""

    data: list[BacklogItemResponse]
    meta: PaginationMeta


class BacklogStatsResponse(BaseModel):
    """Response for backlog statistics."""

    total_items: int
    items_with_conflicts: int
    high_priority_items: int


@router.get("", response_model=BacklogListResponse)
async def list_backlog(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    sort_by: Literal["priority", "urgency", "impact", "risk", "updated"] = Query(
        default="priority",
        description="Sort field",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    backlog_service: BacklogService = Depends(get_backlog_service),
) -> BacklogListResponse:
    """List backlog items for the current workspace.

    Returns unpromoted clusters ordered by priority. Accessible only to
    facilitators and verifiers (FR-BACKLOG-001, NFR-PRIVACY-001).

    Args:
        user: Current authenticated user
        sort_by: Sort field (priority, urgency, impact, risk, updated)
        page: Page number
        per_page: Items per page
        backlog_service: Backlog service

    Returns:
        List of backlog items with pagination
    """
    offset = (page - 1) * per_page

    items = await backlog_service.get_backlog(
        workspace_id=user.slack_team_id,
        limit=per_page,
        offset=offset,
        include_signals=True,
        sort_by=sort_by,
    )

    total = await backlog_service.count_backlog_items(
        workspace_id=user.slack_team_id,
    )

    total_pages = (total + per_page - 1) // per_page

    return BacklogListResponse(
        data=[
            BacklogItemResponse(
                id=str(item.id),
                topic=item.topic,
                summary=item.summary,
                incident_type=item.incident_type,
                signal_count=item.signal_count,
                priority_scores=PriorityScoresResponse(
                    urgency=item.priority_scores.urgency,
                    urgency_reasoning=item.priority_scores.urgency_reasoning,
                    impact=item.priority_scores.impact,
                    impact_reasoning=item.priority_scores.impact_reasoning,
                    risk=item.priority_scores.risk,
                    risk_reasoning=item.priority_scores.risk_reasoning,
                    composite_score=item.composite_score,
                ),
                has_conflicts=item.has_conflicts,
                conflict_count=item.conflict_count,
                unresolved_conflict_count=item.unresolved_conflict_count,
                sample_signals=[
                    SampleSignalResponse(
                        id=s["id"],
                        content=s["content"],
                        slack_permalink=s["slack_permalink"],
                        created_at=s["created_at"],
                    )
                    for s in item.to_dict()["sample_signals"]
                ],
                created_at=item.created_at.isoformat(),
                updated_at=item.updated_at.isoformat(),
            )
            for item in items
        ],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/stats", response_model=dict)
async def get_backlog_stats(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    backlog_service: BacklogService = Depends(get_backlog_service),
) -> dict:
    """Get backlog statistics for the current workspace.

    Returns counts of total items, items with conflicts, and high-priority items.

    Args:
        user: Current authenticated user
        backlog_service: Backlog service

    Returns:
        Backlog statistics
    """
    stats = await backlog_service.get_backlog_stats(
        workspace_id=user.slack_team_id,
    )

    return {
        "data": BacklogStatsResponse(**stats).model_dump(),
    }


@router.get("/{cluster_id}", response_model=dict)
async def get_backlog_item(
    cluster_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
    include_all_signals: bool = Query(
        default=False,
        description="Include all signals (vs sample)",
    ),
    backlog_service: BacklogService = Depends(get_backlog_service),
) -> dict:
    """Get a single backlog item by cluster ID.

    Args:
        cluster_id: Cluster ID
        user: Current authenticated user
        include_all_signals: Whether to include all signals
        backlog_service: Backlog service

    Returns:
        Backlog item details

    Raises:
        HTTPException: If cluster not found or already promoted
    """
    try:
        oid = ObjectId(cluster_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cluster ID format",
        )

    item = await backlog_service.get_backlog_item(
        workspace_id=user.slack_team_id,
        cluster_id=oid,
        include_all_signals=include_all_signals,
    )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backlog item not found",
        )

    # Build full response with all signals if requested
    sample_signals = item.to_dict()["sample_signals"]
    if include_all_signals and item.signals:
        sample_signals = [
            {
                "id": str(s.id),
                "content": s.content,
                "slack_permalink": s.slack_permalink,
                "slack_user_id": s.slack_user_id,
                "created_at": s.created_at.isoformat(),
            }
            for s in item.signals
        ]

    response_data = {
        "id": str(item.id),
        "topic": item.topic,
        "summary": item.summary,
        "incident_type": item.incident_type,
        "signal_count": item.signal_count,
        "priority_scores": {
            "urgency": item.priority_scores.urgency,
            "urgency_reasoning": item.priority_scores.urgency_reasoning,
            "impact": item.priority_scores.impact,
            "impact_reasoning": item.priority_scores.impact_reasoning,
            "risk": item.priority_scores.risk,
            "risk_reasoning": item.priority_scores.risk_reasoning,
            "composite_score": item.composite_score,
        },
        "has_conflicts": item.has_conflicts,
        "conflict_count": item.conflict_count,
        "unresolved_conflict_count": item.unresolved_conflict_count,
        "conflicts": [
            {
                "id": c.id,
                "field": c.field,
                "severity": c.severity,
                "description": c.description,
                "resolved": c.resolved,
            }
            for c in item.cluster.conflicts
        ],
        "signals": sample_signals,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

    return {"data": response_data}


class PromoteRequest(BaseModel):
    """Request body for promoting a cluster."""

    justification: Optional[str] = Field(
        default=None,
        description="Reason for promotion",
    )


class COPCandidateResponse(BaseModel):
    """Response for newly created COP candidate."""

    id: str
    cluster_id: str
    readiness_state: str
    risk_tier: str
    fields: dict
    missing_fields: list[str]
    has_conflicts: bool
    recommended_action: Optional[dict] = None
    created_at: str
    created_by: str


@router.post("/{cluster_id}/promote", response_model=dict)
async def promote_cluster(
    cluster_id: str,
    user: CurrentUser,
    _: None = RequirePromoteCluster,
    request_body: Optional[PromoteRequest] = None,
    backlog_service: BacklogService = Depends(get_backlog_service),
    audit_service: AuditService = Depends(get_audit_service),
) -> dict:
    """Promote a cluster from backlog to COP candidate (FR-BACKLOG-002).

    Creates a new COP candidate from the cluster, marking it as promoted
    so it no longer appears in the backlog. The candidate enters the
    verification workflow in "in_review" state.

    Args:
        cluster_id: Cluster ID to promote
        user: Current authenticated user
        request_body: Optional justification
        backlog_service: Backlog service
        audit_service: Audit service

    Returns:
        Created COP candidate details

    Raises:
        HTTPException: If cluster not found, already promoted, or access denied
    """
    try:
        oid = ObjectId(cluster_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cluster ID format",
        )

    try:
        candidate, cluster = await backlog_service.promote_cluster(
            workspace_id=user.slack_team_id,
            cluster_id=oid,
            promoted_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Log the promotion
    await audit_service.log_action(
        actor=user,
        action_type=AuditActionType.COP_CANDIDATE_PROMOTE,
        target_type=AuditTargetType.COP_CANDIDATE,
        target_id=candidate.id,
        changes_before=None,
        changes_after={
            "cluster_id": str(cluster.id),
            "readiness_state": candidate.readiness_state,
            "risk_tier": candidate.risk_tier,
        },
        justification=request_body.justification if request_body else None,
    )

    # Build response
    response_data = COPCandidateResponse(
        id=str(candidate.id),
        cluster_id=str(candidate.cluster_id),
        readiness_state=candidate.readiness_state,
        risk_tier=candidate.risk_tier,
        fields=candidate.fields.model_dump() if candidate.fields else {},
        missing_fields=candidate.missing_fields,
        has_conflicts=candidate.has_unresolved_conflicts,
        recommended_action=candidate.recommended_action.model_dump()
        if candidate.recommended_action
        else None,
        created_at=candidate.created_at.isoformat(),
        created_by=str(candidate.created_by),
    )

    return {"data": response_data.model_dump()}
