"""FastAPI dependencies for authentication and authorization."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate current user from JWT bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.services.auth.service import AuthService
    auth_service = AuthService(db)
    user = await auth_service.validate_token(credentials.credentials)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return current_user


def require_roles(*allowed_roles: str):
    """Dependency factory: require user to have one of the specified roles."""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        user_roles = set(current_user.role_names)
        if not user_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker


def require_permissions(*required_permissions: str):
    """Dependency factory: require user to have specific permissions."""
    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        from app.services.auth.service import AuthService
        auth_service = AuthService(db)
        user_permissions = await auth_service.get_user_permissions(current_user)

        missing = set(required_permissions) - user_permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing)}",
            )
        return current_user
    return permission_checker


# Convenience type aliases for common role checks
CurrentUser = Annotated[User, Depends(get_current_active_user)]
ITAgentUser = Annotated[User, Depends(require_roles("it_agent", "it_lead", "it_admin"))]
ITLeadUser = Annotated[User, Depends(require_roles("it_lead", "it_admin"))]
AdminUser = Annotated[User, Depends(require_roles("it_admin"))]
AuditorUser = Annotated[User, Depends(require_roles("security_auditor", "it_admin"))]
