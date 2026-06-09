"""Unit tests for the chat service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.chat import ChatMessageResponse
from app.services.agents.chat_service import ChatService, get_chat_service


class TestChatService:
    """Tests for ChatService."""

    def test_factory_returns_instance(self):
        """Factory function should return ChatService instance."""
        service = get_chat_service()
        assert isinstance(service, ChatService)

    @pytest.mark.asyncio
    async def test_process_message_success(self):
        """Should process message through workflow and return response."""
        mock_state = {
            "messages": [AsyncMock(type="ai", content="I can help with that!")],
            "resolution_steps": [
                {"step_number": 1, "instruction": "Restart Outlook", "details": None}
            ],
            "resolution_confidence": 0.85,
            "issue_category": "email/outlook",
            "should_escalate": False,
            "clarification_question": None,
        }

        with patch.object(ChatService, "_invoke_workflow", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = mock_state

            service = ChatService()
            response = await service.process_message(
                session_id="sess-123",
                user_message="My email is broken",
            )

        assert isinstance(response, ChatMessageResponse)
        assert response.session_id == "sess-123"
        assert response.content == "I can help with that!"
        assert response.confidence_score == 0.85
        assert response.issue_category == "email/outlook"
        assert len(response.resolution_steps) == 1

    @pytest.mark.asyncio
    async def test_process_message_error_returns_fallback(self):
        """Should return error response when workflow fails."""
        with patch.object(ChatService, "_invoke_workflow", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.side_effect = RuntimeError("LangGraph error")

            service = ChatService()
            response = await service.process_message(
                session_id="sess-456",
                user_message="Help me",
            )

        assert isinstance(response, ChatMessageResponse)
        assert response.session_id == "sess-456"
        assert response.requires_escalation is True
        assert response.confidence_score == 0.0
        assert "technical issue" in response.content

    @pytest.mark.asyncio
    async def test_format_response_extracts_ai_message(self):
        """Should extract content from the last AI message."""
        service = ChatService()

        mock_msg_human = AsyncMock(type="human", content="help")
        mock_msg_ai = AsyncMock(type="ai", content="Here's my answer")

        result = {
            "messages": [mock_msg_human, mock_msg_ai],
            "resolution_steps": [],
            "resolution_confidence": 0.5,
            "issue_category": None,
            "should_escalate": False,
            "clarification_question": None,
        }

        response = service._format_response("sess-789", result)
        assert response.content == "Here's my answer"

    @pytest.mark.asyncio
    async def test_format_response_fallback_content(self):
        """Should use fallback when no AI message found."""
        service = ChatService()

        result = {
            "messages": [],
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "issue_category": None,
            "should_escalate": False,
            "clarification_question": None,
        }

        response = service._format_response("sess-000", result)
        assert "processing your request" in response.content
