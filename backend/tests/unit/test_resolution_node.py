"""Unit tests for the resolution workflow node."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes.resolution import (
    _direct_resolution,
    resolution_node,
)


def _state_with_article(subtype: str, steps: list[str]) -> dict:
    """Build a minimal resolution_node state for a subtype-matching article."""
    diag_ctx = DiagnosticContext(
        issue_category="email/outlook",
        issue_subtype=subtype,
        symptom=subtype,
    )
    return {
        "session_id": "test-fluid",
        "issue_category": "email/outlook",
        "messages": [HumanMessage(content="my mailbox is full")],
        "knowledge_results": [
            {
                "id": "art-1",
                "title": "Fix Mailbox Full",
                "category": "email/outlook",
                "subcategory": subtype,
                "steps": [{"instruction": s, "details": None} for s in steps],
            }
        ],
        "knowledge_confidence": 0.8,
        # A real subtype match, as retrieval_node would report it.
        "retrieval_trace": {"has_subtype_match": True},
        "diagnostic_context": diag_ctx.to_dict(),
    }


def _state_with_generic_article(
    category: str, subtype: str, steps: list[str], *, knowledge_confidence: float = 0.1
) -> dict:
    """Build a state for a generic article that does NOT match the subtype.

    ``retrieval_trace.has_subtype_match`` is False (as retrieval_node would
    report for a same-family/generic fallback). With the default low
    ``knowledge_confidence`` the composite ``final`` also lands under the 0.35
    advise threshold; pass a high ``knowledge_confidence`` to isolate the
    no-subtype-match signal alone (final can then exceed 0.35).
    """
    diag_ctx = DiagnosticContext(
        issue_category=category,
        issue_subtype=subtype,
        symptom=subtype,
    )
    return {
        "session_id": "test-fluid-weak",
        "issue_category": category,
        "messages": [HumanMessage(content="my app keeps crashing, not sure why")],
        "knowledge_results": [
            {
                "id": "art-generic",
                "title": "General Troubleshooting",
                "category": category,
                "subcategory": subtype,
                "steps": [{"instruction": s, "details": None} for s in steps],
            }
        ],
        "knowledge_confidence": knowledge_confidence,
        "retrieval_trace": {"has_subtype_match": False},
        "diagnostic_context": diag_ctx.to_dict(),
    }


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
            "diagnostic_context": DiagnosticContext(
                issue_category="email/outlook",
                symptom="not-syncing",
            ).to_dict(),
        }

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            result = await resolution_node(state)

        assert result["current_node"] == "resolve"
        # B1: the resolver presents RESOLUTION_STEP_BATCH_SIZE (default 1) steps per
        # turn, not the full KB batch.
        assert len(result["resolution_steps"]) == 1
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
            "diagnostic_context": DiagnosticContext(
                issue_category="other",
            ).to_dict(),
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
            "diagnostic_context": DiagnosticContext(
                issue_category="hardware/camera",
                symptom="camera-not-working",
            ).to_dict(),
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

    def _make_diag_ctx(self):
        return DiagnosticContext(issue_category="email/outlook", symptom="test")

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
        result = _direct_resolution(knowledge, state, self._make_diag_ctx())

        assert len(result["steps"]) == 2
        assert result["steps"][0]["step_number"] == 1
        assert result["steps"][0]["instruction"] == "Do this"
        assert result["steps"][0]["details"] == "More info"
        assert result["steps"][1]["details"] is None

    def test_formats_string_steps(self):
        """Should handle string steps."""
        knowledge = [{"steps": ["Step one", "Step two"]}]
        state = {"knowledge_confidence": 0.5}
        result = _direct_resolution(knowledge, state, self._make_diag_ctx())

        assert len(result["steps"]) == 2
        assert result["steps"][0]["instruction"] == "Step one"
        assert result["steps"][1]["instruction"] == "Step two"

    def test_confidence_calculation(self):
        """Should calculate confidence from knowledge_confidence + 0.1."""
        knowledge = [{"steps": ["s1"]}]
        state = {"knowledge_confidence": 0.6}
        result = _direct_resolution(knowledge, state, self._make_diag_ctx())
        assert result["confidence"] == 0.7

    def test_confidence_capped(self):
        """Should cap confidence at 0.9."""
        knowledge = [{"steps": ["s1"]}]
        state = {"knowledge_confidence": 0.95}
        result = _direct_resolution(knowledge, state, self._make_diag_ctx())
        assert result["confidence"] == 0.9

    def test_progressive_disclosure_limits_steps(self):
        """Should only return first 3 steps for progressive disclosure."""
        knowledge = [{"steps": ["s1", "s2", "s3", "s4", "s5"]}]
        state = {"knowledge_confidence": 0.8}
        result = _direct_resolution(knowledge, state, self._make_diag_ctx())
        assert len(result["steps"]) == 3


class TestFluidChatStepGrouping:
    """FEATURE_FLUID_CHAT: present all remaining grounded steps together."""

    @pytest.mark.asyncio
    async def test_fluid_groups_multiple_steps(self, monkeypatch):
        """Flag-on: a subtype-matching article with 3 steps groups them together."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        state = _state_with_article(
            subtype="mailbox-full",
            steps=["Check mailbox size", "Empty Deleted Items", "Archive old mail"],
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert len(out["resolution_steps"]) >= 3

    @pytest.mark.asyncio
    async def test_flag_off_still_batches_one_step(self, monkeypatch):
        """Flag-off: behavior is unchanged — one step per turn."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", False)
        state = _state_with_article(
            subtype="mailbox-full",
            steps=["Check mailbox size", "Empty Deleted Items", "Archive old mail"],
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert len(out["resolution_steps"]) == 1


class TestHonestHandoffOnWeakGrounding:
    """FEATURE_FLUID_CHAT: don't fabricate confidence on weak/generic grounding."""

    @pytest.mark.asyncio
    async def test_fluid_weak_match_hands_off_not_fabricates(self, monkeypatch):
        """Flag-on + low composite confidence -> honest hand-off, no steps shown."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        state = _state_with_generic_article(
            category="software",
            subtype="other",
            steps=["Restart the app", "Run as administrator"],
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert out["resolution_steps"] == []
        assert out["conversation_phase"] == "escalating"
        assert "reliable, approved guidance" in out["escalation_reason"]
        assert out["diagnostic_context"]["phase"] == "escalating"

    @pytest.mark.asyncio
    async def test_fluid_no_subtype_match_hands_off_even_when_relevant(self, monkeypatch):
        """Flag-on: a same-family generic article that does NOT match the subtype
        must hand off honestly EVEN when its relevance is high enough that the
        composite confidence clears 0.35 — this is the fabrication case (generic
        steps for an unmatched issue) the confidence floor alone would miss.
        """
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        # High knowledge_confidence → composite final can exceed 0.35, so the
        # ONLY signal forcing a hand-off is has_subtype_match=False.
        state = _state_with_generic_article(
            category="software",
            subtype="other",
            steps=["Restart the app", "Run as administrator"],
            knowledge_confidence=0.9,
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert out["resolution_steps"] == []
        assert out["conversation_phase"] == "escalating"

    @pytest.mark.asyncio
    async def test_fluid_confident_match_still_returns_steps(self, monkeypatch):
        """Flag-on control: a confident subtype match still returns steps."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        state = _state_with_article(
            subtype="mailbox-full",
            steps=["Check mailbox size", "Empty Deleted Items"],
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert len(out["resolution_steps"]) > 0
        assert out["conversation_phase"] != "escalating"

    @pytest.mark.asyncio
    async def test_flag_off_weak_match_still_escalates(self, monkeypatch):
        """The reliability floor applies even when fluid chat is disabled."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", False)
        state = _state_with_generic_article(
            category="software",
            subtype="other",
            steps=["Restart the app", "Run as administrator"],
        )

        with patch("app.workflows.nodes.resolution.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.is_available = False
            mock_get_llm.return_value = mock_llm

            out = await resolution_node(state)

        assert out["resolution_steps"] == []
        assert out["conversation_phase"] == "escalating"
