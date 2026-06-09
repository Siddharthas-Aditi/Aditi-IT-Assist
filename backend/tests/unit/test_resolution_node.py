"""Unit tests for the resolution workflow node."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.workflows.nodes.resolution import (
    _direct_resolution,
    _format_resolution_message,
    resolution_node,
)


class TestResolutionNode:
    """Tests for resolution_node function."""

    @pytest.mark.asyncio
    async def test_resolution_with_knowledge(self):
        """Should generate resolution steps from knowledge results."""
        state = {
            "session_id": "test-123",
            "issue_category": "email/outlook",
            "messages": [HumanMessage(content="Outlook not syncing")],
            "knowledge_results": [
                {
                    "id": "art-1",
                    "title": "Fix Outlook Sync",
                    "steps": [
                        {"instruction": "Restart Outlook", "details": "Close and reopen"},
                        {"instruction": "Check network", "details": None},
                    ],
                }
            ],
            "knowledge_confidence": 0.8,
        }

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            result = await resolution_node(state)

        assert result["current_node"] == "resolve"
        assert len(result["resolution_steps"]) == 2
        assert result["resolution_steps"][0]["instruction"] == "Restart Outlook"
        assert result["resolution_confidence"] > 0.0
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_resolution_no_knowledge(self):
        """Should return empty steps when no knowledge available."""
        state = {
            "session_id": "test-456",
            "issue_category": "other",
            "messages": [],
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
        }

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            result = await resolution_node(state)

        assert result["resolution_steps"] == []
        assert result["resolution_confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_resolution_audit_trail(self):
        """Should include audit entry with method and confidence."""
        state = {
            "session_id": "test-789",
            "issue_category": "hardware/camera",
            "messages": [],
            "knowledge_results": [
                {"id": "art-1", "title": "Camera Fix", "steps": ["Enable camera"]}
            ],
            "knowledge_confidence": 0.7,
        }

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            result = await resolution_node(state)

        audit = result["audit_trail"][0]
        assert audit["event"] == "resolution.generated"
        assert audit["method"] == "direct"
        assert audit["steps_count"] == 1


class TestDirectResolution:
    """Tests for _direct_resolution fallback."""

    def test_formats_dict_steps(self):
        """Should format dict steps correctly."""
        knowledge = [
            {
                "steps": [
                    {"instruction": "Do this", "details": "More info"},
                    {"instruction": "Then this"},
                ]
            }
        ]
        state = {"knowledge_confidence": 0.7}
        result = _direct_resolution(knowledge, state)

        assert len(result["steps"]) == 2
        assert result["steps"][0]["step_number"] == 1
        assert result["steps"][0]["instruction"] == "Do this"
        assert result["steps"][0]["details"] == "More info"
        assert result["steps"][1]["details"] is None

    def test_formats_string_steps(self):
        """Should handle string steps."""
        knowledge = [{"steps": ["Step one", "Step two"]}]
        state = {"knowledge_confidence": 0.5}
        result = _direct_resolution(knowledge, state)

        assert len(result["steps"]) == 2
        assert result["steps"][0]["instruction"] == "Step one"
        assert result["steps"][1]["instruction"] == "Step two"

    def test_confidence_calculation(self):
        """Should calculate confidence from knowledge_confidence + 0.1."""
        knowledge = [{"steps": ["s1"]}]
        state = {"knowledge_confidence": 0.6}
        result = _direct_resolution(knowledge, state)
        assert result["confidence"] == 0.7

    def test_confidence_capped(self):
        """Should cap confidence at 0.9."""
        knowledge = [{"steps": ["s1"]}]
        state = {"knowledge_confidence": 0.95}
        result = _direct_resolution(knowledge, state)
        assert result["confidence"] == 0.9


class TestFormatResolutionMessage:
    """Tests for _format_resolution_message."""

    def test_high_confidence_message(self):
        """Should use confident language for high confidence."""
        resolution = {
            "steps": [{"step_number": 1, "instruction": "Do this", "details": None}],
            "confidence": 0.9,
        }
        msg = _format_resolution_message(resolution)
        assert "I can help you with that!" in msg
        assert "**Step 1**" in msg

    def test_low_confidence_message(self):
        """Should offer escalation for low confidence."""
        resolution = {
            "steps": [{"step_number": 1, "instruction": "Try this", "details": None}],
            "confidence": 0.6,
        }
        msg = _format_resolution_message(resolution)
        assert "might help" in msg
        assert "escalate" in msg

    def test_no_steps_message(self):
        """Should suggest human agent when no steps."""
        resolution = {"steps": [], "confidence": 0.0}
        msg = _format_resolution_message(resolution)
        assert "human IT support agent" in msg

    def test_includes_details(self):
        """Should include step details in italics."""
        resolution = {
            "steps": [{"step_number": 1, "instruction": "Click X", "details": "Located top-right"}],
            "confidence": 0.85,
        }
        msg = _format_resolution_message(resolution)
        assert "_Located top-right_" in msg
