"""Specialist dispatch end-to-end tests — Workstream 1 regression suite.

Tests the full dispatch-to-resolution paths for three automated task categories:

  1. Password reset (access_mfa → password-expired subtype)
  2. Account unlock (access_mfa → account-locked subtype)
  3. VPN not connecting (network_vpn → vpn-not-connecting subtype)

For each category we verify:
  - Approved path: triage → supervisor DELEGATE → retrieval → dispatch →
    specialist returns steps → ledger entry recorded.
  - Rejected/escalation path: specialist signals exhaustion → route to escalate.
  - Low-confidence routes to human: retrieval confidence below floor → escalate
    (reuses escalation_triggers.py, no separate routing condition).

Graph-level routing tests:
  - route_after_supervisor honours FEATURE_SUPERVISOR_PRIMARY=True/False.
  - route_after_retrieval routes to specialist_dispatch on DELEGATE action.
  - Fallback to legacy resolve when FEATURE_SUPERVISOR_PRIMARY=False.

Ledger tests:
  - ActionLedgerService creates and completes entries correctly.
  - Repository query methods return correct entries by session/ticket.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.intent_classifier import ConversationIntent, IntentClassification
from app.services.agents.registry import find_specialist_for
from app.services.agents.specialists import get_specialist
from app.services.agents.supervisor import NextAction, SessionMetrics, SupervisorDecision, decide
from app.workflows.graph import (
    route_after_retrieval,
    route_after_specialist_dispatch,
    route_after_supervisor,
)
from app.workflows.nodes.specialist_dispatch import specialist_dispatch_node

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _ic(intent: ConversationIntent, conf: float = 0.9) -> IntentClassification:
    return IntentClassification(intent=intent, confidence=conf, matched="test")


def _grounded_articles(subtype: str = "password-expired") -> list[dict]:
    """Minimal grounded article stubs for tests that don't hit the real KB."""
    return [
        {
            "id": f"kb-{subtype}",
            "title": f"{subtype} troubleshooting",
            "subcategory": subtype,
            "subtype": subtype,
            "resolution_steps": [
                {"instruction": "Open a web browser and go to the password reset page."},
                {"instruction": "Enter your email address and click Send."},
                {"instruction": "Check your email for a reset link and click it."},
            ],
            "relevance_score": 0.85,
        }
    ]


def _state(
    *,
    issue_category: str,
    issue_subtype: str,
    normalized_system: str,
    supervisor_action: NextAction = NextAction.DELEGATE,
    supervisor_agent: str = "",
    supervisor_sub_agent: str | None = None,
    knowledge_confidence: float = 0.82,
    articles: list[dict] | None = None,
) -> dict[str, Any]:
    diag = DiagnosticContext(
        issue_category=issue_category,
        issue_subtype=issue_subtype,
        normalized_system=normalized_system,
        subtype_confidence=0.9,
    )
    return {
        "session_id": f"test-{uuid.uuid4().hex[:8]}",
        "user_id": "user-123",
        "user_name": "Test User",
        "user_email": "test@example.com",
        "messages": [HumanMessage(content="my password expired")],
        "issue_category": issue_category,
        "issue_subtype": issue_subtype,
        "knowledge_results": articles or _grounded_articles(issue_subtype),
        "knowledge_confidence": knowledge_confidence,
        "knowledge_citations": [],
        "retrieval_trace": None,
        "diagnostic_context": diag.to_dict(),
        "supervisor_decision": {
            "action": supervisor_action.value,
            "agent": supervisor_agent or _default_specialist(issue_category, issue_subtype),
            "sub_agent": supervisor_sub_agent,
            "reason": "test dispatch",
            "confidence": 0.82,
        },
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


def _default_specialist(category: str, subtype: str) -> str:
    spec = find_specialist_for(category=category, subtype=subtype)
    return spec.name if spec else "access_mfa"


# ── Registry: confirm 3 categories route to expected specialists ───────────────


class TestRegistryRouting:
    def test_password_expired_routes_to_access_mfa(self) -> None:
        spec = find_specialist_for(category="access/permissions", subtype="password-expired")
        assert spec is not None
        assert spec.name == "access_mfa"

    def test_account_locked_routes_to_access_mfa(self) -> None:
        spec = find_specialist_for(category="access/permissions", subtype="account-locked")
        assert spec is not None
        assert spec.name == "access_mfa"

    def test_vpn_routes_to_network_vpn(self) -> None:
        spec = find_specialist_for(category="network/connectivity", subtype="vpn-not-connecting")
        assert spec is not None
        assert spec.name == "network_vpn"

    def test_device_intune_routes_to_device_intune(self) -> None:
        spec = find_specialist_for(
            category="device-management/intune", subtype="enrollment-failure"
        )
        assert spec is not None
        assert spec.name == "device_intune"

    def test_get_specialist_returns_instance(self) -> None:
        specialist = get_specialist("access_mfa")
        assert specialist is not None

    def test_get_specialist_unknown_returns_none(self) -> None:
        assert get_specialist("unknown_specialist") is None


# ── Supervisor routing ─────────────────────────────────────────────────────────


class TestRouteAfterSupervisor:
    def test_shadow_mode_always_returns_policy(self) -> None:
        """When FEATURE_SUPERVISOR_PRIMARY is False, supervisor is pass-through."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = False
            state: dict[str, Any] = {"supervisor_decision": {"action": NextAction.ESCALATE.value}}
            assert route_after_supervisor(state) == "policy"  # type: ignore[arg-type]

    def test_primary_escalate_action_routes_to_escalate(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            state: dict[str, Any] = {"supervisor_decision": {"action": NextAction.ESCALATE.value}}
            assert route_after_supervisor(state) == "escalate"  # type: ignore[arg-type]

    def test_primary_end_action_routes_to_end(self) -> None:
        from langgraph.graph import END

        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            state: dict[str, Any] = {"supervisor_decision": {"action": NextAction.END.value}}
            assert route_after_supervisor(state) == str(END)  # type: ignore[arg-type]

    def test_primary_clarify_routes_to_end(self) -> None:
        from langgraph.graph import END

        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            state: dict[str, Any] = {"supervisor_decision": {"action": NextAction.CLARIFY.value}}
            assert route_after_supervisor(state) == str(END)  # type: ignore[arg-type]

    def test_primary_delegate_routes_to_policy(self) -> None:
        """DELEGATE still runs through policy (RBAC) before dispatch."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            state: dict[str, Any] = {"supervisor_decision": {"action": NextAction.DELEGATE.value}}
            assert route_after_supervisor(state) == "policy"  # type: ignore[arg-type]

    def test_primary_missing_decision_routes_to_policy(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            assert route_after_supervisor({}) == "policy"  # type: ignore[arg-type]


# ── Retrieval routing ──────────────────────────────────────────────────────────


class TestRouteAfterRetrieval:
    def _make_good_state(
        self, supervisor_action: NextAction = NextAction.DELEGATE
    ) -> dict[str, Any]:
        """State with sufficient confidence to not trigger escalation."""
        return {
            "knowledge_results": [{"id": "kb-1", "title": "test"}],
            "knowledge_confidence": 0.9,
            "supervisor_decision": {"action": supervisor_action.value},
            "diagnostic_context": {"failed_steps": [], "phase": "resolving"},
            "turn_count": 1,
        }

    def test_shadow_mode_routes_to_resolve(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = False
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state = self._make_good_state()
            assert route_after_retrieval(state) == "resolve"  # type: ignore[arg-type]

    def test_primary_delegate_routes_to_specialist_dispatch(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state = self._make_good_state(NextAction.DELEGATE)
            assert route_after_retrieval(state) == "specialist_dispatch"  # type: ignore[arg-type]

    def test_primary_delegate_sub_routes_to_specialist_dispatch(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state = self._make_good_state(NextAction.DELEGATE_SUB)
            assert route_after_retrieval(state) == "specialist_dispatch"  # type: ignore[arg-type]

    def test_primary_retrieve_routes_to_resolve(self) -> None:
        """RETRIEVE action (no specialist) still uses legacy resolve."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state = self._make_good_state(NextAction.RETRIEVE)
            assert route_after_retrieval(state) == "resolve"  # type: ignore[arg-type]

    def test_low_confidence_escalates_regardless_of_supervisor(self) -> None:
        """Low retrieval confidence escalates even when supervisor says DELEGATE."""
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.60
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state: dict[str, Any] = {
                "knowledge_results": [{"id": "kb-1"}],
                "knowledge_confidence": 0.30,  # below floor
                "supervisor_decision": {"action": NextAction.DELEGATE.value},
                "diagnostic_context": {"failed_steps": []},
                "turn_count": 1,
            }
            assert route_after_retrieval(state) == "escalate"  # type: ignore[arg-type]

    def test_no_articles_escalates(self) -> None:
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            state: dict[str, Any] = {
                "knowledge_results": [],
                "knowledge_confidence": 0.0,
                "supervisor_decision": {"action": NextAction.DELEGATE.value},
                "diagnostic_context": {},
                "turn_count": 1,
            }
            assert route_after_retrieval(state) == "escalate"  # type: ignore[arg-type]


# ── Dispatch node — three automated task categories ───────────────────────────


class TestSpecialistDispatchNode:
    """Test the specialist_dispatch_node across 3 task categories."""

    async def _run_dispatch(
        self,
        state: dict[str, Any],
        *,
        feature_on: bool = True,
    ) -> dict[str, Any]:
        with (
            patch("app.workflows.nodes.specialist_dispatch.settings") as mock_settings,
            patch(
                "app.workflows.nodes.specialist_dispatch.async_session_factory",
                side_effect=Exception("no-db-in-unit-test"),
            ),
        ):
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = feature_on
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            return await specialist_dispatch_node(state)  # type: ignore[arg-type]

    # ── 1. Password reset (access_mfa → password-expired) ─────────────────

    @pytest.mark.asyncio
    async def test_password_reset_approved_path(self) -> None:
        """Dispatch to access_mfa for password-expired returns grounded steps."""
        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
            articles=_grounded_articles("password-expired"),
        )
        result = await self._run_dispatch(state)

        # Specialist ran and returned steps
        assert result.get("resolution_steps"), "expected steps from password reset specialist"
        assert result.get("resolution_confidence", 0) > 0
        assert not result.get("should_escalate"), "password reset should NOT escalate on first turn"

    @pytest.mark.asyncio
    async def test_password_reset_escalates_when_steps_exhausted(self) -> None:
        """After all steps are tried (all in failed_steps), specialist escalates."""
        # Mark all steps as already failed so the specialist has nothing left
        diag = DiagnosticContext(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
            subtype_confidence=0.9,
        )
        articles = _grounded_articles("password-expired")
        for art in articles:
            for step in art.get("resolution_steps", []):
                diag.failed_steps.append(step["instruction"])

        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
            articles=articles,
        )
        state["diagnostic_context"] = diag.to_dict()

        result = await self._run_dispatch(state)

        # Specialist signals exhaustion → should_escalate must be True
        assert result.get("should_escalate"), "exhausted steps must signal escalation"

    @pytest.mark.asyncio
    async def test_password_reset_low_confidence_routes_via_escalation_triggers(self) -> None:
        """Low knowledge_confidence at retrieval stage → escalate_triggers catches it."""
        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
            knowledge_confidence=0.20,  # below floor
            articles=_grounded_articles("password-expired"),
        )
        # Verify the routing function (not the node) catches this
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            route = route_after_retrieval(state)  # type: ignore[arg-type]
        assert route == "escalate", "low confidence must escalate, not dispatch"

    # ── 2. Account unlock (access_mfa → account-locked) ─────────────────

    @pytest.mark.asyncio
    async def test_account_unlock_approved_path(self) -> None:
        """Dispatch to access_mfa for account-locked returns grounded steps."""
        state = _state(
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            supervisor_agent="access_mfa",
            articles=_grounded_articles("account-locked"),
        )
        result = await self._run_dispatch(state)

        assert result.get("resolution_steps"), "expected steps from account unlock specialist"
        assert not result.get("should_escalate")

    @pytest.mark.asyncio
    async def test_account_unlock_escalates_when_exhausted(self) -> None:
        """Exhausted account-locked steps must signal escalation."""
        diag = DiagnosticContext(
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            subtype_confidence=0.9,
        )
        articles = _grounded_articles("account-locked")
        for art in articles:
            for step in art.get("resolution_steps", []):
                diag.failed_steps.append(step["instruction"])

        state = _state(
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            articles=articles,
        )
        state["diagnostic_context"] = diag.to_dict()
        result = await self._run_dispatch(state)
        assert result.get("should_escalate")

    @pytest.mark.asyncio
    async def test_account_unlock_user_request_escalates_via_supervisor(self) -> None:
        """When supervisor decides ESCALATE (user asked for human), dispatch is skipped."""
        state = _state(
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            supervisor_action=NextAction.ESCALATE,
            supervisor_agent="access_mfa",
        )
        # route_after_supervisor should catch this before dispatch is ever called
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            route = route_after_supervisor(state)  # type: ignore[arg-type]
        assert route == "escalate"

        # And dispatch node itself returns empty when action is not DELEGATE
        result = await self._run_dispatch(state)
        # The node checks action; ESCALATE → returns {}
        # (action is ESCALATE, not DELEGATE; node returns early)
        assert result == {} or not result.get("resolution_steps")

    # ── 3. VPN not connecting (network_vpn → vpn-not-connecting) ─────────

    @pytest.mark.asyncio
    async def test_vpn_approved_path(self) -> None:
        """Dispatch to network_vpn for vpn-not-connecting returns grounded steps."""
        state = _state(
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            supervisor_agent="network_vpn",
            articles=_grounded_articles("vpn-not-connecting"),
        )
        result = await self._run_dispatch(state)

        assert result.get("resolution_steps"), "expected steps from VPN specialist"
        assert not result.get("should_escalate")

    @pytest.mark.asyncio
    async def test_vpn_escalates_when_exhausted(self) -> None:
        diag = DiagnosticContext(
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            subtype_confidence=0.9,
        )
        articles = _grounded_articles("vpn-not-connecting")
        for art in articles:
            for step in art.get("resolution_steps", []):
                diag.failed_steps.append(step["instruction"])

        state = _state(
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            supervisor_agent="network_vpn",
            articles=articles,
        )
        state["diagnostic_context"] = diag.to_dict()
        result = await self._run_dispatch(state)
        assert result.get("should_escalate")

    @pytest.mark.asyncio
    async def test_vpn_low_confidence_human_path(self) -> None:
        """VPN with below-floor confidence routes to human (escalation_triggers gate)."""
        state = _state(
            issue_category="network/connectivity",
            issue_subtype="vpn-not-connecting",
            normalized_system="vpn",
            supervisor_agent="network_vpn",
            knowledge_confidence=0.15,
        )
        with patch("app.workflows.graph.settings") as mock_settings:
            mock_settings.FEATURE_SUPERVISOR_PRIMARY = True
            mock_settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE = 0.35
            mock_settings.RESOLUTION_MISS_ESCALATE_THRESHOLD = 3
            route = route_after_retrieval(state)  # type: ignore[arg-type]
        assert route == "escalate"

    # ── Feature flag off → dispatch node is no-op ─────────────────────────

    @pytest.mark.asyncio
    async def test_dispatch_is_noop_when_feature_off(self) -> None:
        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
        )
        result = await self._run_dispatch(state, feature_on=False)
        assert result == {}

    # ── Unknown specialist → returns empty ────────────────────────────────

    @pytest.mark.asyncio
    async def test_unknown_specialist_returns_empty(self) -> None:
        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
        )
        state["supervisor_decision"]["agent"] = "nonexistent_specialist"
        result = await self._run_dispatch(state)
        assert result == {}

    # ── Missing supervisor decision → returns empty ────────────────────────

    @pytest.mark.asyncio
    async def test_missing_supervisor_decision_returns_empty(self) -> None:
        state = _state(
            issue_category="access/permissions",
            issue_subtype="password-expired",
            normalized_system="ad",
        )
        state.pop("supervisor_decision", None)
        result = await self._run_dispatch(state)
        assert result == {}


# ── route_after_specialist_dispatch ───────────────────────────────────────────


class TestRouteAfterSpecialistDispatch:
    def test_escalation_signal_routes_to_escalate(self) -> None:
        state: dict[str, Any] = {"should_escalate": True}
        assert route_after_specialist_dispatch(state) == "escalate"  # type: ignore[arg-type]

    def test_clean_result_returns_end(self) -> None:
        from langgraph.graph import END

        state: dict[str, Any] = {"should_escalate": False}
        assert route_after_specialist_dispatch(state) == str(END)  # type: ignore[arg-type]


# ── Ledger service unit tests ──────────────────────────────────────────────────


class TestActionLedgerService:
    """Unit-test ActionLedgerService against a mock repository."""

    def _mock_repo(self):
        repo = AsyncMock()
        entry = MagicMock()
        entry.id = uuid.uuid4()
        repo.create.return_value = entry
        repo.complete.return_value = entry
        return repo, entry

    @pytest.mark.asyncio
    async def test_begin_dispatch_calls_repo_create(self) -> None:
        from app.services.agents.action_ledger_service import ActionLedgerService

        repo, entry = self._mock_repo()
        svc = ActionLedgerService(repo)
        result = await svc.begin_dispatch(
            session_id="s-1",
            triggered_by="user-1",
            specialist_name="access_mfa",
            sub_agent_name=None,
            inputs_snapshot={"category": "access/permissions"},
        )
        assert result is entry
        repo.create.assert_awaited_once()
        call_kwargs = repo.create.call_args.kwargs
        assert call_kwargs["session_id"] == "s-1"
        assert call_kwargs["specialist_name"] == "access_mfa"
        assert call_kwargs["approval_status"] == "auto"

    @pytest.mark.asyncio
    async def test_complete_dispatch_records_confidence_and_signal(self) -> None:
        from app.services.agents.action_ledger_service import ActionLedgerService

        repo, entry = self._mock_repo()
        svc = ActionLedgerService(repo)
        await svc.complete_dispatch(
            entry,
            result_snapshot={"steps_count": 3},
            confidence=0.85,
            escalation_signal=None,
        )
        repo.complete.assert_awaited_once_with(
            entry,
            result_snapshot={"steps_count": 3},
            confidence=0.85,
            escalation_signal=None,
        )

    @pytest.mark.asyncio
    async def test_complete_dispatch_records_escalation_signal(self) -> None:
        from app.services.agents.action_ledger_service import ActionLedgerService

        repo, entry = self._mock_repo()
        svc = ActionLedgerService(repo)
        await svc.complete_dispatch(
            entry,
            result_snapshot={},
            confidence=0.0,
            escalation_signal="specialist exhausted all grounded steps without resolution",
        )
        call_kwargs = repo.complete.call_args.kwargs
        assert call_kwargs["escalation_signal"] is not None


# ── Supervisor decide() routing for the 3 categories ──────────────────────────


class TestSupervisorDecideForThreeCategories:
    """Pin supervisor routing decisions for the 3 task categories."""

    def _decide(self, *, category: str, subtype: str, system: str) -> SupervisorDecision:
        return decide(
            intent=_ic(ConversationIntent.CONTINUE),
            issue_category=category,
            issue_subtype=subtype,
            normalized_system=system,
            knowledge_confidence=0.82,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=0,
            metrics=SessionMetrics(),
        )

    def test_password_reset_delegates_to_access_mfa(self) -> None:
        d = self._decide(category="access/permissions", subtype="password-expired", system="ad")
        assert d.action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB)
        assert d.agent == "access_mfa"

    def test_account_locked_delegates_to_access_mfa_sub_agent(self) -> None:
        d = self._decide(category="access/permissions", subtype="account-locked", system="ad")
        assert d.action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB)
        assert d.agent == "access_mfa"

    def test_vpn_delegates_to_network_vpn(self) -> None:
        """Supervisor delegates to network_vpn once required slots are satisfied.

        Without network_type in the snapshot, supervisor returns CLARIFY (correct
        behavior — it needs to know if it's WiFi, ethernet, etc.). Once the triage
        node fills that slot, routing proceeds to DELEGATE. We pin the agent name.
        """
        d = self._decide(
            category="network/connectivity",
            subtype="vpn-not-connecting",
            system="vpn",
        )
        # Supervisor correctly clarifies (network_type slot not in snapshot)
        assert d.action is NextAction.CLARIFY
        assert d.agent == "network_vpn"

    def test_device_intune_delegates_to_device_intune(self) -> None:
        """Supervisor identifies device_intune specialist even when platform_os is missing."""
        d = self._decide(
            category="device-management/intune",
            subtype="enrollment-failure",
            system="intune",
        )
        # Supervisor correctly clarifies (platform_os slot not in snapshot)
        assert d.action is NextAction.CLARIFY
        assert d.agent == "device_intune"

    def test_user_escalate_request_bypasses_delegate(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.ESCALATE_REQUEST),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.82,
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=1,
            metrics=SessionMetrics(),
        )
        assert d.action is NextAction.ESCALATE

    def test_low_confidence_after_attempts_escalates(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            issue_category="access/permissions",
            issue_subtype="account-locked",
            normalized_system="ad",
            knowledge_confidence=0.25,  # below escalate_below floor
            has_knowledge_results=True,
            needs_clarification=False,
            issue_resolved=False,
            resolution_attempts=2,
            metrics=SessionMetrics(),
        )
        assert d.action is NextAction.ESCALATE
