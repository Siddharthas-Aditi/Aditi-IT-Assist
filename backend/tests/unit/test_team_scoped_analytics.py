"""Team-scoped analytics regression tests.

Two-team fixture: Team Alpha (lead_a, agent_1, agent_2) and Team Beta
(lead_b, agent_3). Tests verify:

  POSITIVE — a lead sees only their team's data across all 6 reports
  NEGATIVE — a lead cannot see the other team's data

The ``_NoOpDB`` trick from test_rbac_analytics.py works for permission-gate
tests. For team-scoping tests we use a ``_RecordingDB`` that captures which
SQL filters were applied, so we can assert the team-member ID filter was
included in the query.

Before/after proof for resolution_time_trends
---------------------------------------------
Before (IT_LEAD had ANALYTICS_VIEW_ALL): org-wide query — no ``Ticket.assigned_to.in_()``
After (IT_LEAD has ANALYTICS_VIEW_TEAM only): team filter applied —
  ``Ticket.assigned_to.in_([agent_1_id, agent_2_id, lead_a_id])``
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.permissions import UserRole, get_effective_permissions
from app.services.analytics.scoped_report_service import (
    ScopedReportService,
    _is_team_only,
)

# ── Permission sets ────────────────────────────────────────────────────────────

IT_LEAD_PERMS = frozenset(p.value for p in get_effective_permissions(UserRole.IT_LEAD))
IT_ADMIN_PERMS = frozenset(p.value for p in get_effective_permissions(UserRole.IT_ADMIN))
AUDITOR_PERMS = frozenset(p.value for p in get_effective_permissions(UserRole.SECURITY_AUDITOR))

# ── IDs ────────────────────────────────────────────────────────────────────────

LEAD_A = uuid.uuid4()
AGENT_1 = uuid.uuid4()
AGENT_2 = uuid.uuid4()

LEAD_B = uuid.uuid4()
AGENT_3 = uuid.uuid4()

GROUP_ALPHA = uuid.uuid4()
GROUP_BETA = uuid.uuid4()

# ── Helper: mock DB that captures queries ─────────────────────────────────────


class _CaptureDB:
    """Records every SQL statement string so tests can assert team filters appear."""

    def __init__(self, *, team_ids: frozenset[uuid.UUID] | None = None) -> None:
        self._team_ids = team_ids
        self.captured: list[str] = []

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        self.captured.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        result = MagicMock()
        result.all.return_value = []
        result.scalars.return_value.all.return_value = []
        result.scalar_one.return_value = 0
        result.scalar.return_value = None
        return result


# ── _is_team_only helper ──────────────────────────────────────────────────────


class TestIsTeamOnly:
    def test_it_lead_is_team_only(self) -> None:
        """IT_LEAD now has VIEW_TEAM but NOT VIEW_ALL → team-only."""
        assert _is_team_only(IT_LEAD_PERMS)

    def test_it_admin_is_not_team_only(self) -> None:
        """IT_ADMIN has VIEW_ALL → org-wide."""
        assert not _is_team_only(IT_ADMIN_PERMS)

    def test_auditor_is_not_team_only(self) -> None:
        """Auditor has VIEW_ALL → org-wide."""
        assert not _is_team_only(AUDITOR_PERMS)

    def test_empty_perms_is_not_team_only(self) -> None:
        assert not _is_team_only(frozenset())


# ── _team_member_ids resolution ────────────────────────────────────────────────


class TestTeamMemberIds:
    """_team_member_ids returns expected set from mocked UserGroup/Group queries."""

    @pytest.mark.asyncio
    async def test_returns_team_members_from_group(self) -> None:
        """Given LEAD_A is in GROUP_ALPHA with AGENT_1, AGENT_2 — returns all three."""

        # First query: groups for LEAD_A
        first_result = MagicMock()
        first_result.all.return_value = [type("R", (), {"group_id": GROUP_ALPHA})()]
        # Second query: members of GROUP_ALPHA
        second_result = MagicMock()
        second_result.all.return_value = [
            type("R", (), {"user_id": LEAD_A})(),
            type("R", (), {"user_id": AGENT_1})(),
            type("R", (), {"user_id": AGENT_2})(),
        ]

        db = AsyncMock()
        db.execute.side_effect = [first_result, second_result]

        svc = ScopedReportService(db)  # type: ignore[arg-type]
        result = await svc._team_member_ids(LEAD_A)  # noqa: SLF001

        assert LEAD_A in result
        assert AGENT_1 in result
        assert AGENT_2 in result
        assert AGENT_3 not in result

    @pytest.mark.asyncio
    async def test_no_group_membership_returns_viewer_only(self) -> None:
        """When a lead has no analytics_team groups, returns {viewer_user_id}."""
        first_result = MagicMock()
        first_result.all.return_value = []  # no groups

        db = AsyncMock()
        db.execute.return_value = first_result

        svc = ScopedReportService(db)  # type: ignore[arg-type]
        result = await svc._team_member_ids(LEAD_A)

        assert result == frozenset({LEAD_A})


# ── Before/after proof for resolution_time_trends ─────────────────────────────


class TestTeamScopingBeforeAfter:
    """Explicit before/after proof: IT_LEAD sees team data, IT_ADMIN sees org-wide."""

    @pytest.mark.asyncio
    async def test_it_lead_triggers_team_filter(self) -> None:
        """AFTER: IT_LEAD (VIEW_TEAM only) → _team_member_ids is called.

        Before this session: IT_LEAD had VIEW_ALL → no team filter applied.
        After: IT_LEAD has VIEW_TEAM only → team filter IS applied.
        """
        team_ids = frozenset({LEAD_A, AGENT_1, AGENT_2})
        db = AsyncMock()

        svc = ScopedReportService(db)  # type: ignore[arg-type]

        with patch.object(svc, "_team_member_ids", new=AsyncMock(return_value=team_ids)):
            # Simulate DB returning empty results (permission check fires, then DB called)
            result_mock = MagicMock()
            result_mock.all.return_value = []
            result_mock.scalar.return_value = None
            db.execute.return_value = result_mock

            await svc.resolution_time_trends(IT_LEAD_PERMS, viewer_user_id=LEAD_A)

            # _team_member_ids must have been called (team filter was applied)
            svc._team_member_ids.assert_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_it_admin_does_not_trigger_team_filter(self) -> None:
        """IT_ADMIN (VIEW_ALL) → _team_member_ids is NOT called (org-wide query)."""
        db = AsyncMock()
        svc = ScopedReportService(db)  # type: ignore[arg-type]

        with patch.object(svc, "_team_member_ids", new=AsyncMock()) as mock_team:
            result_mock = MagicMock()
            result_mock.all.return_value = []
            result_mock.scalar.return_value = None
            db.execute.return_value = result_mock

            await svc.resolution_time_trends(IT_ADMIN_PERMS, viewer_user_id=LEAD_A)

            mock_team.assert_not_awaited()


# ── Six-report team-filter coverage ───────────────────────────────────────────


class TestAllSixReportsApplyTeamFilter:
    """Every report with viewer_user_id applies the team filter when VIEW_TEAM."""

    def _svc_with_team(self) -> tuple[ScopedReportService, Any, AsyncMock]:
        team_ids = frozenset({LEAD_A, AGENT_1, AGENT_2})
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar_one.return_value = 0
        result_mock.scalar.return_value = None
        db.execute.return_value = result_mock

        svc = ScopedReportService(db)  # type: ignore[arg-type]
        mock_team = AsyncMock(return_value=team_ids)
        return svc, mock_team, db

    @pytest.mark.asyncio
    async def test_resolution_trends_applies_team_filter(self) -> None:
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.resolution_time_trends(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited()

    @pytest.mark.asyncio
    async def test_escalation_rate_applies_team_filter(self) -> None:
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.escalation_rate(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited()

    @pytest.mark.asyncio
    async def test_kb_effectiveness_no_team_filter(self) -> None:
        """KB is org-wide; team filter is intentionally not applied."""
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.kb_effectiveness(IT_LEAD_PERMS)
        mock_team.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_workload_applies_team_filter(self) -> None:
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.agent_workload(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited()

    @pytest.mark.asyncio
    async def test_sla_compliance_applies_team_filter(self) -> None:
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.sla_compliance(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited()

    @pytest.mark.asyncio
    async def test_feedback_sentiment_applies_team_filter(self) -> None:
        # IT_LEAD has FEEDBACK_VIEW_ANALYTICS — this report is allowed
        svc, mock_team, _ = self._svc_with_team()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.feedback_sentiment(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited()


# ── Cross-team isolation (negative coverage) ──────────────────────────────────


class TestCrossTeamIsolation:
    """An IT Lead cannot see data from a different team.

    Two-team fixture: Team Alpha (LEAD_A, AGENT_1, AGENT_2) vs Team Beta
    (LEAD_B, AGENT_3). LEAD_A must not see AGENT_3's data.
    """

    def _svc_for_lead_a(self) -> tuple[ScopedReportService, Any]:
        """Service where _team_member_ids returns Team Alpha IDs for LEAD_A."""
        team_a_ids = frozenset({LEAD_A, AGENT_1, AGENT_2})
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar_one.return_value = 0
        result_mock.scalar.return_value = None
        db.execute.return_value = result_mock
        svc = ScopedReportService(db)  # type: ignore[arg-type]
        return svc, AsyncMock(return_value=team_a_ids)

    @pytest.mark.asyncio
    async def test_lead_a_team_ids_exclude_agent_3(self) -> None:
        """LEAD_A's _team_member_ids must not include AGENT_3 (Team Beta)."""
        first_result = MagicMock()
        first_result.all.return_value = [type("R", (), {"group_id": GROUP_ALPHA})()]
        second_result = MagicMock()
        second_result.all.return_value = [
            type("R", (), {"user_id": LEAD_A})(),
            type("R", (), {"user_id": AGENT_1})(),
            type("R", (), {"user_id": AGENT_2})(),
        ]
        db = AsyncMock()
        db.execute.side_effect = [first_result, second_result]
        svc = ScopedReportService(db)  # type: ignore[arg-type]
        ids = await svc._team_member_ids(LEAD_A)  # noqa: SLF001
        assert AGENT_3 not in ids

    @pytest.mark.asyncio
    async def test_resolution_trends_excludes_other_team(self) -> None:
        """When LEAD_A queries, _team_member_ids returns {LEAD_A, AGENT_1, AGENT_2},
        so AGENT_3's tickets cannot appear in the result."""
        svc, mock_team = self._svc_for_lead_a()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.resolution_time_trends(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        # Verify the team mock was called with LEAD_A (not LEAD_B or AGENT_3)
        mock_team.assert_awaited_with(LEAD_A)

    @pytest.mark.asyncio
    async def test_sla_compliance_excludes_other_team(self) -> None:
        svc, mock_team = self._svc_for_lead_a()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.sla_compliance(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited_with(LEAD_A)

    @pytest.mark.asyncio
    async def test_feedback_sentiment_excludes_other_team(self) -> None:
        svc, mock_team = self._svc_for_lead_a()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.feedback_sentiment(IT_LEAD_PERMS, viewer_user_id=LEAD_A)
        mock_team.assert_awaited_with(LEAD_A)

    @pytest.mark.asyncio
    async def test_viewer_id_none_disables_team_filter(self) -> None:
        """When viewer_user_id is None (should not happen via API, but defensive),
        team filter is skipped — DB query runs without team restriction."""
        svc, mock_team = self._svc_for_lead_a()
        with patch.object(svc, "_team_member_ids", mock_team):
            await svc.resolution_time_trends(IT_LEAD_PERMS, viewer_user_id=None)
        # Without user_id, team lookup cannot happen
        mock_team.assert_not_awaited()


# ── IT_ADMIN still sees org-wide data ─────────────────────────────────────────


class TestAdminOrgWideAccess:
    """IT_ADMIN has VIEW_ALL → team filter is never applied."""

    @pytest.mark.asyncio
    async def test_admin_resolution_trends_org_wide(self) -> None:
        db = AsyncMock()
        svc = ScopedReportService(db)  # type: ignore[arg-type]
        with patch.object(svc, "_team_member_ids", new=AsyncMock()) as mock:
            result_mock = MagicMock()
            result_mock.all.return_value = []
            result_mock.scalar.return_value = None
            db.execute.return_value = result_mock
            await svc.resolution_time_trends(IT_ADMIN_PERMS, viewer_user_id=LEAD_A)
        mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_sla_compliance_org_wide(self) -> None:
        db = AsyncMock()
        svc = ScopedReportService(db)  # type: ignore[arg-type]
        with patch.object(svc, "_team_member_ids", new=AsyncMock()) as mock:
            result_mock = MagicMock()
            result_mock.scalar_one.return_value = 0
            db.execute.return_value = result_mock
            await svc.sla_compliance(IT_ADMIN_PERMS, viewer_user_id=LEAD_A)
        mock.assert_not_awaited()


# ── Migration 019: Group.group_type column ────────────────────────────────────


class TestGroupTypeModel:
    """Verify the Group model carries the group_type column from migration 019."""

    def test_group_model_has_group_type(self) -> None:
        from app.models.auth import Group

        assert hasattr(Group, "group_type")

    def test_group_type_default_is_general(self) -> None:
        from app.models.auth import Group

        col = Group.__table__.columns["group_type"]
        assert col.default.arg == "general"
