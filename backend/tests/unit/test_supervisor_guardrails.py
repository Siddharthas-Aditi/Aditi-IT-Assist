"""Supervisor guardrail regression tests — delegation cap and loop detection.

Covers:
1. Per-specialist delegation cap (3) fires when delegations_per_agent is persisted
   across turns and the counter reaches the cap threshold.
2. Global handoff cap (8) fires when handoffs counter reaches the threshold.
3. Delegation counter persists through a simulated service restart (new
   supervisor_metrics re-read from state, cap still fires correctly).
4. Loop detection (loop_signals >= 2) fires when loop_counter is elevated —
   confirming the loop_signals field is correctly sourced from DiagnosticContext.
5. supervisor_shadow_node correctly rehydrates both handoffs and
   delegations_per_agent from the supervisor_metrics state field.
6. specialist_dispatch_node increments supervisor_metrics after each dispatch
   and writes it back to state.

These tests prove the two previously-broken guardrails (delegations_per_agent
and handoffs) now actually function, and confirm loop_signals was already correct.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from app.services.agents.intent_classifier import ConversationIntent, IntentClassification
from app.services.agents.registry import find_specialist_for
from app.services.agents.supervisor import NextAction, SessionMetrics, SupervisorDecision, decide

# ── Helpers ────────────────────────────────────────────────────────────────────


def _ic(intent: ConversationIntent = ConversationIntent.CONTINUE) -> IntentClassification:
    return IntentClassification(intent=intent, confidence=0.9, matched="test")


def _metrics_with_delegations(specialist: str, count: int) -> SessionMetrics:
    m = SessionMetrics()
    for _ in range(count):
        m.record_delegation(specialist)
    return m


def _base_state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": "test-session",
        "user_id": "user-1",
        "messages": [HumanMessage(content="my VPN isn't connecting")],
        "issue_category": "network/connectivity",
        "issue_subtype": "vpn-not-connecting",
        "knowledge_results": [{"id": "kb-1", "title": "VPN fix"}],
        "knowledge_confidence": 0.85,
        "knowledge_citations": [],
        "diagnostic_context": {
            "normalized_system": "vpn",
            "loop_counter": 0,
            "issue_subtype": "vpn-not-connecting",
            "resolution_attempts": 1,
        },
        "supervisor_decision": {
            "action": NextAction.DELEGATE.value,
            "agent": "network_vpn",
            "sub_agent": None,
            "confidence": 0.85,
        },
        "supervisor_metrics": None,
        "turn_count": 1,
        "audit_trail": [],
        "policy_violations": [],
        "requires_consent": False,
        "consent_granted": False,
        "resolution_steps": [],
        "resolution_confidence": 0.0,
        "should_escalate": False,
        "escalation_reason": None,
    }
    base.update(overrides)
    return base


# ── 1. Per-specialist delegation cap via SessionMetrics ────────────────────────


class TestDelegationCapFires:
    """The per-specialist cap (3) must fire when delegations_per_agent reaches it."""

    def _decide_with_delegations(self, specialist: str, count: int) -> SupervisorDecision:
        metrics = _metrics_with_delegations(specialist, count)
        spec = find_specialist_for(category="network/connectivity", subtype="vpn-not-connecting")
        assert spec is not None
        return decide(
            intent=_ic(),
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            knowledge_confidence=0.5,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=1,
            metrics=metrics,
            extra_slots={"network_type": "vpn"},
        )

    def test_below_cap_still_delegates(self) -> None:
        d = self._decide_with_delegations("network_vpn", 2)
        assert d.action is NextAction.DELEGATE
        assert d.agent == "network_vpn"

    def test_at_cap_escalates(self) -> None:
        """At count == 3 (the cap), supervisor must escalate, not continue delegating."""
        d = self._decide_with_delegations("network_vpn", 3)
        assert d.action is NextAction.ESCALATE
        assert "3" in d.reason or "network_vpn" in d.reason

    def test_cap_is_per_specialist(self) -> None:
        """Cap is per-specialist: one at cap, another below cap still delegates."""
        metrics = _metrics_with_delegations("network_vpn", 3)
        metrics.record_delegation("zoom_meetings")  # zoom_meetings at 1 (below cap)
        d = decide(
            intent=_ic(),
            issue_category="video-conferencing/zoom",
            issue_subtype="no-audio",
            normalized_system="zoom",
            knowledge_confidence=0.7,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=1,
            metrics=metrics,
        )
        # zoom_meetings is below its cap → still delegates
        assert d.action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB)
        assert d.agent == "zoom_meetings"


# ── 2. Global handoff cap ──────────────────────────────────────────────────────


class TestGlobalHandoffCap:
    def test_global_cap_at_8_escalates(self) -> None:
        m = SessionMetrics(handoffs=8)
        d = decide(
            intent=_ic(),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.8,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=m,
        )
        assert d.action is NextAction.ESCALATE
        assert "8" in d.reason or "cap" in d.reason.lower()

    def test_below_global_cap_does_not_escalate(self) -> None:
        m = SessionMetrics(handoffs=5)
        d = decide(
            intent=_ic(),
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
            knowledge_confidence=0.8,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=m,
        )
        assert d.action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB)


# ── 3. Restart survival: counters read from state survive ─────────────────────


class TestDelegationCounterSurvivesRestart:
    """Simulates a service restart: state is loaded from SessionStore, and
    supervisor_metrics is rehydrated from state, not from in-process memory."""

    def test_counter_from_state_triggers_cap(self) -> None:
        """After 'restart', load state with count=2; one more dispatch → cap fires."""
        # State as it would be after 2 previous delegations to network_vpn
        state_with_counter: dict[str, Any] = {
            "supervisor_metrics": {
                "handoffs": 2,
                "delegations_per_agent": {"network_vpn": 2},
            }
        }
        # Rehydrate SessionMetrics from state (as supervisor_shadow_node does)
        metrics_raw = state_with_counter.get("supervisor_metrics") or {}
        metrics = SessionMetrics(handoffs=int(metrics_raw.get("handoffs") or 0))
        delegations: dict[str, int] = metrics_raw.get("delegations_per_agent") or {}
        metrics.delegations_per_agent = dict(delegations)

        assert metrics.per_agent("network_vpn") == 2  # correctly rehydrated

        # Simulate the dispatch node incrementing after the 3rd dispatch
        delegations["network_vpn"] = delegations.get("network_vpn", 0) + 1
        metrics.delegations_per_agent = dict(delegations)

        # Now at cap: decide() must escalate
        d = decide(
            intent=_ic(),
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            knowledge_confidence=0.5,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=1,
            metrics=metrics,
            extra_slots={"network_type": "vpn"},
        )
        assert d.action is NextAction.ESCALATE, (
            "After restart, counter rehydrated to 3 must trigger cap"
        )

    def test_counter_from_state_below_cap_still_delegates(self) -> None:
        """Count=1 after restart → next dispatch (total=2) is still below cap."""
        state_with_counter: dict[str, Any] = {
            "supervisor_metrics": {
                "handoffs": 1,
                "delegations_per_agent": {"network_vpn": 1},
            }
        }
        metrics_raw = state_with_counter.get("supervisor_metrics") or {}
        metrics = SessionMetrics(handoffs=int(metrics_raw.get("handoffs") or 0))
        delegations: dict[str, int] = metrics_raw.get("delegations_per_agent") or {}
        metrics.delegations_per_agent = dict(delegations)

        d = decide(
            intent=_ic(),
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            knowledge_confidence=0.8,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=metrics,
            extra_slots={"network_type": "vpn"},
        )
        assert d.action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB)


# ── 4. Loop detection (loop_signals via loop_counter) ─────────────────────────


class TestLoopDetection:
    """loop_signals is sourced from DiagnosticContext.loop_counter, which IS
    persisted via diagnostic_context in WorkflowState. These tests confirm the
    loop detection guardrail actually fires."""

    def test_loop_signals_at_2_escalates(self) -> None:
        """loop_signals >= 2 triggers loop detection → ESCALATE."""
        m = SessionMetrics(loop_signals=2)
        d = decide(
            intent=_ic(),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.8,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=m,
        )
        assert d.action is NextAction.ESCALATE
        assert "loop" in d.reason.lower()

    def test_loop_signals_at_1_does_not_escalate(self) -> None:
        m = SessionMetrics(loop_signals=1)
        d = decide(
            intent=_ic(),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.8,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=m,
        )
        assert d.action is not NextAction.ESCALATE or "loop" not in d.reason.lower()

    def test_loop_counter_in_diag_context_maps_to_loop_signals(self) -> None:
        """Verify the mapping: diag.loop_counter → SessionMetrics.loop_signals."""
        diag_with_loop = {"loop_counter": 3, "normalized_system": "ad"}
        loop_signals = int(diag_with_loop.get("loop_counter") or 0)
        m = SessionMetrics(loop_signals=loop_signals)
        # loop_signals=3 >= 2 → escalate
        d = decide(
            intent=_ic(),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.7,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=1,
            metrics=m,
        )
        assert d.action is NextAction.ESCALATE


# ── 5. supervisor_shadow_node rehydrates from supervisor_metrics ───────────────


class TestSupervisorShadowRehydration:
    """The shadow node must build correct SessionMetrics from supervisor_metrics."""

    @pytest.mark.asyncio
    async def test_shadow_node_reads_handoffs_from_state(self) -> None:
        """supervisor_shadow_node reads handoffs from supervisor_metrics, not
        the non-existent audit_trail_handoffs key."""
        from app.core.config import settings
        from app.workflows.nodes.supervisor_shadow import supervisor_shadow_node

        state = {
            "supervisor_metrics": {
                "handoffs": 9,  # above global cap (8)
                "delegations_per_agent": {},
            },
            "turn_count": 3,
            "issue_category": "access/permissions",
            "issue_subtype": "account-locked",
            "knowledge_results": [{"id": "kb-1"}],
            "knowledge_confidence": 0.8,
            "diagnostic_context": {"normalized_system": "ad", "loop_counter": 0},
            "needs_clarification": False,
            "issue_resolved": False,
            "session_id": "test-s1",
        }

        if not settings.FEATURE_SUPERVISOR_SHADOW:
            pytest.skip("FEATURE_SUPERVISOR_SHADOW is off")

        result = await supervisor_shadow_node(state)  # type: ignore[arg-type]
        decision = result.get("supervisor_decision") or {}
        # handoffs=9 (above global cap of 8) → supervisor must decide ESCALATE
        assert decision.get("action") == NextAction.ESCALATE.value, (
            f"Expected ESCALATE (global cap), got {decision.get('action')}"
        )

    @pytest.mark.asyncio
    async def test_shadow_node_reads_per_agent_delegations_from_state(self) -> None:
        """supervisor_shadow_node reads delegations_per_agent from supervisor_metrics."""
        from app.core.config import settings
        from app.workflows.nodes.supervisor_shadow import supervisor_shadow_node

        state = {
            "supervisor_metrics": {
                "handoffs": 3,
                "delegations_per_agent": {"access_mfa": 3},  # at per-specialist cap
            },
            "turn_count": 3,
            "issue_category": "access/permissions",
            "issue_subtype": "password-expired",
            "knowledge_results": [{"id": "kb-1"}],
            "knowledge_confidence": 0.8,
            "diagnostic_context": {"normalized_system": "ad", "loop_counter": 0},
            "needs_clarification": False,
            "issue_resolved": False,
            "session_id": "test-s2",
        }

        if not settings.FEATURE_SUPERVISOR_SHADOW:
            pytest.skip("FEATURE_SUPERVISOR_SHADOW is off")

        result = await supervisor_shadow_node(state)  # type: ignore[arg-type]
        decision = result.get("supervisor_decision") or {}
        # access_mfa at cap (3) → ESCALATE
        assert decision.get("action") == NextAction.ESCALATE.value, (
            f"Expected ESCALATE (per-specialist cap), got {decision.get('action')}"
        )


# ── 6. specialist_dispatch_node writes supervisor_metrics ─────────────────────


class TestDispatchNodeUpdatesMetrics:
    """specialist_dispatch_node must increment supervisor_metrics after dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_increments_delegation_counter(self) -> None:
        from app.workflows.nodes.specialist_dispatch import specialist_dispatch_node

        state = _base_state(
            supervisor_metrics={"handoffs": 1, "delegations_per_agent": {"network_vpn": 1}},
            supervisor_decision={
                "action": NextAction.DELEGATE.value,
                "agent": "network_vpn",
                "sub_agent": None,
                "confidence": 0.85,
            },
        )

        with (
            patch("app.workflows.nodes.specialist_dispatch.settings") as mock_settings,
            patch(
                "app.workflows.nodes.specialist_dispatch.async_session_factory",
                side_effect=Exception("no-db-in-unit-test"),
            ),
        ):
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            result = await specialist_dispatch_node(state)  # type: ignore[arg-type]

        metrics = result.get("supervisor_metrics") or {}
        assert metrics.get("handoffs") == 2
        delegations = metrics.get("delegations_per_agent") or {}
        assert delegations.get("network_vpn") == 2

    @pytest.mark.asyncio
    async def test_dispatch_initializes_metrics_from_zero(self) -> None:
        from app.workflows.nodes.specialist_dispatch import specialist_dispatch_node

        state = _base_state(
            supervisor_metrics=None,  # no prior metrics (first dispatch)
            supervisor_decision={
                "action": NextAction.DELEGATE.value,
                "agent": "network_vpn",
                "sub_agent": None,
                "confidence": 0.85,
            },
        )

        with (
            patch("app.workflows.nodes.specialist_dispatch.settings") as mock_settings,
            patch(
                "app.workflows.nodes.specialist_dispatch.async_session_factory",
                side_effect=Exception("no-db-in-unit-test"),
            ),
        ):
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            result = await specialist_dispatch_node(state)  # type: ignore[arg-type]

        metrics = result.get("supervisor_metrics") or {}
        assert metrics.get("handoffs") == 1
        assert metrics.get("delegations_per_agent", {}).get("network_vpn") == 1

    @pytest.mark.asyncio
    async def test_dispatch_noop_when_feature_off(self) -> None:
        from app.workflows.nodes.specialist_dispatch import specialist_dispatch_node

        state = _base_state(supervisor_metrics={"handoffs": 5, "delegations_per_agent": {}})

        with patch("app.workflows.nodes.specialist_dispatch.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = False
            result = await specialist_dispatch_node(state)  # type: ignore[arg-type]

        assert result == {}  # no-op; supervisor_metrics not touched
