"""Background / autonomous agent task layer (Phase 8).

Public surface:

* :mod:`.models` — ``AgentTask`` + ``AgentTaskStatus``.
* :mod:`.store` — ``AgentTaskStore`` protocol + ``InMemoryAgentTaskStore``.
* :mod:`.runner` — ``AgentTaskRunner`` (bounded concurrency, retry, audit).
* :mod:`.handlers` — reference background-agent handlers.

See ``docs/architecture/agent-write-actions-and-tasks.md`` and
``plans/agentic-ops-platform-evolution.md`` (Phase 8).
"""

from __future__ import annotations

from app.services.agents.tasks.models import AgentTask, AgentTaskStatus
from app.services.agents.tasks.runner import AgentTaskRunner, RunSummary
from app.services.agents.tasks.store import AgentTaskStore, InMemoryAgentTaskStore

__all__ = [
    "AgentTask",
    "AgentTaskRunner",
    "AgentTaskStatus",
    "AgentTaskStore",
    "InMemoryAgentTaskStore",
    "RunSummary",
]
