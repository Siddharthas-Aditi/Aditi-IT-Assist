"""API tests — live-chat → remote-session bridge + employee consent polling.

The bridge endpoint derives employee/ticket linkage from the chat session,
enforces specialist ownership, and surfaces the consent prompt as a chat
system message. Services are mocked: these tests pin the HTTP contract and
RBAC, not the service internals (covered in unit tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient


def _chat_session(specialist_id: uuid.UUID, status: str = "active") -> MagicMock:
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.ticket_id = uuid.uuid4()
    chat.user_id = uuid.uuid4()
    chat.specialist_id = specialist_id
    chat.status = status
    return chat


def _remote_session() -> MagicMock:
    session = MagicMock()
    session.id = uuid.uuid4()
    session.status = "consent_pending"
    session.session_type = "screen_view"
    session.consent_deadline = datetime.now(UTC) + timedelta(minutes=10)
    return session


class TestChatToRemoteBridge:
    async def test_specialist_can_request_remote_from_chat(
        self, agent_client: AsyncClient, mock_it_agent
    ):
        chat = _chat_session(specialist_id=mock_it_agent.id)
        remote = _remote_session()

        with (
            patch(
                "app.services.specialist_chat_service.SpecialistChatService.get_state",
                new=AsyncMock(return_value=chat),
            ),
            patch(
                "app.services.remote_support.service.RemoteSupportService.request_session",
                new=AsyncMock(return_value=remote),
            ) as mock_request,
            patch(
                "app.services.remote_support.service.RemoteSupportService.send_consent_request",
                new=AsyncMock(return_value=remote),
            ),
            patch(
                "app.services.specialist_chat_service.SpecialistChatService.append_system_message",
                new=AsyncMock(),
            ) as mock_system_msg,
        ):
            response = await agent_client.post(
                f"/api/v1/specialist-chat/{chat.id}/remote-session",
                json={"session_type": "screen_view"},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["remote_session_id"] == str(remote.id)
        assert body["status"] == "consent_pending"

        # Linkage: employee/ticket/chat all derived from the chat session.
        kwargs = mock_request.call_args.kwargs
        assert kwargs["employee_id"] == chat.user_id
        assert kwargs["ticket_id"] == chat.ticket_id
        assert kwargs["support_session_id"] == chat.id

        # Employee sees the consent prompt inside the same chat.
        assert mock_system_msg.await_count == 1
        assert mock_system_msg.call_args.kwargs["event"] == "remote_session_requested"

    async def test_other_specialist_cannot_request(self, agent_client: AsyncClient, mock_it_agent):
        chat = _chat_session(specialist_id=uuid.uuid4())  # someone else's chat
        with patch(
            "app.services.specialist_chat_service.SpecialistChatService.get_state",
            new=AsyncMock(return_value=chat),
        ):
            response = await agent_client.post(
                f"/api/v1/specialist-chat/{chat.id}/remote-session",
                json={"session_type": "screen_view"},
            )
        assert response.status_code == 403

    async def test_ended_chat_rejected(self, agent_client: AsyncClient, mock_it_agent):
        chat = _chat_session(specialist_id=mock_it_agent.id, status="ended_by_user")
        with patch(
            "app.services.specialist_chat_service.SpecialistChatService.get_state",
            new=AsyncMock(return_value=chat),
        ):
            response = await agent_client.post(
                f"/api/v1/specialist-chat/{chat.id}/remote-session",
                json={"session_type": "screen_view"},
            )
        assert response.status_code == 409

    async def test_employee_cannot_use_bridge(self, employee_client: AsyncClient):
        response = await employee_client.post(
            f"/api/v1/specialist-chat/{uuid.uuid4()}/remote-session",
            json={"session_type": "screen_view"},
        )
        assert response.status_code == 403

    async def test_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/specialist-chat/{uuid.uuid4()}/remote-session",
            json={"session_type": "screen_view"},
        )
        assert response.status_code == 401


class TestPendingConsentPolling:
    async def test_no_pending_consent(self, employee_client: AsyncClient):
        with patch(
            "app.services.remote_support.service.RemoteSupportService."
            "get_pending_consent_for_employee",
            new=AsyncMock(return_value=None),
        ):
            response = await employee_client.get("/api/v1/remote-support/consent/pending")
        assert response.status_code == 200
        assert response.json() == {"pending": False}

    async def test_pending_consent_payload(self, employee_client: AsyncClient):
        payload = {
            "session_id": str(uuid.uuid4()),
            "agent_name": "Test Agent",
            "agent_email": "agent@test.aditi.com",
            "session_type": "screen_view",
            "session_type_label": "View Only",
            "justification": None,
            "consent_deadline": datetime.now(UTC) + timedelta(minutes=8),
            "consent_text": "An IT support agent has requested to view your screen…",
            "ticket_reference": None,
        }
        with patch(
            "app.services.remote_support.service.RemoteSupportService."
            "get_pending_consent_for_employee",
            new=AsyncMock(return_value=payload),
        ):
            response = await employee_client.get("/api/v1/remote-support/consent/pending")
        assert response.status_code == 200
        body = response.json()
        assert body["pending"] is True
        assert body["notification"]["agent_name"] == "Test Agent"

    async def test_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/remote-support/consent/pending")
        assert response.status_code == 401
