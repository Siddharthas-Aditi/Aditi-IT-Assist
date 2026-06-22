"""Reference background-agent handlers (Phase 8).

Two autonomous agents that run off the request path via the
:class:`~app.services.agents.tasks.runner.AgentTaskRunner`:

* ``knowledge_improvement_sweep`` — the long-deferred nightly Knowledge
  Improvement Agent: review accrued ``KnowledgeCandidate`` signals and surface
  the strongest for SME review. **Never** auto-publishes to the KB (preserves
  the "no silent self-modification" anti-goal).
* ``proactive_diagnostics`` — pre-fetch read-only MCP diagnostics for an
  at-risk user/device and attach them to a handoff so the human specialist
  starts with context.

Handlers are deliberately thin and take injected callables, so they're unit
-testable without a DB or live MCP server. The real wiring (DB session,
candidate service, MCP runtime) is supplied by the composition root when the
runner is constructed in the app lifespan.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.agents.tasks.models import AgentTask

logger = get_logger(__name__)

# Injected dependency signatures (kept abstract for testability).
CandidateReviewer = Callable[[int], Awaitable[list[dict[str, Any]]]]
DiagnosticsFetcher = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def make_knowledge_improvement_handler(reviewer: CandidateReviewer):
    """Build the nightly knowledge-improvement sweep handler.

    ``reviewer(top_n)`` returns the strongest candidates to surface for SME
    review (review-gated — promotion stays a human action).
    """

    async def handler(task: AgentTask) -> dict[str, Any]:
        top_n = int(task.payload.get("top_n", 10))
        candidates = await reviewer(top_n)
        logger.info("knowledge_improvement_sweep", surfaced=len(candidates))
        return {"surfaced": len(candidates), "candidate_ids": [c.get("id") for c in candidates]}

    return handler


def make_proactive_diagnostics_handler(fetch: DiagnosticsFetcher):
    """Build the proactive-diagnostics handler.

    ``fetch(payload)`` performs read-only MCP lookups (through the governed
    runtime) and returns a structured snapshot to attach to a handoff.
    """

    async def handler(task: AgentTask) -> dict[str, Any]:
        snapshot = await fetch(task.payload)
        return {"diagnostics": snapshot}

    return handler


__all__ = [
    "make_knowledge_improvement_handler",
    "make_proactive_diagnostics_handler",
]
