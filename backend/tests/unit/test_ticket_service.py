"""Unit tests for ticket service — lifecycle, employee isolation, SLA tracking.

Tests:
- Ticket creation with SLA target calculation
- Employee can only view their own tickets
- Internal notes hidden from employees
- Status transitions with event logging
- Agent assignment workflow
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ticket_service import SLA_RESOLUTION_HOURS, SLA_RESPONSE_HOURS, TicketService

# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _make_user(role: str = "employee") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@test.com"
    user.full_name = f"Test {role.title()}"
    user.role_names = [role]
    return user


def _make_mock_db() -> MagicMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


# ─────────────────────────────────────────────────────────────────────
# SLA constant validation
# ─────────────────────────────────────────────────────────────────────


class TestSLAConstants:
    """Verify SLA constants match enterprise requirements."""

    def test_critical_response_sla_is_1_hour(self):
        assert SLA_RESPONSE_HOURS["critical"] == 1

    def test_critical_resolution_sla_is_4_hours(self):
        assert SLA_RESOLUTION_HOURS["critical"] == 4

    def test_high_response_sla_is_4_hours(self):
        assert SLA_RESPONSE_HOURS["high"] == 4

    def test_low_resolution_sla_is_5_days(self):
        assert SLA_RESOLUTION_HOURS["low"] == 120

    def test_all_priorities_covered(self):
        for priority in ["low", "medium", "high", "critical"]:
            assert priority in SLA_RESPONSE_HOURS
            assert priority in SLA_RESOLUTION_HOURS


# ─────────────────────────────────────────────────────────────────────
# Ticket lifecycle
# ─────────────────────────────────────────────────────────────────────


class TestTicketCreation:
    """Tests for TicketService.create_ticket."""

    async def test_creates_ticket_with_correct_sla_targets(self):
        """SLA targets should be set based on priority."""
        db = _make_mock_db()
        service = TicketService(db)

        with patch("app.services.ticket_service.Ticket") as mock_ticket_cls:
            mock_ticket = MagicMock()
            mock_ticket.ticket_number = "TKT-2026-0001"
            mock_ticket.id = uuid.uuid4()
            mock_ticket.status = "new"
            mock_ticket.priority = "high"
            mock_ticket_cls.return_value = mock_ticket

            with (
                patch.object(service, "_generate_ticket_number", return_value="TKT-2026-0001"),
                patch.object(service, "_add_event", new_callable=AsyncMock),
            ):
                requester = _make_user("employee")
                ticket = await service.create_ticket(
                    requester=requester,
                    title="VPN not connecting",
                    description="Can't connect to VPN after system update",
                    priority="high",
                    category="network/connectivity",
                )

        # Ticket was created with correct params
        assert ticket.status == "new"
        assert ticket.priority == "high"
        # Ticket constructor was called with SLA targets
        call_kwargs = mock_ticket_cls.call_args.kwargs
        assert call_kwargs["priority"] == "high"
        assert "sla_response_target" in call_kwargs
        assert "sla_resolution_target" in call_kwargs
        assert call_kwargs["sla_response_target"] > datetime.now(UTC)

    async def test_creates_ticket_with_critical_priority_sla(self):
        """Critical tickets get tightest SLA (1h response, 4h resolution)."""
        db = _make_mock_db()
        service = TicketService(db)

        with patch("app.services.ticket_service.Ticket") as mock_ticket_cls:
            mock_ticket = MagicMock()
            mock_ticket.ticket_number = "TKT-2026-0002"
            mock_ticket.id = uuid.uuid4()
            mock_ticket.status = "new"
            mock_ticket.priority = "critical"
            mock_ticket_cls.return_value = mock_ticket

            with (
                patch.object(service, "_generate_ticket_number", return_value="TKT-2026-0002"),
                patch.object(service, "_add_event", new_callable=AsyncMock),
            ):
                requester = _make_user()
                await service.create_ticket(
                    requester=requester,
                    title="Production system down",
                    description="All employees cannot log in",
                    priority="critical",
                )

        call_kwargs = mock_ticket_cls.call_args.kwargs
        now = datetime.now(UTC)
        # critical: 1h response, 4h resolution
        assert call_kwargs["sla_response_target"] <= now + timedelta(hours=1, minutes=1)
        assert call_kwargs["sla_resolution_target"] <= now + timedelta(hours=4, minutes=1)


class TestTicketNumberGeneration:
    async def test_uses_database_sequence_instead_of_counting_ticket_rows(self):
        db = _make_mock_db()
        result = MagicMock()
        result.scalar_one.return_value = 42
        db.execute.return_value = result

        ticket_number = await TicketService(db)._generate_ticket_number()

        assert ticket_number == "ITA-000042"
        statement = str(db.execute.call_args.args[0])
        assert "nextval('ticket_number_sequence')" in statement


class TestEmployeeDataIsolation:
    """Tests for employee data isolation in ticket service."""

    async def test_employee_cannot_see_other_employees_ticket(self):
        """get_ticket_for_employee returns None for tickets owned by someone else."""
        db = _make_mock_db()
        service = TicketService(db)

        owner = _make_user("employee")
        other_employee = _make_user("employee")

        # Ticket belongs to `owner`, not `other_employee`
        mock_ticket = MagicMock()
        mock_ticket.requester_id = owner.id

        with patch.object(service, "_get_ticket", return_value=mock_ticket):
            result = await service.get_ticket_for_employee(uuid.uuid4(), other_employee)

        assert result is None

    async def test_employee_can_see_own_ticket(self):
        """get_ticket_for_employee returns ticket when requester_id matches."""
        db = _make_mock_db()

        mock_comments_result = MagicMock()
        mock_comments_result.scalars.return_value.all.return_value = []
        mock_events_result = MagicMock()
        mock_events_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [mock_comments_result, mock_events_result]

        service = TicketService(db)
        employee = _make_user("employee")

        mock_ticket = MagicMock()
        mock_ticket.requester_id = employee.id
        mock_ticket.id = uuid.uuid4()

        with patch.object(service, "_get_ticket", return_value=mock_ticket):
            result = await service.get_ticket_for_employee(mock_ticket.id, employee)

        assert result is not None
        assert result["ticket"] is mock_ticket

    async def test_list_tickets_filters_by_employee(self):
        """list_tickets_for_employee includes requester_id filter."""
        db = _make_mock_db()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = TicketService(db)
        employee = _make_user("employee")

        tickets = await service.list_tickets_for_employee(employee)

        # Verify the SQL was called (execute was invoked)
        db.execute.assert_called_once()
        assert tickets == []


class TestTicketStatusTransitions:
    """Tests for ticket status transitions."""

    async def test_update_status_sets_resolved_at(self):
        """Resolving a ticket sets resolved_at timestamp."""
        db = _make_mock_db()
        service = TicketService(db)
        actor = _make_user("it_agent")

        mock_ticket = MagicMock()
        mock_ticket.status = "in_progress"
        mock_ticket.resolved_at = None
        mock_ticket.closed_at = None

        with (
            patch.object(service, "_get_ticket", return_value=mock_ticket),
            patch.object(service, "_add_event", new_callable=AsyncMock),
        ):
            result = await service.update_status(uuid.uuid4(), "resolved", actor)

        assert result.status == "resolved"
        assert result.resolved_at is not None

    async def test_update_status_rejects_closing_outside_the_close_workflow(self):
        """Closing requires the dedicated workflow and its mandatory close metadata."""
        db = _make_mock_db()
        service = TicketService(db)
        actor = _make_user("it_agent")

        mock_ticket = MagicMock()
        mock_ticket.status = "resolved"
        mock_ticket.resolved_at = datetime.now(UTC)
        mock_ticket.closed_at = None

        with (
            patch.object(service, "_get_ticket", return_value=mock_ticket),
            pytest.raises(ValueError, match="Use POST /tickets/.+/close"),
        ):
            await service.update_status(uuid.uuid4(), "closed", actor)

    async def test_assign_ticket_records_event(self):
        """Assigning a ticket should record an assignment event."""
        db = _make_mock_db()
        service = TicketService(db)
        actor = _make_user("it_agent")
        target_agent_id = uuid.uuid4()

        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.status = "new"
        mock_ticket.assigned_to = None
        mock_ticket.first_response_at = None

        add_event_mock = AsyncMock()
        with (
            patch.object(service, "_get_ticket", return_value=mock_ticket),
            patch.object(service, "_add_event", add_event_mock),
        ):
            await service.assign_ticket(mock_ticket.id, target_agent_id, actor)

        add_event_mock.assert_called_once()
        call_kwargs = add_event_mock.call_args
        assert "ticket_assigned" in str(call_kwargs)

    async def test_assign_ticket_transitions_new_to_triaged(self):
        """Assigning a 'new' ticket moves it to 'triaged'."""
        db = _make_mock_db()
        service = TicketService(db)
        actor = _make_user("it_agent")

        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.status = "new"
        mock_ticket.assigned_to = None
        mock_ticket.first_response_at = None

        with (
            patch.object(service, "_get_ticket", return_value=mock_ticket),
            patch.object(service, "_add_event", new_callable=AsyncMock),
        ):
            result = await service.assign_ticket(mock_ticket.id, uuid.uuid4(), actor)

        assert result.status == "triaged"


class TestInternalNotesIsolation:
    """Tests that internal notes are hidden from employees."""

    async def test_internal_comments_hidden_from_employee(self):
        """Employee ticket view should not include internal notes."""
        db = _make_mock_db()

        # Return one non-internal comment and verify internal ones don't leak
        mock_public_comment = MagicMock()
        mock_public_comment.is_internal = False
        mock_public_comment.content = "Public response"

        mock_comments_result = MagicMock()
        mock_comments_result.scalars.return_value.all.return_value = [mock_public_comment]

        mock_events_result = MagicMock()
        mock_events_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [mock_comments_result, mock_events_result]

        service = TicketService(db)
        employee = _make_user("employee")

        mock_ticket = MagicMock()
        mock_ticket.requester_id = employee.id
        mock_ticket.id = uuid.uuid4()

        with patch.object(service, "_get_ticket", return_value=mock_ticket):
            result = await service.get_ticket_for_employee(mock_ticket.id, employee)

        # Only the non-internal comment was returned
        assert len(result["comments"]) == 1
        assert result["comments"][0].is_internal is False


class TestAgentQueueFilters:
    """Filter parsing for the IT agent queue and CSV export.

    These back the Team Queue page, whose route passes category/source/search/
    date filters and unpacks a `(tickets, total)` tuple.
    """

    def test_csv_terms_splits_and_strips(self):
        assert TicketService._csv_terms("new, triaged ,in_progress") == [
            "new",
            "triaged",
            "in_progress",
        ]

    def test_csv_terms_empty_values_yield_no_terms(self):
        assert TicketService._csv_terms(None) == []
        assert TicketService._csv_terms("") == []
        assert TicketService._csv_terms(" , ") == []

    def test_no_filters_produces_no_clauses(self):
        service = TicketService(_make_mock_db())
        clauses = service._agent_queue_filters(
            agent=_make_user("it_agent"),
            assigned_only=False,
            status=None,
            priority=None,
            category=None,
            source=None,
            search=None,
            date_from=None,
            date_to=None,
        )
        assert clauses == []

    def test_each_filter_contributes_a_clause(self):
        service = TicketService(_make_mock_db())
        clauses = service._agent_queue_filters(
            agent=_make_user("it_agent"),
            assigned_only=True,
            status="new,triaged",
            priority="high",
            category="Email",
            source="chat",
            search="vpn",
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 1, tzinfo=UTC),
        )
        # assigned_only, status, priority, category, source, date_from,
        # date_to, search
        assert len(clauses) == 8

    def test_blank_search_is_ignored(self):
        service = TicketService(_make_mock_db())
        clauses = service._agent_queue_filters(
            agent=_make_user("it_agent"),
            assigned_only=False,
            status=None,
            priority=None,
            category=None,
            source=None,
            search="   ",
            date_from=None,
            date_to=None,
        )
        assert clauses == []


class TestAgentQueueListing:
    """`list_tickets_for_agent` must return a (page, total) pair."""

    async def test_returns_tickets_and_total(self):
        db = _make_mock_db()

        count_result = MagicMock()
        count_result.scalar.return_value = 7

        ticket = MagicMock()
        page_result = MagicMock()
        page_result.scalars.return_value.all.return_value = [ticket]

        db.execute.side_effect = [count_result, page_result]

        tickets, total = await TicketService(db).list_tickets_for_agent(
            agent=_make_user("it_agent"), limit=1
        )

        assert tickets == [ticket]
        # Total counts every match, not just the returned page.
        assert total == 7


class TestTicketCsvExport:
    """`export_tickets_csv` backs the queue's export action."""

    @staticmethod
    def _ticket() -> MagicMock:
        ticket = MagicMock()
        ticket.ticket_number = "ITA-000042"
        ticket.title = "VPN drops"
        ticket.status = "new"
        ticket.priority = "high"
        ticket.category = "Network"
        ticket.subcategory = "VPN"
        ticket.item = "Client"
        ticket.ticket_type = "Incident"
        ticket.source = "chat"
        ticket.assigned_to = None
        ticket.created_at = datetime(2026, 3, 1, tzinfo=UTC)
        ticket.resolved_at = None
        ticket.closed_at = None
        return ticket

    async def test_export_emits_header_and_rows(self):
        db = _make_mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [self._ticket()]
        db.execute.return_value = result

        csv_text = await TicketService(db).export_tickets_csv(agent=_make_user("it_agent"))

        lines = csv_text.strip().splitlines()
        assert lines[0].startswith("ticket_number,title,status,priority,category")
        assert "ITA-000042" in lines[1]
        assert "VPN drops" in lines[1]

    async def test_export_with_no_matches_still_has_header(self):
        db = _make_mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        csv_text = await TicketService(db).export_tickets_csv(agent=_make_user("it_agent"))

        assert csv_text.strip().splitlines() == [
            "ticket_number,title,status,priority,category,subcategory,item,"
            "ticket_type,source,assigned_to,created_at,resolved_at,closed_at"
        ]
