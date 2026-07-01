"""API tests for the specialist handoff-view + resolution-comparison endpoints.

RBAC: specialist_queue:view / :resolve (it_agent and above). The EscalationService
is patched so no DB is required.
"""

import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.schemas.escalation import (
    AttemptedStepOut,
    EscalationContextOut,
    SpecialistHandoffView,
    TranscriptMessageOut,
    TranscriptSnapshotOut,
)

TID = "00000000-0000-0000-0000-0000000000aa"


def _handoff_view() -> SpecialistHandoffView:
    return SpecialistHandoffView(
        ticket_id=uuid.UUID(TID),
        ticket_number="ITA-000042",
        issue_summary="Mailbox full",
        category="email/outlook",
        subcategory="mailbox-full",
        affected_system="outlook",
        urgency="high",
        ai_confidence=0.2,
        ai_resolution_status="unresolved",
        escalation_reason="exhausted grounded steps",
        user_problem_statement="cannot send mail",
        steps_attempted=[AttemptedStepOut(instruction="Archive mail", outcome="failed")],
        kb_gap_tags=["article_suggested_but_unresolved"],
        transcript=TranscriptSnapshotOut(
            id=uuid.uuid4(),
            chat_session_id="s",
            captured_at="2026-06-27T10:00:00Z",
            message_count=2,
            context_version="1.0",
            messages=[
                TranscriptMessageOut(seq=0, role="employee", content="help"),
                TranscriptMessageOut(seq=1, role="assistant", content="try this"),
            ],
        ),
    )


def _context_out() -> EscalationContextOut:
    return EscalationContextOut(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(TID),
        chat_session_id="s",
        escalation_created_at="2026-06-27T10:00:00Z",
        kb_gap_tags=["no_matching_article"],
    )


class TestHandoffView:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/specialist-queue/{TID}/handoff-view")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"/api/v1/specialist-queue/{TID}/handoff-view")
        assert resp.status_code == 403

    async def test_agent_gets_summary_first_view(self, agent_client: AsyncClient):
        with patch("app.api.v1.specialist_queue.EscalationService") as cls:
            cls.return_value.get_handoff_view = AsyncMock(return_value=_handoff_view())
            resp = await agent_client.get(
                f"/api/v1/specialist-queue/{TID}/handoff-view"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["issue_summary"] == "Mailbox full"
        assert body["steps_attempted"][0]["outcome"] == "failed"
        # Summary first, transcript second — both present + ordered.
        assert body["transcript"]["message_count"] == 2
        assert body["transcript"]["messages"][0]["role"] == "employee"

    async def test_404_when_ticket_missing(self, agent_client: AsyncClient):
        with patch("app.api.v1.specialist_queue.EscalationService") as cls:
            cls.return_value.get_handoff_view = AsyncMock(return_value=None)
            resp = await agent_client.get(
                f"/api/v1/specialist-queue/{TID}/handoff-view"
            )
        assert resp.status_code == 404


class TestResolutionComparison:
    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.post(
            f"/api/v1/specialist-queue/{TID}/resolution-comparison",
            json={"specialist_resolution_summary": "x"},
        )
        assert resp.status_code == 403

    async def test_agent_records_comparison(self, agent_client: AsyncClient):
        with patch("app.api.v1.specialist_queue.EscalationService") as cls:
            inst = cls.return_value
            inst.record_resolution_comparison = AsyncMock(return_value=object())
            inst.get_context_out = AsyncMock(return_value=_context_out())
            resp = await agent_client.post(
                f"/api/v1/specialist-queue/{TID}/resolution-comparison",
                json={
                    "specialist_resolution_summary": "Raised mailbox quota",
                    "specialist_resolution_steps": ["EAC", "raise quota"],
                    "kb_candidate_flag": True,
                },
            )
        assert resp.status_code == 200
        inst.record_resolution_comparison.assert_awaited_once()

    async def test_404_when_no_context(self, agent_client: AsyncClient):
        with patch("app.api.v1.specialist_queue.EscalationService") as cls:
            cls.return_value.record_resolution_comparison = AsyncMock(return_value=None)
            resp = await agent_client.post(
                f"/api/v1/specialist-queue/{TID}/resolution-comparison",
                json={"specialist_resolution_summary": "x"},
            )
        assert resp.status_code == 404
