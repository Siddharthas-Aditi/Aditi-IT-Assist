"""Unit tests for SupportSessionService — durable chat session persistence."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.support import Message, SupportSession
from app.services.agents.session_store import ChatSession
from app.services.support_session_service import SupportSessionService


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(db: AsyncMock) -> SupportSessionService:
    svc = SupportSessionService(db)
    svc.repo = AsyncMock()
    return svc


class TestSupportSessionService:
    async def test_sync_turn_creates_session_and_messages(self, service: SupportSessionService):
        session_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        service.repo.get_by_id = AsyncMock(return_value=None)
        service.repo.create = AsyncMock(side_effect=lambda row: row)
        service.repo.add_message = AsyncMock(side_effect=lambda msg: msg)

        state = {
            "issue_category": "email/outlook",
            "issue_subcategory": "mailbox-full",
            "resolution_confidence": 0.9,
            "issue_resolved": True,
            "knowledge_citations": [{"article_id": str(uuid.uuid4())}],
        }
        envelope = ChatSession(user_id=user_id, state=state)

        await service.sync_turn(
            session_id,
            user_id,
            user_message="My inbox is full",
            assistant_message="Try archiving old mail.",
            assistant_message_id=str(uuid.uuid4()),
            state=state,
            envelope=envelope,
        )

        service.repo.create.assert_awaited_once()
        created: SupportSession = service.repo.create.await_args.args[0]
        assert created.status == "resolved"
        assert created.issue_category == "email/outlook"
        assert created.metadata_json is not None
        assert service.repo.add_message.await_count == 2

    async def test_sync_turn_updates_existing_session(self, service: SupportSessionService):
        session_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        existing = SupportSession(
            id=uuid.UUID(session_id),
            user_id=uuid.UUID(user_id),
            status="active",
            session_type="ai_chat",
            created_at=datetime.now(UTC),
        )
        service.repo.get_by_id = AsyncMock(return_value=existing)
        service.repo.add_message = AsyncMock()

        envelope = ChatSession(user_id=user_id, state={}, ticket={"ticket_id": "t1"})
        state = {"issue_category": "network/connectivity", "should_escalate": True}

        await service.sync_turn(
            session_id,
            user_id,
            user_message="VPN down",
            assistant_message="I'll connect you with a specialist.",
            assistant_message_id=str(uuid.uuid4()),
            state=state,
            envelope=envelope,
        )

        assert existing.status == "escalated"
        assert existing.session_type == "hybrid"
        service.repo.create.assert_not_awaited()

    async def test_list_sessions_returns_summaries(self, service: SupportSessionService):
        user_id = str(uuid.uuid4())
        row = SupportSession(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            status="resolved",
            session_type="ai_chat",
            issue_category="email/outlook",
            created_at=datetime.now(UTC),
        )
        service.repo.list_for_user = AsyncMock(return_value=[row])

        summaries = await service.list_sessions(user_id)

        assert len(summaries) == 1
        assert summaries[0].session_id == str(row.id)
        assert summaries[0].status == "resolved"

    async def test_get_session_enforces_ownership(self, service: SupportSessionService):
        session_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        row = SupportSession(
            id=uuid.UUID(session_id),
            user_id=uuid.UUID(owner_id),
            status="active",
            session_type="ai_chat",
            created_at=datetime.now(UTC),
            messages=[
                Message(
                    id=uuid.uuid4(),
                    session_id=uuid.UUID(session_id),
                    role="user",
                    content="hello",
                    message_type="text",
                    created_at=datetime.now(UTC),
                )
            ],
        )
        service.repo.get_with_messages = AsyncMock(return_value=row)

        assert await service.get_session(session_id, other_id) is None
        detail = await service.get_session(session_id, owner_id)
        assert detail is not None
        assert len(detail.messages) == 1
