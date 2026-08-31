"""Repository for the agent action ledger — all DB access for ledger entries.

Append-only by design: create() is the only write path. No update() method
exists so rows are immutable once written, matching the ledger contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.agent_action_ledger import AgentActionLedger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class AgentActionLedgerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        session_id: str,
        triggered_by: str,
        action_type: str,
        specialist_name: str,
        sub_agent_name: str | None = None,
        inputs_snapshot: dict[str, Any] | None = None,
        approval_status: str = "auto",
        ticket_id: uuid.UUID | None = None,
    ) -> AgentActionLedger:
        entry = AgentActionLedger(
            session_id=session_id,
            triggered_by=triggered_by,
            action_type=action_type,
            specialist_name=specialist_name,
            sub_agent_name=sub_agent_name,
            inputs_snapshot=inputs_snapshot or {},
            approval_status=approval_status,
            ticket_id=ticket_id,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def complete(
        self,
        entry: AgentActionLedger,
        *,
        result_snapshot: dict[str, Any] | None = None,
        confidence: float | None = None,
        escalation_signal: str | None = None,
    ) -> AgentActionLedger:
        """Record the result of a dispatch. Called after the specialist returns."""
        entry.result_snapshot = result_snapshot
        entry.confidence = confidence
        entry.escalation_signal = escalation_signal
        entry.completed_at = datetime.now(UTC)
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def get_by_session(self, session_id: str) -> list[AgentActionLedger]:
        result = await self._db.execute(
            select(AgentActionLedger)
            .where(AgentActionLedger.session_id == session_id)
            .order_by(AgentActionLedger.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_ticket(self, ticket_id: uuid.UUID) -> list[AgentActionLedger]:
        result = await self._db.execute(
            select(AgentActionLedger)
            .where(AgentActionLedger.ticket_id == ticket_id)
            .order_by(AgentActionLedger.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 50) -> list[AgentActionLedger]:
        result = await self._db.execute(
            select(AgentActionLedger).order_by(AgentActionLedger.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


__all__ = ["AgentActionLedgerRepository"]
