"""Composition root for the background task runner (Phase 8).

Builds an :class:`AgentTaskRunner` with the in-memory store and the reference
handlers registered. The handler *dependencies* (candidate reviewer, diagnostics
fetcher) are the integration seam: the safe defaults here are no-ops that log
"not configured" so enabling ``FEATURE_BACKGROUND_AGENTS`` can never do harm
before the real data sources are wired. A deployment overrides them by passing
concrete callables (DB-backed candidate review, MCP-backed diagnostics).
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.agents.tasks.handlers import (
    CandidateReviewer,
    DiagnosticsFetcher,
    make_knowledge_improvement_handler,
    make_proactive_diagnostics_handler,
)
from app.services.agents.tasks.runner import AgentTaskRunner
from app.services.agents.tasks.store import AgentTaskStore, InMemoryAgentTaskStore

logger = get_logger(__name__)


async def _no_candidate_source(_top_n: int) -> list[dict[str, Any]]:
    logger.info("knowledge_improvement_no_source", note="candidate reviewer not configured")
    return []


async def _no_diagnostics_source(_payload: dict[str, Any]) -> dict[str, Any]:
    logger.info("proactive_diagnostics_no_source", note="diagnostics fetcher not configured")
    return {}


def build_default_task_runner(
    *,
    store: AgentTaskStore | None = None,
    candidate_reviewer: CandidateReviewer | None = None,
    diagnostics_fetcher: DiagnosticsFetcher | None = None,
) -> AgentTaskRunner:
    runner = AgentTaskRunner(
        store or InMemoryAgentTaskStore(),
        concurrency=settings.AGENT_BACKGROUND_CONCURRENCY,
    )
    runner.register(
        "knowledge_improvement_sweep",
        make_knowledge_improvement_handler(candidate_reviewer or _no_candidate_source),
    )
    runner.register(
        "proactive_diagnostics",
        make_proactive_diagnostics_handler(diagnostics_fetcher or _no_diagnostics_source),
    )
    return runner


# Process-wide singleton so the lifespan runner loop and the agent-ops API
# (enqueue + monitor) operate on the SAME store/runner instance.
_runner: AgentTaskRunner | None = None


def get_task_runner() -> AgentTaskRunner:
    global _runner
    if _runner is None:
        _runner = build_default_task_runner()
    return _runner


__all__ = ["build_default_task_runner", "get_task_runner"]
