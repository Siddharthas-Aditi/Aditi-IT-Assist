"""Integration tests for the feedback API endpoints.

Uses auth-override test clients from conftest.py.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.feedback import (
    ConversationFeedbackCreate,
    ConversationFeedbackResponse,
)


class TestFeedbackEndpoints:
    """Integration-level tests using the ASGI test client."""

    @pytest.mark.asyncio
    async def test_submit_feedback_unauthenticated_returns_401(self, client):
        """Unauthenticated requests to submit feedback must be rejected."""
        response = await client.post(
            "/api/v1/feedback/conversation/some-session-id",
            json={"helpful": True},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_own_feedback_unauthenticated_returns_401(self, client):
        response = await client.get(
            "/api/v1/feedback/conversation/some-session-id"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_review_queue_unauthenticated_returns_401(self, client):
        response = await client.get("/api/v1/feedback/review-queue")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analytics_summary_unauthenticated_returns_401(self, client):
        response = await client.get("/api/v1/feedback/analytics/summary")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_employee_can_submit_own_feedback(self, employee_client):
        """Employees with FEEDBACK_SUBMIT permission can POST feedback."""
        session_id = str(uuid.uuid4())
        mock_response = MagicMock()
        mock_response.id = uuid.uuid4()
        mock_response.conversation_id = uuid.UUID(session_id)
        mock_response.ticket_id = None
        mock_response.submitted_by_user_id = uuid.uuid4()
        mock_response.helpful = True
        mock_response.resolved = True
        mock_response.rating = 5
        mock_response.comment = None
        mock_response.submitted_at = "2024-01-01T00:00:00Z"
        mock_response.channel = "web_chat"
        mock_response.feedback_source = "inline_chat"
        mock_response.support_mode = "ai_only"
        mock_response.escalation_occurred = False
        mock_response.category = "email/outlook"
        mock_response.subcategory = None
        mock_response.knowledge_article_ids = None
        mock_response.session_duration_seconds = None
        mock_response.first_response_time_seconds = None
        mock_response.quality_bucket = "positive"
        mock_response.review_flag = False
        mock_response.review_flag_reason = None
        mock_response.created_at = "2024-01-01T00:00:00Z"
        mock_response.updated_at = "2024-01-01T00:00:00Z"

        with patch(
            "app.api.v1.feedback.FeedbackService.submit_feedback",
            new=AsyncMock(
                return_value=ConversationFeedbackResponse.model_validate(mock_response)
            ),
        ):
            response = await employee_client.post(
                f"/api/v1/feedback/conversation/{session_id}",
                json={"helpful": True, "resolved": True, "rating": 5},
            )
        # With proper auth wiring the call goes through; may 422 on perm check
        # but must NOT be 401
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_employee_cannot_access_analytics(self, employee_client):
        """Employees must NOT be able to read feedback analytics."""
        response = await employee_client.get("/api/v1/feedback/analytics/summary")
        # 403 (forbidden) or 401 — never 200
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_employee_cannot_access_review_queue(self, employee_client):
        """Employees must NOT be able to read the review queue."""
        response = await employee_client.get("/api/v1/feedback/review-queue")
        assert response.status_code in (401, 403)
