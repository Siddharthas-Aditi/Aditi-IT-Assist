"""B2: web-research findings from state are persisted on the escalation context."""

import uuid

from app.models.escalation import EscalationContext
from app.models.ticket import Ticket
from app.services.escalation_service import EscalationService


def test_model_has_web_research_findings_column():
    assert "web_research_findings" in EscalationContext.__table__.columns


# ── Service-level persistence ────────────────────────────────────────────────


class FakeSession:
    """Minimal async session: records adds, assigns PKs on flush."""

    def __init__(self, *, ticket=None, context_result=None):
        self._ticket = ticket
        self._context_result = context_result
        self.added: list = []
        self.committed = False

    async def get(self, _model, _id):
        return self._ticket

    async def execute(self, _stmt):
        from unittest.mock import MagicMock

        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=self._context_result)
        return res

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.committed = True


def _ticket(**kw):
    t = Ticket(
        ticket_number=kw.get("ticket_number", "ITA-000042"),
        title=kw.get("title", "Outlook Email Issue"),
        description="d",
        requester_id=uuid.uuid4(),
    )
    t.id = uuid.uuid4()
    t.category = kw.get("category", "email/outlook")
    t.subcategory = kw.get("subcategory", "mailbox-full")
    t.ai_summary = kw.get("ai_summary", "Mailbox is full and cannot send mail")
    t.ai_confidence = kw.get("ai_confidence", 0.2)
    t.urgency = kw.get("urgency", "high")
    return t


class TestWebResearchFindingsPersistence:
    async def test_create_escalation_artifacts_persists_web_research_findings(self):
        ticket = _ticket()
        session = FakeSession(context_result=None)
        svc = EscalationService(session)
        findings = [
            {
                "title": "Outlook mailbox quota errors",
                "url": "https://support.microsoft.com/mailbox-quota",
                "snippet": "How to resolve mailbox full errors in Outlook.",
                "trust_tier": "official_vendor",
                "provider": "bing",
            }
        ]
        state = {"messages": [], "web_research_findings": findings}

        context = await svc.create_escalation_artifacts(
            ticket=ticket, chat_session_id="sess-1", state=state
        )

        assert context.web_research_findings == findings

    async def test_create_escalation_artifacts_defaults_to_none(self):
        ticket = _ticket()
        session = FakeSession(context_result=None)
        svc = EscalationService(session)

        context = await svc.create_escalation_artifacts(
            ticket=ticket, chat_session_id="sess-1", state={"messages": []}
        )

        assert context.web_research_findings is None
