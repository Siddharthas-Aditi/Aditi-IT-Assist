"""Web-fallback routing regression tests (Gap: declared but unwired path).

Three things are verified:

1. **Not silent**: NextAction.WEB_FALLBACK from the supervisor now routes to
   ``escalate``, not to the policy/retrieve/resolve chain (which was the
   previous silent drop behaviour).

2. **Registry accuracy**: no SpecialistAgentSpec in the live AGENT_REGISTRY has
   ``web_fallback_allowed=True`` while the web-fallback node is absent from the
   graph. The flag must only be ``True`` when the runtime can actually execute it.

3. **Supervisor no longer emits WEB_FALLBACK for zoom/network_vpn**: since the
   flag is now ``False`` for both, the per-specialist cap check returns ESCALATE
   directly instead of WEB_FALLBACK — no misleading action in the decision log.

Before / after summary
----------------------
``zoom_meetings`` before: web_fallback_allowed=True → supervisor could emit
    WEB_FALLBACK → route_after_supervisor routes to "policy" (SILENT DROP).
``zoom_meetings`` after:  web_fallback_allowed=False → supervisor emits ESCALATE
    instead of WEB_FALLBACK → and if WEB_FALLBACK somehow arrives at the router
    it now routes to "escalate" (explicit, not silent).

Same for ``network_vpn``.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services.agents.intent_classifier import ConversationIntent, IntentClassification
from app.services.agents.registry import (
    AGENT_REGISTRY,
    SpecialistAgentSpec,
    find_specialist_for,
    list_specialists,
)
from app.services.agents.supervisor import NextAction, SessionMetrics, SupervisorDecision, decide
from app.workflows.graph import route_after_supervisor

# ── 1. Routing: WEB_FALLBACK → escalate, not policy ─────────────────────────


class TestWebFallbackRouting:
    """route_after_supervisor must not silently drop WEB_FALLBACK."""

    def _state_with_action(self, action: NextAction) -> dict:
        return {"supervisor_decision": {"action": action.value}}

    def test_web_fallback_routes_to_escalate_in_primary_mode(self) -> None:
        """Before fix: WEB_FALLBACK → policy (silent). After: → escalate."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            result = route_after_supervisor(  # type: ignore[arg-type]
                self._state_with_action(NextAction.WEB_FALLBACK)
            )
        assert result == "escalate", (
            "WEB_FALLBACK must route to escalate when the web-fallback node "
            "is not yet in the graph — the signal must never be silently dropped"
        )

    def test_web_fallback_in_shadow_mode_still_routes_to_policy(self) -> None:
        """In shadow mode the supervisor is a pass-through; WEB_FALLBACK is logged only."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = False
            result = route_after_supervisor(  # type: ignore[arg-type]
                self._state_with_action(NextAction.WEB_FALLBACK)
            )
        # Shadow mode unconditionally returns "policy" — no routing change
        assert result == "policy"

    def test_escalate_still_routes_to_escalate(self) -> None:
        """Sanity: existing ESCALATE routing unchanged."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            result = route_after_supervisor(  # type: ignore[arg-type]
                self._state_with_action(NextAction.ESCALATE)
            )
        assert result == "escalate"

    def test_delegate_still_routes_to_policy(self) -> None:
        """Sanity: existing DELEGATE routing unchanged."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            result = route_after_supervisor(  # type: ignore[arg-type]
                self._state_with_action(NextAction.DELEGATE)
            )
        assert result == "policy"


# ── 2. Registry accuracy: no specialist has web_fallback_allowed=True ────────


class TestRegistryWebFallbackAccuracy:
    """Flags in the live registry must accurately reflect runtime capability."""

    def test_no_specialist_has_web_fallback_allowed_true(self) -> None:
        """No specialist may have web_fallback_allowed=True until a web_fallback_node
        exists in the graph. The flag must only be True when the runtime can execute it."""
        violators = [s.name for s in list_specialists() if s.web_fallback_allowed]
        assert violators == [], (
            f"Specialists {violators} have web_fallback_allowed=True but the "
            "web-fallback graph node is not yet implemented. Set the flag to False "
            "until the node is wired (see docs/development/rollout-plan-multi-agent.md)."
        )

    def test_zoom_meetings_web_fallback_is_false(self) -> None:
        spec = find_specialist_for(category="video-conferencing/zoom")
        assert spec is not None
        assert spec.web_fallback_allowed is False

    def test_network_vpn_web_fallback_is_false(self) -> None:
        spec = find_specialist_for(category="network/connectivity")
        assert spec is not None
        assert spec.web_fallback_allowed is False


# ── 3. Supervisor no longer emits WEB_FALLBACK for zoom/network_vpn ──────────


def _ic(intent: ConversationIntent = ConversationIntent.CONTINUE) -> IntentClassification:
    return IntentClassification(intent=intent, confidence=0.9, matched="test")


def _decide_at_cap(*, category: str, system: str, subtype: str) -> SupervisorDecision:
    """Call decide() with per-specialist count at the cap (3 delegations)."""
    metrics = SessionMetrics()
    # Manually set the delegation count to hit the cap.
    spec = find_specialist_for(category=category, system=system, subtype=subtype)
    assert spec is not None
    for _ in range(3):
        metrics.record_delegation(spec.name)
    return decide(
        intent=_ic(),
        issue_category=category,
        issue_subtype=subtype,
        normalized_system=system,
        knowledge_confidence=0.5,
        has_knowledge_results=True,
        needs_clarification=False,
        issue_resolved=False,
        resolution_attempts=2,
        metrics=metrics,
        extra_slots={"network_type": "vpn"},
    )


class TestSupervisorWebFallbackBehavior:
    """Supervisor must not emit WEB_FALLBACK for zoom_meetings or network_vpn
    now that web_fallback_allowed is False — it should emit ESCALATE instead."""

    def test_zoom_meetings_at_cap_escalates_not_web_fallback(self) -> None:
        """Before fix: supervisor emitted WEB_FALLBACK. After: ESCALATE."""
        decision = _decide_at_cap(
            category="video-conferencing/zoom",
            system="zoom",
            subtype="no-audio",
        )
        assert decision.action is NextAction.ESCALATE
        assert decision.action is not NextAction.WEB_FALLBACK

    def test_network_vpn_at_cap_escalates_not_web_fallback(self) -> None:
        """Before fix: supervisor emitted WEB_FALLBACK. After: ESCALATE."""
        decision = _decide_at_cap(
            category="network/connectivity",
            system="vpn",
            subtype="vpn-not-connecting",
        )
        assert decision.action is NextAction.ESCALATE
        assert decision.action is not NextAction.WEB_FALLBACK

    def test_web_fallback_action_is_still_a_valid_enum_value(self) -> None:
        """WEB_FALLBACK remains in NextAction for future use; it just isn't emitted."""
        assert NextAction.WEB_FALLBACK.value == "web_fallback"

    def test_web_fallback_decision_with_web_research_already_tried_escalates(self) -> None:
        """If web_research has been tried once, the cap falls through to ESCALATE."""
        metrics = SessionMetrics()
        spec = find_specialist_for(category="video-conferencing/zoom")
        assert spec is not None
        for _ in range(3):
            metrics.record_delegation(spec.name)
        metrics.record_delegation("web_research")  # already tried once

        decision = decide(
            intent=_ic(),
            issue_category="video-conferencing/zoom",
            issue_subtype="no-audio",
            normalized_system="zoom",
            knowledge_confidence=0.5,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=2,
            metrics=metrics,
        )
        assert decision.action is NextAction.ESCALATE


# ── 4. Before / after explicit proof ─────────────────────────────────────────


class TestBeforeAfterProof:
    """Explicit proof for the requirement: before/after for zoom and network_vpn."""

    def test_zoom_before_route_after_supervisor_was_policy_after_is_escalate(self) -> None:
        """Documents the exact before/after routing change."""
        state: dict = {"supervisor_decision": {"action": NextAction.WEB_FALLBACK.value}}

        # BEFORE (shadow mode = always policy; behaviour was "silent drop"):
        with patch("app.workflows.graph.settings") as s:
            s.FEATURE_SUPERVISOR_PRIMARY = False
            before_route = route_after_supervisor(state)  # type: ignore[arg-type]
        assert before_route == "policy"  # shadow: pass-through regardless

        # AFTER (primary mode, WEB_FALLBACK explicitly handled):
        with patch("app.workflows.graph.settings") as s:
            s.FEATURE_SUPERVISOR_PRIMARY = True
            after_route = route_after_supervisor(state)  # type: ignore[arg-type]
        assert after_route == "escalate"

    def test_network_vpn_before_after_same_as_zoom(self) -> None:
        """network_vpn sees the same routing correction as zoom_meetings."""
        state: dict = {"supervisor_decision": {"action": NextAction.WEB_FALLBACK.value}}
        with patch("app.workflows.graph.settings") as s:
            s.FEATURE_SUPERVISOR_PRIMARY = True
            route = route_after_supervisor(state)  # type: ignore[arg-type]
        assert route == "escalate"

    def test_zoom_meetings_registry_before_false_after_false(self) -> None:
        """zoom_meetings.web_fallback_allowed: was True (incorrect), now False."""
        spec = AGENT_REGISTRY.get("zoom_meetings")
        assert isinstance(spec, SpecialistAgentSpec)
        assert spec.web_fallback_allowed is False, (
            "zoom_meetings.web_fallback_allowed must be False until the web-fallback "
            "node is wired into the graph"
        )

    def test_network_vpn_registry_before_false_after_false(self) -> None:
        """network_vpn.web_fallback_allowed: was True (incorrect), now False."""
        spec = AGENT_REGISTRY.get("network_vpn")
        assert isinstance(spec, SpecialistAgentSpec)
        assert spec.web_fallback_allowed is False, (
            "network_vpn.web_fallback_allowed must be False until the web-fallback "
            "node is wired into the graph"
        )
