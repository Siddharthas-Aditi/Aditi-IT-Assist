"""Close abandoned pre-fix live-support tickets so the queue reflects reality.

A ticket qualifies when: source='chat', title starts with 'Live support request',
status still in the queue window, no active specialist_chat_session, and older than
the fallback window. Dry-run by default; pass --apply to mutate.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.specialist_chat import SpecialistChatSession
from app.models.ticket import Ticket


async def _run(apply: bool) -> dict:
    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.LIVE_HANDOFF_FALLBACK_SECONDS
    )
    async with async_session_factory() as db:
        active_sub = select(SpecialistChatSession.ticket_id).where(
            SpecialistChatSession.status.in_(("active", "idle_warning"))
        )
        stmt = select(Ticket).where(
            and_(
                Ticket.source == "chat",
                Ticket.title.like("Live support request%"),
                Ticket.status.in_(("new", "triaged", "escalated")),
                Ticket.created_at < cutoff,
                Ticket.id.not_in(active_sub),
            )
        )
        tickets = (await db.execute(stmt)).scalars().all()
        print(f"Found {len(tickets)} stale handoff ticket(s).")
        for t in tickets:
            print(
                f"  {t.ticket_number}  status={t.status}  created={t.created_at}"
            )
            if apply:
                t.status = "waiting_for_user"  # out of queue; visible for async
        if apply:
            await db.commit()
            print(f"Applied: moved {len(tickets)} ticket(s) out of the live queue.")
        else:
            print("Dry run — pass --apply to mutate.")
    return {"count": len(tickets), "applied": apply}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
