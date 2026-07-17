"""Read-side service for the immutable audit log.

The write side lives in ``app.services.audit_service.AuditService``; this service
is purely for querying — filtering, paginating, and fetching single events for
the Audit Logs admin screen and for security auditors.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.schemas.admin import AuditEventDetail, AuditEventOut, AuditFacets


class AuditQueryService:
    """Query and filter audit events."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_events(
        self,
        *,
        severity: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        actor: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventOut], int]:
        """Filtered, paginated, newest-first list of audit events."""
        conditions = []
        if severity:
            conditions.append(AuditEvent.severity == severity)
        if action:
            conditions.append(AuditEvent.action == action)
        if resource_type:
            conditions.append(AuditEvent.resource_type == resource_type)
        if actor:
            conditions.append(AuditEvent.actor_email.ilike(f"%{actor.strip()}%"))
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    AuditEvent.description.ilike(like),
                    AuditEvent.resource_id.ilike(like),
                    AuditEvent.action.ilike(like),
                )
            )
        if date_from:
            conditions.append(AuditEvent.created_at >= date_from)
        if date_to:
            conditions.append(AuditEvent.created_at <= date_to)

        count_stmt = select(func.count(AuditEvent.id))
        list_stmt = select(AuditEvent)
        for c in conditions:
            count_stmt = count_stmt.where(c)
            list_stmt = list_stmt.where(c)

        total = (await self.db.execute(count_stmt)).scalar() or 0
        list_stmt = list_stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.db.execute(list_stmt)).scalars().all()
        return [self._to_out(r) for r in rows], total

    async def get_event(self, event_id: uuid.UUID) -> AuditEventDetail | None:
        """Fetch a single audit event with full payload diffs."""
        row = (
            await self.db.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return AuditEventDetail(
            id=str(row.id),
            actor_email=row.actor_email,
            actor_role=row.actor_role,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            description=row.description,
            severity=row.severity,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at,
            old_value=row.old_value,
            new_value=row.new_value,
            metadata_json=row.metadata_json,
        )

    async def facets(self) -> AuditFacets:
        """Distinct values for the filter dropdowns."""
        actions = (
            (
                await self.db.execute(
                    select(AuditEvent.action).distinct().order_by(AuditEvent.action)
                )
            )
            .scalars()
            .all()
        )
        resources = (
            (
                await self.db.execute(
                    select(AuditEvent.resource_type).distinct().order_by(AuditEvent.resource_type)
                )
            )
            .scalars()
            .all()
        )
        severities = (
            (
                await self.db.execute(
                    select(AuditEvent.severity).distinct().order_by(AuditEvent.severity)
                )
            )
            .scalars()
            .all()
        )
        return AuditFacets(
            actions=[a for a in actions if a],
            resource_types=[r for r in resources if r],
            severities=[s for s in severities if s],
        )

    @staticmethod
    def _to_out(row: AuditEvent) -> AuditEventOut:
        return AuditEventOut(
            id=str(row.id),
            actor_email=row.actor_email,
            actor_role=row.actor_role,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            description=row.description,
            severity=row.severity,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
