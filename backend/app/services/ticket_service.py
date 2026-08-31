"""Ticket service — enterprise helpdesk ticket lifecycle management."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.ticket import Ticket, TicketComment, TicketEvent
from app.services.ticket_category_validation import validate_category_cascade

logger = structlog.get_logger()

# SLA targets by priority (in hours)
SLA_RESPONSE_HOURS = {"critical": 1, "high": 4, "medium": 8, "low": 24}
SLA_RESOLUTION_HOURS = {"critical": 4, "high": 12, "medium": 48, "low": 120}


class TicketService:
    """Manages enterprise ticket lifecycle with SLA tracking."""

    _STAFF = frozenset({"it_agent", "it_lead", "it_admin"})

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
        now = datetime.now(UTC)
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
            ticket.id,
            None,
            "ticket_created",
            f"Ticket {ticket_number} created by {requester.full_name}",
        )

        logger.info("ticket_created", ticket_number=ticket_number, requester=requester.email)
        return ticket

    async def request_live_agent(self, ticket_id: uuid.UUID, actor: User) -> Ticket:
        """Queue an existing ticket for a live IT agent (human handoff).

        Surfaces the ticket in the IT operations queue: moves it out of the raw
        "new" state into "triaged" (ready for pickup), records a live-agent
        request event + an internal note, and guarantees at least `high`
        priority so it is picked up promptly. Idempotent-friendly: calling it on
        an already-queued ticket simply re-records the request.
        """
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        if ticket.status == "new":
            ticket.status = "triaged"
        if ticket.priority in ("low", "medium"):
            ticket.priority = "high"

        await self._add_event(
            ticket_id,
            actor.id,
            "live_agent_requested",
            f"Live agent requested by {actor.full_name} from chat handoff",
        )
        await self.add_comment(
            ticket_id,
            actor,
            "Employee requested a live IT specialist from the support chat. "
            "Conversation context and attempted steps are captured in this ticket.",
            is_internal=True,
            comment_type="system",
        )

        logger.info(
            "live_agent_requested",
            ticket_number=ticket.ticket_number,
            requester=actor.email,
        )
        return ticket

    async def update_status(
        self,
        ticket_id: uuid.UUID,
        new_status: str,
        actor: User,
        comment: str | None = None,
    ) -> Ticket:
        """Update ticket status with event logging."""
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        if new_status == "closed":
            raise ValueError("Use POST /tickets/{id}/close")

        old_status = ticket.status
        ticket.status = new_status

        # Timestamp tracking
        now = datetime.now(UTC)
        if new_status == "resolved":
            ticket.resolved_at = now

        await self._add_event(
            ticket_id,
            actor.id,
            "status_changed",
            f"Status changed from {old_status} to {new_status}",
            old_value=old_status,
            new_value=new_status,
        )

        if comment:
            await self.add_comment(ticket_id, actor, comment, is_internal=True)

        return ticket

    async def close_ticket(
        self,
        ticket_id: uuid.UUID,
        actor: User,
        *,
        resolution_notes: str,
        category: str,
        subcategory: str,
        item: str,
        close_notes: str | None = None,
    ) -> Ticket:
        """Close a ticket — IT staff only; mandatory notes + full category cascade."""
        roles = set(getattr(actor, "role_names", None) or [])
        if not roles & self._STAFF:
            raise PermissionError("Only IT staff can close tickets")

        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        if ticket.status == "closed":
            raise ValueError("Ticket is already closed")

        notes = (resolution_notes or "").strip()
        if not notes:
            raise ValueError("resolution_notes is required")

        await validate_category_cascade(self.db, category, subcategory, item)

        old_status = ticket.status
        now = datetime.now(UTC)
        ticket.status = "closed"
        ticket.closed_at = now
        ticket.closed_by = actor.id
        ticket.resolution_notes = notes
        ticket.close_notes = (close_notes or "").strip() or None
        ticket.category = category.strip()
        ticket.subcategory = subcategory.strip()
        ticket.item = item.strip()
        if not ticket.resolved_at:
            ticket.resolved_at = now

        await self._add_event(
            ticket_id,
            actor.id,
            "status_changed",
            f"Status changed from {old_status} to closed",
            old_value=old_status,
            new_value="closed",
        )
        return ticket

    async def update_ticket_properties(
        self,
        ticket_id: uuid.UUID,
        actor: User,
        *,
        priority: str | None = None,
        urgency: str | None = None,
        impact: str | None = None,
        ticket_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        item: str | None = None,
        status: str | None = None,
        resolution_notes: str | None = None,
    ) -> Ticket:
        """Partial property update for IT staff. Cannot set status=closed."""
        roles = set(getattr(actor, "role_names", None) or [])
        if not roles & self._STAFF:
            raise PermissionError("Only IT staff can update ticket properties")

        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        if status == "closed":
            raise ValueError("Use POST /tickets/{id}/close")

        if status is not None:
            if status not in (
                "new",
                "triaged",
                "in_progress",
                "waiting_for_user",
                "escalated",
                "resolved",
            ):
                raise ValueError(f"Invalid status '{status}'")
            old = ticket.status
            ticket.status = status
            if status == "resolved" and not ticket.resolved_at:
                ticket.resolved_at = datetime.now(UTC)
            await self._add_event(
                ticket_id,
                actor.id,
                "status_changed",
                f"Status changed from {old} to {status}",
                old_value=old,
                new_value=status,
            )

        if priority is not None:
            ticket.priority = priority
        if urgency is not None:
            ticket.urgency = urgency
        if impact is not None:
            ticket.impact = impact
        if ticket_type is not None:
            ticket.ticket_type = ticket_type
        if resolution_notes is not None:
            ticket.resolution_notes = resolution_notes

        # Classification: if any of the three provided, require full valid cascade
        if category is not None or subcategory is not None or item is not None:
            cat = category if category is not None else ticket.category
            sub = subcategory if subcategory is not None else ticket.subcategory
            itm = item if item is not None else ticket.item
            await validate_category_cascade(self.db, cat or "", sub or "", itm or "")
            ticket.category = (cat or "").strip()
            ticket.subcategory = (sub or "").strip()
            ticket.item = (itm or "").strip()

        return ticket

    async def reopen_ticket(
        self,
        ticket_id: uuid.UUID,
        actor: User,
        comment: str | None = None,
    ) -> Ticket:
        """Reopen a resolved/closed ticket back to active work.

        Logs a `status_changed` event (what the specialist report derives
        "reopened" from) and clears the resolution/closure timestamps. Only
        valid from a terminal state (`resolved`/`closed`) — reopening a
        ticket that's already active is rejected.
        """
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        if ticket.status not in ("resolved", "closed"):
            raise ValueError(f"Cannot reopen a ticket in status '{ticket.status}'")

        old_status = ticket.status
        ticket.status = "in_progress"
        ticket.resolved_at = None
        ticket.closed_at = None

        await self._add_event(
            ticket_id,
            actor.id,
            "status_changed",
            f"Status changed from {old_status} to in_progress (reopened)",
            old_value=old_status,
            new_value="in_progress",
        )

        if comment:
            await self.add_comment(ticket_id, actor, comment, is_internal=True)

        return ticket

    async def assign_ticket(
        self,
        ticket_id: uuid.UUID,
        agent_id: uuid.UUID,
        actor: User,
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
            ticket.first_response_at = datetime.now(UTC)

        await self._add_event(
            ticket_id,
            actor.id,
            "ticket_assigned",
            f"Ticket assigned to agent {agent_id}",
            old_value=old_assigned,
            new_value=str(agent_id),
        )

        return ticket

    async def add_comment(
        self,
        ticket_id: uuid.UUID,
        author: User,
        content: str,
        is_internal: bool = False,
        comment_type: str = "note",
    ) -> TicketComment:
        """Add a comment to a ticket.

        Employees may only comment on their own tickets, and never as
        internal notes (``is_internal`` is forced False for non-staff).
        """
        ticket = await self._get_ticket(ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")

        staff_roles = {"it_agent", "it_lead", "it_admin"}
        author_roles = set(getattr(author, "role_names", None) or [])
        is_staff = bool(author_roles & staff_roles)

        if not is_staff:
            if ticket.requester_id != author.id:
                raise PermissionError("You may only comment on your own tickets")
            is_internal = False

        comment = TicketComment(
            ticket_id=ticket_id,
            author_id=author.id,
            content=content,
            is_internal=is_internal,
            comment_type=comment_type,
        )
        self.db.add(comment)

        await self._add_event(
            ticket_id,
            author.id,
            "internal_note_added" if is_internal else "comment_added",
            f"{'Internal note' if is_internal else 'Comment'} added by {author.full_name}",
        )

        return comment

    async def get_ticket_for_employee(
        self,
        ticket_id: uuid.UUID,
        employee: User,
    ) -> dict[str, object] | None:
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

    async def get_ticket_for_agent(self, ticket_id: uuid.UUID) -> dict[str, object] | None:
        """Get full ticket detail for IT staff — all comments (incl. internal) + events.

        Unlike the employee view this is not scoped to the requester and includes
        internal notes, since IT agents/leads/admins work the whole queue.
        """
        ticket = await self._get_ticket(ticket_id)
        if not ticket:
            return None

        comments_stmt = (
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at)
        )
        comments = (await self.db.execute(comments_stmt)).scalars().all()

        events_stmt = (
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at)
        )
        events = (await self.db.execute(events_stmt)).scalars().all()

        # Requester identity travels with the detail so the workspace can show
        # who raised it — and resolve their assigned assets — without a second
        # round trip to an admin-only user endpoint.
        requester = await self.db.get(User, ticket.requester_id)

        return {
            "ticket": ticket,
            "comments": comments,
            "events": events,
            "requester_name": requester.full_name if requester else None,
            "requester_email": requester.email if requester else None,
        }

    async def list_tickets_for_employee(
        self,
        employee: User,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Ticket]:
        """List tickets belonging to an employee."""
        stmt = select(Ticket).where(Ticket.requester_id == employee.id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _csv_terms(raw: str | None) -> list[str]:
        """Split a comma-separated filter value into non-empty terms."""
        if not raw:
            return []
        return [term.strip() for term in raw.split(",") if term.strip()]

    def _agent_queue_filters(
        self,
        agent: User,
        assigned_only: bool,
        status: str | None,
        priority: str | None,
        category: str | None,
        source: str | None,
        search: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[ColumnElement[bool]]:
        """Build the WHERE clauses shared by the agent queue and CSV export.

        `status`/`priority` accept comma-separated values so the UI can filter
        on several at once; everything else is a single value.
        """
        clauses: list[ColumnElement[bool]] = []
        if assigned_only:
            clauses.append(Ticket.assigned_to == agent.id)

        statuses = self._csv_terms(status)
        if statuses:
            clauses.append(Ticket.status.in_(statuses))

        priorities = self._csv_terms(priority)
        if priorities:
            clauses.append(Ticket.priority.in_(priorities))

        if category:
            clauses.append(Ticket.category == category)
        if source:
            clauses.append(Ticket.source == source)
        if date_from:
            clauses.append(Ticket.created_at >= date_from)
        if date_to:
            clauses.append(Ticket.created_at <= date_to)

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            clauses.append(
                or_(
                    Ticket.ticket_number.ilike(pattern),
                    Ticket.title.ilike(pattern),
                    Ticket.description.ilike(pattern),
                    Ticket.category.ilike(pattern),
                )
            )
        return clauses

    async def list_tickets_for_agent(
        self,
        agent: User,
        assigned_only: bool = False,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        source: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Ticket], int]:
        """List tickets visible to an IT agent.

        Returns `(page_of_tickets, total_matching)` — the total is counted
        against the same filters but ignores limit/offset, so the UI can
        paginate accurately instead of inferring the count from the page.
        """
        clauses = self._agent_queue_filters(
            agent=agent,
            assigned_only=assigned_only,
            status=status,
            priority=priority,
            category=category,
            source=source,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )

        total_stmt = select(func.count(Ticket.id)).where(*clauses)
        total = (await self.db.execute(total_stmt)).scalar() or 0

        stmt = (
            select(Ticket)
            .where(*clauses)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def export_tickets_csv(
        self,
        agent: User,
        assigned_only: bool = False,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        source: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> str:
        """Render every ticket matching the queue filters as CSV text.

        Deliberately unpaginated — this backs the "export what I'm looking at"
        action, so it must apply the same filters as the queue but no limit.
        """
        clauses = self._agent_queue_filters(
            agent=agent,
            assigned_only=assigned_only,
            status=status,
            priority=priority,
            category=category,
            source=source,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = select(Ticket).where(*clauses).order_by(Ticket.created_at.desc())
        tickets = list((await self.db.execute(stmt)).scalars().all())

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "ticket_number",
                "title",
                "status",
                "priority",
                "category",
                "subcategory",
                "item",
                "ticket_type",
                "source",
                "assigned_to",
                "created_at",
                "resolved_at",
                "closed_at",
            ]
        )
        for ticket in tickets:
            writer.writerow(
                [
                    ticket.ticket_number,
                    ticket.title,
                    ticket.status,
                    ticket.priority,
                    ticket.category or "",
                    ticket.subcategory or "",
                    ticket.item or "",
                    ticket.ticket_type or "",
                    ticket.source,
                    str(ticket.assigned_to) if ticket.assigned_to else "",
                    ticket.created_at.isoformat() if ticket.created_at else "",
                    ticket.resolved_at.isoformat() if ticket.resolved_at else "",
                    ticket.closed_at.isoformat() if ticket.closed_at else "",
                ]
            )
        return buffer.getvalue()

    async def get_queue_summary(self) -> dict[str, int]:
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
        self,
        ticket_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        event_type: str,
        description: str,
        old_value: str | None = None,
        new_value: str | None = None,
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
        """Generate a unique ticket number using PostgreSQL's atomic sequence.

        Counting rows races under concurrent ticket creation and can also reuse
        numbers after deletion. ``nextval`` is database-owned and non-
        transactional, so every caller receives a distinct value even when a
        surrounding ticket insert is rolled back.
        """
        result = await self.db.execute(text("SELECT nextval('ticket_number_sequence')"))
        return f"ITA-{result.scalar_one():06d}"
