"""API routes for integration management (Sprint 8, Task S8-20).

Implements:
- FR-INT-003: External verification source integration
- Task S8-20: Inbound verification source API
"""

from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import CurrentUser
from integritykit.models.external_source import (
    ExternalSource,
    ExternalSourceCreate,
    ExternalSourceUpdate,
    ImportRequest,
    ImportResult,
    TrustLevel,
)
from integritykit.models.user import User, UserRole
from integritykit.services.database import get_collection
from integritykit.services.external_sources import ExternalSourceService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ============================================================================
# Response Models
# ============================================================================


class ExternalSourceResponse(BaseModel):
    """Response model for external source operations."""

    data: ExternalSource


class ExternalSourceListResponse(BaseModel):
    """Response model for external source listing."""

    data: list[ExternalSource]
    meta: dict


class ImportResultResponse(BaseModel):
    """Response model for import operations."""

    data: ImportResult


# ============================================================================
# Dependencies
# ============================================================================


def get_external_source_service() -> ExternalSourceService:
    """Get external source service instance."""
    return ExternalSourceService(
        sources_collection=get_collection("external_sources"),
        imports_collection=get_collection("imported_verifications"),
        candidates_collection=get_collection("cop_candidates"),
    )


def require_workspace_admin(user: CurrentUser) -> User:
    """Require workspace_admin role for integration management.

    Args:
        user: Current authenticated user

    Returns:
        User if authorized

    Raises:
        HTTPException: If user is not workspace_admin
    """
    if user.role != UserRole.WORKSPACE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace admins can manage external sources",
        )
    return user


RequireWorkspaceAdmin = Annotated[User, Depends(require_workspace_admin)]
ExternalSourceServiceDep = Annotated[
    ExternalSourceService, Depends(get_external_source_service)
]


# ============================================================================
# External Source CRUD Endpoints
# ============================================================================


@router.get("/sources", response_model=ExternalSourceListResponse)
async def list_sources(
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
    source_type: Optional[str] = Query(
        default=None, description="Filter by source type"
    ),
    trust_level: Optional[TrustLevel] = Query(
        default=None, description="Filter by trust level"
    ),
    enabled: Optional[bool] = Query(default=None, description="Filter by enabled status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
) -> ExternalSourceListResponse:
    """List configured external verification sources.

    Requires workspace_admin role.

    External sources provide pre-verified data from authoritative systems
    (government APIs, NGO feeds, verified reporter systems). Each source
    has a trust level that determines how imported data is handled:

    - HIGH: Auto-promote to verified candidate (no manual review needed)
    - MEDIUM: Create in-review candidate (requires facilitator review)
    - LOW: Import as signal (requires full verification)

    Args:
        user: Current user (workspace_admin)
        service: External source service
        source_type: Filter by source type (optional)
        trust_level: Filter by trust level (optional)
        enabled: Filter by enabled status (optional)
        page: Page number
        per_page: Items per page

    Returns:
        List of external sources with pagination metadata
    """
    skip = (page - 1) * per_page

    sources = await service.list_sources(
        workspace_id=user.workspace_id,
        source_type=source_type,
        trust_level=trust_level,
        enabled=enabled,
        skip=skip,
        limit=per_page,
    )

    # Count total (simplified - in production would use count_documents)
    total = len(sources)

    return ExternalSourceListResponse(
        data=sources,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


@router.post("/sources", response_model=ExternalSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source_data: ExternalSourceCreate,
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
) -> ExternalSourceResponse:
    """Register a new external verification source.

    Requires workspace_admin role.

    This endpoint registers an external API or feed as a verification source.
    The source can then be used to import pre-verified data into the system.

    Trust levels determine import behavior:
    - HIGH: Government APIs, official sources (auto-verify)
    - MEDIUM: NGO feeds, credentialed reporters (review required)
    - LOW: Other sources (full verification required)

    Authentication types supported:
    - none: No authentication
    - api_key: API key in custom header
    - bearer: Bearer token in Authorization header
    - basic: Basic authentication
    - oauth2: OAuth 2.0 client credentials flow

    Args:
        source_data: Source configuration
        user: Current user (workspace_admin)
        service: External source service

    Returns:
        Created external source

    Raises:
        HTTPException: If source_id already exists or endpoint is invalid
    """
    try:
        source = await service.create_source(
            source_data=source_data,
            workspace_id=user.workspace_id,
            created_by=str(user.id),
        )
        return ExternalSourceResponse(data=source)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/sources/{source_id}", response_model=ExternalSourceResponse)
async def get_source(
    source_id: str,
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
) -> ExternalSourceResponse:
    """Get external source details.

    Requires workspace_admin role.

    Retrieves configuration and statistics for an external verification source.
    Authentication credentials are redacted for security.

    Args:
        source_id: Source ID
        user: Current user (workspace_admin)
        service: External source service

    Returns:
        External source details

    Raises:
        HTTPException: If source not found
    """
    try:
        source_oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid source ID",
        )

    source = await service.get_source(
        source_id=source_oid,
        workspace_id=user.workspace_id,
    )

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External source not found",
        )

    return ExternalSourceResponse(data=source)


@router.put("/sources/{source_id}", response_model=ExternalSourceResponse)
async def update_source(
    source_id: str,
    update_data: ExternalSourceUpdate,
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
) -> ExternalSourceResponse:
    """Update external source configuration.

    Requires workspace_admin role.

    Updates source configuration including endpoint URL, authentication,
    trust level, and sync interval. Changes take effect on the next sync.

    Args:
        source_id: Source ID
        update_data: Update data
        user: Current user (workspace_admin)
        service: External source service

    Returns:
        Updated external source

    Raises:
        HTTPException: If source not found or update invalid
    """
    try:
        source_oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid source ID",
        )

    try:
        source = await service.update_source(
            source_id=source_oid,
            workspace_id=user.workspace_id,
            update_data=update_data,
        )

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="External source not found",
            )

        return ExternalSourceResponse(data=source)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: str,
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
) -> None:
    """Delete external source.

    Requires workspace_admin role. This action cannot be undone.

    Deletes the source configuration. Previously imported data and
    COP candidates remain in the system for audit purposes.

    Args:
        source_id: Source ID
        user: Current user (workspace_admin)
        service: External source service

    Raises:
        HTTPException: If source not found
    """
    try:
        source_oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid source ID",
        )

    deleted = await service.delete_source(
        source_id=source_oid,
        workspace_id=user.workspace_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External source not found",
        )


# ============================================================================
# Import Endpoints
# ============================================================================


@router.post("/sources/{source_id}/import", response_model=ImportResultResponse)
async def import_verified_data(
    source_id: str,
    import_request: ImportRequest,
    user: RequireWorkspaceAdmin,
    service: ExternalSourceServiceDep,
) -> ImportResultResponse:
    """Import verified data from an external source.

    Requires workspace_admin role.

    This endpoint triggers an import from the external source API:

    1. Fetches data from external API (within specified time range)
    2. Transforms data to COP candidate schema
    3. Checks for duplicates (by external_id)
    4. Creates COP candidates with appropriate readiness state:
       - HIGH trust + auto_promote=true → verified (ready to publish)
       - MEDIUM/LOW trust → in_review (requires facilitator review)
    5. Logs provenance to external source in audit trail

    Import is rate limited to 100 imports per source per hour.

    Args:
        source_id: Source ID
        import_request: Import parameters (time range, filters, auto-promote)
        user: Current user (workspace_admin)
        service: External source service

    Returns:
        Import result with statistics:
        - items_fetched: Number of items from external API
        - items_imported: Number successfully imported
        - duplicates_skipped: Number of duplicates skipped
        - candidates_created: Number of COP candidates created
        - errors: Number of errors encountered

    Raises:
        HTTPException: If source not found, disabled, or import fails
    """
    try:
        source_oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid source ID",
        )

    try:
        result = await service.import_verified_data(
            source_id=source_oid,
            workspace_id=user.workspace_id,
            import_request=import_request,
            imported_by=str(user.id),
        )

        return ImportResultResponse(data=result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}",
        )
