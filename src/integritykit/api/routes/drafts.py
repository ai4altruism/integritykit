"""API routes for COP draft generation.

Implements:
- FR-COPDRAFT-001: Generate COP line items
- FR-COPDRAFT-002: Assemble COP drafts by section
- FR-COP-WORDING-001: Wording guidance
"""

from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequirePublishCOP,
    RequireViewBacklog,
)
from integritykit.models.cop_candidate import COPCandidate
from integritykit.models.user import User
from integritykit.services.database import COPCandidateRepository, get_collection
from integritykit.services.draft import COPDraft, COPLineItem, COPSection, DraftService

router = APIRouter(prefix="/drafts", tags=["COP Drafts"])


# ============================================================================
# Response Models
# ============================================================================


class LineItemResponse(BaseModel):
    """Response model for a COP line item."""

    candidate_id: str
    status_label: str
    line_item_text: str
    citations: list[str]
    wording_style: str
    section: str
    next_verification_step: Optional[str] = None
    recheck_time: Optional[str] = None
    generated_at: str


class DraftResponse(BaseModel):
    """Response model for a COP draft."""

    draft_id: str
    workspace_id: str
    title: str
    generated_at: str
    verified_count: int
    in_review_count: int
    disproven_count: int
    open_questions_count: int
    verified_items: list[LineItemResponse]
    in_review_items: list[LineItemResponse]
    disproven_items: list[LineItemResponse]
    open_questions: list[str]
    metadata: dict


class DraftMarkdownResponse(BaseModel):
    """Response model for draft in Markdown format."""

    draft_id: str
    title: str
    markdown: str


class DraftSlackBlocksResponse(BaseModel):
    """Response model for draft in Slack Block Kit format."""

    draft_id: str
    title: str
    blocks: list[dict]


class GenerateDraftRequest(BaseModel):
    """Request model for generating a draft."""

    candidate_ids: Optional[list[str]] = Field(
        default=None,
        description="Specific candidate IDs to include (default: all publishable)",
    )
    title: Optional[str] = Field(
        default=None,
        description="Custom title for the draft",
    )
    include_in_review: bool = Field(
        default=True,
        description="Include In-Review items in draft",
    )
    include_open_questions: bool = Field(
        default=True,
        description="Include Open Questions section",
    )


# ============================================================================
# Helper Functions
# ============================================================================


def _line_item_to_response(item: COPLineItem) -> LineItemResponse:
    """Convert COPLineItem to API response."""
    return LineItemResponse(
        candidate_id=item.candidate_id,
        status_label=item.status_label,
        line_item_text=item.line_item_text,
        citations=item.citations,
        wording_style=item.wording_style.value,
        section=item.section.value,
        next_verification_step=item.next_verification_step,
        recheck_time=item.recheck_time,
        generated_at=item.generated_at.isoformat(),
    )


def _draft_to_response(draft: COPDraft) -> DraftResponse:
    """Convert COPDraft to API response."""
    return DraftResponse(
        draft_id=draft.draft_id,
        workspace_id=draft.workspace_id,
        title=draft.title,
        generated_at=draft.generated_at.isoformat(),
        verified_count=len(draft.verified_items),
        in_review_count=len(draft.in_review_items),
        disproven_count=len(draft.disproven_items),
        open_questions_count=len(draft.open_questions),
        verified_items=[_line_item_to_response(i) for i in draft.verified_items],
        in_review_items=[_line_item_to_response(i) for i in draft.in_review_items],
        disproven_items=[_line_item_to_response(i) for i in draft.disproven_items],
        open_questions=draft.open_questions,
        metadata=draft.metadata,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/{candidate_id}/line-item", response_model=LineItemResponse)
async def generate_line_item(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> LineItemResponse:
    """Generate a COP line item for a single candidate.

    Applies wording guidance based on verification status:
    - Verified items: Direct, factual phrasing
    - In-Review items: Hedged, uncertain phrasing

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    draft_service = DraftService(use_llm=False)
    line_item = await draft_service.generate_line_item(candidate)

    return _line_item_to_response(line_item)


@router.post("/generate", response_model=DraftResponse)
async def generate_draft(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    request: Optional[GenerateDraftRequest] = None,
) -> DraftResponse:
    """Generate a complete COP draft from candidates.

    Groups items by section:
    - Verified Updates
    - In Review (Unconfirmed)
    - Rumor Control / Corrections
    - Open Questions / Gaps

    Requires VIEW_BACKLOG permission.
    """
    workspace_id = user.slack_team_id
    candidate_repo = COPCandidateRepository()

    # Get cluster IDs for workspace
    cluster_collection = get_collection("clusters")
    cluster_ids = []
    async for doc in cluster_collection.find(
        {"workspace_id": workspace_id},
        {"_id": 1},
    ):
        cluster_ids.append(doc["_id"])

    if not cluster_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clusters found for workspace",
        )

    # Get candidates
    if request and request.candidate_ids:
        # Specific candidates requested
        candidates = []
        for cid in request.candidate_ids:
            try:
                obj_id = ObjectId(cid)
                candidate = await candidate_repo.get_by_id(obj_id)
                if candidate:
                    candidates.append(candidate)
            except Exception:
                pass
    else:
        # Get all publishable candidates
        candidates = await candidate_repo.list_by_workspace(
            cluster_ids=cluster_ids,
            limit=100,
        )

        # Filter to verified and in-review
        if request and not request.include_in_review:
            candidates = [
                c for c in candidates
                if c.readiness_state.value == "verified"
            ]

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidates found for draft generation",
        )

    # Generate draft
    draft_service = DraftService(use_llm=False)
    draft = await draft_service.generate_draft(
        workspace_id=workspace_id,
        candidates=candidates,
        title=request.title if request else None,
        include_open_questions=request.include_open_questions if request else True,
    )

    return _draft_to_response(draft)


@router.post("/generate/markdown", response_model=DraftMarkdownResponse)
async def generate_draft_markdown(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    request: Optional[GenerateDraftRequest] = None,
) -> DraftMarkdownResponse:
    """Generate a COP draft in Markdown format.

    Useful for copying to external systems or documentation.

    Requires VIEW_BACKLOG permission.
    """
    # Reuse generate_draft logic
    draft_response = await generate_draft(user, _, request)

    # Reconstruct draft for markdown conversion
    workspace_id = user.slack_team_id
    candidate_repo = COPCandidateRepository()

    cluster_collection = get_collection("clusters")
    cluster_ids = []
    async for doc in cluster_collection.find(
        {"workspace_id": workspace_id},
        {"_id": 1},
    ):
        cluster_ids.append(doc["_id"])

    if request and request.candidate_ids:
        candidates = []
        for cid in request.candidate_ids:
            try:
                obj_id = ObjectId(cid)
                candidate = await candidate_repo.get_by_id(obj_id)
                if candidate:
                    candidates.append(candidate)
            except Exception:
                pass
    else:
        candidates = await candidate_repo.list_by_workspace(
            cluster_ids=cluster_ids,
            limit=100,
        )

    draft_service = DraftService(use_llm=False)
    draft = await draft_service.generate_draft(
        workspace_id=workspace_id,
        candidates=candidates,
        title=request.title if request else None,
        include_open_questions=request.include_open_questions if request else True,
    )

    return DraftMarkdownResponse(
        draft_id=draft.draft_id,
        title=draft.title,
        markdown=draft.to_markdown(),
    )


@router.post("/generate/slack-blocks", response_model=DraftSlackBlocksResponse)
async def generate_draft_slack_blocks(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    request: Optional[GenerateDraftRequest] = None,
) -> DraftSlackBlocksResponse:
    """Generate a COP draft as Slack Block Kit blocks.

    Useful for posting to Slack channels or modals.

    Requires VIEW_BACKLOG permission.
    """
    workspace_id = user.slack_team_id
    candidate_repo = COPCandidateRepository()

    cluster_collection = get_collection("clusters")
    cluster_ids = []
    async for doc in cluster_collection.find(
        {"workspace_id": workspace_id},
        {"_id": 1},
    ):
        cluster_ids.append(doc["_id"])

    if request and request.candidate_ids:
        candidates = []
        for cid in request.candidate_ids:
            try:
                obj_id = ObjectId(cid)
                candidate = await candidate_repo.get_by_id(obj_id)
                if candidate:
                    candidates.append(candidate)
            except Exception:
                pass
    else:
        candidates = await candidate_repo.list_by_workspace(
            cluster_ids=cluster_ids,
            limit=100,
        )

    draft_service = DraftService(use_llm=False)
    draft = await draft_service.generate_draft(
        workspace_id=workspace_id,
        candidates=candidates,
        title=request.title if request else None,
        include_open_questions=request.include_open_questions if request else True,
    )

    return DraftSlackBlocksResponse(
        draft_id=draft.draft_id,
        title=draft.title,
        blocks=draft.to_slack_blocks(),
    )


@router.get("/preview/{candidate_id}", response_model=LineItemResponse)
async def preview_line_item(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
    force_verified: bool = Query(
        False, description="Preview as if verified"
    ),
    force_in_review: bool = Query(
        False, description="Preview as if in review"
    ),
) -> LineItemResponse:
    """Preview a line item with different wording styles.

    Allows facilitators to see how the item would appear
    in different verification states before publishing.

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # Temporarily override readiness state for preview
    from integritykit.models.cop_candidate import ReadinessState

    original_state = candidate.readiness_state

    if force_verified:
        candidate.readiness_state = ReadinessState.VERIFIED
    elif force_in_review:
        candidate.readiness_state = ReadinessState.IN_REVIEW

    draft_service = DraftService(use_llm=False)
    line_item = await draft_service.generate_line_item(candidate)

    # Restore original state
    candidate.readiness_state = original_state

    return _line_item_to_response(line_item)
