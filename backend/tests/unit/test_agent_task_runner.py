"""Unit tests for the background agent task runner (Phase 8).

In-memory store, no DB, no sleeping (we drive ``run_once`` directly). Covers:
enqueue + idempotency, successful execution, unknown task type, retry-then-fail,
bounded concurrency, and the reference handlers.
"""

from __future__ import annotations

import asyncio

from app.services.agents.tasks.handlers import (
    make_knowledge_improvement_handler,
    make_proactive_diagnostics_handler,
)
from app.services.agents.tasks.models import AgentTask, AgentTaskStatus
from app.services.agents.tasks.runner import AgentTaskRunner
from app.services.agents.tasks.store import InMemoryAgentTaskStore


def _runner(handlers=None, *, concurrency=2):
    store = InMemoryAgentTaskStore()
    return AgentTaskRunner(store, handlers or {}, concurrency=concurrency,
                           audit_sink=lambda e: None), store


class TestStore:
    async def test_enqueue_and_claim(self) -> None:
        store = InMemoryAgentTaskStore()
        await store.enqueue(AgentTask(task_type="x"))
        claimed = await store.claim_pending(10)
        assert len(claimed) == 1
        assert claimed[0].status is AgentTaskStatus.RUNNING
        assert claimed[0].attempts == 1
        # Already claimed → not handed out again.
        assert await store.claim_pending(10) == []

    async def test_idempotent_enqueue(self) -> None:
        store = InMemoryAgentTaskStore()
        a = await store.enqueue(AgentTask(task_type="x", idempotency_key="k1"))
        b = await store.enqueue(AgentTask(task_type="x", idempotency_key="k1"))
        assert a.id == b.id
        assert len(await store.list_all()) == 1


class TestRunOnce:
    async def test_runs_handler_and_completes(self) -> None:
        seen = []

        async def handler(task: AgentTask):
            seen.append(task.id)
            return {"ok": True}

        runner, store = _runner({"job": handler})
        task = await runner.enqueue(AgentTask(task_type="job"))
        summary = await runner.run_once()
        assert summary.completed == 1
        stored = await store.get(task.id)
        assert stored.status is AgentTaskStatus.COMPLETED
        assert stored.result == {"ok": True}
        assert seen == [task.id]

    async def test_unknown_task_type_fails_cleanly(self) -> None:
        runner, store = _runner({})
        task = await runner.enqueue(AgentTask(task_type="nope"))
        summary = await runner.run_once()
        assert summary.skipped_unknown == 1
        stored = await store.get(task.id)
        assert stored.status is AgentTaskStatus.FAILED
        assert "no handler" in (stored.error or "")

    async def test_retry_then_fail(self) -> None:
        async def boom(task: AgentTask):
            raise RuntimeError("nope")

        runner, store = _runner({"job": boom})
        task = await runner.enqueue(AgentTask(task_type="job", max_attempts=2))

        s1 = await runner.run_once()
        assert s1.retried == 1
        assert (await store.get(task.id)).status is AgentTaskStatus.PENDING

        s2 = await runner.run_once()
        assert s2.failed == 1
        stored = await store.get(task.id)
        assert stored.status is AgentTaskStatus.FAILED
        assert stored.attempts == 2

    async def test_empty_queue_is_noop(self) -> None:
        runner, _ = _runner({"job": lambda t: None})
        summary = await runner.run_once()
        assert summary.claimed == 0


class TestConcurrencyBound:
    async def test_never_exceeds_concurrency(self) -> None:
        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def slow(task: AgentTask):
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return {}

        runner, _ = _runner({"job": slow}, concurrency=2)
        for _ in range(6):
            await runner.enqueue(AgentTask(task_type="job"))
        # run_once claims up to `concurrency` per pass.
        await runner.run_once()
        assert peak <= 2


class TestReferenceHandlers:
    async def test_knowledge_improvement_handler(self) -> None:
        async def reviewer(top_n: int):
            return [{"id": "c1"}, {"id": "c2"}][:top_n]

        handler = make_knowledge_improvement_handler(reviewer)
        out = await handler(AgentTask(task_type="k", payload={"top_n": 1}))
        assert out["surfaced"] == 1
        assert out["candidate_ids"] == ["c1"]

    async def test_proactive_diagnostics_handler(self) -> None:
        async def fetch(payload: dict):
            return {"locked": True, "for": payload.get("upn")}

        handler = make_proactive_diagnostics_handler(fetch)
        out = await handler(AgentTask(task_type="d", payload={"upn": "a@b.com"}))
        assert out["diagnostics"]["locked"] is True
        assert out["diagnostics"]["for"] == "a@b.com"
