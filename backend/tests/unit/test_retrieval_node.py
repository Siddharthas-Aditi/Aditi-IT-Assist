"""Unit tests for the retrieval workflow node."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.knowledge_service import RetrievalResult
from app.workflows.nodes.retrieval import retrieval_node


class TestRetrievalNode:
    """Tests for the retrieval_node function."""

    @pytest.mark.asyncio
    async def test_retrieval_with_results(self):
        """Should return knowledge results and confidence."""
        mock_result = RetrievalResult(
            articles=[
                {"id": "art-1", "title": "Fix Outlook", "steps": ["step1"]},
                {"id": "art-2", "title": "Sync Email", "steps": ["step1", "step2"]},
            ],
            confidence=0.85,
            source="keyword",
        )

        with patch(
            "app.workflows.nodes.retrieval.get_knowledge_service"
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            mock_svc.retrieve_for_category = AsyncMock(return_value=mock_result)
            mock_get_svc.return_value = mock_svc

            state = {
                "session_id": "test-123",
                "issue_category": "email/outlook",
                "messages": [],
            }
            result = await retrieval_node(state)

        assert result["current_node"] == "retrieve"
        assert len(result["knowledge_results"]) == 2
        assert result["knowledge_confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_retrieval_no_results(self):
        """Should return empty results with zero confidence."""
        mock_result = RetrievalResult(
            articles=[],
            confidence=0.0,
            source="keyword",
        )

        with patch(
            "app.workflows.nodes.retrieval.get_knowledge_service"
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            mock_svc.retrieve_for_category = AsyncMock(return_value=mock_result)
            mock_get_svc.return_value = mock_svc

            state = {
                "session_id": "test-123",
                "issue_category": "nonexistent/category",
                "messages": [],
            }
            result = await retrieval_node(state)

        assert result["knowledge_results"] == []
        assert result["knowledge_confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_retrieval_defaults_to_other_category(self):
        """Should default to 'other' when issue_category is None."""
        mock_result = RetrievalResult(articles=[], confidence=0.0, source="keyword")

        with patch(
            "app.workflows.nodes.retrieval.get_knowledge_service"
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            mock_svc.retrieve_for_category = AsyncMock(return_value=mock_result)
            mock_get_svc.return_value = mock_svc

            state = {
                "session_id": "test-456",
                "issue_category": None,
                "messages": [],
            }
            result = await retrieval_node(state)

        # Should have called with "other"
        mock_svc.retrieve_for_category.assert_called_once_with("other")
        assert result["current_node"] == "retrieve"

    @pytest.mark.asyncio
    async def test_retrieval_audit_trail(self):
        """Should include audit trail entry."""
        mock_result = RetrievalResult(
            articles=[{"id": "a1", "title": "Test"}],
            confidence=0.7,
            source="keyword",
        )

        with patch(
            "app.workflows.nodes.retrieval.get_knowledge_service"
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            mock_svc.retrieve_for_category = AsyncMock(return_value=mock_result)
            mock_get_svc.return_value = mock_svc

            state = {
                "session_id": "test-789",
                "issue_category": "hardware/camera",
                "messages": [],
            }
            result = await retrieval_node(state)

        audit = result["audit_trail"][0]
        assert audit["event"] == "knowledge.searched"
        assert audit["category"] == "hardware/camera"
        assert audit["results_count"] == 1
        assert audit["confidence"] == 0.7
        assert audit["source"] == "keyword"
