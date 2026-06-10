"""Ticket service — enterprise helpdesk ticket lifecycle management."""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.ticket import Ticket, TicketComment, TicketEvent

logger = structlog.get_logger()

# SLA targets by priority (in hours)
SLA_RESPONSE_HOURS = {"critical": 1, "high": 4, "medium": 8, "low": 24}
SLA_RESOLUTION_HOURS = {"critical": 4, "high": 12, "medium": 48, "low": 120}


class TicketService:
    """Manages enterprise ticket lifecycle with SLA tracking."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._next_ticket_number: int | None = None

    async def create_ticket(
        self,
        requester: User,
        title: str,
        description: str,
        *,
        priority: str = "medium",
        category: str | None = None,
        subcategory: str | None = None,
        source: str = "chat",
        session_id: uuid.UUID | None = None,
        ai_summary: str | None = None,
    ) -> Ticket:
        """Create a new support ticket with SLA targets."""
        ticket_number = await self._generate_ticket_number()

        # Calculate SLA targets
        now = datetime.now(timezone.utc)
        response_hours = SLA_RESPONSE_HOURS.get(priority, 8)
        resolution_hours = SLA_RESOLUTION_HOURS.get(priority, 48)

        ticket = Ticket(
            ticket_number=ticket_number,
            title=title,
            description=description,
            requester_id=requester.id,
            priority=priority,
            category=category,
            subcategory=subcategory,
            source=source,
            session_id=session_id,
            status="new",
            ai_summary=ai_summary,
            sla_response_target=now + timedelta(hours=response_hours),
            sla_resolution_target=now + timedelta(hours=resolution_hours),
        )
        self.db.add(ticket)
        await self.db.flush()

        # Record creation event
        await self._add_event(
            ticket.id, None, "ticket_created",
            f"Ticket {ticket_number} created by {requester.full_name}",
        )

        logger.info("ticket_created", ticket_number=ticket_number, requester=requester.email)
        return ticket

    async def update_status(
        self, ticket_id: uuid.UUID, new_status: str, actor: User,
        comment: str | None = None,
    ) -> Ticket:
        """Update ticket status with event logging."""
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        old_status = ticket.status
        ticket.status = new_status

        # Timestamp tracking
        now = datetime.now(timezone.utc)
        if new_status == "resolved":
            ticket.resolved_at = now
        elif new_status == "closed":
            ticket.closed_at = now

        await self._add_event(
            ticket_id, actor.id, "status_changed",
            f"Status changed from {old_status} to {new_status}",
            old_value=old_status, new_value=new_status,
        )

        if comment:
            await self.add_comment(ticket_id, actor, comment, is_internal=True)

        return ticket

    async def assign_ticket(
        self, ticket_id: uuid.UUID, agent_id: uuid.UUID, actor: User,
    ) -> Ticket:
        """Assign or reassign a ticket to an IT agent."""
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        old_assigned = str(ticket.assigned_to) if ticket.assigned_to else None
        ticket.assigned_to = agent_id

        if ticket.status == "new":
            ticket.status = "triaged"

        # Record first response time
        if not ticket.first_response_at:
            ticket.first_response_at = datetime.now(timezone.utc)

        await self._add_event(
            ticket_id, actor.id, "ticket_assigned",
            f"Ticket assigned to agent {agent_id}",
            old_value=old_assigned, new_value=str(agent_id),
        )

        return ticket

    async def add_comment(
        self, ticket_id: uuid.UUID, author: User, content: str,
        is_internal: bool = False, comment_type: str = "note",
    ) -> TicketComment:
        """Add a comment to a ticket."""
        comment = TicketComment(
            ticket_id=ticket_id,
            author_id=author.id,
            content=content,
            is_internal=is_internal,
            comment_type=comment_type,
        )
        self.db.add(comment)

        await self._add_event(
            ticket_id, author.id,
            "internal_note_added" if is_internal else "comment_added",
            f"{'Internal note' if is_internal else 'Comment'} added by {author.full_name}",
        )

        return comment

    async def get_ticket_for_employee(
        self, ticket_id: uuid.UUID, employee: User,
    ) -> dict | None:
        """Get ticket visible to the requesting employee (own tickets only)."""
        ticket = await self._get_ticket(ticket_id)
        if not ticket or ticket.requester_id != employee.id:
            return None

        # Get non-internal comments only
        comments_stmt = (
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id, TicketComment.is_internal.is_(False))
            .order_by(TicketComment.created_at)
        )
        comments_result = await self.db.execute(comments_stmt)
        comments = comments_result.scalars().all()

        events_stmt = (
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at)
        )
        events_result = await self.db.execute(events_stmt)
        events = events_result.scalars().all()

        return {
            "ticket": ticket,
            "comments": comments,
            "events": events,
        }

    async def list_tickets_for_employee(
        self, employee: User, status: str | None = None,
        limit: int = 20, offset: int = 0,
    ) -> list[Ticket]:
        """List tickets belonging to an employee."""
        stmt = select(Ticket).where(Ticket.requester_id == employee.id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_tickets_for_agent(
        self, agent: User, assigned_only: bool = False,
        status: str | None = None, priority: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Ticket]:
        """List tickets visible to an IT agent."""
        stmt = select(Ticket)
        if assigned_only:
            stmt = stmt.where(Ticket.assigned_to == agent.id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        if priority:
            stmt = stmt.where(Ticket.priority == priority)
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_queue_summary(self) -> dict:
        """Get ticket queue summary for IT agents."""
        # Unassigned tickets
        unassigned_stmt = select(func.count(Ticket.id)).where(
            Ticket.assigned_to.is_(None),
            Ticket.status.in_(["new", "triaged"]),
        )
        unassigned_result = await self.db.execute(unassigned_stmt)
        unassigned = unassigned_result.scalar() or 0

        # Active tickets
        active_stmt = select(func.count(Ticket.id)).where(
            Ticket.status.in_(["new", "triaged", "in_progress", "waiting_for_user"]),
        )
        active_result = await self.db.execute(active_stmt)
        active = active_result.scalar() or 0

        return {
            "unassigned": unassigned,
            "active": active,
        }

    async def _get_ticket(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Fetch a ticket by ID."""
        stmt = select(Ticket).where(Ticket.id == ticket_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _add_event(
        self, ticket_id: uuid.UUID, actor_id: uuid.UUID | None,
        event_type: str, description: str,
        old_value: str | None = None, new_value: str | None = None,
    ) -> None:
        """Add a timeline event to a ticket."""
        event = TicketEvent(
            ticket_id=ticket_id,
            actor_id=actor_id,
            event_type=event_type,
            description=description,
            old_value=old_value,
            new_value=new_value,
        )
        self.db.add(event)

    async def _generate_ticket_number(self) -> str:
        """Generate a unique sequential ticket number."""
        stmt = select(func.count(Ticket.id))
        result = await self.db.execute(stmt)
        count = result.scalar() or 0
        return f"ITA-{count + 1:06d}"
