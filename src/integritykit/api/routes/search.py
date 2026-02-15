"""Facilitator search API routes.

Implements:
- FR-SEARCH-001: Searchable index with role-based access
"""

from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequireSearch,
)
from integritykit.services.search import SearchService, get_search_service

router = APIRouter(prefix="/search", tags=["Search"])


class SearchResultResponse(BaseModel):
    """Response for a single search result."""

    type: str
    id: str
    content: str
    preview: str
    relevance_score: float
    slack_permalink: Optional[str] = None
    cluster_ids: list[str]
    cluster_topics: list[str]
    cop_candidate_id: Optional[str] = None
    cop_candidate_state: Optional[str] = None
    channel_id: Optional[str] = None
    created_at: Optional[str] = None


class SearchCountResponse(BaseModel):
    """Response for search result counts."""

    signals: int
    clusters: int
    total: int


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class SearchListResponse(BaseModel):
    """Response for search list endpoint."""

    data: list[SearchResultResponse]
    counts: SearchCountResponse
    meta: PaginationMeta


@router.get("", response_model=SearchListResponse)
async def search(
    user: CurrentUser,
    _: None = RequireSearch,
    q: Optional[str] = Query(
        default=None,
        description="Search query (keyword search)",
        min_length=2,
    ),
    channel_id: Optional[str] = Query(
        default=None,
        description="Filter by Slack channel ID",
    ),
    start_time: Optional[datetime] = Query(
        default=None,
        description="Filter results after this time (ISO format)",
    ),
    end_time: Optional[datetime] = Query(
        default=None,
        description="Filter results before this time (ISO format)",
    ),
    include_types: list[Literal["signal", "cluster", "cop_candidate"]] = Query(
        default=["signal", "cluster"],
        description="Result types to include",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Results per page"),
    search_service: SearchService = Depends(get_search_service),
) -> SearchListResponse:
    """Search signals, clusters, and COP candidates (FR-SEARCH-001).

    Provides full-text search across all ingested content. Accessible only
    to facilitators and verifiers. Results include message previews and
    Slack permalinks.

    Args:
        user: Current authenticated user
        q: Search query (keywords)
        channel_id: Filter by Slack channel
        start_time: Filter results after this time
        end_time: Filter results before this time
        include_types: Types of results to include
        page: Page number
        per_page: Results per page
        search_service: Search service

    Returns:
        Search results with pagination
    """
    offset = (page - 1) * per_page

    results = await search_service.search(
        workspace_id=user.slack_team_id,
        query=q,
        channel_id=channel_id,
        start_time=start_time,
        end_time=end_time,
        include_signals="signal" in include_types,
        include_clusters="cluster" in include_types,
        include_candidates="cop_candidate" in include_types,
        limit=per_page,
        offset=offset,
    )

    # Get total counts
    counts = await search_service.count_results(
        workspace_id=user.slack_team_id,
        query=q,
        channel_id=channel_id,
        start_time=start_time,
        end_time=end_time,
    )

    total = counts["total"]
    total_pages = (total + per_page - 1) // per_page

    return SearchListResponse(
        data=[
            SearchResultResponse(
                type=r.result_type,
                id=str(r.entity_id),
                content=r.content,
                preview=r.preview,
                relevance_score=r.relevance_score,
                slack_permalink=r.slack_permalink,
                cluster_ids=[str(cid) for cid in r.cluster_ids],
                cluster_topics=r.cluster_topics,
                cop_candidate_id=str(r.cop_candidate_id) if r.cop_candidate_id else None,
                cop_candidate_state=r.cop_candidate_state,
                channel_id=r.channel_id,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in results
        ],
        counts=SearchCountResponse(**counts),
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/counts", response_model=dict)
async def search_counts(
    user: CurrentUser,
    _: None = RequireSearch,
    q: Optional[str] = Query(
        default=None,
        description="Search query",
        min_length=2,
    ),
    channel_id: Optional[str] = Query(
        default=None,
        description="Filter by Slack channel ID",
    ),
    start_time: Optional[datetime] = Query(
        default=None,
        description="Filter results after this time",
    ),
    end_time: Optional[datetime] = Query(
        default=None,
        description="Filter results before this time",
    ),
    search_service: SearchService = Depends(get_search_service),
) -> dict:
    """Get search result counts by type.

    Quick endpoint to get counts without fetching full results.

    Args:
        user: Current authenticated user
        q: Search query
        channel_id: Filter by channel
        start_time: Filter after this time
        end_time: Filter before this time
        search_service: Search service

    Returns:
        Counts by result type
    """
    counts = await search_service.count_results(
        workspace_id=user.slack_team_id,
        query=q,
        channel_id=channel_id,
        start_time=start_time,
        end_time=end_time,
    )

    return {"data": SearchCountResponse(**counts).model_dump()}


@router.get("/channels", response_model=dict)
async def list_searchable_channels(
    user: CurrentUser,
    _: None = RequireSearch,
    search_service: SearchService = Depends(get_search_service),
) -> dict:
    """List channels with signals available for search.

    Returns channels in the workspace that have ingested signals,
    allowing the UI to populate channel filter dropdown.

    Args:
        user: Current authenticated user
        search_service: Search service

    Returns:
        List of channels with signal counts
    """
    collection = search_service.signal_repo.collection

    # Aggregate to get unique channels with counts
    pipeline = [
        {"$match": {"slack_workspace_id": user.slack_team_id}},
        {
            "$group": {
                "_id": "$slack_channel_id",
                "signal_count": {"$sum": 1},
                "latest_signal": {"$max": "$created_at"},
            }
        },
        {"$sort": {"signal_count": -1}},
    ]

    channels = []
    async for doc in collection.aggregate(pipeline):
        channels.append(
            {
                "channel_id": doc["_id"],
                "signal_count": doc["signal_count"],
                "latest_signal": doc["latest_signal"].isoformat()
                if doc.get("latest_signal")
                else None,
            }
        )

    return {"data": channels}
