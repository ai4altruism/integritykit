"""API routes for webhook management (Sprint 8, Task S8-17).

Implements:
- FR-INT-001: Webhook system with retry and logging
- Task S8-17: Outbound webhook system
"""

from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import CurrentUser
from integritykit.models.user import User, UserRole
from integritykit.models.webhook import (
    Webhook,
    WebhookCreate,
    WebhookDelivery,
    WebhookStatus,
    WebhookTestResult,
    WebhookUpdate,
)
from integritykit.services.database import get_collection
from integritykit.services.webhooks import WebhookService

router = APIRouter(prefix="/integrations/webhooks", tags=["Integrations"])


# ============================================================================
# Response Models
# ============================================================================


class WebhookResponse(BaseModel):
    """Response model for webhook operations."""

    data: Webhook


class WebhookListResponse(BaseModel):
    """Response model for webhook listing."""

    data: list[Webhook]
    meta: dict


class WebhookDeliveryListResponse(BaseModel):
    """Response model for webhook delivery history."""

    data: list[WebhookDelivery]
    meta: dict


class WebhookTestResponse(BaseModel):
    """Response model for webhook test."""

    data: WebhookTestResult


# ============================================================================
# Dependencies
# ============================================================================


def get_webhook_service() -> WebhookService:
    """Get webhook service instance."""
    return WebhookService(
        webhooks_collection=get_collection("webhooks"),
        deliveries_collection=get_collection("webhook_deliveries"),
    )


def require_workspace_admin(user: CurrentUser) -> User:
    """Require workspace_admin role for webhook management.

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
            detail="Only workspace admins can manage webhooks",
        )
    return user


RequireWorkspaceAdmin = Annotated[User, Depends(require_workspace_admin)]
WebhookServiceDep = Annotated[WebhookService, Depends(get_webhook_service)]


# ============================================================================
# Webhook CRUD Endpoints
# ============================================================================


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
    enabled: Optional[bool] = Query(default=None, description="Filter by enabled status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
) -> WebhookListResponse:
    """List configured webhooks.

    Requires workspace_admin role.

    Args:
        user: Current user (workspace_admin)
        service: Webhook service
        enabled: Filter by enabled status (optional)
        page: Page number
        per_page: Items per page

    Returns:
        List of webhooks with pagination metadata
    """
    skip = (page - 1) * per_page

    webhooks = await service.list_webhooks(
        workspace_id=user.workspace_id,
        enabled=enabled,
        skip=skip,
        limit=per_page,
    )

    # Count total (simplified - in production would use count_documents)
    total = len(webhooks)  # This is approximate for pagination

    return WebhookListResponse(
        data=webhooks,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    webhook_data: WebhookCreate,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
) -> WebhookResponse:
    """Create a new webhook.

    Requires workspace_admin role.

    Webhooks are triggered on specified events (e.g., cop_update.published).
    Supports multiple authentication types and automatic retry with exponential backoff.

    Args:
        webhook_data: Webhook configuration
        user: Current user (workspace_admin)
        service: Webhook service

    Returns:
        Created webhook

    Raises:
        HTTPException: If webhook URL is invalid or already exists
    """
    try:
        webhook = await service.create_webhook(
            webhook_data=webhook_data,
            workspace_id=user.workspace_id,
            created_by=str(user.id),
        )
        return WebhookResponse(data=webhook)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
) -> WebhookResponse:
    """Get webhook details.

    Requires workspace_admin role.

    Args:
        webhook_id: Webhook ID
        user: Current user (workspace_admin)
        service: Webhook service

    Returns:
        Webhook details

    Raises:
        HTTPException: If webhook not found
    """
    try:
        webhook_oid = ObjectId(webhook_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook ID",
        )

    webhook = await service.get_webhook(
        webhook_id=webhook_oid,
        workspace_id=user.workspace_id,
    )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    return WebhookResponse(data=webhook)


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    update_data: WebhookUpdate,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
) -> WebhookResponse:
    """Update webhook configuration.

    Requires workspace_admin role.

    Args:
        webhook_id: Webhook ID
        update_data: Update data
        user: Current user (workspace_admin)
        service: Webhook service

    Returns:
        Updated webhook

    Raises:
        HTTPException: If webhook not found or update invalid
    """
    try:
        webhook_oid = ObjectId(webhook_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook ID",
        )

    try:
        webhook = await service.update_webhook(
            webhook_id=webhook_oid,
            workspace_id=user.workspace_id,
            update_data=update_data,
        )

        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook not found",
            )

        return WebhookResponse(data=webhook)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
) -> None:
    """Delete webhook.

    Requires workspace_admin role. This action cannot be undone.

    Args:
        webhook_id: Webhook ID
        user: Current user (workspace_admin)
        service: Webhook service

    Raises:
        HTTPException: If webhook not found
    """
    try:
        webhook_oid = ObjectId(webhook_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook ID",
        )

    deleted = await service.delete_webhook(
        webhook_id=webhook_oid,
        workspace_id=user.workspace_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )


# ============================================================================
# Webhook Testing & Delivery History
# ============================================================================


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
) -> WebhookTestResponse:
    """Test webhook delivery.

    Sends a test payload to the webhook endpoint to verify configuration.
    Returns delivery status and response details.

    Requires workspace_admin role.

    Args:
        webhook_id: Webhook ID
        user: Current user (workspace_admin)
        service: Webhook service

    Returns:
        Test result with success status, response time, and response body

    Raises:
        HTTPException: If webhook not found
    """
    try:
        webhook_oid = ObjectId(webhook_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook ID",
        )

    try:
        result = await service.test_webhook(
            webhook_id=webhook_oid,
            workspace_id=user.workspace_id,
        )
        return WebhookTestResponse(data=result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def get_webhook_deliveries(
    webhook_id: str,
    user: RequireWorkspaceAdmin,
    service: WebhookServiceDep,
    status_filter: Optional[WebhookStatus] = Query(
        default=None,
        alias="status",
        description="Filter by delivery status",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
) -> WebhookDeliveryListResponse:
    """Get webhook delivery history.

    Retrieve delivery history including successes, failures, and retry attempts.

    Requires workspace_admin role.

    Args:
        webhook_id: Webhook ID
        user: Current user (workspace_admin)
        service: Webhook service
        status_filter: Filter by delivery status (optional)
        page: Page number
        per_page: Items per page

    Returns:
        Delivery history with pagination metadata

    Raises:
        HTTPException: If webhook not found
    """
    try:
        webhook_oid = ObjectId(webhook_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook ID",
        )

    skip = (page - 1) * per_page

    deliveries = await service.get_webhook_deliveries(
        webhook_id=webhook_oid,
        workspace_id=user.workspace_id,
        status=status_filter,
        skip=skip,
        limit=per_page,
    )

    # Count total (simplified)
    total = len(deliveries)

    return WebhookDeliveryListResponse(
        data=deliveries,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
