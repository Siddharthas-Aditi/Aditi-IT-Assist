"""Tests for the agent registry.

The registry is the source of truth for routing; these tests pin its
contract so a careless edit can't silently re-scope a specialist.
"""

from __future__ import annotations

from app.services.agents.registry import (
    AGENT_REGISTRY,
    REGISTRY_VERSION,
    AgentRole,
    SpecialistAgentSpec,
    find_specialist_for,
    find_sub_agent_for,
    get_agent,
    list_specialists,
)


class TestRegistryShape:
    def test_supervisor_present(self) -> None:
        spec = get_agent("supervisor")
        assert spec is not None
        assert spec.role is AgentRole.SUPERVISOR

    def test_all_specialists_typed(self) -> None:
        for spec in list_specialists():
            assert isinstance(spec, SpecialistAgentSpec)
            assert spec.role is AgentRole.SPECIALIST
            assert spec.systems or spec.categories, (
                f"{spec.name}: must declare systems or categories"
            )

    def test_version_pinned(self) -> None:
        assert REGISTRY_VERSION  # any non-empty string

    def test_shared_subtypes_resolved_by_system(self) -> None:
        """Subtypes may be shared across specialists when systems disambiguate.

        Example: both ``access_mfa`` and ``sixth_sense`` legitimately handle
        ``account-locked`` — the *system* selects the right specialist. The
        registry's resolution rule must pick the system-specific match.
        """
        access = find_specialist_for(system="ad", subtype="account-locked")
        assert access is not None and access.name == "access_mfa"

        ss = find_specialist_for(system="sixth_sense", subtype="account-locked")
        assert ss is not None and ss.name == "sixth_sense"


class TestFindSpecialist:
    def test_by_subtype_wins(self) -> None:
        spec = find_specialist_for(subtype="mailbox-full")
        assert spec is not None and spec.name == "outlook"

    def test_by_system(self) -> None:
        spec = find_specialist_for(system="outlook")
        assert spec is not None and spec.name == "outlook"

    def test_by_category(self) -> None:
        spec = find_specialist_for(category="email/outlook")
        assert spec is not None and spec.name == "outlook"

    def test_no_match_returns_none(self) -> None:
        assert find_specialist_for(category="not-a-real-category") is None

    def test_subtype_overrides_unrelated_system(self) -> None:
        """The most specific signal wins."""
        spec = find_specialist_for(
            system="not-real",
            category="not-real",
            subtype="account-locked",
        )
        assert spec is not None and spec.name == "access_mfa"


class TestFindSubAgent:
    def test_resolves_outlook_mailbox_full(self) -> None:
        outlook = find_specialist_for(category="email/outlook")
        assert outlook is not None
        sub = find_sub_agent_for(outlook, "mailbox-full")
        assert sub is not None and sub.name == "outlook.mailbox_full"

    def test_unknown_subtype_returns_none(self) -> None:
        outlook = find_specialist_for(category="email/outlook")
        assert outlook is not None
        assert find_sub_agent_for(outlook, "totally-unknown") is None


class TestAgentSpecBounds:
    def test_reasonable_bounds(self) -> None:
        for spec in AGENT_REGISTRY.values():
            assert 1 <= spec.max_handoffs <= 20
            assert 1 <= spec.max_turns <= 50
            assert 0 < spec.timeout_seconds <= 120
            t = spec.thresholds
            assert 0.0 <= t.escalate_below <= t.clarify_below
            assert t.clarify_below <= t.answer_with_disclaimer
            assert t.answer_with_disclaimer <= t.answer_directly <= 1.0
