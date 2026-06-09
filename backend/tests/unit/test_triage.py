"""Unit tests for the triage workflow node."""

import pytest

from app.workflows.nodes.triage import triage_node, _classify_issue


class TestClassifyIssue:
    """Tests for the _classify_issue function."""

    @pytest.mark.asyncio
    async def test_classify_outlook_issue(self):
        """Should classify Outlook-related messages correctly."""
        result = await _classify_issue("My Outlook is not receiving emails")
        assert result["category"] == "email/outlook"
        assert result["confidence"] >= 0.8
        assert result["needs_clarification"] is False

    @pytest.mark.asyncio
    async def test_classify_zoom_issue(self):
        """Should classify Zoom-related messages correctly."""
        result = await _classify_issue("I can't sign into Zoom")
        assert result["category"] == "video-conferencing/zoom"
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_classify_intune_issue(self):
        """Should classify Intune compliance messages correctly."""
        result = await _classify_issue("My laptop shows non-compliant in Intune")
        assert result["category"] == "device-management/intune"
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_classify_camera_issue(self):
        """Should classify camera-related messages correctly."""
        result = await _classify_issue("My webcam is not working")
        assert result["category"] == "hardware/camera"
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_classify_vague_message(self):
        """Should request clarification for vague messages."""
        result = await _classify_issue("something is broken")
        assert result["needs_clarification"] is True
        assert result["confidence"] < 0.5


class TestTriageNode:
    """Tests for the triage_node function."""

    @pytest.mark.asyncio
    async def test_triage_empty_messages(self):
        """Should ask for description when no messages present."""
        state = {"messages": [], "session_id": "test-123"}
        result = await triage_node(state)
        assert result["needs_clarification"] is True
        assert result["current_node"] == "triage"
