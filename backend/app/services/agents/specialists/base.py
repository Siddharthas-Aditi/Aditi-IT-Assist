"""Specialist agent base — the contract every domain specialist implements.

The :class:`SpecialistAgent` protocol is intentionally narrow: a specialist
takes a :class:`SpecialistInput` (immutable inputs assembled by the
supervisor) and returns a :class:`SpecialistOutput` (typed, structured
result). Side effects (LLM calls, DB writes) happen inside the
implementation, but the public contract is pure values — this makes
specialists trivially mockable in tests and replayable in golden
conversations.

What a specialist owns
----------------------
* Choosing which grounded steps to present this turn (it reads
  ``DiagnosticContext.suggested_steps`` and ``failed_steps`` to advance).
* Rendering the user-facing message (concise, natural, grounded).
* Detecting when its own scope is exhausted and signaling escalation
  (``escalation_signal`` on the output).
* Producing :class:`KnowledgeImprovementHint` candidates from each turn so
  the Knowledge Improvement Agent can review them later — never writing to
  production KB directly.

What a specialist does NOT own
------------------------------
* Routing — the supervisor decides whether to call this specialist.
* Retrieval — the retrieval agent is upstream; a specialist receives the
  grounded articles.
* Ticket creation — the escalation + chat service own that.
* Web fallback — a separate agent, governed by the registry's
  ``web_fallback_allowed`` flag.

This separation keeps the cognitive load per module bounded: a new
specialist is a single file with one well-defined contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.services.agents.diagnostic_state import DiagnosticContext
    from app.services.agents.registry import SpecialistAgentSpec, SubAgentSpec
    from app.services.agents.tools.base import ToolContext


@dataclass(frozen=True)
class SpecialistInput:
    """Everything a specialist needs to produce its turn.

    The supervisor assembles this from workflow state and passes it to the
    specialist. Frozen so a specialist cannot accidentally mutate shared
    state — outputs go on :class:`SpecialistOutput`.
    """

    user_message: str
    diag_ctx: DiagnosticContext
    knowledge_results: tuple[dict, ...]
    knowledge_confidence: float
    knowledge_citations: tuple[dict, ...]
    sub_agent: SubAgentSpec | None = None  # set when supervisor picked a sub-agent
    session_id: str = ""
    turn_count: int = 0
    # Caller identity + authorization for tool calls (Phase 5). When ``None``,
    # the specialist's tool-use path stays off — tools never run without an
    # authorized context, even if FEATURE_AGENT_TOOLS is enabled.
    tool_context: ToolContext | None = None


@dataclass(frozen=True)
class ResolutionStep:
    """One troubleshooting step the specialist wants to present."""

    step_number: int
    instruction: str
    details: str | None = None
    citation_title: str | None = None  # KB article this step came from


@dataclass(frozen=True)
class KnowledgeImprovementHint:
    """A draft KB-improvement signal emitted by the specialist for review.

    The Knowledge Improvement Agent ingests these into the candidates table.
    A specialist must NEVER write to production KB — only hint at gaps.
    """

    reason: str                        # short why (e.g. "subtype lacks article")
    issue_subtype: str | None = None
    suggested_title: str | None = None
    notes: str = ""
    confidence: float = 0.5


@dataclass(frozen=True)
class SpecialistOutput:
    """The specialist's reply to the supervisor."""

    message: str                       # natural-language reply for the user
    steps: tuple[ResolutionStep, ...] = field(default_factory=tuple)
    confidence: float = 0.0            # specialist's own confidence in this turn
    # If set, the specialist is telling the supervisor "I'm done — escalate".
    escalation_signal: str | None = None
    # Tried-step memory the workflow records into DiagnosticContext.
    presented_steps: tuple[str, ...] = field(default_factory=tuple)
    # Drafts for the Knowledge Improvement loop.
    knowledge_hints: tuple[KnowledgeImprovementHint, ...] = field(default_factory=tuple)
    # Free-form audit trail entry the workflow appends.
    audit: dict = field(default_factory=dict)


@runtime_checkable
class SpecialistAgent(Protocol):
    """The contract every specialist implements.

    Two methods, both pure-ish (LLM calls are allowed but must be bounded
    by the AgentSpec's ``timeout_seconds`` and ``thresholds``).
    """

    spec: SpecialistAgentSpec

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        """Produce the specialist's turn."""
        ...

    def can_handle(self, inp: SpecialistInput) -> bool:
        """Cheap pre-flight check; defaults to system/category match.

        The supervisor's :func:`find_specialist_for` already consults the
        registry, so this is mostly a defense-in-depth hook for specialists
        with extra preconditions (e.g. require ``platform_os`` to be set).
        """
        ...


__all__ = [
    "KnowledgeImprovementHint",
    "ResolutionStep",
    "SpecialistAgent",
    "SpecialistInput",
    "SpecialistOutput",
]
