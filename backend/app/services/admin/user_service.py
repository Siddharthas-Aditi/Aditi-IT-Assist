"""Admin user-management service.

Lists, inspects, and mutates users and their role assignments. Every mutation
is audit-logged with before/after snapshots. Backed entirely by the existing
``User`` / ``Role`` / ``UserRoleAssignment`` models — no new tables.

Service-layer policy (not route policy):
- A user must always retain at least one role (we never strip the last role).
- Role names must exist in the canonical role table.
- Activation state is mutated here, not in the route handler.
"""

import uuid

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Role, User, UserRoleAssignment
from app.schemas.admin import (
    RoleAssignmentInfo,
    RoleSummary,
    UserDetail,
    UserSummary,
)
from app.services.audit_service import AuditService

logger = structlog.get_logger()


class AdminUserError(Exception):
    """Raised for business-rule violations (bad role, last-role removal, 404)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AdminUserService:
    """User and role administration for the Admin Console."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ── Queries ──────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[UserSummary], int]:
        """List users with optional search, role, and status filters."""
        base = select(User)
        count_base = select(func.count(func.distinct(User.id))).select_from(User)

        if role:
            base = base.join(UserRoleAssignment, UserRoleAssignment.user_id == User.id).join(
                Role, Role.id == UserRoleAssignment.role_id
            )
            count_base = count_base.join(
                UserRoleAssignment, UserRoleAssignment.user_id == User.id
            ).join(Role, Role.id == UserRoleAssignment.role_id)
            base = base.where(Role.name == role)
            count_base = count_base.where(Role.name == role)

        if search:
            like = f"%{search.strip()}%"
            cond = or_(User.email.ilike(like), User.full_name.ilike(like))
            base = base.where(cond)
            count_base = count_base.where(cond)

        if status == "active":
            base = base.where(User.is_active.is_(True))
            count_base = count_base.where(User.is_active.is_(True))
        elif status == "inactive":
            base = base.where(User.is_active.is_(False))
            count_base = count_base.where(User.is_active.is_(False))

        total = (await self.db.execute(count_base)).scalar() or 0

        stmt = base.order_by(User.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).unique().scalars().all()
        return [self._to_summary(u) for u in rows], total

    async def get_user(self, user_id: uuid.UUID) -> UserDetail | None:
        """Fetch a single user (active or not) with role provenance."""
        user = await self._load(user_id)
        return self._to_detail(user) if user else None

    async def list_roles(self) -> list[RoleSummary]:
        """List assignable roles, highest priority first."""
        stmt = select(Role).order_by(Role.priority.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            RoleSummary(
                name=r.name,
                display_name=r.display_name,
                description=r.description,
                priority=r.priority,
            )
            for r in rows
        ]

    # ── Mutations (audited) ──────────────────────────────────────────

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
        phone: str | None = None,
        is_active: bool | None = None,
        actor: User | None = None,
    ) -> UserDetail:
        """Patch profile fields and/or activation state."""
        user = await self._require(user_id)

        # Guardrail: an admin cannot suspend their own account (self-lockout).
        if actor is not None and actor.id == user.id and is_active is False:
            raise AdminUserError(
                "You cannot suspend your own account.", status_code=409
            )

        before = {
            "full_name": user.full_name,
            "department": user.department,
            "job_title": user.job_title,
            "phone": user.phone,
            "is_active": user.is_active,
        }

        if full_name is not None:
            user.full_name = full_name
        if department is not None:
            user.department = department
        if job_title is not None:
            user.job_title = job_title
        if phone is not None:
            user.phone = phone

        activation_changed = is_active is not None and is_active != user.is_active
        if is_active is not None:
            user.is_active = is_active

        await self.db.flush()

        after = {
            "full_name": user.full_name,
            "department": user.department,
            "job_title": user.job_title,
            "phone": user.phone,
            "is_active": user.is_active,
        }

        action = "user_updated"
        if activation_changed:
            action = "user_activated" if user.is_active else "user_suspended"

        await self.audit.log(
            action,
            "user",
            actor=actor,
            resource_id=str(user.id),
            description=f"Admin updated {user.email}",
            old_value=before,
            new_value=after,
            severity="warning" if activation_changed else "info",
        )

        return await self._reload_detail(user_id)

    async def assign_role(
        self, user_id: uuid.UUID, role_name: str, *, actor: User | None = None
    ) -> UserDetail:
        """Grant a role to a user (idempotent)."""
        user = await self._require(user_id)
        role = await self._role_by_name(role_name)

        existing = await self.db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.role_id == role.id,
            )
        )
        if existing.scalar_one_or_none() is None:
            self.db.add(
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=actor.id if actor else None,
                )
            )
            await self.db.flush()
            await self.audit.log(
                "role_assigned",
                "user",
                actor=actor,
                resource_id=str(user.id),
                description=f"Granted role '{role_name}' to {user.email}",
                new_value={"role": role_name},
                severity="warning",
            )

        return await self._reload_detail(user_id)

    async def revoke_role(
        self, user_id: uuid.UUID, role_name: str, *, actor: User | None = None
    ) -> UserDetail:
        """Revoke a role from a user. Refuses to remove the user's last role."""
        user = await self._require(user_id)
        role = await self._role_by_name(role_name)

        assignments = list(user.role_assignments)
        target = next((a for a in assignments if a.role_id == role.id), None)
        if target is None:
            return self._to_detail(user)  # nothing to do — already absent

        if len(assignments) <= 1:
            raise AdminUserError(
                "Cannot remove the user's only role — assign another role first.",
                status_code=409,
            )

        await self.db.delete(target)
        await self.db.flush()
        await self.audit.log(
            "role_revoked",
            "user",
            actor=actor,
            resource_id=str(user.id),
            description=f"Revoked role '{role_name}' from {user.email}",
            old_value={"role": role_name},
            severity="warning",
        )

        return await self._reload_detail(user_id)

    # ── Internals ────────────────────────────────────────────────────

    async def _load(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _require(self, user_id: uuid.UUID) -> User:
        user = await self._load(user_id)
        if user is None:
            raise AdminUserError("User not found", status_code=404)
        return user

    async def _reload_detail(self, user_id: uuid.UUID) -> UserDetail:
        # populate_existing forces the identity-mapped instance (and its
        # role_assignments) to be re-read after a flush, so a freshly
        # assigned/revoked role is always reflected in the response.
        stmt = (
            select(User)
            .options(selectinload(User.role_assignments).selectinload(UserRoleAssignment.role))
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        user = (await self.db.execute(stmt)).scalar_one()
        return self._to_detail(user)

    async def _role_by_name(self, role_name: str) -> Role:
        role = (
            await self.db.execute(select(Role).where(Role.name == role_name))
        ).scalar_one_or_none()
        if role is None:
            raise AdminUserError(f"Unknown role '{role_name}'", status_code=400)
        return role

    @staticmethod
    def _to_summary(user: User) -> UserSummary:
        return UserSummary(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            department=user.department,
            job_title=user.job_title,
            is_active=user.is_active,
            is_verified=user.is_verified,
            primary_role=user.primary_role,
            roles=user.role_names,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )

    @classmethod
    def _to_detail(cls, user: User) -> UserDetail:
        summary = cls._to_summary(user)
        assignments = [
            RoleAssignmentInfo(
                role=a.role.name,
                display_name=a.role.display_name,
                assigned_at=a.assigned_at,
                expires_at=a.expires_at,
            )
            for a in user.role_assignments
        ]
        return UserDetail(
            **summary.model_dump(),
            employee_id=user.employee_id,
            phone=user.phone,
            role_assignments=assignments,
        )
