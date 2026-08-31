"""Action ledger service — records every agentic dispatch to the durable ledger.

The service wraps the repository with a simple interface that the dispatch node
calls. It handles the two-phase write: an entry is created before the
specialist runs (so a crash during execution is still visible as an incomplete
row) and completed once the specialist returns.

The service is intentionally thin. It does not own approval logic (that lives
in ``AgentToolRuntime``) or routing logic (that lives in the graph). It is a
pure persistence sink for the dispatch node.

Durability vs. performance
---------------------------
The dispatch node holds a DB session that it uses for the ledger. If the
specialist raises an exception, the outer transaction is rolled back and the
incomplete entry is NOT committed — this is acceptable because the crash itself
will surface in the audit trail via structlog. The trade-off is simplicity over
partial-write guarantees; a future enhancement could use a separate session for
the ledger to achieve true durability-on-crash.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.repositories.agent_action_ledger_repository import AgentActionLedgerRepository

logger = get_logger(__name__)


class ActionLedgerService:
    """Persist agentic dispatch entries to the agent_action_ledger table."""

    def __init__(self, repo: AgentActionLedgerRepository) -> None:
        self._repo = repo

    async def begin_dispatch(
        self,
        *,
        session_id: str,
        triggered_by: str,
        specialist_name: str,
        sub_agent_name: str | None,
        inputs_snapshot: dict[str, Any],
        action_type: str = "specialist_dispatch",
        ticket_id: uuid.UUID | None = None,
    ) -> Any:
        """Open a ledger row for a specialist dispatch (pre-execution)."""
        entry = await self._repo.create(
            session_id=session_id,
            triggered_by=triggered_by,
            action_type=action_type,
            specialist_name=specialist_name,
            sub_agent_name=sub_agent_name,
            inputs_snapshot=inputs_snapshot,
            approval_status="auto",
            ticket_id=ticket_id,
        )
        logger.info(
            "agent_dispatch_started",
            ledger_id=str(entry.id),
            session_id=session_id,
            specialist=specialist_name,
            sub_agent=sub_agent_name,
        )
        return entry

    async def complete_dispatch(
        self,
        entry: Any,
        *,
        result_snapshot: dict[str, Any] | None,
        confidence: float | None,
        escalation_signal: str | None,
    ) -> Any:
        """Record the result of a specialist dispatch (post-execution)."""
        completed = await self._repo.complete(
            entry,
            result_snapshot=result_snapshot,
            confidence=confidence,
            escalation_signal=escalation_signal,
        )
        logger.info(
            "agent_dispatch_completed",
            ledger_id=str(completed.id),
            confidence=confidence,
            escalation_signal=escalation_signal,
        )
        return completed


__all__ = ["ActionLedgerService"]
