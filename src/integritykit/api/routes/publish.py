"""API routes for COP update publishing workflow.

Implements:
- FR-COP-PUB-001: Human-approved COP publishing
- NFR-TRANSPARENCY-001: Full audit trail
"""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequirePublishCOP,
    RequireViewBacklog,
)
from integritykit.models.cop_update import COPUpdate, COPUpdateResponse, COPUpdateStatus
from integritykit.services.publish import (
    COPUpdateRepository,
    PublishService,
    get_clarification_template,
)

router = APIRouter(prefix="/publish", tags=["COP Publishing"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateDraftRequest(BaseModel):
    """Request to create a COP update draft."""

    candidate_ids: list[str] = Field(
        ...,
        description="IDs of COP candidates to include",
        min_length=1,
    )
    title: Optional[str] = Field(
        default=None,
        description="Custom title (auto-generated if not provided)",
    )


class EditLineItemRequest(BaseModel):
    """Request to edit a line item."""

    item_index: int = Field(
        ...,
        description="Index of the line item to edit",
        ge=0,
    )
    new_text: str = Field(
        ...,
        description="New text for the line item",
        min_length=1,
    )


class ApproveRequest(BaseModel):
    """Request to approve an update for publishing."""

    notes: Optional[str] = Field(
        default=None,
        description="Approval notes",
    )


class PublishRequest(BaseModel):
    """Request to publish an approved update."""

    channel_id: str = Field(
        ...,
        description="Slack channel ID to publish to",
    )


class ClarificationRequest(BaseModel):
    """Request to get a clarification template."""

    template_type: str = Field(
        ...,
        description="Type: location, time, source, status, impact, general",
    )
    topic: str = Field(
        ...,
        description="Topic to insert into template",
    )


class DraftPreviewResponse(BaseModel):
    """Response containing draft preview."""

    update_id: str
    title: str
    status: str
    markdown: str
    blocks: list[dict]
    verified_count: int
    in_review_count: int
    open_questions_count: int


class LineItemResponse(BaseModel):
    """Response for a line item."""

    index: int
    candidate_id: str
    section: str
    status_label: str
    text: str
    citations: list[str]
    was_edited: bool


class UpdateDetailResponse(BaseModel):
    """Detailed response for a COP update."""

    id: str
    workspace_id: str
    update_number: int
    title: str
    status: str
    line_items: list[LineItemResponse]
    open_questions: list[str]
    created_by: str
    created_at: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    published_at: Optional[str] = None
    slack_permalink: Optional[str] = None
    edit_count: int


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/drafts", response_model=COPUpdateResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    request: CreateDraftRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> COPUpdateResponse:
    """Create a COP update draft from selected candidates.

    Requires VIEW_BACKLOG permission.

    Args:
        request: Draft creation request
        user: Current authenticated user

    Returns:
        Created draft update
    """
    try:
        candidate_ids = [ObjectId(cid) for cid in request.candidate_ids]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    publish_service = PublishService()

    try:
        update = await publish_service.create_draft_from_candidates(
            workspace_id=user.slack_team_id,
            candidate_ids=candidate_ids,
            user=user,
            title=request.title,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return COPUpdateResponse.from_model(update)


@router.get("/drafts", response_model=list[COPUpdateResponse])
async def list_drafts(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    status_filter: Optional[COPUpdateStatus] = Query(
        default=None,
        description="Filter by status",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[COPUpdateResponse]:
    """List COP update drafts for the workspace.

    Requires VIEW_BACKLOG permission.

    Args:
        user: Current authenticated user
        status_filter: Optional status filter
        limit: Maximum results
        offset: Results to skip

    Returns:
        List of COP updates
    """
    update_repo = COPUpdateRepository()

    updates = await update_repo.list_by_workspace(
        workspace_id=user.slack_team_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    return [COPUpdateResponse.from_model(u) for u in updates]


@router.get("/drafts/{update_id}", response_model=UpdateDetailResponse)
async def get_draft(
    update_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> UpdateDetailResponse:
    """Get detailed COP update draft.

    Requires VIEW_BACKLOG permission.

    Args:
        update_id: Update ID
        user: Current authenticated user

    Returns:
        Detailed update information
    """
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update ID format",
        )

    update_repo = COPUpdateRepository()
    update = await update_repo.get_by_id(oid)

    if not update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update not found",
        )

    if update.workspace_id != user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Update belongs to different workspace",
        )

    line_items = [
        LineItemResponse(
            index=i,
            candidate_id=str(li.candidate_id),
            section=li.section,
            status_label=li.status_label,
            text=li.text,
            citations=li.citations,
            was_edited=li.was_edited,
        )
        for i, li in enumerate(update.line_items)
    ]

    return UpdateDetailResponse(
        id=str(update.id),
        workspace_id=update.workspace_id,
        update_number=update.update_number,
        title=update.title,
        status=update.status.value,
        line_items=line_items,
        open_questions=update.open_questions,
        created_by=str(update.created_by),
        created_at=update.created_at.isoformat(),
        approved_by=str(update.approved_by) if update.approved_by else None,
        approved_at=update.approved_at.isoformat() if update.approved_at else None,
        published_at=update.published_at.isoformat() if update.published_at else None,
        slack_permalink=update.slack_permalink,
        edit_count=update.edit_count,
    )


@router.get("/drafts/{update_id}/preview", response_model=DraftPreviewResponse)
async def preview_draft(
    update_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> DraftPreviewResponse:
    """Preview how a draft will appear when published.

    Requires VIEW_BACKLOG permission.

    Args:
        update_id: Update ID
        user: Current authenticated user

    Returns:
        Preview with markdown and Slack blocks
    """
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update ID format",
        )

    publish_service = PublishService()

    try:
        preview = await publish_service.get_draft_preview(oid)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    update = preview["update"]

    verified = [li for li in update.line_items if li.section == "verified"]
    in_review = [li for li in update.line_items if li.section == "in_review"]

    return DraftPreviewResponse(
        update_id=str(update.id),
        title=update.title,
        status=update.status.value,
        markdown=preview["markdown"],
        blocks=preview["blocks"],
        verified_count=len(verified),
        in_review_count=len(in_review),
        open_questions_count=len(update.open_questions),
    )


@router.patch("/drafts/{update_id}/line-items", response_model=COPUpdateResponse)
async def edit_line_item(
    update_id: str,
    request: EditLineItemRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> COPUpdateResponse:
    """Edit a line item in a draft.

    Requires VIEW_BACKLOG permission.

    Args:
        update_id: Update ID
        request: Edit request
        user: Current authenticated user

    Returns:
        Updated draft
    """
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update ID format",
        )

    publish_service = PublishService()

    try:
        update = await publish_service.edit_line_item(
            update_id=oid,
            item_index=request.item_index,
            new_text=request.new_text,
            user=user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return COPUpdateResponse.from_model(update)


@router.post("/drafts/{update_id}/approve", response_model=COPUpdateResponse)
async def approve_draft(
    update_id: str,
    request: ApproveRequest,
    user: CurrentUser,
    _: None = RequirePublishCOP,
) -> COPUpdateResponse:
    """Approve a draft for publishing (FR-COP-PUB-001).

    This is the required human approval step before a COP update
    can be published to Slack.

    Requires PUBLISH_COP permission.

    Args:
        update_id: Update ID
        request: Approval request
        user: Current authenticated user

    Returns:
        Approved update
    """
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update ID format",
        )

    publish_service = PublishService()

    try:
        update = await publish_service.approve(
            update_id=oid,
            user=user,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return COPUpdateResponse.from_model(update)


@router.post("/drafts/{update_id}/publish", response_model=COPUpdateResponse)
async def publish_to_slack(
    update_id: str,
    request: PublishRequest,
    user: CurrentUser,
    _: None = RequirePublishCOP,
) -> COPUpdateResponse:
    """Publish an approved update to Slack (FR-COP-PUB-001).

    The update MUST be approved before it can be published.
    This ensures no automated publishing without human approval.

    Requires PUBLISH_COP permission.

    Args:
        update_id: Update ID
        request: Publish request
        user: Current authenticated user

    Returns:
        Published update with Slack permalink
    """
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update ID format",
        )

    # Get Slack client from app context
    # In production, this would come from the app's Slack integration
    from integritykit.config import settings

    if not settings.slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack integration not configured",
        )

    from slack_sdk.web.async_client import AsyncWebClient

    slack_client = AsyncWebClient(token=settings.slack_bot_token)

    publish_service = PublishService(slack_client=slack_client)

    try:
        update = await publish_service.publish_to_slack(
            update_id=oid,
            channel_id=request.channel_id,
            user=user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return COPUpdateResponse.from_model(update)


@router.get("/history", response_model=list[COPUpdateResponse])
async def get_publish_history(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[COPUpdateResponse]:
    """Get published COP update history.

    Requires VIEW_BACKLOG permission.

    Args:
        user: Current authenticated user
        limit: Maximum results
        offset: Results to skip

    Returns:
        List of published updates
    """
    update_repo = COPUpdateRepository()

    updates = await update_repo.list_by_workspace(
        workspace_id=user.slack_team_id,
        status=COPUpdateStatus.PUBLISHED,
        limit=limit,
        offset=offset,
    )

    return [COPUpdateResponse.from_model(u) for u in updates]


@router.get("/latest", response_model=Optional[COPUpdateResponse])
async def get_latest_published(
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> Optional[COPUpdateResponse]:
    """Get the most recently published COP update.

    Requires VIEW_BACKLOG permission.

    Args:
        user: Current authenticated user

    Returns:
        Latest published update or null
    """
    update_repo = COPUpdateRepository()

    update = await update_repo.get_latest_published(
        workspace_id=user.slack_team_id,
    )

    if update:
        return COPUpdateResponse.from_model(update)
    return None


# ============================================================================
# Clarification Templates (S4-4)
# ============================================================================


@router.post("/clarification-template", response_model=dict)
async def get_clarification(
    request: ClarificationRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> dict:
    """Get a clarification request template.

    Facilitators can use these templates to request additional
    information from message authors.

    Requires VIEW_BACKLOG permission.

    Args:
        request: Template request
        user: Current authenticated user

    Returns:
        Template text
    """
    valid_types = ["location", "time", "source", "status", "impact", "general"]

    if request.template_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template type. Must be one of: {', '.join(valid_types)}",
        )

    template = get_clarification_template(
        template_type=request.template_type,
        topic=request.topic,
    )

    return {
        "template_type": request.template_type,
        "topic": request.topic,
        "message": template,
    }


@router.get("/clarification-templates", response_model=dict)
async def list_clarification_templates(
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> dict:
    """List available clarification request templates.

    Requires VIEW_BACKLOG permission.

    Args:
        user: Current authenticated user

    Returns:
        Dictionary of template types and descriptions
    """
    return {
        "templates": {
            "location": "Request specific location details",
            "time": "Request timing clarification",
            "source": "Request source/verification info",
            "status": "Request current status update",
            "impact": "Request impact assessment",
            "general": "General follow-up request",
        },
        "usage": "Use POST /publish/clarification-template with template_type and topic",
    }
