"""B1: escalation + ticketing messages are LLM-phrased with deterministic fallbacks."""

import pytest

import app.services.agents.conversation_messages as CM  # noqa: N812
from app.services.agents.diagnostic_state import DiagnosticContext


class _FakeLLM:
    def __init__(self, available, text=""):
        self.is_available = available
        self._text = text

    async def complete(self, prompt, system_prompt=None, temperature=0.8, max_tokens=200):
        return self._text


@pytest.fixture
def ctx():
    c = DiagnosticContext()
    c.affected_system = "your laptop"
    return c


@pytest.mark.asyncio
async def test_escalation_offer_uses_llm(monkeypatch, ctx):
    monkeypatch.setattr(
        CM,
        "get_llm_service",
        lambda: _FakeLLM(True, "I'll bring in our IT team to help you further."),
    )
    msg = await CM.generate_escalation_offer(ctx, "steps exhausted")
    assert msg == "I'll bring in our IT team to help you further."


@pytest.mark.asyncio
async def test_escalation_offer_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_escalation_offer(ctx, "steps exhausted")
    assert "IT team" in msg and len(msg) > 20


@pytest.mark.asyncio
async def test_escalation_confirmed_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_escalation_confirmed(ctx)
    assert "connect" in msg.lower() and len(msg) > 20


@pytest.mark.asyncio
async def test_ticket_offer_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_ticket_offer(ctx, "high", "hardware/laptop")
    assert "ticket" in msg.lower() and len(msg) > 20


@pytest.mark.asyncio
async def test_ticket_created_includes_number(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_ticket_created("INC-1001", ctx)
    assert "INC-1001" in msg
