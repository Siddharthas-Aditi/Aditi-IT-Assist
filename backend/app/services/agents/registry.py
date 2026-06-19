"""Agent + sub-agent registry — the declarative contract for the multi-agent system.

The registry is the single source of truth for **what agents exist, what each
agent owns, and what it is allowed to do**. The supervisor reads from it on
every turn to route the conversation; specialist agents read from it to know
their scope; tests pin behavior against it.

Why a registry (and not "one big router function")
--------------------------------------------------
The old chat system encoded routing rules in code paths sprinkled across
``triage.py``, ``retrieval.py``, ``resolution.py``. Adding a new specialist
(e.g. a Zoom agent) meant editing every layer. The registry inverts that:

* Specialist agents register a ``SpecialistAgentSpec`` declaring their
  *systems*, *subtypes*, *required slots*, *retrieval domain*, *escalation
  triggers*, *max handoff depth*, and *required confidence floor*.
* The supervisor's routing logic is one function over the registry — no edits
  needed to add a new specialist.
* Governance lives in one place: every specialist is auditable, version-pinned,
  and has a documented owner.

Versioned, typed, deterministic
-------------------------------
* ``REGISTRY_VERSION`` bumps every change. Audit + analytics queries join on
  the version so we can detect behavior shifts in production.
* ``AgentSpec`` is a frozen dataclass; specs are constructed at import time
  and never mutated.
* Every spec has a stable ``name`` (used in audit logs, queue routing, and
  observability dashboards).

What's in here
--------------
* :class:`AgentRole` — coarse role (supervisor, triage, retrieval, specialist,
  web_research, escalation, response, knowledge_improvement).
* :class:`AgentSpec` — base spec. Every agent has one.
* :class:`SpecialistAgentSpec` — extends AgentSpec with scope + slot strategy.
* :class:`SubAgentSpec` — sub-agent of a specialist, scoped to one subtype
  family within the specialist's domain (e.g. *outlook → mailbox-full*).
* :data:`AGENT_REGISTRY` — the live mapping ``{agent_name: AgentSpec}``.
* :func:`get_agent`, :func:`find_specialist_for`, :func:`list_specialists`
  — read-only accessors used by the supervisor and tests.

What's NOT in here
------------------
* Runtime behavior — that lives in each agent's implementation module
  (``app/services/agents/specialists/<name>.py``). The registry only describes
  *what an agent can do*, not *how*. Keeping the description-vs-implementation
  boundary clean is what lets us write strong tests against the registry
  without instantiating agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Bump on any registry change (new agent, scope change, threshold change).
REGISTRY_VERSION = "1.0.0"


class AgentRole(StrEnum):
    """Coarse classification of an agent. Governs which contracts it must satisfy."""

    SUPERVISOR = "supervisor"
    TRIAGE = "triage"
    RETRIEVAL = "retrieval"
    SPECIALIST = "specialist"
    SUB_AGENT = "sub_agent"
    WEB_RESEARCH = "web_research"
    ESCALATION = "escalation"
    RESPONSE = "response"
    KNOWLEDGE_IMPROVEMENT = "knowledge_improvement"


# Confidence thresholds used by the supervisor + escalation logic. Defined here
# (not magic numbers in code) so they're tunable in one place and auditable.
@dataclass(frozen=True)
class ConfidenceThresholds:
    """Thresholds for the four routing decisions the supervisor makes."""

    clarify_below: float = 0.40       # below → ask a follow-up question
    answer_with_disclaimer: float = 0.55  # answer but flag uncertainty
    answer_directly: float = 0.75     # confident — answer plainly
    escalate_below: float = 0.30      # below → hand off to a human


DEFAULT_THRESHOLDS = ConfidenceThresholds()


@dataclass(frozen=True, kw_only=True)
class AgentSpec:
    """Base agent specification — every agent has one of these.

    ``kw_only=True`` keeps inheritance clean: subclasses can add their own
    non-default fields without bumping into the "non-default after default"
    rule that Python dataclasses normally enforce.
    """

    name: str                          # stable id, e.g. "supervisor", "outlook"
    role: AgentRole
    description: str
    owner: str = "platform-team"       # accountable team / individual
    version: str = "1.0.0"             # bump on behavior change
    # Resource bounds — the supervisor enforces these.
    max_handoffs: int = 3              # max times this agent may receive a handoff in one session
    max_turns: int = 10                # safety cap; supervisor escalates beyond this
    timeout_seconds: float = 25.0
    # Confidence floors — below escalate_below the supervisor escalates instead
    # of asking this agent to keep trying.
    thresholds: ConfidenceThresholds = DEFAULT_THRESHOLDS


@dataclass(frozen=True, kw_only=True)
class SubAgentSpec(AgentSpec):
    """A sub-agent inside a specialist's domain.

    Each sub-agent owns ONE issue subtype (or a small family of related
    subtypes) within a specialist. Sub-agents are the leaves of the routing
    tree: they map directly onto playbooks.
    """

    role: AgentRole = AgentRole.SUB_AGENT
    parent_specialist: str = ""        # the SpecialistAgentSpec.name this belongs to
    subtypes: tuple[str, ...] = field(default_factory=tuple)
    playbook_id: str = ""              # link into playbooks.py
    required_slots: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, kw_only=True)
class SpecialistAgentSpec(AgentSpec):
    """A specialist agent — owns a system / product domain.

    Example: the Outlook specialist owns ``email/outlook`` plus all aliases.
    The supervisor consults :func:`find_specialist_for` to pick the right one.
    """

    role: AgentRole = AgentRole.SPECIALIST
    # Systems / aliases this specialist owns (canonical entity names).
    systems: tuple[str, ...] = field(default_factory=tuple)
    # Issue categories this specialist handles ("email/outlook" etc.).
    categories: tuple[str, ...] = field(default_factory=tuple)
    # All subtypes this specialist or its sub-agents can handle.
    subtypes: tuple[str, ...] = field(default_factory=tuple)
    # Slot names that MUST be filled before this specialist will attempt a fix.
    required_slots: tuple[str, ...] = field(default_factory=tuple)
    # Domain filters for the retrieval agent. Empty = no filter.
    kb_domain_filter: tuple[str, ...] = field(default_factory=tuple)
    # Sub-agents owned by this specialist (keyed by sub-agent name).
    sub_agents: tuple[SubAgentSpec, ...] = field(default_factory=tuple)
    # Triggers that move from "try harder" to "hand off to a human".
    escalation_triggers: tuple[str, ...] = field(
        default_factory=lambda: (
            "user_requested_human",
            "exhausted_grounded_steps",
            "repeated_failure",
            "missing_required_data",
            "confidence_below_floor",
            "loop_detected",
        )
    )
    # Whether this specialist is allowed to use the web-research fallback.
    web_fallback_allowed: bool = False


# ── The registry ───────────────────────────────────────────────────────────
#
# Entries are constructed at import time (frozen dataclasses, no mutation
# after this point). Adding an agent is one declaration here + an
# implementation module under ``specialists/``.

_SUPERVISOR = AgentSpec(
    name="supervisor",
    role=AgentRole.SUPERVISOR,
    description=(
        "Top-level orchestrator. Reads conversation state + ConversationIntent, "
        "decides whether to clarify, retrieve, delegate to a specialist, "
        "fall back to web research, or hand off to a human."
    ),
    max_handoffs=6,  # supervisor sees every handoff; cap is global
)

_TRIAGE = AgentSpec(
    name="triage",
    role=AgentRole.TRIAGE,
    description="Entity normalization, intent detection, subtype classification.",
)

_RETRIEVAL = AgentSpec(
    name="retrieval",
    role=AgentRole.RETRIEVAL,
    description="Narrow, system-aware, subtype-aware KB retrieval with grounding guard.",
)

_RESPONSE = AgentSpec(
    name="response",
    role=AgentRole.RESPONSE,
    description="Renders the final user-facing message from grounded content.",
)

_ESCALATION = AgentSpec(
    name="escalation",
    role=AgentRole.ESCALATION,
    description="Builds the typed handoff package and queues it for IT Specialists.",
)

_WEB_RESEARCH = AgentSpec(
    name="web_research",
    role=AgentRole.WEB_RESEARCH,
    description=(
        "Controlled external-search fallback. Trust-tier filtered. Never writes "
        "to production KB — produces KnowledgeCandidate drafts for SME review."
    ),
)

_KNOWLEDGE_IMPROVEMENT = AgentSpec(
    name="knowledge_improvement",
    role=AgentRole.KNOWLEDGE_IMPROVEMENT,
    description=(
        "Converts feedback, unresolved sessions, specialist resolutions, and "
        "web-fallback hits into KnowledgeCandidate rows for review."
    ),
)

# ── Specialists ────────────────────────────────────────────────────────────
# Each specialist declares its scope. Sub-agents are co-located with their
# parent for readability — the supervisor walks the tree.

_OUTLOOK_SUB_AGENTS: tuple[SubAgentSpec, ...] = (
    SubAgentSpec(
        name="outlook.mailbox_full",
        description="Mailbox-quota issues (full, near full, send failures from quota).",
        parent_specialist="outlook",
        subtypes=("mailbox-full",),
        playbook_id="outlook/mailbox-full",
        required_slots=("affected_system",),
    ),
    SubAgentSpec(
        name="outlook.not_receiving",
        description="Inbound mail not arriving (filters, junk, rules, server-side).",
        parent_specialist="outlook",
        subtypes=("not-receiving-emails",),
        playbook_id="outlook/not-receiving-emails",
        required_slots=("affected_system",),
    ),
    SubAgentSpec(
        name="outlook.sending_failure",
        description="Outbound send failures (auth, server, attachment limits).",
        parent_specialist="outlook",
        subtypes=("sending-failure",),
        playbook_id="outlook/sending-failure",
    ),
    SubAgentSpec(
        name="outlook.startup",
        description="Outlook won't start, crashes on launch, or freezes.",
        parent_specialist="outlook",
        subtypes=("outlook-crash", "outlook-slow", "offline-mode"),
        playbook_id="outlook/startup",
    ),
)

_OUTLOOK = SpecialistAgentSpec(
    name="outlook",
    description="Microsoft Outlook + Exchange + M365 email scope.",
    systems=("outlook",),
    categories=("email/outlook",),
    subtypes=tuple(s for sub in _OUTLOOK_SUB_AGENTS for s in sub.subtypes),
    required_slots=("affected_system",),
    kb_domain_filter=("email/outlook",),
    sub_agents=_OUTLOOK_SUB_AGENTS,
    web_fallback_allowed=False,  # mature internal coverage; no web fallback needed
)

_ACCESS_SUB_AGENTS: tuple[SubAgentSpec, ...] = (
    SubAgentSpec(
        name="access.account_locked",
        description="AD/M365 account locked by failed sign-ins or policy.",
        parent_specialist="access_mfa",
        subtypes=("account-locked",),
        playbook_id="access/account-locked",
    ),
    SubAgentSpec(
        name="access.mfa_not_working",
        description="MFA prompt missing, code rejected, push not arriving.",
        parent_specialist="access_mfa",
        subtypes=("mfa-not-working", "otp-issue"),
        playbook_id="access/mfa",
    ),
    SubAgentSpec(
        name="access.password_expired",
        description="Password reset / expired.",
        parent_specialist="access_mfa",
        subtypes=("password-expired",),
        playbook_id="access/password-expired",
    ),
)

_ACCESS_MFA = SpecialistAgentSpec(
    name="access_mfa",
    description="Account access, MFA, password reset, sign-in failures.",
    systems=("ad", "m365", "okta"),
    categories=("access/permissions",),
    subtypes=tuple(s for sub in _ACCESS_SUB_AGENTS for s in sub.subtypes),
    required_slots=("normalized_system",),
    kb_domain_filter=("access/permissions",),
    sub_agents=_ACCESS_SUB_AGENTS,
)

_ZOOM = SpecialistAgentSpec(
    name="zoom_meetings",
    description="Zoom and Teams meeting issues — audio, video, screen share, joining.",
    systems=("zoom", "teams"),
    categories=("video-conferencing/zoom",),
    subtypes=("no-audio", "no-video", "cant-join-meeting", "screen-share-issue", "poor-quality"),
    required_slots=("normalized_system",),
    kb_domain_filter=("video-conferencing/zoom",),
    web_fallback_allowed=True,  # external vendor; web docs supplement KB
)

_DEVICE_INTUNE = SpecialistAgentSpec(
    name="device_intune",
    description="Intune / device-compliance / enrollment.",
    systems=("intune",),
    categories=("device-management/intune",),
    subtypes=("non-compliant", "enrollment-failure"),
    required_slots=("normalized_system", "platform_os"),
    kb_domain_filter=("device-management/intune",),
)

_SIXTH_SENSE = SpecialistAgentSpec(
    name="sixth_sense",
    description="Sixth Sense (Naukri) login and account issues.",
    systems=("sixth_sense",),
    categories=("access/sixth_sense",),
    subtypes=("login-failure", "account-locked", "otp-issue", "unhandled-message"),
    required_slots=("normalized_system",),
    kb_domain_filter=("access/sixth_sense",),
)

_HARDWARE = SpecialistAgentSpec(
    name="hardware",
    description="Camera, audio, peripherals, and other on-device hardware faults.",
    systems=("camera", "microphone", "headset"),
    categories=("hardware/camera", "hardware/audio", "hardware/other"),
    subtypes=("camera-not-detected", "microphone-not-working", "no-audio"),
    required_slots=("device_type",),
    kb_domain_filter=("hardware/camera", "hardware/audio", "hardware/other"),
)

_NETWORK_VPN = SpecialistAgentSpec(
    name="network_vpn",
    description="VPN, Wi-Fi, internet connectivity, and 3CX VoIP.",
    systems=("vpn", "3cx"),
    categories=("network/connectivity",),
    subtypes=(
        "vpn-not-connecting", "wifi-disconnecting", "internet-slow",
        "specific-site-unreachable", "3cx-voip-issue",
    ),
    required_slots=("network_type",),
    kb_domain_filter=("network/connectivity",),
    web_fallback_allowed=True,
)

# Master mapping. Every spec is intentionally enumerated here — no dynamic
# registration — so tests and audits can grep this file as the source of truth.
AGENT_REGISTRY: dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (
        _SUPERVISOR, _TRIAGE, _RETRIEVAL, _RESPONSE,
        _ESCALATION, _WEB_RESEARCH, _KNOWLEDGE_IMPROVEMENT,
        _OUTLOOK, _ACCESS_MFA, _ZOOM, _DEVICE_INTUNE,
        _SIXTH_SENSE, _HARDWARE, _NETWORK_VPN,
    )
}


# ── Accessors ──────────────────────────────────────────────────────────────


def get_agent(name: str) -> AgentSpec | None:
    """Return the spec for an agent by name, or ``None`` if unknown."""
    return AGENT_REGISTRY.get(name)


def list_specialists() -> list[SpecialistAgentSpec]:
    """All specialist agents, sorted by name (stable for tests)."""
    return sorted(
        (s for s in AGENT_REGISTRY.values() if isinstance(s, SpecialistAgentSpec)),
        key=lambda s: s.name,
    )


def find_specialist_for(
    *,
    system: str | None = None,
    category: str | None = None,
    subtype: str | None = None,
) -> SpecialistAgentSpec | None:
    """Find the best specialist for a (system, category, subtype) triple.

    Resolution order, most specific first:
      1. **System + subtype both match** — exact target (disambiguates shared
         subtypes like ``account-locked`` between ``access_mfa`` and
         ``sixth_sense``: the *system* picks the right specialist).
      2. **Subtype match only** — pick the specialist whose ``subtypes``
         includes it (deterministic by sorted name on ties).
      3. **System match only** — pick the specialist whose ``systems``
         includes it.
      4. **Category match** — broadest fallback.
      5. ``None`` — no specialist owns this; the supervisor falls back to
         general retrieval or escalates.

    Empty/None inputs are ignored. If multiple specialists match at the same
    level, the first by sorted name wins (deterministic).
    """
    specialists = list_specialists()
    sys_norm = system.replace("_", "-").lower() if system else None
    sub_norm = subtype.replace("_", "-").lower() if subtype else None

    # 1. System + subtype combined match wins outright.
    if sys_norm and sub_norm:
        for s in specialists:
            systems = {x.replace("_", "-").lower() for x in s.systems}
            subtypes = {x.replace("_", "-").lower() for x in s.subtypes}
            if sys_norm in systems and sub_norm in subtypes:
                return s

    # 2. Subtype-only match.
    if sub_norm:
        for s in specialists:
            normalized = {x.replace("_", "-").lower() for x in s.subtypes}
            if sub_norm in normalized:
                return s

    # 3. System-only match.
    if sys_norm:
        for s in specialists:
            normalized = {x.replace("_", "-").lower() for x in s.systems}
            if sys_norm in normalized:
                return s

    # 4. Category match.
    if category:
        for s in specialists:
            if category in s.categories:
                return s

    return None


def find_sub_agent_for(
    specialist: SpecialistAgentSpec, subtype: str | None
) -> SubAgentSpec | None:
    """Inside a specialist, find the sub-agent that owns ``subtype``, if any."""
    if not subtype:
        return None
    sub_norm = subtype.replace("_", "-").lower()
    for sub_agent in specialist.sub_agents:
        normalized = {x.replace("_", "-").lower() for x in sub_agent.subtypes}
        if sub_norm in normalized:
            return sub_agent
    return None


__all__ = [
    "AGENT_REGISTRY",
    "REGISTRY_VERSION",
    "AgentRole",
    "AgentSpec",
    "ConfidenceThresholds",
    "DEFAULT_THRESHOLDS",
    "SpecialistAgentSpec",
    "SubAgentSpec",
    "find_specialist_for",
    "find_sub_agent_for",
    "get_agent",
    "list_specialists",
]
