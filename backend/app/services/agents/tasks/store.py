"""Storage abstraction for background agent tasks (Phase 8).

The runner depends on the :class:`AgentTaskStore` protocol, not a concrete
backend, so the in-memory store (dev/tests) and a future DB-backed store are
interchangeable. ``claim_pending`` is the concurrency-safe hand-off point: an
implementation must atomically flip a task to ``running`` so two workers never
pick up the same task (the in-memory version is single-process and uses a lock;
a DB version would use ``SELECT ... FOR UPDATE SKIP LOCKED``).
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from app.services.agents.tasks.models import AgentTask, AgentTaskStatus


@runtime_checkable
class AgentTaskStore(Protocol):
    async def enqueue(self, task: AgentTask) -> AgentTask: ...
    async def claim_pending(self, limit: int) -> list[AgentTask]: ...
    async def save(self, task: AgentTask) -> None: ...
    async def get(self, task_id: str) -> AgentTask | None: ...
    async def list_all(self) -> list[AgentTask]: ...


class InMemoryAgentTaskStore:
    """Single-process, lock-guarded store. Suitable for dev/tests and a single
    app instance. Multi-instance deployments should use a DB-backed store with
    row-level claim locking (documented in the Phase 8 design doc)."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, task: AgentTask) -> AgentTask:
        async with self._lock:
            # Idempotent enqueue: if a non-terminal task with the same key
            # exists, return it rather than queueing a duplicate.
            if task.idempotency_key:
                for existing in self._tasks.values():
                    if existing.idempotency_key == task.idempotency_key and existing.status in (
                        AgentTaskStatus.PENDING,
                        AgentTaskStatus.RUNNING,
                    ):
                        return existing
            self._tasks[task.id] = task
            return task

    async def claim_pending(self, limit: int) -> list[AgentTask]:
        async with self._lock:
            claimed: list[AgentTask] = []
            for task in self._tasks.values():
                if task.status is AgentTaskStatus.PENDING:
                    task.status = AgentTaskStatus.RUNNING
                    task.attempts += 1
                    task.touch()
                    claimed.append(task)
                    if len(claimed) >= limit:
                        break
            return claimed

    async def save(self, task: AgentTask) -> None:
        async with self._lock:
            self._tasks[task.id] = task

    async def get(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    async def list_all(self) -> list[AgentTask]:
        return list(self._tasks.values())


__all__ = ["AgentTaskStore", "InMemoryAgentTaskStore"]
