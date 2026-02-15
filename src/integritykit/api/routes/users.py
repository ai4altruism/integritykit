"""User management API routes.

Implements:
- FR-ROLE-001: Role assignment
- FR-ROLE-002: Role-based access enforcement
- FR-ROLE-003: Role-change audit logging
- NFR-ABUSE-002: User suspension
"""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequireAdmin,
    RequireManageRoles,
    get_user_repository,
)
from integritykit.models.user import User, UserResponse, UserRole
from integritykit.services.audit import AuditService, get_audit_service
from integritykit.services.database import UserRepository

router = APIRouter(prefix="/users", tags=["Users"])


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class UserListResponse(BaseModel):
    """Response for list users endpoint."""

    data: list[UserResponse]
    meta: PaginationMeta


class RoleAssignmentRequest(BaseModel):
    """Request body for role assignment."""

    role: UserRole = Field(..., description="Role to assign")
    justification: str = Field(
        ...,
        min_length=10,
        description="Reason for role assignment",
    )


class SuspendUserRequest(BaseModel):
    """Request body for user suspension."""

    reason: str = Field(
        ...,
        min_length=10,
        description="Reason for suspension",
    )


class ReinstateUserRequest(BaseModel):
    """Request body for user reinstatement."""

    reason: Optional[str] = Field(
        default=None,
        description="Reason for reinstatement",
    )


@router.get("/me", response_model=dict)
async def get_current_user(
    user: CurrentUser,
) -> dict:
    """Get current authenticated user.

    Returns:
        Current user details with roles and permissions
    """
    return {
        "data": UserResponse.from_user(user).model_dump(),
    }


@router.get("", response_model=UserListResponse)
async def list_users(
    user: CurrentUser,
    _: None = RequireAdmin,
    role: Optional[UserRole] = Query(default=None, description="Filter by role"),
    is_suspended: Optional[bool] = Query(
        default=None, description="Filter by suspension status"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserListResponse:
    """List users in the workspace.

    Requires workspace_admin role.

    Args:
        user: Current authenticated user
        role: Filter by role (optional)
        is_suspended: Filter by suspension status (optional)
        page: Page number
        per_page: Items per page
        user_repo: User repository

    Returns:
        List of users with pagination
    """
    offset = (page - 1) * per_page

    users = await user_repo.list_by_workspace(
        slack_team_id=user.slack_team_id,
        role=role,
        is_suspended=is_suspended,
        limit=per_page,
        offset=offset,
    )

    total = await user_repo.count_by_workspace(
        slack_team_id=user.slack_team_id,
        role=role,
        is_suspended=is_suspended,
    )

    total_pages = (total + per_page - 1) // per_page

    return UserListResponse(
        data=[UserResponse.from_user(u) for u in users],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    current_user: CurrentUser,
    _: None = RequireAdmin,
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict:
    """Get user by ID.

    Requires workspace_admin role.

    Args:
        user_id: User ID to fetch
        current_user: Current authenticated user
        user_repo: User repository

    Returns:
        User details

    Raises:
        HTTPException: If user not found
    """
    try:
        target_user = await user_repo.get_by_id(ObjectId(user_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Ensure user is in same workspace
    if target_user.slack_team_id != current_user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {
        "data": UserResponse.from_user(target_user).model_dump(),
    }


@router.post("/{user_id}/roles", response_model=dict)
async def assign_role(
    user_id: str,
    request: RoleAssignmentRequest,
    current_user: CurrentUser,
    _: None = RequireManageRoles,
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict:
    """Assign role to user.

    Requires workspace_admin role. Action is logged to audit trail (FR-ROLE-003).

    Args:
        user_id: User ID to modify
        request: Role assignment request
        current_user: Current authenticated user
        user_repo: User repository

    Returns:
        Updated user details

    Raises:
        HTTPException: If user not found or role already assigned
    """
    try:
        target_user_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    target_user = await user_repo.get_by_id(target_user_id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Ensure user is in same workspace
    if target_user.slack_team_id != current_user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if role already assigned
    if target_user.has_role(request.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already has role: {request.role.value}",
        )

    # Capture old roles for audit log
    old_roles = [r.value if isinstance(r, UserRole) else r for r in target_user.roles]

    # Add role with audit trail
    updated_user = await user_repo.add_role(
        user_id=target_user_id,
        role=request.role,
        changed_by=current_user.id,
        reason=request.justification,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )

    # Log to audit trail (FR-ROLE-003)
    new_roles = [r.value if isinstance(r, UserRole) else r for r in updated_user.roles]
    audit_service = get_audit_service()
    await audit_service.log_role_change(
        actor=current_user,
        target_user=updated_user,
        old_roles=old_roles,
        new_roles=new_roles,
        justification=request.justification,
    )

    return {
        "data": UserResponse.from_user(updated_user).model_dump(),
    }


@router.delete("/{user_id}/roles", response_model=dict)
async def revoke_role(
    user_id: str,
    role: UserRole = Query(..., description="Role to revoke"),
    justification: str = Query(..., min_length=10, description="Reason for revocation"),
    current_user: CurrentUser = None,
    _: None = RequireManageRoles,
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict:
    """Revoke role from user.

    Requires workspace_admin role. Action is logged to audit trail (FR-ROLE-003).

    Args:
        user_id: User ID to modify
        role: Role to revoke
        justification: Reason for revocation
        current_user: Current authenticated user
        user_repo: User repository

    Returns:
        Updated user details

    Raises:
        HTTPException: If user not found, role not assigned, or base role
    """
    try:
        target_user_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    # Cannot revoke base role
    if role == UserRole.GENERAL_PARTICIPANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke base role: general_participant",
        )

    target_user = await user_repo.get_by_id(target_user_id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Ensure user is in same workspace
    if target_user.slack_team_id != current_user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if role is assigned
    if not target_user.has_role(role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User does not have role: {role.value}",
        )

    # Capture old roles for audit log
    old_roles = [r.value if isinstance(r, UserRole) else r for r in target_user.roles]

    # Remove role with audit trail
    updated_user = await user_repo.remove_role(
        user_id=target_user_id,
        role=role,
        changed_by=current_user.id,
        reason=justification,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )

    # Log to audit trail (FR-ROLE-003)
    new_roles = [r.value if isinstance(r, UserRole) else r for r in updated_user.roles]
    audit_service = get_audit_service()
    await audit_service.log_role_change(
        actor=current_user,
        target_user=updated_user,
        old_roles=old_roles,
        new_roles=new_roles,
        justification=justification,
    )

    return {
        "data": UserResponse.from_user(updated_user).model_dump(),
    }


@router.post("/{user_id}/suspend", response_model=dict)
async def suspend_user(
    user_id: str,
    request: SuspendUserRequest,
    current_user: CurrentUser,
    _: None = RequireAdmin,
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict:
    """Suspend a user account (NFR-ABUSE-002).

    Requires workspace_admin role.

    Args:
        user_id: User ID to suspend
        request: Suspension request
        current_user: Current authenticated user
        user_repo: User repository

    Returns:
        Updated user details

    Raises:
        HTTPException: If user not found or already suspended
    """
    try:
        target_user_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    # Cannot suspend yourself
    if target_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend your own account",
        )

    target_user = await user_repo.get_by_id(target_user_id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Ensure user is in same workspace
    if target_user.slack_team_id != current_user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if target_user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already suspended",
        )

    updated_user = await user_repo.suspend_user(
        user_id=target_user_id,
        suspended_by=current_user.id,
        reason=request.reason,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to suspend user",
        )

    # Log to audit trail (NFR-ABUSE-002)
    audit_service = get_audit_service()
    await audit_service.log_user_suspend(
        actor=current_user,
        target_user=updated_user,
        reason=request.reason,
    )

    return {
        "data": UserResponse.from_user(updated_user).model_dump(),
    }


@router.post("/{user_id}/reinstate", response_model=dict)
async def reinstate_user(
    user_id: str,
    request: ReinstateUserRequest,
    current_user: CurrentUser,
    _: None = RequireAdmin,
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict:
    """Reinstate a suspended user.

    Requires workspace_admin role.

    Args:
        user_id: User ID to reinstate
        request: Reinstatement request
        current_user: Current authenticated user
        user_repo: User repository

    Returns:
        Updated user details

    Raises:
        HTTPException: If user not found or not suspended
    """
    try:
        target_user_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    target_user = await user_repo.get_by_id(target_user_id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Ensure user is in same workspace
    if target_user.slack_team_id != current_user.slack_team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not target_user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not suspended",
        )

    updated_user = await user_repo.reinstate_user(
        user_id=target_user_id,
        reinstated_by=current_user.id,
        reason=request.reason,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reinstate user",
        )

    # Log to audit trail
    audit_service = get_audit_service()
    await audit_service.log_user_reinstate(
        actor=current_user,
        target_user=updated_user,
        reason=request.reason,
    )

    return {
        "data": UserResponse.from_user(updated_user).model_dump(),
    }
