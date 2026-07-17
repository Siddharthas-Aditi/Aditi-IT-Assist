"""Chat session store — the persistence seam for multi-turn chat state.

Replaces three process-local module dicts (`_sessions`, `_session_tickets`,
`_waiting_since`) that were the biggest reliability/security liability in the
chat service:

* **IDOR** — nothing bound a session to its owner, so any caller who knew a
  session id could resume/read/act on someone else's conversation. The
  envelope now carries ``user_id`` and the service enforces ownership.
* **Unbounded growth / multi-worker** — the dicts never evicted and were
  per-process, so a second worker saw an empty session (context loss) and long
  uptime leaked memory. The in-memory store is now a bounded LRU with TTL, and
  a Redis backend shares state across workers and survives restarts.
* **Non-durable idempotency** — the created-ticket reference lived only in
  memory, so a restart or a second worker could mint a duplicate ticket. It now
  lives in the same envelope (Redis-durable when configured).

Two backends behind one async protocol:

* :class:`InMemorySessionStore` — default; bounded + TTL; single process.
* :class:`RedisSessionStore` — durable + shared; JSON envelope with per-key
  TTL; degrades to an internal in-memory map if Redis is unreachable so chat
  never hard-fails on a cache outage.

The workflow state holds LangChain ``BaseMessage`` objects, which are not JSON
by default — the Redis backend (de)serializes them via
``messages_to_dict``/``messages_from_dict``; every other state value is already
JSON-safe (primitives, lists, and the serialized ``diagnostic_context`` dict).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from langchain_core.messages import messages_from_dict, messages_to_dict

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatSession:
    """One conversation's persisted envelope.

    ``state`` is the LangGraph workflow state dict (with live ``BaseMessage``
    objects while in memory). ``ticket`` is the idempotency record for the
    escalation ticket (dict form of ``TicketRef``). ``waiting_since`` tracks
    when the employee started waiting for a live specialist.
    """

    user_id: str | None
    state: dict[str, Any]
    ticket: dict[str, Any] | None = None
    waiting_since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionStore(Protocol):
    """Async persistence protocol for chat sessions."""

    async def load(self, session_id: str) -> ChatSession | None: ...
    async def save(self, session_id: str, session: ChatSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...


# ── Serialization helpers (shared by the Redis backend + tests) ───────────────


def _dump_session(session: ChatSession) -> str:
    state = dict(session.state)
    state["messages"] = messages_to_dict(state.get("messages") or [])
    envelope = {
        "user_id": session.user_id,
        "state": state,
        "ticket": session.ticket,
        "waiting_since": session.waiting_since.isoformat() if session.waiting_since else None,
        "updated_at": session.updated_at.isoformat(),
    }
    return json.dumps(envelope)


def _load_session(raw: str) -> ChatSession:
    envelope = json.loads(raw)
    state = dict(envelope.get("state") or {})
    state["messages"] = messages_from_dict(state.get("messages") or [])
    waiting = envelope.get("waiting_since")
    updated = envelope.get("updated_at")
    return ChatSession(
        user_id=envelope.get("user_id"),
        state=state,
        ticket=envelope.get("ticket"),
        waiting_since=datetime.fromisoformat(waiting) if waiting else None,
        updated_at=datetime.fromisoformat(updated) if updated else datetime.now(UTC),
    )


# ── In-memory backend ─────────────────────────────────────────────────────────


class InMemorySessionStore:
    """Bounded, TTL'd, single-process store.

    LRU eviction caps memory under session churn (the old dicts grew forever),
    and a TTL drops abandoned conversations. Suitable for dev/tests and any
    single-worker deployment.
    """

    def __init__(self, *, max_sessions: int = 5000, ttl_seconds: int = 86_400) -> None:
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, ChatSession] = OrderedDict()

    def _expired(self, session: ChatSession, now: datetime) -> bool:
        return (now - session.updated_at).total_seconds() > self._ttl

    async def load(self, session_id: str) -> ChatSession | None:
        session = self._data.get(session_id)
        if session is None:
            return None
        if self._expired(session, datetime.now(UTC)):
            self._data.pop(session_id, None)
            return None
        self._data.move_to_end(session_id)  # LRU touch
        return session

    async def save(self, session_id: str, session: ChatSession) -> None:
        session.updated_at = datetime.now(UTC)
        self._data[session_id] = session
        self._data.move_to_end(session_id)
        while len(self._data) > self._max:
            evicted, _ = self._data.popitem(last=False)
            logger.info("chat_session_evicted", session_id=evicted, reason="lru_cap")

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


# ── Redis backend ──────────────────────────────────────────────────────────────


class RedisSessionStore:
    """Durable, cross-worker store backed by Redis with a JSON envelope.

    Degrades to an internal in-memory store on any Redis error so a cache
    outage never takes down chat — the same fail-soft stance as the rate
    limiter and token denylist.
    """

    def __init__(self, redis_client: Any | None = None, *, ttl_seconds: int = 86_400) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._fallback = InMemorySessionStore(ttl_seconds=ttl_seconds)
        self._degraded = False

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chatsession:{session_id}"

    def _client(self) -> Any | None:
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("chat_session_redis_init_failed", error=str(exc))
                return None
        return self._redis

    async def load(self, session_id: str) -> ChatSession | None:
        client = self._client()
        if client is None:
            return await self._fallback.load(session_id)
        try:
            raw = await client.get(self._key(session_id))
            return _load_session(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            self._on_error("load", exc)
            return await self._fallback.load(session_id)

    async def save(self, session_id: str, session: ChatSession) -> None:
        session.updated_at = datetime.now(UTC)
        client = self._client()
        if client is None:
            await self._fallback.save(session_id, session)
            return
        try:
            await client.set(self._key(session_id), _dump_session(session), ex=self._ttl)
        except Exception as exc:  # noqa: BLE001
            self._on_error("save", exc)
            await self._fallback.save(session_id, session)

    async def delete(self, session_id: str) -> None:
        client = self._client()
        if client is None:
            await self._fallback.delete(session_id)
            return
        try:
            await client.delete(self._key(session_id))
        except Exception as exc:  # noqa: BLE001
            self._on_error("delete", exc)
            await self._fallback.delete(session_id)

    def _on_error(self, op: str, exc: Exception) -> None:
        if not self._degraded:
            self._degraded = True
            logger.warning("chat_session_redis_unavailable", op=op, error=str(exc))


# ── Factory / singleton ─────────────────────────────────────────────────────────

_store: SessionStore | None = None


def build_session_store() -> SessionStore:
    """Construct the store from config (``CHAT_SESSION_BACKEND``)."""
    backend = getattr(settings, "CHAT_SESSION_BACKEND", "memory").lower()
    ttl = getattr(settings, "CHAT_SESSION_TTL_SECONDS", 86_400)
    if backend == "redis":
        return RedisSessionStore(ttl_seconds=ttl)
    return InMemorySessionStore(ttl_seconds=ttl)


def get_session_store() -> SessionStore:
    """Process-wide session store singleton (shared by the chat service)."""
    global _store
    if _store is None:
        _store = build_session_store()
    return _store


def set_session_store(store: SessionStore | None) -> None:
    """Test seam: inject a store (or reset to None to rebuild from config)."""
    global _store
    _store = store


__all__ = [
    "ChatSession",
    "InMemorySessionStore",
    "RedisSessionStore",
    "SessionStore",
    "build_session_store",
    "get_session_store",
    "set_session_store",
]
