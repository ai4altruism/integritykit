"""FastAPI dependencies for authentication and authorization.

Implements:
- FR-ROLE-002: Role-based access enforcement via dependency injection
- Slack OAuth authentication
- Permission-based route protection
"""

from typing import Annotated, Callable, Optional

from bson import ObjectId
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from integritykit.models.user import Permission, User, UserRole
from integritykit.services.database import UserRepository, get_collection
from integritykit.services.rbac import (
    AccessDeniedError,
    RBACService,
    UserSuspendedError,
    get_rbac_service,
)


class TokenPayload(BaseModel):
    """Decoded token payload from Slack OAuth."""

    user_id: str
    team_id: str
    email: Optional[str] = None
    name: Optional[str] = None


# Dependency to get user repository
async def get_user_repository() -> UserRepository:
    """Get user repository instance.

    Returns:
        UserRepository instance
    """
    return UserRepository(get_collection("users"))


# Dependency to get RBAC service
def get_rbac() -> RBACService:
    """Get RBAC service instance.

    Returns:
        RBACService instance
    """
    return get_rbac_service()


async def get_current_user_from_token(
    request: Request,
    authorization: Annotated[Optional[str], Header()] = None,
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Extract and validate current user from request.

    This dependency handles:
    1. Extracting token from Authorization header or session cookie
    2. Validating token
    3. Looking up or creating user in database
    4. Returning User model

    Args:
        request: FastAPI request
        authorization: Authorization header value
        user_repo: User repository

    Returns:
        Current user

    Raises:
        HTTPException: If authentication fails
    """
    # For development/testing, check for test user header
    test_user_id = request.headers.get("X-Test-User-Id")
    test_team_id = request.headers.get("X-Test-Team-Id")

    if test_user_id and test_team_id:
        # Development mode: use test headers
        user, _ = await user_repo.get_or_create_by_slack_id(
            slack_user_id=test_user_id,
            slack_team_id=test_team_id,
        )
        return user

    # Check for session in request state (set by middleware)
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    # Check Authorization header
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            # TODO: Validate Slack OAuth token and get user info
            # For now, return 401 until Slack OAuth is implemented
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Slack OAuth not yet implemented",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Type alias for current user dependency
CurrentUser = Annotated[User, Depends(get_current_user_from_token)]


def require_permission(permission: Permission) -> Callable:
    """Create a dependency that requires a specific permission.

    Args:
        permission: Required permission

    Returns:
        FastAPI dependency function

    Example:
        @router.get("/backlog")
        async def get_backlog(
            user: CurrentUser,
            _: None = Depends(require_permission(Permission.VIEW_BACKLOG)),
        ):
            ...
    """

    async def check_permission(
        user: CurrentUser,
        rbac: RBACService = Depends(get_rbac),
    ) -> None:
        try:
            rbac.require_permission(user, permission)
        except UserSuspendedError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended",
            )
        except AccessDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=e.message,
            )

    return check_permission


def require_role(role: UserRole) -> Callable:
    """Create a dependency that requires a specific role.

    Args:
        role: Required role

    Returns:
        FastAPI dependency function

    Example:
        @router.post("/users/{user_id}/roles")
        async def assign_role(
            user: CurrentUser,
            _: None = Depends(require_role(UserRole.WORKSPACE_ADMIN)),
        ):
            ...
    """

    async def check_role(
        user: CurrentUser,
        rbac: RBACService = Depends(get_rbac),
    ) -> None:
        try:
            rbac.require_role(user, role)
        except UserSuspendedError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended",
            )
        except AccessDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=e.message,
            )

    return check_role


def require_any_role(roles: list[UserRole]) -> Callable:
    """Create a dependency that requires any of the specified roles.

    Args:
        roles: List of acceptable roles

    Returns:
        FastAPI dependency function
    """

    async def check_roles(
        user: CurrentUser,
        rbac: RBACService = Depends(get_rbac),
    ) -> None:
        try:
            rbac.require_any_role(user, roles)
        except UserSuspendedError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended",
            )
        except AccessDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=e.message,
            )

    return check_roles


# Pre-built dependencies for common permission checks
RequireFacilitator = Depends(require_role(UserRole.FACILITATOR))
RequireVerifier = Depends(require_any_role([UserRole.VERIFIER, UserRole.FACILITATOR]))
RequireAdmin = Depends(require_role(UserRole.WORKSPACE_ADMIN))

# Permission-specific dependencies
RequireViewBacklog = Depends(require_permission(Permission.VIEW_BACKLOG))
RequirePromoteCluster = Depends(require_permission(Permission.PROMOTE_CLUSTER))
RequirePublishCOP = Depends(require_permission(Permission.PUBLISH_COP))
RequireSearch = Depends(require_permission(Permission.SEARCH))
RequireManageRoles = Depends(require_permission(Permission.MANAGE_ROLES))
RequireViewAudit = Depends(require_permission(Permission.VIEW_AUDIT_LOG))


async def get_current_user_optional(
    request: Request,
    authorization: Annotated[Optional[str], Header()] = None,
    user_repo: UserRepository = Depends(get_user_repository),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None.

    Useful for endpoints that behave differently for authenticated users.

    Args:
        request: FastAPI request
        authorization: Authorization header value
        user_repo: User repository

    Returns:
        Current user or None
    """
    try:
        return await get_current_user_from_token(request, authorization, user_repo)
    except HTTPException:
        return None


# Type alias for optional current user
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
