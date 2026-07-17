"""C2: the scheduled-report job registers only when enabled."""

import pytest

from app.services import scheduler as sched


@pytest.mark.asyncio
async def test_scheduled_report_job_registered_when_enabled(monkeypatch):
    created = []
    real_create_task = sched.asyncio.create_task

    def _spy(coro, name=None):
        created.append(name)
        return real_create_task(coro, name=name)

    monkeypatch.setattr(sched.asyncio, "create_task", _spy)
    async with sched.start_background_jobs(
        idle_sweeper_enabled=False,
        remote_sweeper_enabled=False,
        scheduled_reports_enabled=True,
        scheduled_report_interval_seconds=3600,
    ):
        pass
    assert any(n == "reporting.scheduled_report" for n in created)


@pytest.mark.asyncio
async def test_scheduled_report_job_absent_when_disabled(monkeypatch):
    created = []
    real_create_task = sched.asyncio.create_task
    monkeypatch.setattr(
        sched.asyncio,
        "create_task",
        lambda coro, name=None: (created.append(name), real_create_task(coro, name=name))[1],
    )
    async with sched.start_background_jobs(
        idle_sweeper_enabled=False,
        remote_sweeper_enabled=False,
        scheduled_reports_enabled=False,
    ):
        pass
    assert "reporting.scheduled_report" not in created
