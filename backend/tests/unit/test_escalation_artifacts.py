"""Unit tests for chat-escalation artifacts (transcript snapshot + context).

These exercise the EscalationService assembly logic and ChatService wiring with
a lightweight fake async session — no Postgres required. DB-integration and the
full end-to-end flow are covered by the QA checklist
(docs/development/chat-escalation-qa-checklist.md) and run in Docker.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.models.escalation import EscalationContext, TranscriptSnapshot
from app.models.ticket import Ticket
from app.services.agents import chat_service as cs_mod
from app.services.agents.chat_service import ChatService
from app.services.escalation_service import EscalationService, extract_transcript


# ── Fake async session ────────────────────────────────────────────────────


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


def _requester():
    return MagicMock(id=uuid.uuid4(), email="emp@aditi.com", full_name="Emp",
                     primary_role="employee")


# ── extract_transcript (pure) ──────────────────────────────────────────────


class TestExtractTranscript:
    def test_ordering_and_role_mapping(self):
        msgs = [
            HumanMessage(content="Outlook won't send"),
            AIMessage(content="Let's check your mailbox quota"),
            HumanMessage(content="still broken"),
        ]
        out = extract_transcript(msgs)
        assert [m["seq"] for m in out] == [0, 1, 2]
        assert [m["role"] for m in out] == ["employee", "assistant", "employee"]
        assert out[0]["content"] == "Outlook won't send"

    def test_accepts_dicts(self):
        out = extract_transcript(
            [{"role": "user", "content": "hi"}, {"role": "system", "content": "evt"}]
        )
        assert out[0]["role"] == "employee"
        assert out[1]["role"] == "system"

    def test_skips_empty_content(self):
        out = extract_transcript([HumanMessage(content=""), AIMessage(content="x")])
        assert len(out) == 1
        assert out[0]["seq"] == 0

    def test_returns_independent_copy(self):
        """Mutating the source after extraction must not change the snapshot."""
        msgs = [HumanMessage(content="original")]
        out = extract_transcript(msgs)
        msgs.append(AIMessage(content="added later"))
        assert len(out) == 1  # snapshot unchanged by later mutation
        assert out[0]["content"] == "original"


# ── Artifact creation ───────────────────────────────────────────────────────


class TestCreateArtifacts:
    async def test_creates_snapshot_and_context(self):
        ticket = _ticket()
        session = FakeSession(context_result=None)
        svc = EscalationService(session)
        state = {
            "messages": [
                HumanMessage(content="Outlook mailbox full"),
                AIMessage(content="Try archiving old mail"),
                HumanMessage(content="didn't work"),
            ],
            "issue_category": "email/outlook",
            "issue_subtype": "mailbox-full",
            "resolution_confidence": 0.2,
            "escalation_reason": "AI exhausted grounded steps",
            "knowledge_results": [{"id": "kb1", "title": "Mailbox quota", "score": 0.7}],
            "knowledge_citations": [{"article_id": "kb1", "title": "Mailbox quota"}],
            "diagnostic_context": {
                "exact_problem_statement": "Mailbox full, cannot send",
                "affected_system": "outlook",
                "failed_steps": ["Archive old mail", "Empty deleted items"],
                "live_agent_requested": False,
            },
        }

        context = await svc.create_escalation_artifacts(
            ticket=ticket, chat_session_id="sess-1", state=state, requester=_requester()
        )

        snapshots = [o for o in session.added if isinstance(o, TranscriptSnapshot)]
        contexts = [o for o in session.added if isinstance(o, EscalationContext)]
        assert len(snapshots) == 1
        assert len(contexts) == 1
        snap = snapshots[0]
        assert snap.message_count == 3
        assert snap.messages[0]["role"] == "employee"
        # Context carries attempted steps + escalation reason + gap tags.
        assert context.escalation_reason == "AI exhausted grounded steps"
        assert len(context.ai_attempted_steps) == 2
        assert context.ai_attempted_steps[0]["outcome"] == "failed"
        assert "article_suggested_but_unresolved" in context.kb_gap_tags
        assert context.transcript_snapshot_id == snap.id
        assert context.live_support_required is True

    async def test_idempotent_when_context_exists(self):
        existing = EscalationContext(ticket_id=uuid.uuid4(), chat_session_id="s")
        existing.id = uuid.uuid4()
        session = FakeSession(context_result=existing)
        svc = EscalationService(session)

        result = await svc.create_escalation_artifacts(
            ticket=_ticket(), chat_session_id="sess-1", state={"messages": []}
        )
        assert result is existing
        # No new snapshot/context were added.
        assert session.added == []

    async def test_snapshot_immutable_against_later_state_change(self):
        ticket = _ticket()
        session = FakeSession(context_result=None)
        svc = EscalationService(session)
        messages = [HumanMessage(content="first"), AIMessage(content="reply")]
        state = {"messages": messages, "diagnostic_context": {}}

        await svc.create_escalation_artifacts(
            ticket=ticket, chat_session_id="s", state=state
        )
        # The snapshot is in session.added (not via ORM relationship in unit test).
        snap = next(o for o in session.added if isinstance(o, TranscriptSnapshot))
        original_count = snap.message_count

        # Later session mutation must NOT alter the captured snapshot.
        messages.append(HumanMessage(content="added after handoff"))
        state["messages"][0].content = "tampered"
        assert snap.message_count == original_count == 2
        assert snap.messages[0]["content"] == "first"


# ── Handoff view (summary first, transcript second) ─────────────────────────


class TestHandoffView:
    def _context_with_transcript(self, ticket):
        snap = TranscriptSnapshot(
            ticket_id=ticket.id,
            chat_session_id="s",
            message_count=2,
            messages=[
                {"seq": 0, "role": "employee", "content": "help", "message_type": None,
                 "timestamp": None},
                {"seq": 1, "role": "assistant", "content": "try this", "message_type": None,
                 "timestamp": None},
            ],
            context_version="1.0",
        )
        snap.id = uuid.uuid4()
        snap.captured_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        ctx = EscalationContext(
            ticket_id=ticket.id,
            transcript_snapshot_id=snap.id,
            chat_session_id="s",
        )
        ctx.id = uuid.uuid4()
        ctx.escalation_created_at = snap.captured_at
        ctx.issue_summary = "Mailbox full"
        ctx.category = "email/outlook"
        ctx.subcategory = "mailbox-full"
        ctx.affected_system = "outlook"
        ctx.urgency = "high"
        ctx.ai_confidence = 0.2
        ctx.ai_resolution_status = "unresolved"
        ctx.escalation_reason = "exhausted"
        ctx.user_problem_statement = "cannot send mail"
        ctx.detected_intent = "troubleshoot"
        ctx.ai_attempted_steps = [
            {"instruction": "Archive mail", "outcome": "failed", "source_kb_title": None}
        ]
        ctx.kb_articles_referenced = [
            {"article_id": "kb1", "title": "Quota", "relevance": 0.7}
        ]
        ctx.kb_gap_tags = ["article_suggested_but_unresolved"]
        ctx.transcript_snapshot = snap
        return ctx

    async def test_returns_summary_and_transcript(self):
        ticket = _ticket()
        ctx = self._context_with_transcript(ticket)
        session = FakeSession(ticket=ticket, context_result=ctx)
        view = await EscalationService(session).get_handoff_view(ticket.id)

        assert view is not None
        assert view.has_structured_context is True
        assert view.issue_summary == "Mailbox full"
        assert len(view.steps_attempted) == 1
        assert view.kb_gap_tags == ["article_suggested_but_unresolved"]
        # Transcript present + ordered.
        assert view.transcript is not None
        assert view.transcript.message_count == 2
        assert [m.seq for m in view.transcript.messages] == [0, 1]
        assert view.transcript.messages[0].role == "employee"

    async def test_degrades_without_context(self):
        ticket = _ticket()
        session = FakeSession(ticket=ticket, context_result=None)
        view = await EscalationService(session).get_handoff_view(ticket.id)
        assert view is not None
        assert view.has_structured_context is False
        assert view.issue_summary  # falls back to ticket fields
        assert view.transcript is None


# ── Resolution comparison ────────────────────────────────────────────────────


class TestResolutionComparison:
    async def test_records_comparison_fields(self):
        ctx = EscalationContext(ticket_id=uuid.uuid4(), chat_session_id="s")
        ctx.id = uuid.uuid4()
        session = FakeSession(context_result=ctx)
        updated = await EscalationService(session).record_resolution_comparison(
            ticket_id=ctx.ticket_id,
            specialist_resolution_summary="Increased mailbox quota in Exchange admin",
            specialist_resolution_steps=["Open EAC", "Raise quota", "Notify user"],
            final_resolution_category="email/outlook",
            ai_vs_specialist_resolution_gap="AI suggested self-serve archive; fix needed admin action",
            kb_candidate_flag=True,
        )
        assert updated is ctx
        assert ctx.kb_candidate_flag is True
        assert ctx.specialist_resolution_steps == ["Open EAC", "Raise quota", "Notify user"]
        assert ctx.resolution_compared_at is not None

    async def test_no_context_returns_none(self):
        session = FakeSession(context_result=None)
        result = await EscalationService(session).record_resolution_comparison(
            ticket_id=uuid.uuid4(),
            specialist_resolution_summary="x",
            specialist_resolution_steps=[],
            final_resolution_category=None,
            ai_vs_specialist_resolution_gap=None,
            kb_candidate_flag=False,
        )
        assert result is None


# ── ChatService wiring ───────────────────────────────────────────────────────


class TestChatServiceWiring:
    async def test_persist_and_queue_creates_artifacts_with_state(self):
        cs_mod._sessions.clear()
        cs_mod._session_tickets.clear()

        ticket = MagicMock()
        ticket.id = uuid.uuid4()
        ticket.ticket_number = "ITA-000099"
        ticket.status = "triaged"
        ticket.priority = "high"

        svc = MagicMock()
        svc.create_ticket = AsyncMock(return_value=ticket)
        svc.request_live_agent = AsyncMock()
        svc.db = MagicMock()
        svc.db.commit = AsyncMock()

        chat = ChatService(svc)
        state = {
            "ticket_draft": {"title": "T", "description": "D", "priority": "high",
                             "category": "email/outlook", "problem_statement": "P"},
            "messages": [HumanMessage(content="hi")],
            "diagnostic_context": {},
        }

        with patch(
            "app.services.escalation_service.EscalationService"
        ) as MockEsc:
            instance = MockEsc.return_value
            instance.create_escalation_artifacts = AsyncMock()
            ref = await chat._persist_and_queue(
                "sess-x", state["ticket_draft"], _requester(), state=state
            )

        assert ref.ticket_number == "ITA-000099"
        instance.create_escalation_artifacts.assert_awaited_once()
        kwargs = instance.create_escalation_artifacts.call_args.kwargs
        assert kwargs["chat_session_id"] == "sess-x"
        assert kwargs["state"] is state
        # Ticket still created + queued + committed.
        svc.create_ticket.assert_awaited_once()
        svc.request_live_agent.assert_awaited_once()
        svc.db.commit.assert_awaited_once()
