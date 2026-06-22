"""Background scheduler — pure-asyncio recurring jobs.

Phase 1 has one job: the live-specialist-chat idle sweeper. Lazy in-poll
evaluation already covers sessions whose participants are still polling;
this job exists to clean up **abandoned** sessions where neither tab is
open anymore and the session would otherwise live as ``active`` until a
manual end.

Why asyncio instead of APScheduler / Celery
-------------------------------------------
* Zero new runtime dependencies.
* Lives inside the same event loop as the FastAPI app, so there's no IPC,
  no broker, and no separate worker process to deploy.
* Cancels cleanly on app shutdown via the lifespan.
* One-job-per-task means a failure in the sweeper can't take down other
  scheduled work (there isn't any other work yet, but the pattern is set
  up to add more — e.g. session-stale-cleanup, queue-age-alerts).

Future scheduled jobs slot in by adding another ``_run_loop(...)`` task
under :func:`start_background_jobs`. Each gets its own try/except so one
crash doesn't kill the others.

What this module does NOT do
----------------------------
* Cron-style "every Tuesday at 3am" scheduling — that's APScheduler
  territory. For now we only need fixed-interval sweeps.
* Distributed locking — fine in single-instance dev/test. When we scale
  to multiple workers, add a Redis-based lease (see
  ``docs/development/rollout-plan-multi-agent.md`` Phase 3).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

logger = get_logger(__name__)

# Defaults — tunable per job at start time.
_IDLE_SWEEPER_INTERVAL_SECONDS = 30


async def _sweep_idle_once() -> int:
    """Run one pass of the idle sweeper. Returns count ended.

    Opens a short-lived DB session per pass so failures don't tie up the
    main app's connection pool.
    """
    from app.core.database import async_session_factory
    from app.services.specialist_chat_service import SpecialistChatService

    async with async_session_factory() as db:
        try:
            service = SpecialistChatService(db)
            ended = await service.sweep_idle()
            if ended:
                await db.commit()
                logger.info("idle_sweeper_ended_sessions", count=ended)
            return ended
        except Exception:  # noqa: BLE001 — never let a bad pass kill the loop
            await db.rollback()
            logger.exception("idle_sweeper_pass_failed")
            return 0


async def _run_loop(
    name: str,
    job: Callable[[], Awaitable[object]],
    interval_seconds: int,
) -> None:
    """Long-running loop: sleep → run job → repeat. Survives job errors."""
    logger.info("scheduled_job_started", job=name, interval=interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Catch-all in case the job itself didn't — guarantees the
                # loop keeps running across one-off failures.
                logger.exception("scheduled_job_iteration_failed", job=name)
    except asyncio.CancelledError:
        logger.info("scheduled_job_cancelled", job=name)
        raise


@asynccontextmanager
async def start_background_jobs(
    *,
    idle_sweeper_enabled: bool = True,
    idle_sweeper_interval_seconds: int = _IDLE_SWEEPER_INTERVAL_SECONDS,
    background_agents_enabled: bool = False,
    background_agents_poll_seconds: int = 60,
) -> AsyncIterator[None]:
    """Async context manager — start jobs on enter, cancel on exit.

    Usage::

        async with start_background_jobs():
            yield  # app runs here

    Each job is a separate asyncio.Task. Cancellation is structured: we
    cancel them all, then ``gather`` with ``return_exceptions=True`` so
    even if one job's shutdown handler raises, the others still tear down.
    """
    tasks: list[asyncio.Task[None]] = []

    if idle_sweeper_enabled:
        tasks.append(
            asyncio.create_task(
                _run_loop(
                    "specialist_chat.idle_sweeper",
                    _sweep_idle_once,
                    idle_sweeper_interval_seconds,
                ),
                name="specialist_chat.idle_sweeper",
            )
        )

    if background_agents_enabled:
        # Phase 8 — autonomous agent task runner (nightly knowledge improvement,
        # proactive diagnostics). Its own poll loop; failures stay isolated.
        from app.services.agents.tasks.factory import get_task_runner

        runner = get_task_runner()
        tasks.append(
            asyncio.create_task(
                runner.run_forever(poll_seconds=background_agents_poll_seconds),
                name="agents.task_runner",
            )
        )

    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("background_jobs_stopped", count=len(tasks))


__all__ = ["start_background_jobs"]
