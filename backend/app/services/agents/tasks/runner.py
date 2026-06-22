"""AgentTaskRunner — executes background/autonomous agent work (Phase 8).

A small, dependency-light runner that mirrors the existing asyncio scheduler
(``app/services/scheduler.py``): it polls a task store, claims pending tasks,
and runs their registered handlers with **bounded concurrency**. Every run is
audited; failures retry up to the task's budget then terminate as ``failed``.

Design choices (consistent with the rest of the platform):
* **Handlers are declarative + registered**, like agents/tools — nothing runs
  that isn't registered for a ``task_type``.
* **Pure, testable core**: :meth:`run_once` drains one batch and returns a
  summary; the infinite loop (:meth:`run_forever`) just calls it on an interval,
  so behaviour is unit-tested without sleeping.
* **No new infra**: in-process asyncio, injectable store, injectable audit sink.
  A failed task can never take down the loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.services.agents.tasks.models import AgentTask, AgentTaskStatus

if TYPE_CHECKING:
    from app.services.agents.tasks.store import AgentTaskStore

logger = get_logger(__name__)

# A handler takes the task and returns a JSON-able result dict.
TaskHandler = Callable[[AgentTask], Awaitable[dict[str, Any]]]
AuditSink = Callable[[dict[str, Any]], None]


def _default_audit_sink(event: dict[str, Any]) -> None:
    logger.info("agent_task", **event)


@dataclass
class RunSummary:
    claimed: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    skipped_unknown: int = 0


class AgentTaskRunner:
    """Claims and executes background tasks with bounded concurrency."""

    def __init__(
        self,
        store: AgentTaskStore,
        handlers: dict[str, TaskHandler] | None = None,
        *,
        concurrency: int = 2,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._store = store
        self._handlers: dict[str, TaskHandler] = dict(handlers or {})
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._concurrency = max(1, concurrency)
        self._audit = audit_sink or _default_audit_sink

    def register(self, task_type: str, handler: TaskHandler) -> None:
        self._handlers[task_type] = handler

    async def enqueue(self, task: AgentTask) -> AgentTask:
        return await self._store.enqueue(task)

    async def run_once(self) -> RunSummary:
        """Claim up to ``concurrency`` pending tasks and run them concurrently."""
        summary = RunSummary()
        claimed = await self._store.claim_pending(self._concurrency)
        summary.claimed = len(claimed)
        if not claimed:
            return summary

        results = await asyncio.gather(
            *(self._execute(task) for task in claimed), return_exceptions=False
        )
        for outcome in results:
            if outcome == "completed":
                summary.completed += 1
            elif outcome == "retried":
                summary.retried += 1
            elif outcome == "failed":
                summary.failed += 1
            elif outcome == "skipped_unknown":
                summary.skipped_unknown += 1
        return summary

    async def _execute(self, task: AgentTask) -> str:
        handler = self._handlers.get(task.task_type)
        if handler is None:
            task.status = AgentTaskStatus.FAILED
            task.error = f"no handler registered for task_type {task.task_type!r}"
            task.touch()
            await self._store.save(task)
            self._audit({"task_id": task.id, "task_type": task.task_type,
                         "status": "skipped_unknown"})
            return "skipped_unknown"

        async with self._sem:
            try:
                result = await handler(task)
                task.status = AgentTaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.touch()
                await self._store.save(task)
                self._audit({"task_id": task.id, "task_type": task.task_type,
                             "status": "completed", "attempts": task.attempts})
                return "completed"
            except Exception as exc:  # noqa: BLE001 — one task can't crash the runner
                task.error = str(exc)
                if task.attempts >= task.max_attempts:
                    task.status = AgentTaskStatus.FAILED
                    outcome = "failed"
                else:
                    task.status = AgentTaskStatus.PENDING  # re-queue for retry
                    outcome = "retried"
                task.touch()
                await self._store.save(task)
                self._audit({"task_id": task.id, "task_type": task.task_type,
                             "status": outcome, "attempts": task.attempts, "error": str(exc)})
                logger.warning("agent_task_failed", task_id=task.id,
                               task_type=task.task_type, attempts=task.attempts, error=str(exc))
                return outcome

    async def run_forever(self, *, poll_seconds: int) -> None:
        """Infinite poll loop. Survives individual pass failures."""
        logger.info("agent_task_runner_started", concurrency=self._concurrency,
                    poll_seconds=poll_seconds, handlers=sorted(self._handlers))
        try:
            while True:
                await asyncio.sleep(poll_seconds)
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("agent_task_runner_pass_failed")
        except asyncio.CancelledError:
            logger.info("agent_task_runner_cancelled")
            raise


__all__ = ["AgentTaskRunner", "RunSummary", "TaskHandler"]
