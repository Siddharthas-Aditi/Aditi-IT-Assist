"""Typed model for background/autonomous agent work (Phase 8).

An :class:`AgentTask` is a durable, observable unit of work executed off the
request path by the :class:`~app.services.agents.tasks.runner.AgentTaskRunner`.
The model is storage-agnostic (a dataclass, not an ORM row) so the in-memory
store used in dev/tests and a future DB-backed store share one contract.

Every background action a task performs still flows through the same
``AgentToolRuntime`` (allow-list / RBAC / human-approval / audit) — the task
layer schedules *when* work runs, never what an agent is allowed to do.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AgentTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"  # exhausted retries
    CANCELLED = "cancelled"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class AgentTask:
    """One scheduled/queued background task."""

    task_type: str  # maps to a registered handler
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    # Optional idempotency key so the same logical job isn't enqueued twice.
    idempotency_key: str | None = None

    def touch(self) -> None:
        self.updated_at = _now()


__all__ = ["AgentTask", "AgentTaskStatus"]
