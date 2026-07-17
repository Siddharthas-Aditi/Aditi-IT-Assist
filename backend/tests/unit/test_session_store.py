"""Unit tests for the chat session store (Wave-3 persistence seam).

Covers the in-memory backend (bounded LRU + TTL), the JSON envelope
serialization used by the Redis backend (incl. LangChain message round-trip),
and the ticket-idempotency / waiting fields carried on the envelope.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.services.agents.session_store import (
    ChatSession,
    InMemorySessionStore,
    _dump_session,
    _load_session,
)


def _state() -> dict:
    return {
        "session_id": "s1",
        "user_id": "u1",
        "messages": [HumanMessage(content="hi"), AIMessage(content="hello there")],
        "issue_category": "email/outlook",
        "turn_count": 2,
        "diagnostic_context": {"issue_subtype": "mailbox-full", "suggested_steps": ["a", "b"]},
        "resolution_steps": [],
    }


class TestInMemoryStore:
    async def test_save_load_roundtrip(self):
        store = InMemorySessionStore()
        await store.save("s1", ChatSession(user_id="u1", state=_state()))
        loaded = await store.load("s1")
        assert loaded is not None
        assert loaded.user_id == "u1"
        assert loaded.state["issue_category"] == "email/outlook"
        assert len(loaded.state["messages"]) == 2

    async def test_missing_returns_none(self):
        store = InMemorySessionStore()
        assert await store.load("nope") is None

    async def test_delete(self):
        store = InMemorySessionStore()
        await store.save("s1", ChatSession(user_id="u1", state={}))
        await store.delete("s1")
        assert await store.load("s1") is None

    async def test_ttl_expiry(self):
        store = InMemorySessionStore(ttl_seconds=60)
        sess = ChatSession(user_id="u1", state={})
        await store.save("s1", sess)
        # Backdate beyond the TTL — load must treat it as expired and drop it.
        sess.updated_at = datetime.now(UTC) - timedelta(seconds=120)
        assert await store.load("s1") is None

    async def test_lru_eviction_bounds_memory(self):
        store = InMemorySessionStore(max_sessions=3)
        for i in range(5):
            await store.save(f"s{i}", ChatSession(user_id="u", state={}))
        # Oldest two evicted; only the last three remain.
        assert await store.load("s0") is None
        assert await store.load("s1") is None
        assert await store.load("s4") is not None

    async def test_ticket_and_waiting_fields_persist(self):
        store = InMemorySessionStore()
        ts = datetime.now(UTC)
        await store.save(
            "s1",
            ChatSession(
                user_id="u1",
                state={},
                ticket={"ticket_number": "INC-1"},
                waiting_since=ts,
            ),
        )
        loaded = await store.load("s1")
        assert loaded.ticket == {"ticket_number": "INC-1"}
        assert loaded.waiting_since == ts


class TestEnvelopeSerialization:
    def test_json_roundtrip_preserves_messages_and_fields(self):
        original = ChatSession(
            user_id="u1",
            state=_state(),
            ticket={"ticket_number": "INC-9", "status": "triaged"},
            waiting_since=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        )
        restored = _load_session(_dump_session(original))

        assert restored.user_id == "u1"
        assert restored.ticket == {"ticket_number": "INC-9", "status": "triaged"}
        assert restored.waiting_since == original.waiting_since
        # LangChain messages survive the dict round-trip with type + content.
        msgs = restored.state["messages"]
        assert isinstance(msgs[0], HumanMessage) and msgs[0].content == "hi"
        assert isinstance(msgs[1], AIMessage) and msgs[1].content == "hello there"
        # Nested serialized diagnostic context is preserved.
        assert restored.state["diagnostic_context"]["issue_subtype"] == "mailbox-full"

    def test_empty_state_roundtrip(self):
        restored = _load_session(_dump_session(ChatSession(user_id=None, state={})))
        assert restored.user_id is None
        assert restored.state["messages"] == []


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
