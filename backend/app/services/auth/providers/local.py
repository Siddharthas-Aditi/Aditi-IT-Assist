"""Local authentication provider — email/password with JWT."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from app.models.auth import LoginSession, User
from app.services.auth.providers.base import AuthProvider, AuthResult


class LocalAuthProvider(AuthProvider):
    """Email/password authentication with JWT tokens."""

    @property
    def provider_name(self) -> str:
        return "local"

    async def authenticate(
        self, *, email: str, password: str, db: AsyncSession, **kwargs
    ) -> AuthResult:
        """Authenticate via email and password."""
        stmt = select(User).where(User.email == email, User.is_active.is_(True))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return AuthResult(success=False, error="Invalid email or password")

        if not verify_password(password, user.hashed_password):
            return AuthResult(success=False, error="Invalid email or password")

        # Update last login
        user.last_login_at = datetime.now(UTC)

        return AuthResult(
            success=True,
            user=user,
            provider="local",
            provider_user_id=str(user.id),
        )

    async def validate_session(self, token: str, **kwargs) -> AuthResult:
        """Validate a JWT access token.

        Rejects:
        * structurally invalid / expired tokens,
        * refresh tokens (``type=refresh``) — a refresh token must never
          authenticate an API call, only the ``/auth/refresh`` exchange,
        * revoked tokens (jti on the Redis denylist — logout / rotation).
        """
        payload = verify_token(token)
        if not payload:
            return AuthResult(success=False, error="Invalid or expired token")

        if payload.get("type") == "refresh":
            return AuthResult(success=False, error="Refresh token cannot be used for access")

        from app.core.token_store import get_token_denylist

        try:
            revoked = await get_token_denylist().is_revoked(payload.get("jti"))
        except RuntimeError:
            # Fail-closed mode with denylist unavailable.
            return AuthResult(success=False, error="Token revocation check unavailable")
        if revoked:
            return AuthResult(success=False, error="Token has been revoked")

        return AuthResult(
            success=True,
            provider="local",
            provider_user_id=payload.get("sub"),
            claims=payload,
        )

    async def create_session(
        self,
        user: User,
        db: AsyncSession,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str]:
        """Create JWT tokens and persist login session."""
        jti = str(uuid.uuid4())
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.primary_role,
            "roles": user.role_names,
            "jti": jti,
        }

        access_token = create_access_token(data=token_data)
        # Refresh token: its own jti + REFRESH_TOKEN_EXPIRE_DAYS expiry, so it
        # can be rotated/revoked independently of the access token.
        refresh_token = create_refresh_token(data={"sub": str(user.id), "email": user.email})

        # Persist session
        from datetime import timedelta

        session = LoginSession(
            user_id=user.id,
            token_jti=jti,
            ip_address=ip_address,
            user_agent=user_agent,
            provider="local",
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        db.add(session)

        return access_token, refresh_token

    async def logout(self, user_id: str, session_id: str) -> bool:
        """Revoke a login session."""
        return True
