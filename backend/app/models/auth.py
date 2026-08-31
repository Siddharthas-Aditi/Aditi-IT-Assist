"""Authentication & RBAC models — Users, Roles, Permissions, Groups."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────

USER_ROLES = ("employee", "it_agent", "it_lead", "it_admin", "security_auditor")
AUTH_PROVIDER_TYPES = ("local", "saml", "oidc")


# ─────────────────────────────────────────────────────────────────────
# Permission Model
# ─────────────────────────────────────────────────────────────────────


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fine-grained permission definition."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(50))

    roles: Mapped[list["RolePermission"]] = relationship(back_populates="permission")


# ─────────────────────────────────────────────────────────────────────
# Role Model
# ─────────────────────────────────────────────────────────────────────


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Role definition for RBAC."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(default=0)

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role")
    user_assignments: Mapped[list["UserRoleAssignment"]] = relationship(back_populates="role")


class RolePermission(Base):
    """Many-to-many: Role ↔ Permission."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship(back_populates="roles")


# ─────────────────────────────────────────────────────────────────────
# Group Model
# ─────────────────────────────────────────────────────────────────────


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Organizational group for bulk role assignment (e.g., SAML group mapping)."""

    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 'general' | 'saml_sync' | 'analytics_team' — added in migration 019
    group_type: Mapped[str] = mapped_column(String(32), default="general")


class UserGroup(Base):
    """Many-to-many: User ↔ Group."""

    __tablename__ = "user_groups"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )


# ─────────────────────────────────────────────────────────────────────
# User Model (upgraded)
# ─────────────────────────────────────────────────────────────────────


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User model — employees, IT agents, leads, admins."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    employee_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    role_assignments: Mapped[list["UserRoleAssignment"]] = relationship(
        back_populates="user",
        foreign_keys="[UserRoleAssignment.user_id]",
        lazy="selectin",
    )
    auth_identities: Mapped[list["AuthIdentity"]] = relationship(back_populates="user")
    sessions: Mapped[list["LoginSession"]] = relationship(back_populates="user")

    @property
    def primary_role(self) -> str:
        """Return the highest-priority role name."""
        if not self.role_assignments:
            return "employee"
        sorted_assignments = sorted(
            self.role_assignments, key=lambda a: a.role.priority, reverse=True
        )
        return sorted_assignments[0].role.name

    @property
    def role_names(self) -> list[str]:
        """Return all assigned role names."""
        return [a.role.name for a in self.role_assignments]


# ─────────────────────────────────────────────────────────────────────
# User Role Assignment
# ─────────────────────────────────────────────────────────────────────


class UserRoleAssignment(UUIDPrimaryKeyMixin, Base):
    """Assigns a role to a user with optional expiry."""

    __tablename__ = "user_role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), index=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="role_assignments", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship(back_populates="user_assignments", lazy="selectin")


# ─────────────────────────────────────────────────────────────────────
# Auth Identity (SSO/SAML mapping)
# ─────────────────────────────────────────────────────────────────────


class AuthIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """External identity provider link (SAML, OIDC, etc.)."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    provider: Mapped[str] = mapped_column(Enum(*AUTH_PROVIDER_TYPES, name="auth_provider_type"))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="auth_identities")


# ─────────────────────────────────────────────────────────────────────
# Login Session
# ─────────────────────────────────────────────────────────────────────


class LoginSession(UUIDPrimaryKeyMixin, Base):
    """Tracks active login sessions for security and audit."""

    __tablename__ = "login_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    token_jti: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="local")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
