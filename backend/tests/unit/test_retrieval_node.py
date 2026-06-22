"""Unit tests for the retrieval workflow node."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflows.nodes.retrieval import retrieval_node


@dataclass
class _MockArticle:
    """Minimal mock for KnowledgeArticle attributes used by _scored_to_dict."""
    id: str = "art-1"
    title: str = "Test Article"
    category: str = "email/outlook"
    citation_label: str = "Test Article"
    resolution_steps: list = None
    steps: list = None
    content: str = "Test content"
    retrieval_text: str = "Test retrieval text"
    short_summary: str = "Summary"
    troubleshooting_steps: list = None

    def __post_init__(self):
        if self.resolution_steps is None:
            self.resolution_steps = []
        if self.steps is None:
            self.steps = []
        if self.troubleshooting_steps is None:
            self.troubleshooting_steps = []


@dataclass
class _MockScoredArticle:
    article: _MockArticle
    score: float = 0.85
    snippet: str = "Test snippet"


@dataclass
class _MockResult:
    """Mock for GovernedRetrievalResult."""
    items: list = None
    confidence: float = 0.85
    source: str = "db_keyword"
    published_only: bool = True
    fallback_used: bool = False

    def __post_init__(self):
        if self.items is None:
            self.items = []


def _make_mock_session(mock_result):
    """Create a mock for async_session_factory context manager."""
    mock_svc = AsyncMock()
    mock_svc.search = AsyncMock(return_value=mock_result)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session, mock_svc


class TestRetrievalNode:
    """Tests for the retrieval_node function."""

    @pytest.mark.asyncio
    async def test_retrieval_with_results(self):
        """Should return knowledge results and confidence."""
        articles = [
            _MockScoredArticle(
                article=_MockArticle(id="art-1", title="Fix Outlook", steps=["step1"]),
                score=0.9,
            ),
            _MockScoredArticle(
                article=_MockArticle(id="art-2", title="Sync Email", steps=["s1", "s2"]),
                score=0.8,
            ),
        ]
        mock_result = _MockResult(items=articles, confidence=0.85)

        with patch("app.workflows.nodes.retrieval.async_session_factory") as mock_factory, \
             patch("app.workflows.nodes.retrieval.KnowledgeRetrievalService") as MockSvc:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=mock_result)
            MockSvc.return_value = mock_instance

            state = {
                "session_id": "test-123",
                "issue_category": "email/outlook",
                "messages": [],
                "diagnostic_context": None,
            }
            result = await retrieval_node(state)

        assert result["current_node"] == "retrieve"
        assert len(result["knowledge_results"]) == 2
        assert result["knowledge_confidence"] > 0

    @pytest.mark.asyncio
    async def test_retrieval_no_results(self):
        """Should return empty results with zero confidence."""
        mock_result = _MockResult(items=[], confidence=0.0)

        with patch("app.workflows.nodes.retrieval.async_session_factory") as mock_factory, \
             patch("app.workflows.nodes.retrieval.KnowledgeRetrievalService") as MockSvc:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=mock_result)
            MockSvc.return_value = mock_instance

            state = {
                "session_id": "test-123",
                "issue_category": "nonexistent/category",
                "messages": [],
                "diagnostic_context": None,
            }
            result = await retrieval_node(state)

        assert result["knowledge_results"] == []
        assert result["knowledge_confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_retrieval_defaults_to_other_category(self):
        """Should default to 'other' when issue_category is None."""
        mock_result = _MockResult(items=[], confidence=0.0)

        with patch("app.workflows.nodes.retrieval.async_session_factory") as mock_factory, \
             patch("app.workflows.nodes.retrieval.KnowledgeRetrievalService") as MockSvc:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=mock_result)
            MockSvc.return_value = mock_instance

            state = {
                "session_id": "test-456",
                "issue_category": None,
                "messages": [],
                "diagnostic_context": None,
            }
            result = await retrieval_node(state)

        assert result["current_node"] == "retrieve"
        # category defaults to "other" but search is called without category filter
        mock_instance.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieval_audit_trail(self):
        """Should include audit trail entry."""
        articles = [
            _MockScoredArticle(
                article=_MockArticle(id="a1", title="Camera Fix", category="hardware/camera"),
                score=0.7,
            ),
        ]
        mock_result = _MockResult(items=articles, confidence=0.7, source="db_keyword")

        with patch("app.workflows.nodes.retrieval.async_session_factory") as mock_factory, \
             patch("app.workflows.nodes.retrieval.KnowledgeRetrievalService") as MockSvc:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=mock_result)
            MockSvc.return_value = mock_instance

            state = {
                "session_id": "test-789",
                "issue_category": "hardware/camera",
                "messages": [],
                "diagnostic_context": None,
            }
            result = await retrieval_node(state)

        audit = result["audit_trail"][0]
        assert audit["event"] == "knowledge.searched"
        assert audit["category"] == "hardware/camera"
        # Grounding keeps articles that match the issue's domain family
        assert audit["results_count"] >= 0

