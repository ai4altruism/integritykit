"""Audit log API routes.

Implements:
- FR-AUD-001: Audit log access for compliance and abuse detection
- FR-ROLE-003: Role change audit queries
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from integritykit.api.dependencies import (
    CurrentUser,
    RequireViewAudit,
)
from integritykit.models.audit import (
    AuditActionType,
    AuditLogEntry,
    AuditLogResponse,
    AuditTargetType,
)
from integritykit.services.audit import AuditRepository, get_audit_repository

router = APIRouter(prefix="/audit", tags=["Audit"])


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class AuditListResponse(BaseModel):
    """Response for list audit entries endpoint."""

    data: list[AuditLogResponse]
    meta: PaginationMeta


@router.get("", response_model=AuditListResponse)
async def list_audit_entries(
    user: CurrentUser,
    _: None = RequireViewAudit,
    action_type: Optional[AuditActionType] = Query(
        default=None, description="Filter by action type"
    ),
    target_entity_type: Optional[AuditTargetType] = Query(
        default=None, description="Filter by entity type"
    ),
    start_time: Optional[datetime] = Query(
        default=None, description="Filter entries after this time"
    ),
    end_time: Optional[datetime] = Query(
        default=None, description="Filter entries before this time"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditListResponse:
    """List audit log entries.

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        action_type: Filter by action type (optional)
        target_entity_type: Filter by entity type (optional)
        start_time: Filter entries after this time (optional)
        end_time: Filter entries before this time (optional)
        page: Page number
        per_page: Items per page
        audit_repo: Audit repository

    Returns:
        List of audit entries with pagination
    """
    offset = (page - 1) * per_page

    entries = await audit_repo.list_all(
        action_type=action_type,
        target_entity_type=target_entity_type,
        start_time=start_time,
        end_time=end_time,
        limit=per_page,
        offset=offset,
    )

    total = await audit_repo.count(
        action_type=action_type,
        target_entity_type=target_entity_type,
        start_time=start_time,
        end_time=end_time,
    )

    total_pages = (total + per_page - 1) // per_page

    return AuditListResponse(
        data=[AuditLogResponse.from_entry(e) for e in entries],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/role-changes", response_model=AuditListResponse)
async def list_role_changes(
    user: CurrentUser,
    _: None = RequireViewAudit,
    target_user_id: Optional[str] = Query(
        default=None, description="Filter by target user ID"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditListResponse:
    """List role change audit entries (FR-ROLE-003).

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        target_user_id: Filter by target user (optional)
        page: Page number
        per_page: Items per page
        audit_repo: Audit repository

    Returns:
        List of role change audit entries
    """
    offset = (page - 1) * per_page

    target_id = None
    if target_user_id:
        try:
            target_id = ObjectId(target_user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format",
            )

    entries = await audit_repo.list_role_changes(
        target_user_id=target_id,
        limit=per_page,
        offset=offset,
    )

    # Count total (approximate - use action type filter)
    total = await audit_repo.count(
        action_type=AuditActionType.USER_ROLE_CHANGE,
    )

    total_pages = (total + per_page - 1) // per_page

    return AuditListResponse(
        data=[AuditLogResponse.from_entry(e) for e in entries],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/flagged", response_model=AuditListResponse)
async def list_flagged_entries(
    user: CurrentUser,
    _: None = RequireViewAudit,
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditListResponse:
    """List flagged audit entries for abuse detection (NFR-ABUSE-001).

    Requires facilitator or workspace_admin role.

    Args:
        user: Current authenticated user
        page: Page number
        per_page: Items per page
        audit_repo: Audit repository

    Returns:
        List of flagged audit entries
    """
    offset = (page - 1) * per_page

    entries = await audit_repo.list_flagged(
        limit=per_page,
        offset=offset,
    )

    # Simple count - flagged entries are typically few
    total = len(entries)
    if len(entries) == per_page:
        # Might be more entries, estimate
        total = per_page * 2

    total_pages = (total + per_page - 1) // per_page

    return AuditListResponse(
        data=[AuditLogResponse.from_entry(e) for e in entries],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/entity/{entity_type}/{entity_id}", response_model=AuditListResponse)
async def list_entity_audit_trail(
    entity_type: AuditTargetType,
    entity_id: str,
    user: CurrentUser,
    _: None = RequireViewAudit,
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditListResponse:
    """List audit trail for a specific entity.

    Requires facilitator or workspace_admin role.

    Args:
        entity_type: Type of entity
        entity_id: Entity ID
        user: Current authenticated user
        page: Page number
        per_page: Items per page
        audit_repo: Audit repository

    Returns:
        List of audit entries for the entity
    """
    try:
        oid = ObjectId(entity_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entity ID format",
        )

    offset = (page - 1) * per_page

    entries = await audit_repo.list_by_entity(
        entity_type=entity_type,
        entity_id=oid,
        limit=per_page,
        offset=offset,
    )

    total = len(entries)
    if len(entries) == per_page:
        total = per_page * 2

    total_pages = (total + per_page - 1) // per_page

    return AuditListResponse(
        data=[AuditLogResponse.from_entry(e) for e in entries],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{entry_id}", response_model=dict)
async def get_audit_entry(
    entry_id: str,
    user: CurrentUser,
    _: None = RequireViewAudit,
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> dict:
    """Get a specific audit log entry.

    Requires facilitator or workspace_admin role.

    Args:
        entry_id: Audit entry ID
        user: Current authenticated user
        audit_repo: Audit repository

    Returns:
        Audit entry details
    """
    try:
        oid = ObjectId(entry_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entry ID format",
        )

    entry = await audit_repo.get_by_id(oid)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit entry not found",
        )

    return {
        "data": AuditLogResponse.from_entry(entry).model_dump(),
    }
