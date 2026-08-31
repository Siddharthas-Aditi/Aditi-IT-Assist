"""Regression coverage for RAG reliability boundaries and recovery."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.models.support import Message, SupportSession
from app.services.agents.chat_service import ChatService
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.escalation_triggers import EscalationTrigger, evaluate_escalation
from app.services.agents.session_store import (
    InMemorySessionStore,
    get_session_store,
    set_session_store,
)
from app.services.support_session_service import SupportSessionService
from app.workflows.graph import route_after_retrieval
from app.workflows.nodes.escalation import escalation_node
from app.workflows.nodes.resolution import resolution_node


@pytest.mark.parametrize(
    ("stage", "state", "expected"),
    [
        (
            "triage",
            {"diagnostic_context": {"live_agent_requested": True}},
            EscalationTrigger.USER_REQUEST,
        ),
        (
            "triage",
            {"turn_count": 10, "issue_category": "email/outlook"},
            EscalationTrigger.MAX_TURNS,
        ),
        ("triage", {"turn_count": 1}, EscalationTrigger.UNCLASSIFIABLE_ISSUE),
        ("retrieval", {"knowledge_results": []}, EscalationTrigger.NO_GROUNDED_ARTICLES),
        (
            "retrieval",
            {"knowledge_results": [{"id": "kb-1"}], "knowledge_confidence": 0.34},
            EscalationTrigger.LOW_RETRIEVAL_CONFIDENCE,
        ),
        (
            "progression",
            {"diagnostic_context": {"failed_steps": ["one", "two", "three"]}},
            EscalationTrigger.FAILED_STEP_THRESHOLD,
        ),
        (
            "resolution",
            {"diagnostic_context": {"phase": "escalating"}, "resolution_steps": []},
            EscalationTrigger.GROUNDED_STEPS_EXHAUSTED,
        ),
        (
            "resolution",
            {"resolution_steps": [{"instruction": "x"}], "resolution_confidence": 0.34},
            EscalationTrigger.LOW_RESOLUTION_CONFIDENCE,
        ),
    ],
)
def test_each_escalation_trigger_is_deterministic(stage, state, expected):
    decision = evaluate_escalation(
        state,
        stage=stage,
        minimum_confidence=0.35,
        miss_threshold=3,
        max_turns=10,
    )
    assert decision.trigger is expected


def test_escalation_policy_does_not_fire_for_reliable_grounded_resolution():
    decision = evaluate_escalation(
        {
            "turn_count": 2,
            "issue_category": "email/outlook",
            "knowledge_results": [{"id": "kb-1"}],
            "knowledge_confidence": 0.8,
            "resolution_steps": [{"instruction": "Archive old mail"}],
            "resolution_confidence": 0.8,
            "diagnostic_context": {"failed_steps": [], "phase": "confirming"},
        },
        stage="resolution",
        minimum_confidence=0.35,
        miss_threshold=3,
        max_turns=10,
    )
    assert not decision.should_escalate


async def test_low_confidence_retrieval_refuses_generation_and_escalates():
    state = {
        "session_id": "reliability-session",
        "messages": [HumanMessage(content="My Outlook issue is unusual")],
        "knowledge_results": [
            {
                "id": "kb-weak",
                "title": "Generic Outlook article",
                "category": "email/outlook",
                "steps": ["Restart Outlook"],
            }
        ],
        "knowledge_confidence": 0.34,
        "retrieval_trace": {"has_subtype_match": False},
        "diagnostic_context": DiagnosticContext(issue_category="email/outlook").to_dict(),
    }

    assert route_after_retrieval(state) == "escalate"
    with patch("app.workflows.nodes.resolution.get_llm_service") as llm:
        result = await resolution_node(state)

    assert result["resolution_steps"] == []
    assert result["diagnostic_context"]["phase"] == "escalating"
    assert "reliable, approved guidance" in result["escalation_reason"]
    llm.assert_not_called()

    offer = await escalation_node(
        {
            **state,
            **result,
            "messages": [HumanMessage(content="My Outlook issue is unusual")],
            "resolution_attempts": 0,
        }
    )
    assert "don’t want to guess" in offer["messages"][0].content


def test_grounded_response_includes_visible_citations_in_api_payload():
    response = ChatService()._format_response(
        "session-1",
        {
            "messages": [AIMessage(content="Try archiving old mail.")],
            "resolution_confidence": 0.8,
            "knowledge_citations": [],
            "knowledge_results": [
                {
                    "id": "kb-123",
                    "title": "Mailbox quota management",
                    "version": "4",
                    "citation_label": "KB-OUTLOOK-123",
                    "category": "email/outlook",
                }
            ],
        },
    )

    assert response.citations
    assert response.citations[0].article_id == "kb-123"
    assert response.citations[0].version == "4"


async def test_database_recovery_restores_step_history_after_session_store_loss():
    session_id = str(uuid4())
    user_id = str(uuid4())
    context = DiagnosticContext(
        issue_category="email/outlook",
        issue_subtype="mailbox-full",
        suggested_steps=["Archive old mail"],
        failed_steps=["Empty deleted items"],
    )
    row = SupportSession(
        id=uuid4(),
        user_id=uuid4(),
        status="active",
        session_type="ai_chat",
        created_at=datetime.now(UTC),
        metadata_json={
            "workflow_recovery": {
                "diagnostic_context": context.to_dict(),
                "turn_count": 2,
                "issue_category": "email/outlook",
            }
        },
        messages=[],
    )
    row.id = UUID(session_id)
    row.user_id = UUID(user_id)
    row.messages = [
        Message(
            id=uuid4(),
            session_id=row.id,
            role="user",
            content="Mailbox is full",
            message_type="text",
            created_at=datetime.now(UTC),
        ),
        Message(
            id=uuid4(),
            session_id=row.id,
            role="assistant",
            content="Try archiving old mail",
            message_type="text",
            created_at=datetime.now(UTC),
        ),
    ]
    durable = SupportSessionService(AsyncMock())
    durable.repo = AsyncMock()
    durable.repo.get_with_messages = AsyncMock(return_value=row)

    # Simulate a fresh process: the new in-memory store has no envelope.
    original_store = get_session_store()
    set_session_store(InMemorySessionStore())
    try:
        service = ChatService(support_session_service=durable)
        recovered = await service._load_owned(session_id, user_id)
    finally:
        set_session_store(original_store)

    assert recovered is not None
    diagnostic = recovered.state["diagnostic_context"]
    assert diagnostic["suggested_steps"] == ["Archive old mail"]
    assert diagnostic["failed_steps"] == ["Empty deleted items"]
    assert len(recovered.state["messages"]) == 2
