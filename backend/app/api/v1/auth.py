"""Authentication endpoints (placeholder for future Azure AD SSO)."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request schema."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response schema."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest) -> LoginResponse:
    """Authenticate user and return access token.

    Current: simple email/password auth.
    Future: Azure AD SSO integration.
    """
    # TODO(team): Implement real authentication with database lookup
    # This is a placeholder for development
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": data.email, "role": "employee"})
    return LoginResponse(
        access_token=token,
        user_id="dev-user-001",
        email=data.email,
        full_name="Dev User",
        role="employee",
    )


@router.post("/logout")
async def logout() -> dict[str, str]:
    """Logout user (invalidate token)."""
    # TODO(team): Implement token blacklisting
    return {"message": "Logged out successfully"}
