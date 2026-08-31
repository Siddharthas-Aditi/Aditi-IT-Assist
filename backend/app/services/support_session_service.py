"""Support session persistence — bridges ephemeral chat state to durable DB rows.

Chat workflow state stays in the SessionStore (Redis/memory) for low-latency
multi-turn continuity. This service mirrors each successful turn into
``support_sessions`` + ``messages`` so feedback, analytics, session history APIs,
and ticket FK linkage work against real data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from app.models.support import Message, SupportSession
from app.repositories.support_session_repository import SupportSessionRepository
from app.schemas.chat import SessionDetail, SessionSummary

if TYPE_CHECKING:
    from app.services.agents.session_store import ChatSession

logger = structlog.get_logger()


def _parse_session_id(session_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return None


def _derive_status(state: dict[str, Any], envelope: ChatSession | None) -> str:
    if state.get("issue_resolved"):
        return "resolved"
    if envelope and envelope.waiting_since:
        return "live_support"
    if envelope and envelope.ticket:
        return "escalated"
    if state.get("needs_clarification"):
        return "awaiting_user"
    return "active"


def _derive_session_type(state: dict[str, Any], envelope: ChatSession | None) -> str:
    if envelope and envelope.waiting_since:
        return "live_support"
    if envelope and envelope.ticket:
        return "hybrid"
    return "ai_chat"


def _knowledge_article_ids(state: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for citation in state.get("knowledge_citations") or []:
        article_id = citation.get("article_id")
        if article_id:
            ids.append(str(article_id))
    return ids


def _recovery_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return the DB-safe subset required to resume diagnostic progression.

    LangGraph messages are persisted in the normalized ``messages`` table;
    keeping them out of JSONB avoids serializing LangChain objects. The
    diagnostic context contains the suggested/failed step history and is the
    authoritative durable state for restart recovery.
    """
    keys = (
        "session_id",
        "user_id",
        "user_name",
        "user_email",
        "issue_category",
        "issue_subcategory",
        "issue_subtype",
        "severity",
        "urgency",
        "impact",
        "turn_count",
        "diagnostic_context",
        "conversation_phase",
        "issue_resolved",
        "resolution_confirmed",
    )
    return {key: state.get(key) for key in keys if key in state}


class SupportSessionService:
    """Persist and query durable support session records."""

    def __init__(self, db) -> None:  # noqa: ANN001 — AsyncSession
        self.db = db
        self.repo = SupportSessionRepository(db)

    async def sync_turn(
        self,
        session_id: str,
        user_id: str,
        *,
        user_message: str,
        assistant_message: str,
        assistant_message_id: str | None,
        state: dict[str, Any],
        envelope: ChatSession | None,
    ) -> None:
        """Upsert the session row and append this turn's user/assistant messages."""
        parsed_id = _parse_session_id(session_id)
        if parsed_id is None:
            logger.warning("support_session_skip_invalid_id", session_id=session_id)
            return

        uid = uuid.UUID(user_id)
        now = datetime.now(UTC)
        status = _derive_status(state, envelope)
        session_type = _derive_session_type(state, envelope)
        confidence = state.get("resolution_confidence") or state.get("knowledge_confidence")
        article_ids = _knowledge_article_ids(state)
        metadata: dict[str, Any] = {
            "workflow_recovery": _recovery_state(state),
            "session_ticket": envelope.ticket if envelope else None,
            "waiting_since": envelope.waiting_since.isoformat()
            if envelope and envelope.waiting_since
            else None,
        }
        if article_ids:
            metadata["knowledge_article_ids"] = article_ids

        record = await self.repo.get_by_id(parsed_id)
        if record is None:
            record = SupportSession(
                id=parsed_id,
                user_id=uid,
                status=status,
                session_type=session_type,
                issue_category=state.get("issue_category"),
                issue_subcategory=state.get("issue_subcategory"),
                severity=state.get("severity"),
                urgency=state.get("urgency"),
                confidence_score=float(confidence) if confidence is not None else None,
                metadata_json=metadata,
                created_at=now,
            )
            if status == "resolved":
                record.resolved_at = now
            await self.repo.create(record)
        else:
            if str(record.user_id) != user_id:
                logger.warning(
                    "support_session_ownership_mismatch",
                    session_id=session_id,
                    owner=str(record.user_id),
                    requester=user_id,
                )
                return
            record.status = status
            record.session_type = session_type
            record.issue_category = state.get("issue_category") or record.issue_category
            record.issue_subcategory = state.get("issue_subcategory") or record.issue_subcategory
            record.severity = state.get("severity") or record.severity
            record.urgency = state.get("urgency") or record.urgency
            if confidence is not None:
                record.confidence_score = float(confidence)
            if metadata:
                merged = dict(record.metadata_json or {})
                merged.update(metadata)
                record.metadata_json = merged
            if status == "resolved" and record.resolved_at is None:
                record.resolved_at = now

        user_msg = Message(
            id=uuid.uuid4(),
            session_id=parsed_id,
            sender_id=uid,
            role="user",
            content=user_message,
            message_type="text",
        )
        assistant_msg = Message(
            id=_parse_session_id(assistant_message_id or "") or uuid.uuid4(),
            session_id=parsed_id,
            sender_id=None,
            role="assistant",
            content=assistant_message,
            message_type="resolution" if status == "resolved" else "text",
        )
        await self.repo.add_message(user_msg)
        await self.repo.add_message(assistant_msg)

    async def restore_chat_session(self, session_id: str, user_id: str) -> ChatSession | None:
        """Rebuild a chat envelope from the durable database after cache loss.

        This is the restart/pod-reschedule path. Ownership is checked against
        the database before any messages or diagnostic state are returned.
        """
        parsed_id = _parse_session_id(session_id)
        if parsed_id is None:
            return None
        row = await self.repo.get_with_messages(parsed_id)
        if row is None or str(row.user_id) != user_id:
            return None

        metadata = row.metadata_json or {}
        stored = metadata.get("workflow_recovery") or {}
        state = dict(stored) if isinstance(stored, dict) else {}
        state["session_id"] = session_id
        state["user_id"] = user_id
        state["messages"] = [
            HumanMessage(content=message.content)
            if message.role == "user"
            else AIMessage(content=message.content)
            for message in sorted(row.messages, key=lambda item: item.created_at)
            if message.role in {"user", "assistant"}
        ]

        waiting_raw = metadata.get("waiting_since")
        waiting_since = (
            datetime.fromisoformat(waiting_raw) if isinstance(waiting_raw, str) else None
        )
        from app.services.agents.session_store import ChatSession

        return ChatSession(
            user_id=user_id,
            state=state,
            ticket=(
                metadata.get("session_ticket")
                if isinstance(metadata.get("session_ticket"), dict)
                else None
            ),
            waiting_since=waiting_since,
        )

    async def sync_envelope(
        self,
        session_id: str,
        user_id: str,
        *,
        state: dict[str, Any],
        envelope: ChatSession | None,
    ) -> None:
        """Update session status/metadata without appending messages (handoff paths)."""
        parsed_id = _parse_session_id(session_id)
        if parsed_id is None:
            return

        uid = uuid.UUID(user_id)
        now = datetime.now(UTC)
        status = _derive_status(state, envelope)
        session_type = _derive_session_type(state, envelope)

        record = await self.repo.get_by_id(parsed_id)
        if record is None:
            record = SupportSession(
                id=parsed_id,
                user_id=uid,
                status=status,
                session_type=session_type,
                issue_category=state.get("issue_category"),
                issue_subcategory=state.get("issue_subcategory"),
                created_at=now,
            )
            await self.repo.create(record)
            return

        if str(record.user_id) != user_id:
            return

        record.status = status
        record.session_type = session_type
        if state.get("issue_category"):
            record.issue_category = state.get("issue_category")

    async def list_sessions(self, user_id: str, *, limit: int = 50) -> list[SessionSummary]:
        uid = uuid.UUID(user_id)
        rows = await self.repo.list_for_user(uid, limit=limit)
        return [
            SessionSummary(
                session_id=str(row.id),
                status=row.status,
                issue_category=row.issue_category,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ]

    async def get_session(self, session_id: str, user_id: str) -> SessionDetail | None:
        parsed_id = _parse_session_id(session_id)
        if parsed_id is None:
            return None
        row = await self.repo.get_with_messages(parsed_id)
        if row is None or str(row.user_id) != user_id:
            return None
        messages = sorted(row.messages, key=lambda m: m.created_at)
        return SessionDetail(
            session_id=str(row.id),
            status=row.status,
            issue_category=row.issue_category,
            confidence_score=row.confidence_score or 0.0,
            created_at=row.created_at.isoformat(),
            messages=[
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "message_type": msg.message_type,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ],
        )


def get_support_session_service(db) -> SupportSessionService:  # noqa: ANN001
    return SupportSessionService(db)
