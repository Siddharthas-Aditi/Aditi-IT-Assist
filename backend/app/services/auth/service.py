"""Authentication service — orchestrates auth providers and session management."""

import contextlib
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.auth import User, UserRoleAssignment
from app.services.auth.providers.base import AuthProvider
from app.services.auth.providers.local import LocalAuthProvider
from app.services.auth.providers.saml import SAMLAuthProvider

logger = structlog.get_logger()


class AuthService:
    """Central authentication service with pluggable provider support."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._providers: dict[str, AuthProvider] = {
            "local": LocalAuthProvider(),
            "saml": SAMLAuthProvider(),
        }

    @property
    def active_provider(self) -> AuthProvider:
        """Get the configured active authentication provider."""
        return self._providers.get(settings.AUTH_PROVIDER, self._providers["local"])

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Authenticate user via local provider."""
        provider = self._providers["local"]
        result = await provider.authenticate(email=email, password=password, db=self.db)

        if not result.success or not result.user:
            logger.warning("login_failed", email=email, error=result.error)
            raise AuthenticationError(result.error or "Authentication failed")

        user = result.user
        access_token, refresh_token = await provider.create_session(
            user=user, db=self.db, ip_address=ip_address, user_agent=user_agent
        )

        logger.info("login_success", user_id=str(user.id), email=user.email)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.primary_role,
                "roles": user.role_names,
            },
        }

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch user by ID with role assignments loaded."""
        stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch user by email."""
        stmt = select(User).where(User.email == email, User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def register_user(
        self, email: str, password: str, full_name: str, role_name: str = "employee", **kwargs
    ) -> User:
        """Register a new user with local credentials."""
        from app.core.security import hash_password
        from app.models.auth import Role

        # Check if exists
        existing = await self.get_user_by_email(email)
        if existing:
            raise AuthenticationError("Email already registered")

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
            is_verified=True,
            **{k: v for k, v in kwargs.items() if hasattr(User, k)},
        )
        self.db.add(user)
        await self.db.flush()

        # Assign role
        role_stmt = select(Role).where(Role.name == role_name)
        role_result = await self.db.execute(role_stmt)
        role = role_result.scalar_one_or_none()
        if role:
            assignment = UserRoleAssignment(user_id=user.id, role_id=role.id)
            self.db.add(assignment)

        return user

    async def validate_token(self, token: str) -> User | None:
        """Validate a token and return the associated user."""
        result = await self.active_provider.validate_session(token)
        if not result.success or not result.provider_user_id:
            return None
        try:
            user_id = uuid.UUID(result.provider_user_id)
        except ValueError:
            return None
        return await self.get_user_by_id(user_id)

    async def get_user_permissions(self, user: User) -> set[str]:
        """Get all permission codes for a user across all roles.

        Uses the code-defined ROLE_PERMISSIONS as the authoritative source so
        the DB never drifts out of sync when new permissions are added.  Any
        extra permissions stored in the DB (future per-user grants) are merged
        in on top.
        """
        from app.core.permissions import UserRole, get_effective_permissions

        # 1. Code-defined permissions for every role the user holds
        code_perms: set[str] = set()
        for assignment in user.role_assignments:
            role_name = (
                assignment.role.name
                if hasattr(assignment.role, "name")
                else str(assignment.role_id)
            )
            # unknown role name — skip gracefully
            with contextlib.suppress(ValueError):
                code_perms |= {str(p) for p in get_effective_permissions(UserRole(role_name))}

        # 2. DB-stored permissions (custom grants, future extensibility)
        from app.models.auth import Permission, RolePermission

        role_ids = [a.role_id for a in user.role_assignments]
        if role_ids:
            stmt = (
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id.in_(role_ids))
            )
            result = await self.db.execute(stmt)
            db_perms = {row[0] for row in result.all()}
        else:
            db_perms = set()

        return code_perms | db_perms


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        self.message = message
        super().__init__(self.message)
