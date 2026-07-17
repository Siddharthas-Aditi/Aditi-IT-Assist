"""Regression tests for chat session ownership (IDOR fix, Wave 3).

Before the SessionStore, nothing bound a session to its owner: any caller who
knew/guessed a session id could resume, read, or act on another user's
conversation. These tests pin that a foreign user is rejected and cannot read
or clobber the owner's session.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.services.agents.chat_service import ChatService
from app.services.agents.session_store import (
    ChatSession,
    InMemorySessionStore,
    get_session_store,
    set_session_store,
)


@pytest.fixture(autouse=True)
def _fresh_store():
    set_session_store(InMemorySessionStore())
    yield
    set_session_store(None)


def _requester(uid: str) -> MagicMock:
    return MagicMock(id=uid, full_name="U", email="u@aditi.com")


def _ticket_service() -> MagicMock:
    svc = MagicMock()
    svc.db = MagicMock()
    return svc


class TestSessionOwnership:
    async def test_foreign_user_cannot_read_or_clobber_session(self):
        store = get_session_store()
        # Owner establishes a session with meaningful state.
        await store.save(
            "sess-owned",
            ChatSession(
                user_id="user-A",
                state={"session_id": "sess-owned", "messages": [], "issue_category": "vpn"},
            ),
        )

        chat = ChatService(_ticket_service())
        # A different authenticated user references the same id.
        resp = await chat.process_message(
            session_id="sess-owned",
            user_message="show me the conversation",
            user_id="user-B",
        )

        # Generic error, no disclosure of the owner's content.
        assert resp.confidence_score == 0.0
        assert "vpn" not in resp.content.lower()
        # The owner's stored session is untouched (not overwritten by user-B).
        still = await store.load("sess-owned")
        assert still is not None and still.user_id == "user-A"
        assert still.state["issue_category"] == "vpn"

    async def test_owner_can_still_use_their_session(self):
        store = get_session_store()
        await store.save(
            "sess-mine",
            ChatSession(user_id="user-A", state={"session_id": "sess-mine", "messages": []}),
        )
        chat = ChatService(_ticket_service())
        # Same user — must NOT raise ownership error (returns a real response).
        resp = await chat.process_message(
            session_id="sess-mine",
            user_message="my outlook is broken",
            user_id="user-A",
        )
        assert resp is not None
        assert resp.session_id == "sess-mine"

    async def test_request_live_agent_rejects_foreign_session(self):
        store = get_session_store()
        await store.save(
            "sess-x",
            ChatSession(
                user_id="user-A",
                state={"session_id": "sess-x", "ticket_draft": {"title": "t"}},
                ticket={"ticket_number": "INC-A", "ticket_id": str(uuid.uuid4())},
            ),
        )
        chat = ChatService(_ticket_service())
        message, ref = await chat.request_live_agent("sess-x", _requester("user-B"))
        # No ticket returned to the foreign caller, and no disclosure of INC-A.
        assert ref is None
        assert "INC-A" not in message
