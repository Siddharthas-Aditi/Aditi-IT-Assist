# Reliable Live-Chat Handoff + Auto-Routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI→human handoff reliable: auto-route each live-support request to the best-fit Available specialist, notify them, advance the request on silence (re-offer → broaden → graceful fallback), so a waiting employee always reaches a terminal, honest state instead of an infinite "Please wait…".

**Architecture:** Two new DB-backed concepts — specialist **presence** (`specialist_availability`) and a handoff **offer lifecycle** (`live_handoff_offers`) — driven by pure decision functions (`is_available`, `rank_candidates`, `decide_next`) and advanced by a periodic scheduler job that mirrors the existing idle sweeper. Escalation creates an offer; a specialist accepting it reuses the existing atomic claim + `SpecialistChatService.start`; the employee's existing `waiting-status` poll is extended to show connecting/busy/fallback.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / PostgreSQL. Frontend React 18 + TS + Vite, `apiRequest` clients + `setInterval` polling (no React Query for this surface). Tests: pytest (backend), Vitest + RTL (frontend).

## Global Constraints

- Line length 100; Ruff lint + format must pass (`uv run ruff check . && uv run ruff format --check .`).
- Services never commit; callers/endpoints/scheduler own the transaction (existing convention).
- Pure decision logic lives as module-level functions beside its service (mirrors `evaluate_idle` in `specialist_chat_service.py`, `waiting_info` in `specialist_queue_service.py`) and must be unit-testable with no DB/LLM/network.
- Degrade, never hang: any routing/presence error falls back to the plain claimable queue; the employee still gets the fallback path.
- RBAC via `require_permissions(P.*)` (permission-based, matching both specialist routers). Reuse `P.SPECIALIST_QUEUE_VIEW` / `P.SPECIALIST_QUEUE_CLAIM`.
- New migration is `013_live_handoff.py`, `down_revision = "012_support_sessions"`, mirroring `012_support_sessions.py` structure (enum `.create(checkfirst=True)` before `create_table`; drop in reverse in `downgrade`).
- Frontend specialist API additions go in `frontend/src/features/specialist-chat/api.ts` as `apiRequest`-based methods; components poll with `setInterval`. Frontend tests mock the client methods with `vi.spyOn(queueApi, 'x').mockResolvedValue(...)`.
- All new config settings have defaults (dev/test must boot with none set): `LIVE_OFFER_TTL_SECONDS=30`, `LIVE_OFFER_MAX_ROUNDS=2`, `LIVE_HANDOFF_FALLBACK_SECONDS=120`, `SPECIALIST_PRESENCE_TTL_SECONDS=60`, `HANDOFF_SWEEPER_ENABLED=True`, `HANDOFF_SWEEPER_INTERVAL_SECONDS=10`.

---

## File Structure

**Create:**
- `backend/app/models/live_handoff.py` — `SpecialistAvailability`, `LiveHandoffOffer` ORM models + enum tuples.
- `backend/alembic/versions/013_live_handoff.py` — two tables + two enums.
- `backend/app/services/specialist_presence_service.py` — pure `is_available()` + `PresenceService`.
- `backend/app/services/specialist_handoff_service.py` — pure `rank_candidates()`, `decide_next()` + `HandoffService`.
- `backend/app/schemas/specialist_handoff.py` — presence + offer + routing DTOs.
- `backend/scripts/cleanup_stale_handoffs.py` — one-off maintenance for pre-fix queue rows.
- Tests: `backend/tests/unit/test_specialist_presence.py`, `backend/tests/unit/test_handoff_routing.py`, `backend/tests/unit/test_handoff_decision.py`, `backend/tests/api/test_specialist_presence_api.py`, `backend/tests/unit/test_handoff_service.py`, `frontend/src/features/specialist-chat/presence.test.tsx` (co-located with a small presence component test), `frontend/src/pages/employee/SupportChatWaiting.test.tsx`.

**Modify:**
- `backend/app/core/config.py` — new settings (after line ~223, near `LIVE_WAIT_TIMEOUT_SECONDS`).
- `backend/app/services/scheduler.py` — `_advance_handoff_offers_once` + registration in `start_background_jobs`.
- `backend/app/main.py:80-92` — pass the new sweeper kwargs.
- `backend/app/services/agents/chat_service.py` — create an offer in `request_live_agent`; extend `get_waiting_status` output.
- `backend/app/schemas/chat.py` — extend `WaitingStatusResponse` with handoff-state fields.
- `backend/app/api/v1/specialist_queue.py` — presence endpoints + accept-offer endpoint.
- `frontend/src/features/specialist-chat/api.ts` — presence + offer types & client methods.
- `frontend/src/pages/operations/LiveQueuePage.tsx` — Available/Away toggle + heartbeat + offer section.
- `frontend/src/pages/employee/SupportChatPage.tsx` — waiting banner: connecting/busy/fallback.

---

## Task 1: Config settings

**Files:**
- Modify: `backend/app/core/config.py` (after `LIVE_WAIT_TIMEOUT_SECONDS`, ~line 223)
- Test: `backend/tests/unit/test_handoff_config.py`

**Interfaces:**
- Produces: `settings.LIVE_OFFER_TTL_SECONDS: int`, `settings.LIVE_OFFER_MAX_ROUNDS: int`, `settings.LIVE_HANDOFF_FALLBACK_SECONDS: int`, `settings.SPECIALIST_PRESENCE_TTL_SECONDS: int`, `settings.HANDOFF_SWEEPER_ENABLED: bool`, `settings.HANDOFF_SWEEPER_INTERVAL_SECONDS: int`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_handoff_config.py
from __future__ import annotations

from app.core.config import Settings


def test_handoff_defaults_present():
    s = Settings()
    assert s.LIVE_OFFER_TTL_SECONDS == 30
    assert s.LIVE_OFFER_MAX_ROUNDS == 2
    assert s.LIVE_HANDOFF_FALLBACK_SECONDS == 120
    assert s.SPECIALIST_PRESENCE_TTL_SECONDS == 60
    assert s.HANDOFF_SWEEPER_ENABLED is True
    assert s.HANDOFF_SWEEPER_INTERVAL_SECONDS == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_config.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'LIVE_OFFER_TTL_SECONDS'`.

- [ ] **Step 3: Add the settings**

In `backend/app/core/config.py`, immediately after the `LIVE_WAIT_TIMEOUT_SECONDS: int = 900` line:

```python
    # ── Live handoff: offer lifecycle + specialist presence ────────────────
    LIVE_OFFER_TTL_SECONDS: int = 30  # how long a targeted offer stays with one specialist
    LIVE_OFFER_MAX_ROUNDS: int = 2  # targeted re-offers before broadening to all Available
    LIVE_HANDOFF_FALLBACK_SECONDS: int = 120  # overall cap before graceful fallback
    SPECIALIST_PRESENCE_TTL_SECONDS: int = 60  # heartbeat freshness for "Available"
    HANDOFF_SWEEPER_ENABLED: bool = True
    HANDOFF_SWEEPER_INTERVAL_SECONDS: int = 10  # tighter than idle sweeper — offers expire in 30s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/unit/test_handoff_config.py
git commit -m "feat(handoff): add offer-lifecycle + presence config settings"
```

---

## Task 2: Models + migration (specialist_availability, live_handoff_offers)

**Files:**
- Create: `backend/app/models/live_handoff.py`
- Create: `backend/alembic/versions/013_live_handoff.py`
- Modify: `backend/app/models/__init__.py` (register the new models for metadata import)
- Test: `backend/tests/unit/test_live_handoff_models.py`

**Interfaces:**
- Produces:
  - `SpecialistAvailability(user_id: UUID [PK/FK users.id], status: str, last_heartbeat_at: datetime, created_at, updated_at)`; enum `specialist_availability_status = ("available","away")`.
  - `LiveHandoffOffer(id: UUID, ticket_id: UUID [FK tickets.id], offered_to: UUID|None [FK users.id], offered_at: datetime, expires_at: datetime, round_index: int, state: str, created_at, updated_at)`; enum `live_handoff_offer_state = ("offered","accepted","expired","broadened","fallback")`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_live_handoff_models.py
from __future__ import annotations

from app.models.live_handoff import (
    LIVE_HANDOFF_OFFER_STATES,
    SPECIALIST_AVAILABILITY_STATUSES,
    LiveHandoffOffer,
    SpecialistAvailability,
)


def test_enum_tuples():
    assert SPECIALIST_AVAILABILITY_STATUSES == ("available", "away")
    assert set(LIVE_HANDOFF_OFFER_STATES) == {
        "offered", "accepted", "expired", "broadened", "fallback",
    }


def test_table_names_and_columns():
    assert SpecialistAvailability.__tablename__ == "specialist_availability"
    assert LiveHandoffOffer.__tablename__ == "live_handoff_offers"
    # key columns exist
    assert "status" in SpecialistAvailability.__table__.columns
    assert "last_heartbeat_at" in SpecialistAvailability.__table__.columns
    for col in ("ticket_id", "offered_to", "expires_at", "round_index", "state"):
        assert col in LiveHandoffOffer.__table__.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_live_handoff_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.live_handoff'`.

- [ ] **Step 3: Create the models**

```python
# backend/app/models/live_handoff.py
"""Live-handoff presence + offer models.

`specialist_availability` — one row per specialist tracking Available/Away + a
heartbeat, so auto-routing only offers to genuinely-present specialists (survives
restarts and is correct across workers).

`live_handoff_offers` — the connection-attempt lifecycle for a queued live-support
ticket: a targeted offer to one specialist that the sweeper advances (re-offer →
broaden → fallback) until a specialist accepts or the attempt is exhausted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SPECIALIST_AVAILABILITY_STATUSES = ("available", "away")
LIVE_HANDOFF_OFFER_STATES = ("offered", "accepted", "expired", "broadened", "fallback")


class SpecialistAvailability(TimestampMixin, Base):
    """Presence for a single specialist. PK is the user id (one row per specialist)."""

    __tablename__ = "specialist_availability"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*SPECIALIST_AVAILABILITY_STATUSES, name="specialist_availability_status"),
        nullable=False,
        default="away",
        server_default="away",
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LiveHandoffOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One connection attempt for a queued live-support ticket."""

    __tablename__ = "live_handoff_offers"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offered_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(
        Enum(*LIVE_HANDOFF_OFFER_STATES, name="live_handoff_offer_state"),
        nullable=False,
        default="offered",
        index=True,
    )
```

> Check `backend/app/models/base.py` for the exact mixin names (`UUIDPrimaryKeyMixin`, `TimestampMixin`, `Base`) — they are used by `specialist_chat.py`. If a mixin name differs, match the existing one.

- [ ] **Step 4: Register models for metadata**

In `backend/app/models/__init__.py`, add (follow the existing import/`__all__` style in that file):

```python
from app.models.live_handoff import LiveHandoffOffer, SpecialistAvailability  # noqa: F401
```

Add `"LiveHandoffOffer"` and `"SpecialistAvailability"` to `__all__` if the file maintains one.

- [ ] **Step 5: Run the model test**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_live_handoff_models.py -q`
Expected: PASS.

- [ ] **Step 6: Write the migration**

```python
# backend/alembic/versions/013_live_handoff.py
"""live handoff: specialist_availability + live_handoff_offers

Revision ID: 013_live_handoff
Revises: 012_support_sessions
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013_live_handoff"
down_revision = "012_support_sessions"
branch_labels = None
depends_on = None

_AVAIL = postgresql.ENUM(
    "available", "away", name="specialist_availability_status", create_type=False
)
_OFFER = postgresql.ENUM(
    "offered", "accepted", "expired", "broadened", "fallback",
    name="live_handoff_offer_state", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _AVAIL.create(bind, checkfirst=True)
    _OFFER.create(bind, checkfirst=True)

    op.create_table(
        "specialist_availability",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "status",
            sa.Enum(*_AVAIL.enums, name="specialist_availability_status", create_type=False),
            nullable=False,
            server_default="away",
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "live_handoff_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offered_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "state",
            sa.Enum(*_OFFER.enums, name="live_handoff_offer_state", create_type=False),
            nullable=False,
            server_default="offered",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offered_to"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_live_handoff_offers_ticket_id", "live_handoff_offers", ["ticket_id"])
    op.create_index("ix_live_handoff_offers_state", "live_handoff_offers", ["state"])
    # One active (non-terminal) offer per ticket.
    op.create_index(
        "ix_live_handoff_active_per_ticket",
        "live_handoff_offers",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('offered','broadened')"),
    )


def downgrade() -> None:
    op.drop_index("ix_live_handoff_active_per_ticket", table_name="live_handoff_offers")
    op.drop_index("ix_live_handoff_offers_state", table_name="live_handoff_offers")
    op.drop_index("ix_live_handoff_offers_ticket_id", table_name="live_handoff_offers")
    op.drop_table("live_handoff_offers")
    op.drop_table("specialist_availability")
    op.execute("DROP TYPE IF EXISTS live_handoff_offer_state")
    op.execute("DROP TYPE IF EXISTS specialist_availability_status")
```

- [ ] **Step 7: Apply the migration and verify**

Run:
```bash
docker compose exec -T backend uv run alembic upgrade head
docker compose exec -T postgres psql -U aditi -d aditi_assist -c "\dt" | grep -E "specialist_availability|live_handoff_offers"
```
Expected: both tables listed. Then verify downgrade/upgrade round-trips:
```bash
docker compose exec -T backend uv run alembic downgrade -1
docker compose exec -T backend uv run alembic upgrade head
```
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/live_handoff.py backend/app/models/__init__.py \
        backend/alembic/versions/013_live_handoff.py \
        backend/tests/unit/test_live_handoff_models.py
git commit -m "feat(handoff): add specialist_availability + live_handoff_offers models + migration 013"
```

---

## Task 3: Presence — pure `is_available` + `PresenceService`

**Files:**
- Create: `backend/app/services/specialist_presence_service.py`
- Test: `backend/tests/unit/test_specialist_presence.py`

**Interfaces:**
- Consumes: `SpecialistAvailability` (Task 2), `settings.SPECIALIST_PRESENCE_TTL_SECONDS` (Task 1).
- Produces:
  - `is_available(status: str, last_heartbeat_at: datetime | None, now: datetime, ttl_seconds: int) -> bool`
  - `PresenceService(db)` with:
    - `async set_status(user_id: uuid.UUID, status: str) -> SpecialistAvailability`
    - `async heartbeat(user_id: uuid.UUID) -> SpecialistAvailability`
    - `async get(user_id: uuid.UUID) -> SpecialistAvailability | None`
    - `async list_available_ids(now: datetime | None = None) -> list[uuid.UUID]`

- [ ] **Step 1: Write the failing test (pure fn)**

```python
# backend/tests/unit/test_specialist_presence.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.specialist_presence_service import is_available

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)


def test_available_with_fresh_heartbeat():
    assert is_available("available", NOW - timedelta(seconds=30), NOW, 60) is True


def test_available_but_stale_heartbeat_is_unavailable():
    assert is_available("available", NOW - timedelta(seconds=120), NOW, 60) is False


def test_away_is_never_available():
    assert is_available("away", NOW, NOW, 60) is False


def test_missing_heartbeat_is_unavailable():
    assert is_available("available", None, NOW, 60) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_specialist_presence.py -q`
Expected: FAIL — module/function missing.

- [ ] **Step 3: Implement the module**

```python
# backend/app/services/specialist_presence_service.py
"""Specialist presence: explicit Available/Away + heartbeat freshness.

`is_available` is pure so routing decisions are unit-testable. The service is a
thin DB upsert/query layer; it does NOT commit (callers own the transaction).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.live_handoff import SpecialistAvailability

logger = get_logger(__name__)


def is_available(
    status: str,
    last_heartbeat_at: datetime | None,
    now: datetime,
    ttl_seconds: int,
) -> bool:
    """True only when explicitly Available AND the heartbeat is fresh."""
    if status != "available" or last_heartbeat_at is None:
        return False
    hb = last_heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=UTC)
    return (now - hb) <= timedelta(seconds=ttl_seconds)


class PresenceService:
    def __init__(self, db) -> None:  # AsyncSession
        self.db = db

    async def _upsert(self, user_id: uuid.UUID, *, status: str | None, touch: bool):
        row = await self.db.get(SpecialistAvailability, user_id)
        now = datetime.now(UTC)
        if row is None:
            row = SpecialistAvailability(
                user_id=user_id,
                status=status or "away",
                last_heartbeat_at=now,
            )
            self.db.add(row)
        else:
            if status is not None:
                row.status = status
            if touch:
                row.last_heartbeat_at = now
        await self.db.flush()
        return row

    async def set_status(self, user_id: uuid.UUID, status: str) -> SpecialistAvailability:
        if status not in ("available", "away"):
            raise ValueError(f"invalid status {status!r}")
        # Setting a status also counts as presence activity.
        return await self._upsert(user_id, status=status, touch=True)

    async def heartbeat(self, user_id: uuid.UUID) -> SpecialistAvailability:
        return await self._upsert(user_id, status=None, touch=True)

    async def get(self, user_id: uuid.UUID) -> SpecialistAvailability | None:
        return await self.db.get(SpecialistAvailability, user_id)

    async def list_available_ids(self, now: datetime | None = None) -> list[uuid.UUID]:
        from app.core.config import settings

        ts = now or datetime.now(UTC)
        ttl = settings.SPECIALIST_PRESENCE_TTL_SECONDS
        rows = (await self.db.execute(select(SpecialistAvailability))).scalars().all()
        return [
            r.user_id for r in rows if is_available(r.status, r.last_heartbeat_at, ts, ttl)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_specialist_presence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/specialist_presence_service.py backend/tests/unit/test_specialist_presence.py
git commit -m "feat(handoff): specialist presence service + pure is_available"
```

---

## Task 4: Routing — pure `rank_candidates`

**Files:**
- Create: `backend/app/services/specialist_handoff_service.py` (routing half only in this task)
- Test: `backend/tests/unit/test_handoff_routing.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) SpecialistLoad(user_id: uuid.UUID, active_load: int)`
  - `rank_candidates(ticket_category: str | None, available: list[SpecialistLoad], recent_category_handlers: set[uuid.UUID]) -> list[uuid.UUID]` (best first; lowest load, category-recent handlers boosted at equal load; deterministic tie-break by `str(user_id)`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_handoff_routing.py
from __future__ import annotations

import uuid

from app.services.specialist_handoff_service import SpecialistLoad, rank_candidates

A = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
B = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
C = uuid.UUID("00000000-0000-0000-0000-0000000000cc")


def test_orders_by_lowest_load():
    out = rank_candidates(
        "email/outlook",
        [SpecialistLoad(A, 3), SpecialistLoad(B, 1), SpecialistLoad(C, 2)],
        recent_category_handlers=set(),
    )
    assert out == [B, C, A]


def test_category_handler_boosted_at_equal_load():
    # A and B both load 2; C recently handled the category -> C ahead of equals.
    out = rank_candidates(
        "network/vpn",
        [SpecialistLoad(A, 2), SpecialistLoad(B, 2), SpecialistLoad(C, 2)],
        recent_category_handlers={C},
    )
    assert out[0] == C


def test_empty_available_returns_empty():
    assert rank_candidates("x", [], set()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_routing.py -q`
Expected: FAIL — module/function missing.

- [ ] **Step 3: Implement routing (start the handoff service module)**

```python
# backend/app/services/specialist_handoff_service.py
"""Live-handoff offer lifecycle: routing + decision (pure) and the DB service.

Pure functions (`rank_candidates`, `decide_next`) hold all the policy and are
unit-tested without I/O. `HandoffService` applies them against the DB and is
driven by both the escalation path (create the first offer) and the periodic
sweeper (advance expired offers).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialistLoad:
    user_id: uuid.UUID
    active_load: int


def rank_candidates(
    ticket_category: str | None,
    available: list[SpecialistLoad],
    recent_category_handlers: set[uuid.UUID],
) -> list[uuid.UUID]:
    """Best-first ordering: lowest load, category-recent handlers boosted, stable."""

    def sort_key(s: SpecialistLoad) -> tuple[int, int, str]:
        boosted = 0 if s.user_id in recent_category_handlers else 1
        return (s.active_load, boosted, str(s.user_id))

    return [s.user_id for s in sorted(available, key=sort_key)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_routing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/specialist_handoff_service.py backend/tests/unit/test_handoff_routing.py
git commit -m "feat(handoff): pure rank_candidates routing"
```

---

## Task 5: Offer lifecycle — pure `decide_next`

**Files:**
- Modify: `backend/app/services/specialist_handoff_service.py` (add decision types + fn)
- Test: `backend/tests/unit/test_handoff_decision.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) HandoffDecision(action: str, next_specialist_id: uuid.UUID | None = None)` where `action ∈ {"hold","reoffer","broaden","fallback"}`.
  - `decide_next(*, offered_at, request_started_at, round_index, candidates_remaining: list[uuid.UUID], any_available: bool, now, offer_ttl_seconds: int, max_rounds: int, fallback_seconds: int) -> HandoffDecision`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_handoff_decision.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.services.specialist_handoff_service import HandoffDecision, decide_next

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
X = uuid.uuid4()


def _call(**kw):
    base = dict(
        offered_at=NOW,
        request_started_at=NOW,
        round_index=0,
        candidates_remaining=[X],
        any_available=True,
        now=NOW,
        offer_ttl_seconds=30,
        max_rounds=2,
        fallback_seconds=120,
    )
    base.update(kw)
    return decide_next(**base)


def test_fresh_offer_holds():
    assert _call(now=NOW + timedelta(seconds=10)).action == "hold"


def test_expired_offer_reoffers_next_candidate():
    d = _call(now=NOW + timedelta(seconds=31))
    assert d == HandoffDecision("reoffer", X)


def test_round_cap_broadens_when_available():
    d = _call(now=NOW + timedelta(seconds=31), round_index=1, max_rounds=2)
    assert d.action == "broaden"


def test_no_candidates_and_none_available_falls_back():
    d = _call(now=NOW + timedelta(seconds=31), candidates_remaining=[], any_available=False)
    assert d.action == "fallback"


def test_overall_deadline_forces_fallback():
    d = _call(now=NOW + timedelta(seconds=121))
    assert d.action == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_decision.py -q`
Expected: FAIL — names missing.

- [ ] **Step 3: Implement `decide_next` (append to the handoff service module)**

```python
# append to backend/app/services/specialist_handoff_service.py
from datetime import datetime  # noqa: E402  (add to the existing imports block at top)


@dataclass(frozen=True)
class HandoffDecision:
    action: str  # "hold" | "reoffer" | "broaden" | "fallback"
    next_specialist_id: uuid.UUID | None = None


def decide_next(
    *,
    offered_at: datetime,
    request_started_at: datetime,
    round_index: int,
    candidates_remaining: list[uuid.UUID],
    any_available: bool,
    now: datetime,
    offer_ttl_seconds: int,
    max_rounds: int,
    fallback_seconds: int,
) -> HandoffDecision:
    """Decide how to advance a live-handoff offer. Pure."""
    if (now - request_started_at).total_seconds() >= fallback_seconds:
        return HandoffDecision("fallback")
    if (now - offered_at).total_seconds() < offer_ttl_seconds:
        return HandoffDecision("hold")
    # Offer expired. Try another targeted round unless we've hit the cap.
    if round_index + 1 < max_rounds and candidates_remaining:
        return HandoffDecision("reoffer", candidates_remaining[0])
    # Cap reached or no targeted candidate left → broaden if anyone is Available.
    if any_available:
        return HandoffDecision("broaden")
    return HandoffDecision("fallback")
```

> Move the `from datetime import datetime` up into the module's top import block rather than mid-file; the inline note above is only to show which import is needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_decision.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/specialist_handoff_service.py backend/tests/unit/test_handoff_decision.py
git commit -m "feat(handoff): pure decide_next offer-lifecycle decision"
```

---

## Task 6: `HandoffService` — create / accept / advance (DB)

**Files:**
- Modify: `backend/app/services/specialist_handoff_service.py` (add `HandoffService`)
- Test: `backend/tests/unit/test_handoff_service.py` (uses the repo's async DB test fixture — mirror `backend/tests/api/test_admin.py` or an existing service test for the session/factory fixture)

**Interfaces:**
- Consumes: `PresenceService.list_available_ids` (Task 3), `rank_candidates`/`decide_next` (Tasks 4-5), `LiveHandoffOffer`/`Ticket` models, `settings.*` (Task 1).
- Produces `HandoffService(db)` with:
  - `async create_offer(ticket, *, now=None) -> LiveHandoffOffer | None` — ranks Available specialists, inserts an `offered` row for the top candidate; returns `None` if none Available (caller then leaves it as a plain queue entry; advance/fallback still applies).
  - `async accept(ticket_id, *, specialist) -> LiveHandoffOffer` — marks the active offer `accepted` (idempotent; raises `PermissionError` if already accepted by someone else). Called from the claim path.
  - `async advance_once(*, now=None) -> dict[str, int]` — one sweeper pass over active offers; applies `decide_next`; returns counts `{"reoffered","broadened","fallback","held"}`.
  - `async active_offer_for(ticket_id) -> LiveHandoffOffer | None`
  - Helper `async _load_map(candidate_ids) -> list[SpecialistLoad]` and `async _recent_category_handlers(category) -> set[uuid.UUID]` (derive from recent resolved tickets in that category; last 30 days, `assigned_to`).

- [ ] **Step 1: Write the failing test** (service-level, real DB session fixture)

```python
# backend/tests/unit/test_handoff_service.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.live_handoff import LiveHandoffOffer
from app.services.specialist_handoff_service import HandoffService
from app.services.specialist_presence_service import PresenceService

pytestmark = pytest.mark.asyncio


async def _make_specialist(db, email):
    # Reuse the repo's user factory if one exists; otherwise create via ORM.
    from app.models.user import User

    u = User(email=email, full_name=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _make_chat_ticket(db, requester):
    from app.models.ticket import Ticket

    t = Ticket(
        ticket_number=f"ITA-TEST-{uuid.uuid4().hex[:6]}",
        title="Live support request",
        description="x",
        requester_id=requester.id,
        source="chat",
        status="triaged",
        priority="medium",
        category="email/outlook",
    )
    db.add(t)
    await db.flush()
    return t


async def test_create_offer_targets_available_specialist(db_session):
    db = db_session
    spec = await _make_specialist(db, "spec1@x.com")
    requester = await _make_specialist(db, "emp1@x.com")
    await PresenceService(db).set_status(spec.id, "available")
    ticket = await _make_chat_ticket(db, requester)

    offer = await HandoffService(db).create_offer(ticket)

    assert offer is not None
    assert offer.offered_to == spec.id
    assert offer.state == "offered"


async def test_create_offer_none_when_no_one_available(db_session):
    db = db_session
    requester = await _make_specialist(db, "emp2@x.com")
    ticket = await _make_chat_ticket(db, requester)
    assert await HandoffService(db).create_offer(ticket) is None


async def test_advance_expired_offer_falls_back_when_none_available(db_session):
    db = db_session
    requester = await _make_specialist(db, "emp3@x.com")
    ticket = await _make_chat_ticket(db, requester)
    stale = datetime.now(UTC) - timedelta(seconds=300)
    db.add(LiveHandoffOffer(
        ticket_id=ticket.id, offered_to=None, offered_at=stale,
        expires_at=stale + timedelta(seconds=30), round_index=1, state="offered",
    ))
    await db.flush()

    counts = await HandoffService(db).advance_once()

    assert counts["fallback"] >= 1
    offer = await HandoffService(db).active_offer_for(ticket.id)
    assert offer is None  # moved to terminal 'fallback'
```

> Use the project's existing async DB fixture name. Find it: `grep -rn "async def db_session\|@pytest.fixture" backend/tests/conftest.py`. If the fixture is named differently (e.g. `session`, `async_session`), rename the parameter accordingly. If no transactional DB fixture exists, mirror the setup in `backend/tests/api/test_admin.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_service.py -q`
Expected: FAIL — `HandoffService` has no `create_offer`.

- [ ] **Step 3: Implement `HandoffService`** (append to the module)

```python
# append to backend/app/services/specialist_handoff_service.py
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update

from app.core.config import settings
from app.core.logging import get_logger
from app.models.live_handoff import LiveHandoffOffer
from app.models.ticket import Ticket
from app.services.specialist_presence_service import PresenceService

logger = get_logger(__name__)

_ACTIVE_OFFER_STATES = ("offered", "broadened")


class HandoffService:
    def __init__(self, db) -> None:  # AsyncSession
        self.db = db
        self.presence = PresenceService(db)

    async def active_offer_for(self, ticket_id: uuid.UUID) -> LiveHandoffOffer | None:
        stmt = (
            select(LiveHandoffOffer)
            .where(
                LiveHandoffOffer.ticket_id == ticket_id,
                LiveHandoffOffer.state.in_(_ACTIVE_OFFER_STATES),
            )
            .order_by(LiveHandoffOffer.offered_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_map(self, candidate_ids: list[uuid.UUID]) -> list[SpecialistLoad]:
        if not candidate_ids:
            return []
        stmt = (
            select(Ticket.assigned_to, func.count().label("n"))
            .where(
                Ticket.assigned_to.in_(candidate_ids),
                Ticket.status.in_(("triaged", "in_progress", "waiting_for_user", "escalated")),
            )
            .group_by(Ticket.assigned_to)
        )
        counts = {row[0]: row[1] for row in (await self.db.execute(stmt)).all()}
        return [SpecialistLoad(cid, int(counts.get(cid, 0))) for cid in candidate_ids]

    async def _recent_category_handlers(self, category: str | None) -> set[uuid.UUID]:
        if not category:
            return set()
        since = datetime.now(UTC) - timedelta(days=30)
        stmt = (
            select(Ticket.assigned_to)
            .where(
                Ticket.category == category,
                Ticket.assigned_to.is_not(None),
                Ticket.resolved_at.is_not(None),
                Ticket.resolved_at >= since,
            )
            .distinct()
        )
        return {row[0] for row in (await self.db.execute(stmt)).all() if row[0]}

    async def _ranked_available(
        self, ticket: Ticket, *, exclude: set[uuid.UUID] | None = None
    ) -> list[uuid.UUID]:
        available = set(await self.presence.list_available_ids())
        if exclude:
            available -= exclude
        # Never offer to the requester.
        available.discard(ticket.requester_id)
        ids = list(available)
        loads = await self._load_map(ids)
        handlers = await self._recent_category_handlers(ticket.category)
        return rank_candidates(ticket.category, loads, handlers)

    async def create_offer(
        self, ticket: Ticket, *, now: datetime | None = None
    ) -> LiveHandoffOffer | None:
        ts = now or datetime.now(UTC)
        ranked = await self._ranked_available(ticket)
        if not ranked:
            logger.info("handoff_no_available_specialist", ticket_id=str(ticket.id))
            return None
        offer = LiveHandoffOffer(
            ticket_id=ticket.id,
            offered_to=ranked[0],
            offered_at=ts,
            expires_at=ts + timedelta(seconds=settings.LIVE_OFFER_TTL_SECONDS),
            round_index=0,
            state="offered",
        )
        self.db.add(offer)
        await self.db.flush()
        logger.info("handoff_offer_created", ticket_id=str(ticket.id), offered_to=str(ranked[0]))
        return offer

    async def accept(self, ticket_id: uuid.UUID, *, specialist) -> LiveHandoffOffer:
        offer = await self.active_offer_for(ticket_id)
        if offer is None:
            # No active offer (already accepted/broadened-claimed). Idempotent no-op record.
            raise PermissionError("No active handoff offer for this ticket")
        offer.state = "accepted"
        offer.offered_to = specialist.id
        await self.db.flush()
        return offer

    async def advance_once(self, *, now: datetime | None = None) -> dict[str, int]:
        ts = now or datetime.now(UTC)
        counts = {"reoffered": 0, "broadened": 0, "fallback": 0, "held": 0}
        stmt = (
            select(LiveHandoffOffer)
            .where(LiveHandoffOffer.state.in_(_ACTIVE_OFFER_STATES))
            .with_for_update(skip_locked=True)
            .limit(200)
        )
        offers = (await self.db.execute(stmt)).scalars().all()
        for offer in offers:
            ticket = await self.db.get(Ticket, offer.ticket_id)
            if ticket is None or ticket.assigned_to is not None:
                # Claimed/accepted already → terminalize.
                offer.state = "accepted"
                continue
            tried = {offer.offered_to} if offer.offered_to else set()
            ranked = await self._ranked_available(ticket, exclude=tried)
            decision = decide_next(
                offered_at=offer.offered_at,
                request_started_at=offer.created_at,
                round_index=offer.round_index,
                candidates_remaining=ranked,
                any_available=bool(await self.presence.list_available_ids()),
                now=ts,
                offer_ttl_seconds=settings.LIVE_OFFER_TTL_SECONDS,
                max_rounds=settings.LIVE_OFFER_MAX_ROUNDS,
                fallback_seconds=settings.LIVE_HANDOFF_FALLBACK_SECONDS,
            )
            if decision.action == "hold":
                counts["held"] += 1
            elif decision.action == "reoffer" and decision.next_specialist_id:
                offer.offered_to = decision.next_specialist_id
                offer.offered_at = ts
                offer.expires_at = ts + timedelta(seconds=settings.LIVE_OFFER_TTL_SECONDS)
                offer.round_index += 1
                counts["reoffered"] += 1
            elif decision.action == "broaden":
                offer.state = "broadened"
                offer.offered_to = None
                counts["broadened"] += 1
            else:  # fallback
                offer.state = "fallback"
                counts["fallback"] += 1
        return counts
```

> `create_offer` and `accept` do not commit. `advance_once` does not commit — the scheduler wrapper commits (Task 7). Confirm `Ticket` has `resolved_at` (it does per the model map).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_service.py -q`
Expected: PASS. If the DB fixture doesn't auto-commit, ensure the test flushes (it does) — reads happen in the same session.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/specialist_handoff_service.py backend/tests/unit/test_handoff_service.py
git commit -m "feat(handoff): HandoffService create/accept/advance offer lifecycle"
```

---

## Task 7: Scheduler job — advance offers periodically

**Files:**
- Modify: `backend/app/services/scheduler.py`
- Modify: `backend/app/main.py:80-92`
- Test: `backend/tests/unit/test_handoff_sweeper.py`

**Interfaces:**
- Consumes: `HandoffService.advance_once` (Task 6), `settings.HANDOFF_SWEEPER_*` (Task 1).
- Produces: `_advance_handoff_offers_once()` coroutine; new kwargs on `start_background_jobs`: `handoff_sweeper_enabled: bool = True`, `handoff_sweeper_interval_seconds: int = 10`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_handoff_sweeper.py
from __future__ import annotations

import pytest

from app.services import scheduler

pytestmark = pytest.mark.asyncio


async def test_advance_handoff_offers_once_runs_without_error(monkeypatch):
    called = {"n": 0}

    class _FakeSvc:
        def __init__(self, db):  # noqa: D401
            pass

        async def advance_once(self):
            called["n"] += 1
            return {"reoffered": 0, "broadened": 0, "fallback": 0, "held": 0}

    monkeypatch.setattr(scheduler, "HandoffService", _FakeSvc, raising=False)
    await scheduler._advance_handoff_offers_once()
    assert called["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_sweeper.py -q`
Expected: FAIL — `scheduler` has no `_advance_handoff_offers_once` / no `HandoffService` attr.

- [ ] **Step 3: Add the one-pass coroutine + import**

In `backend/app/services/scheduler.py`, add near the other `_sweep_*_once` coroutines, and import at top:

```python
from app.services.specialist_handoff_service import HandoffService
```

```python
async def _advance_handoff_offers_once() -> None:
    """One pass advancing live-handoff offers (re-offer/broaden/fallback)."""
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            counts = await HandoffService(db).advance_once()
            if any(v for k, v in counts.items() if k != "held"):
                await db.commit()
            else:
                await db.rollback()
        except Exception:
            await db.rollback()
            logger.exception("handoff_advance_failed")
```

- [ ] **Step 4: Register the job in `start_background_jobs`**

Add two kwargs to the signature: `handoff_sweeper_enabled: bool = True, handoff_sweeper_interval_seconds: int = 10`. In the registration block, mirroring the idle sweeper:

```python
    if handoff_sweeper_enabled:
        tasks.append(
            asyncio.create_task(
                _run_loop(
                    "handoff.advance_offers",
                    _advance_handoff_offers_once,
                    handoff_sweeper_interval_seconds,
                ),
                name="handoff.advance_offers",
            )
        )
```

- [ ] **Step 5: Wire it in the lifespan**

In `backend/app/main.py`, inside the `start_background_jobs(...)` call, add:

```python
        handoff_sweeper_enabled=settings.HANDOFF_SWEEPER_ENABLED,
        handoff_sweeper_interval_seconds=settings.HANDOFF_SWEEPER_INTERVAL_SECONDS,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_handoff_sweeper.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/scheduler.py backend/app/main.py backend/tests/unit/test_handoff_sweeper.py
git commit -m "feat(handoff): periodic sweeper to advance handoff offers"
```

---

## Task 8: Presence + accept-offer API endpoints

**Files:**
- Modify: `backend/app/api/v1/specialist_queue.py`
- Create: `backend/app/schemas/specialist_handoff.py`
- Test: `backend/tests/api/test_specialist_presence_api.py`

**Interfaces:**
- Consumes: `PresenceService` (Task 3), `HandoffService.accept` (Task 6), existing `SpecialistQueueService.claim` + `SpecialistChatService.start`.
- Produces routes (prefix `/specialist-queue`):
  - `PUT /availability` body `{status: "available"|"away"}` → `PresenceOut` (dep `QueueViewerDep`).
  - `POST /availability/heartbeat` → `PresenceOut` (dep `QueueViewerDep`).
  - `GET /availability` → `PresenceOut` (dep `QueueViewerDep`).
  - `GET /offers/mine` → `list[OfferOut]` — active offers targeted to the caller (dep `QueueViewerDep`).
  - `POST /offers/{ticket_id}/accept` → `ClaimResponse` — accept an offer: claim + start session (dep `ClaimerDep`).
- DTOs in `schemas/specialist_handoff.py`: `PresenceOut{user_id, status, last_heartbeat_at, is_available}`, `PresenceUpdate{status}`, `OfferOut{ticket_id, ticket_number, offered_at, expires_at, round_index, state, summary: HandoffSummary}`.

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/api/test_specialist_presence_api.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_set_and_get_availability(client, it_lead_token):
    h = {"Authorization": f"Bearer {it_lead_token}"}
    r = await client.put("/api/v1/specialist-queue/availability", json={"status": "available"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "available"
    assert body["is_available"] is True

    r2 = await client.get("/api/v1/specialist-queue/availability", headers=h)
    assert r2.status_code == 200
    assert r2.json()["status"] == "available"


async def test_heartbeat_keeps_available(client, it_lead_token):
    h = {"Authorization": f"Bearer {it_lead_token}"}
    await client.put("/api/v1/specialist-queue/availability", json={"status": "available"}, headers=h)
    r = await client.post("/api/v1/specialist-queue/availability/heartbeat", headers=h)
    assert r.status_code == 200
    assert r.json()["is_available"] is True


async def test_availability_requires_specialist(client, employee_token):
    h = {"Authorization": f"Bearer {employee_token}"}
    r = await client.put("/api/v1/specialist-queue/availability", json={"status": "available"}, headers=h)
    assert r.status_code == 403
```

> Reuse existing API test fixtures. Find them: `grep -rn "it_lead_token\|employee_token\|async def client" backend/tests/conftest.py backend/tests/api/conftest.py`. If token fixtures have different names (e.g. `lead_headers`), adapt. `test_admin.py` is the reference for the client + auth fixture pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/api/test_specialist_presence_api.py -q`
Expected: FAIL — 404 (routes missing).

- [ ] **Step 3: Create the schemas**

```python
# backend/app/schemas/specialist_handoff.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.specialist_queue import HandoffSummary


class PresenceUpdate(BaseModel):
    status: Literal["available", "away"]


class PresenceOut(BaseModel):
    user_id: uuid.UUID
    status: Literal["available", "away"]
    last_heartbeat_at: datetime | None
    is_available: bool


class OfferOut(BaseModel):
    ticket_id: uuid.UUID
    ticket_number: str
    offered_at: datetime
    expires_at: datetime
    round_index: int
    state: str
    summary: HandoffSummary
```

> Confirm `HandoffSummary` import path from `backend/app/schemas/specialist_queue.py`. If `HandoffSummary` requires fields the offer path can't cheaply build, make `summary` optional (`HandoffSummary | None = None`) and populate from `SpecialistQueueService._to_queue_entry`.

- [ ] **Step 4: Add the endpoints**

In `backend/app/api/v1/specialist_queue.py`, add imports and routes. Use the existing `QueueViewerDep`/`ClaimerDep` and `DBDep` patterns already in the file:

```python
from datetime import UTC, datetime

from app.core.config import settings
from app.schemas.specialist_handoff import OfferOut, PresenceOut, PresenceUpdate
from app.services.specialist_handoff_service import HandoffService
from app.services.specialist_presence_service import PresenceService, is_available
from app.services.specialist_chat_service import SpecialistChatService


def _presence_out(row) -> PresenceOut:
    now = datetime.now(UTC)
    return PresenceOut(
        user_id=row.user_id,
        status=row.status,
        last_heartbeat_at=row.last_heartbeat_at,
        is_available=is_available(
            row.status, row.last_heartbeat_at, now, settings.SPECIALIST_PRESENCE_TTL_SECONDS
        ),
    )


@router.put("/availability", response_model=PresenceOut)
async def set_availability(body: PresenceUpdate, user: QueueViewerDep, db: DBDep) -> PresenceOut:
    row = await PresenceService(db).set_status(user.id, body.status)
    await db.commit()
    return _presence_out(row)


@router.post("/availability/heartbeat", response_model=PresenceOut)
async def heartbeat(user: QueueViewerDep, db: DBDep) -> PresenceOut:
    row = await PresenceService(db).heartbeat(user.id)
    await db.commit()
    return _presence_out(row)


@router.get("/availability", response_model=PresenceOut)
async def get_availability(user: QueueViewerDep, db: DBDep) -> PresenceOut:
    row = await PresenceService(db).get(user.id)
    if row is None:
        # Default: away, never-heartbeated.
        return PresenceOut(user_id=user.id, status="away", last_heartbeat_at=None, is_available=False)
    return _presence_out(row)


@router.post("/offers/{ticket_id}/accept", response_model=ClaimResponse)
async def accept_offer(ticket_id: uuid.UUID, user: ClaimerDep, db: DBDep) -> ClaimResponse:
    # Atomic claim (reuses the existing claim guard), then mark the offer accepted and
    # start the live session — the same steps the queue "claim" performs.
    queue = SpecialistQueueService(db)
    ticket = await queue.claim(ticket_id, claimer=user)
    try:
        await HandoffService(db).accept(ticket_id, specialist=user)
    except PermissionError:
        pass  # broadened offer already terminal — claim still valid
    requester = await db.get(User, ticket.requester_id)
    live = await SpecialistChatService(db).start(ticket=ticket, specialist=user, user=requester)
    await db.commit()
    return _claim_response(ticket, live)  # reuse the helper claim_ticket uses
```

> The exact `ClaimResponse` construction is whatever `claim_ticket` in this file already does after `claim()`. Extract that into a `_claim_response(ticket, live_session=None)` helper and call it from both `claim_ticket` and `accept_offer` (DRY). If `claim_ticket` currently returns without starting a session, keep that behavior for `claim_ticket` and only start a session in `accept_offer` (accepting an offer means "I'm joining now").

- [ ] **Step 5: Add the `GET /offers/mine` route**

```python
@router.get("/offers/mine", response_model=list[OfferOut])
async def my_offers(user: QueueViewerDep, db: DBDep) -> list[OfferOut]:
    from app.models.live_handoff import LiveHandoffOffer
    from app.models.ticket import Ticket
    from sqlalchemy import select

    stmt = (
        select(LiveHandoffOffer, Ticket)
        .join(Ticket, Ticket.id == LiveHandoffOffer.ticket_id)
        .where(
            LiveHandoffOffer.state == "offered",
            LiveHandoffOffer.offered_to == user.id,
        )
        .order_by(LiveHandoffOffer.offered_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    queue = SpecialistQueueService(db)
    out: list[OfferOut] = []
    for offer, ticket in rows:
        entry = queue._to_queue_entry(ticket)  # reuse existing summary builder
        out.append(OfferOut(
            ticket_id=ticket.id, ticket_number=ticket.ticket_number,
            offered_at=offer.offered_at, expires_at=offer.expires_at,
            round_index=offer.round_index, state=offer.state, summary=entry.summary,
        ))
    return out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/api/test_specialist_presence_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/specialist_queue.py backend/app/schemas/specialist_handoff.py \
        backend/tests/api/test_specialist_presence_api.py
git commit -m "feat(handoff): presence + accept-offer API endpoints"
```

---

## Task 9: Wire escalation → create offer; extend waiting-status

**Files:**
- Modify: `backend/app/services/agents/chat_service.py` (`request_live_agent`, `get_waiting_status`)
- Modify: `backend/app/schemas/chat.py` (`WaitingStatusResponse`)
- Test: `backend/tests/unit/test_chat_handoff_wiring.py`

**Interfaces:**
- Consumes: `HandoffService.create_offer`/`active_offer_for` (Task 6).
- Produces: `WaitingStatusResponse` gains `handoff_state: Literal["connecting","busy","connected","fallback"]` and keeps `specialist_available: bool` for backward-compat. `request_live_agent` calls `HandoffService(self.ticket_service.db).create_offer(ticket)` after `_persist_and_queue`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_chat_handoff_wiring.py
from __future__ import annotations

from app.schemas.chat import WaitingStatusResponse


def test_waiting_status_has_handoff_state():
    r = WaitingStatusResponse(
        waiting=True, waited_seconds=5, specialist_available=True, handoff_state="connecting"
    )
    assert r.handoff_state == "connecting"
```

> Match `WaitingStatusResponse`'s existing required fields (inspect `backend/app/schemas/chat.py`). Adjust the constructor kwargs to the real field set; the point of the test is that `handoff_state` exists and accepts the literal.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_chat_handoff_wiring.py -q`
Expected: FAIL — unexpected kwarg `handoff_state`.

- [ ] **Step 3: Extend the schema**

In `backend/app/schemas/chat.py`, add to `WaitingStatusResponse`:

```python
    handoff_state: Literal["connecting", "busy", "connected", "fallback"] = "connecting"
```

(Add `from typing import Literal` if not present.)

- [ ] **Step 4: Create the offer on live-agent request**

In `chat_service.py` `request_live_agent`, after `ref = await self._persist_and_queue(...)` and before setting `waiting_since`, add (best-effort — never block handoff):

```python
        # Route the request to an Available specialist (offer lifecycle). Best-effort:
        # if presence/routing is unavailable, the ticket still sits in the claimable queue
        # and the sweeper will drive re-offer/broaden/fallback.
        try:
            from app.services.specialist_handoff_service import HandoffService

            ticket_obj = await self.ticket_service._get_ticket(ref.ticket_id)
            if ticket_obj is not None:
                await HandoffService(self.ticket_service.db).create_offer(ticket_obj)
                await self.ticket_service.db.commit()
        except Exception:
            logger.warning("handoff_offer_create_failed", ticket_id=str(ref.ticket_id))
```

> Confirm `TicketService` exposes `_get_ticket` and `.db` (the map shows `svc.db.commit()` is used in `_persist_and_queue`, so `.db` exists). If `_get_ticket` is private/unavailable, `await self.ticket_service.db.get(Ticket, ref.ticket_id)`.

- [ ] **Step 5: Compute `handoff_state` in `get_waiting_status`**

In `get_waiting_status`, after computing `waited_seconds`/`specialist_available`, derive `handoff_state`:

```python
        handoff_state = "connecting"
        if session and session.ticket:
            from app.services.specialist_handoff_service import HandoffService
            from app.services.specialist_chat_service import SpecialistChatService

            ticket_id = uuid.UUID(session.ticket["ticket_id"])
            live = await SpecialistChatService(self.ticket_service.db).get_active_for_participant(
                requester.id
            )
            if live is not None:
                handoff_state = "connected"
            else:
                offer = await HandoffService(self.ticket_service.db).active_offer_for(ticket_id)
                if offer is None:
                    handoff_state = "fallback" if not specialist_available else "busy"
                elif offer.state == "broadened":
                    handoff_state = "busy"
                else:
                    handoff_state = "connecting"
```

Then include `handoff_state=handoff_state` in the returned `WaitingStatusResponse(...)`. Keep `specialist_available` as-is.

> `requester` is the owner; the method already loads the session by owner. Use the user id available in that scope (the map shows `get_waiting_status` reads `session.waiting_since`; thread the caller's user id — the endpoint passes it). If the current signature doesn't have the user, use the session's `user_id`.

- [ ] **Step 6: Run test + targeted regression**

Run:
```bash
docker compose exec -T backend uv run pytest tests/unit/test_chat_handoff_wiring.py -q
docker compose exec -T backend uv run pytest tests/unit/ -k "chat or waiting" -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agents/chat_service.py backend/app/schemas/chat.py \
        backend/tests/unit/test_chat_handoff_wiring.py
git commit -m "feat(handoff): create offer on live-agent request; expose handoff_state in waiting-status"
```

---

## Task 10: Data cleanup script for stale pre-fix handoffs

**Files:**
- Create: `backend/scripts/cleanup_stale_handoffs.py`
- Test: manual run (idempotent, read-then-write); no unit test required (one-off maintenance), but guard with a dry-run default.

**Interfaces:**
- Produces: `python -m scripts.cleanup_stale_handoffs [--apply]` — lists (dry-run) or resolves abandoned `source=chat` "Live support request" tickets older than `LIVE_HANDOFF_FALLBACK_SECONDS` with no active `specialist_chat_session`, setting them to a non-queue terminal state and logging counts.

- [ ] **Step 1: Write the script**

```python
# backend/scripts/cleanup_stale_handoffs.py
"""Close abandoned pre-fix live-support tickets so the queue reflects reality.

A ticket qualifies when: source='chat', title starts with 'Live support request',
status still in the queue window, no active specialist_chat_session, and older than
the fallback window. Dry-run by default; pass --apply to mutate.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.specialist_chat import SpecialistChatSession
from app.models.ticket import Ticket


async def _run(apply: bool) -> dict:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.LIVE_HANDOFF_FALLBACK_SECONDS)
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
            print(f"  {t.ticket_number}  status={t.status}  created={t.created_at}")
            if apply:
                t.status = "waiting_for_user"  # out of the live queue; visible for async follow-up
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
```

> `waiting_for_user` keeps the ticket alive for async follow-up but drops it out of the "waiting for a live specialist" chime set (which keys on `waiting_state=='waiting'`). Confirm `_QUEUE_STATUSES` still includes it — if you want it fully out of `list_queue`, use a status not in `_QUEUE_STATUSES` (the queue map lists `waiting_for_user` as in-queue, so if the goal is to fully clear the queue, set `status='closed'` with a resolution note instead). Pick per intent; default here keeps them recoverable.

- [ ] **Step 2: Dry-run**

Run: `docker compose exec -T backend uv run python -m scripts.cleanup_stale_handoffs`
Expected: prints the count (~39) and lists them; no mutation.

- [ ] **Step 3: Apply**

Run: `docker compose exec -T backend uv run python -m scripts.cleanup_stale_handoffs --apply`
Expected: "Applied: moved N ticket(s)". Re-running dry-run shows 0.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/cleanup_stale_handoffs.py
git commit -m "chore(handoff): maintenance script to clear stale pre-fix handoff tickets"
```

---

## Task 11: Frontend — presence toggle + heartbeat + offers (LiveQueuePage)

**Files:**
- Modify: `frontend/src/features/specialist-chat/api.ts` (types + `queueApi` methods)
- Modify: `frontend/src/pages/operations/LiveQueuePage.tsx`
- Test: `frontend/src/features/specialist-chat/presence.test.tsx`

**Interfaces:**
- Consumes: backend routes from Task 8.
- Produces on `queueApi`:
  - `getAvailability(): Promise<Presence>`
  - `setAvailability(status: 'available' | 'away'): Promise<Presence>`
  - `heartbeat(): Promise<Presence>`
  - `myOffers(): Promise<Offer[]>`
  - `acceptOffer(ticketId: string): Promise<ClaimResponse>`
- Types: `Presence { user_id: string; status: 'available' | 'away'; last_heartbeat_at: string | null; is_available: boolean }`, `Offer { ticket_id; ticket_number; offered_at; expires_at; round_index; state; summary: HandoffSummary }`.

- [ ] **Step 1: Add types + client methods**

In `frontend/src/features/specialist-chat/api.ts`, add the types (near `QueueEntry`) and methods to the `queueApi` object:

```typescript
export interface Presence {
  user_id: string;
  status: 'available' | 'away';
  last_heartbeat_at: string | null;
  is_available: boolean;
}

export interface Offer {
  ticket_id: string;
  ticket_number: string;
  offered_at: string;
  expires_at: string;
  round_index: number;
  state: string;
  summary: HandoffSummary;
}
```

Add to `queueApi`:

```typescript
  getAvailability: () => apiRequest<Presence>('/specialist-queue/availability'),
  setAvailability: (status: 'available' | 'away') =>
    apiRequest<Presence>('/specialist-queue/availability', { method: 'PUT', body: { status } }),
  heartbeat: () =>
    apiRequest<Presence>('/specialist-queue/availability/heartbeat', { method: 'POST' }),
  myOffers: () => apiRequest<Offer[]>('/specialist-queue/offers/mine'),
  acceptOffer: (ticketId: string) =>
    apiRequest<ClaimResponse>(`/specialist-queue/offers/${ticketId}/accept`, { method: 'POST' }),
```

- [ ] **Step 2: Write the failing component test**

```tsx
// frontend/src/features/specialist-chat/presence.test.tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { queueApi } from './api';
import { AvailabilityToggle } from './AvailabilityToggle';

describe('AvailabilityToggle', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('shows current status and flips on click', async () => {
    vi.spyOn(queueApi, 'getAvailability').mockResolvedValue({
      user_id: 'u1', status: 'away', last_heartbeat_at: null, is_available: false,
    });
    const setSpy = vi.spyOn(queueApi, 'setAvailability').mockResolvedValue({
      user_id: 'u1', status: 'available', last_heartbeat_at: 't', is_available: true,
    });
    render(<AvailabilityToggle />);
    await waitFor(() => expect(screen.getByText(/away/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /go available|available/i }));
    await waitFor(() => expect(setSpy).toHaveBeenCalledWith('available'));
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/specialist-chat/presence.test.tsx`
Expected: FAIL — `AvailabilityToggle` module missing.

- [ ] **Step 4: Create `AvailabilityToggle` component**

```tsx
// frontend/src/features/specialist-chat/AvailabilityToggle.tsx
import { useEffect, useRef, useState } from 'react';
import { queueApi, type Presence } from './api';

const HEARTBEAT_MS = 20000;

export function AvailabilityToggle() {
  const [presence, setPresence] = useState<Presence | null>(null);
  const available = presence?.status === 'available';
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    queueApi.getAvailability().then(setPresence).catch(() => {});
  }, []);

  useEffect(() => {
    if (!available) {
      if (timer.current) clearInterval(timer.current);
      return;
    }
    timer.current = setInterval(() => {
      queueApi.heartbeat().then(setPresence).catch(() => {});
    }, HEARTBEAT_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [available]);

  const toggle = async () => {
    const next = available ? 'away' : 'available';
    try {
      setPresence(await queueApi.setAvailability(next));
    } catch {
      /* non-critical */
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={`rounded-md px-3 py-1.5 text-sm font-medium ${
        available ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
      }`}
      aria-label={available ? 'Go away' : 'Go available'}
    >
      {available ? '● Available' : '○ Away'}
    </button>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/features/specialist-chat/presence.test.tsx`
Expected: PASS.

- [ ] **Step 6: Mount toggle + offers in LiveQueuePage**

In `frontend/src/pages/operations/LiveQueuePage.tsx`, import `AvailabilityToggle` and render it in the header flex row (the `<div className="flex items-center gap-2">` at ~line 137), before the Sound toggle:

```tsx
import { AvailabilityToggle } from '@/features/specialist-chat/AvailabilityToggle';
// ...
<AvailabilityToggle />
```

Add an offers strip above the queue table: a `useState<Offer[]>` polled via `queueApi.myOffers()` in the existing `load`/interval (reuse the 15s loop — add `queueApi.myOffers()` to the same `load`), and for each offer render an "Offered to you — Accept / Pass" card whose Accept calls `queueApi.acceptOffer(ticket_id)` then `navigate('/operations/live-chat/' + res.live_session_id)`. Follow the existing `onClaim` error handling (catch `ApiError` 409 → inline banner + reload).

> The exact `ClaimResponse` field for the started session id is what `accept_offer` returns (Task 8 `_claim_response`). Ensure it includes `live_session_id` (mirror what `liveChatApi.start` returns / what `onClaim` uses to navigate). If `accept_offer` returns the session under a different key, align the type.

- [ ] **Step 7: Lint + typecheck + test**

Run:
```bash
cd frontend && npm run lint && npx tsc --noEmit && npx vitest run src/features/specialist-chat/presence.test.tsx
```
Expected: clean; test PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/specialist-chat/api.ts \
        frontend/src/features/specialist-chat/AvailabilityToggle.tsx \
        frontend/src/features/specialist-chat/presence.test.tsx \
        frontend/src/pages/operations/LiveQueuePage.tsx
git commit -m "feat(handoff): specialist Available/Away toggle + offer accept in LiveQueuePage"
```

---

## Task 12: Frontend — employee waiting states (connecting / busy / fallback)

**Files:**
- Modify: `frontend/src/features/specialist-chat/api.ts` (extend the waiting-status type — actually `chatApi.getWaitingStatus` lives in `frontend/src/lib/api.ts`; extend its return type there)
- Modify: `frontend/src/pages/employee/SupportChatPage.tsx`
- Test: `frontend/src/pages/employee/SupportChatWaiting.test.tsx`

**Interfaces:**
- Consumes: `handoff_state` from `GET /chat/waiting-status/{id}` (Task 9).
- Produces: waiting banner text driven by `handoff_state`:
  - `connecting` → "Connecting you to a live IT specialist…"
  - `busy` → "Our IT specialists are busy at the moment — someone may join your chat shortly. Hang tight."
  - `connected` → handled by the existing `/specialist-chat/active` path (emerald "joined" banner).
  - `fallback` → the existing unavailable message ("No specialist is free right now — I've logged ticket … and the team will follow up").

- [ ] **Step 1: Extend the waiting-status type**

In `frontend/src/lib/api.ts`, find the `getWaitingStatus` return type (the `WaitingStatus`/inline type used by `chatApi.getWaitingStatus`) and add:

```typescript
  handoff_state?: 'connecting' | 'busy' | 'connected' | 'fallback';
```

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/src/pages/employee/SupportChatWaiting.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WaitingBanner } from './WaitingBanner';

describe('WaitingBanner', () => {
  it('shows busy message when handoff_state=busy', () => {
    render(<WaitingBanner handoffState="busy" onCancel={() => {}} />);
    expect(screen.getByText(/busy at the moment/i)).toBeInTheDocument();
  });

  it('shows fallback message when handoff_state=fallback', () => {
    render(<WaitingBanner handoffState="fallback" onCancel={() => {}} />);
    expect(screen.getByText(/logged|follow up/i)).toBeInTheDocument();
  });

  it('shows connecting message by default', () => {
    render(<WaitingBanner handoffState="connecting" onCancel={() => {}} />);
    expect(screen.getByText(/connecting you/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/employee/SupportChatWaiting.test.tsx`
Expected: FAIL — `WaitingBanner` missing.

- [ ] **Step 4: Extract a `WaitingBanner` component**

Extract the amber waiting banner JSX from `SupportChatPage.tsx` (~lines 546-583) into a small presentational component so it's testable:

```tsx
// frontend/src/pages/employee/WaitingBanner.tsx
type HandoffState = 'connecting' | 'busy' | 'connected' | 'fallback';

const MESSAGES: Record<HandoffState, string> = {
  connecting: 'Connecting you to a live IT specialist…',
  busy: 'Our IT specialists are busy at the moment — someone may join your chat shortly. Hang tight.',
  connected: 'An IT specialist has joined.',
  fallback:
    "No specialist is free right now — I've logged your ticket and the team will follow up. You can keep chatting with me in the meantime.",
};

export function WaitingBanner({
  handoffState,
  onCancel,
}: {
  handoffState: HandoffState;
  onCancel: () => void;
}) {
  const terminal = handoffState === 'fallback';
  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {!terminal && (
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
      )}
      <span className="flex-1">{MESSAGES[handoffState]}</span>
      {!terminal && (
        <button type="button" onClick={onCancel} className="text-amber-700 underline">
          Cancel
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Use it in SupportChatPage**

In `SupportChatPage.tsx`: track `handoffState` from the `getWaitingStatus` poll (line ~291-319) — set it from `status.handoff_state ?? 'connecting'`. When `handoff_state === 'fallback'`, keep the existing `specialistUnavailable` behavior (stop implying imminent connection). Replace the inline amber banner (546-583) with `<WaitingBanner handoffState={handoffState} onCancel={cancelWaiting} />`, rendered whenever `waitingForSpecialist && !liveSession`.

> Keep the existing `/specialist-chat/active` 5s poll that flips to the emerald "joined" banner — that path already handles `connected`. `WaitingBanner` covers connecting/busy/fallback only.

- [ ] **Step 6: Run test + lint + typecheck**

Run:
```bash
cd frontend && npx vitest run src/pages/employee/SupportChatWaiting.test.tsx && npm run lint && npx tsc --noEmit
```
Expected: PASS; clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/pages/employee/WaitingBanner.tsx \
        frontend/src/pages/employee/SupportChatWaiting.test.tsx \
        frontend/src/pages/employee/SupportChatPage.tsx
git commit -m "feat(handoff): employee waiting banner reflects connecting/busy/fallback"
```

---

## Task 13: End-to-end verification (manual, in Docker)

**Files:** none (verification only).

- [ ] **Step 1: Rebuild + migrate**

```bash
docker compose up --build -d
docker compose exec -T backend uv run alembic upgrade head
```

- [ ] **Step 2: Backend suite + lint**

```bash
docker compose exec -T backend uv run pytest tests/unit tests/api -q
docker compose exec -T backend uv run ruff check . && docker compose exec -T backend uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 3: Drive the two-actor flow (browser or curl)**

1. Log in as IT Lead (sagar) → `/operations/queue` → set **Available**.
2. Log in as employee (naresh) in another browser → Support Chat → escalate to a specialist ("talk to a specialist").
3. Confirm the specialist sees an **offer** card and the employee sees "Connecting…".
4. Specialist clicks **Accept** → employee flips to "An IT specialist has joined" in the same window; both can chat.
5. Repeat but have the specialist **ignore** the offer → after ~30s it re-offers, then broadens; with nobody accepting for ~2 min the employee sees the **fallback** message and the spinner stops.
6. Repeat with the specialist set **Away** before escalation → employee should reach fallback (no infinite wait).

- [ ] **Step 4: Confirm DB state**

```bash
docker compose exec -T postgres psql -U aditi -d aditi_assist -c \
 "select state, count(*) from live_handoff_offers group by state;"
docker compose exec -T postgres psql -U aditi -d aditi_assist -c \
 "select status, count(*) from specialist_availability group by status;"
```
Expected: offers reach terminal states; availability rows exist.

- [ ] **Step 5: Commit any doc/verification notes** (if applicable), then finish per the finishing-a-development-branch skill.

---

## Self-Review Notes (author checklist — completed)

- **Spec coverage:** §3.1 presence → Tasks 2,3,8,11. §3.2 routing → Task 4. §3.3 offer lifecycle + sweeper → Tasks 2,5,6,7. §3.4 frontend → Tasks 11,12. §3.5 cleanup → Task 10. §4 error handling → best-effort try/except in Tasks 6,7,9. §5 testing → each task's TDD steps. §6 config → Task 1. §7 migration/rollout → Task 2 + Task 13.
- **Type consistency:** `rank_candidates`/`decide_next`/`is_available`/`create_offer`/`accept`/`advance_once` signatures are identical across the tasks that define and consume them. Offer states (`offered/accepted/expired/broadened/fallback`) and availability states (`available/away`) are consistent between model, migration, service, and DTOs. `handoff_state` literals (`connecting/busy/connected/fallback`) match between backend schema (Task 9), frontend type (Task 12), and `WaitingBanner`.
- **Known integration risks flagged inline for the implementer:** exact test-fixture names (Tasks 6, 8), `TicketService._get_ticket`/`.db` availability (Task 9), `ClaimResponse` session-id field name (Tasks 8, 11), and `WaitingStatusResponse` required fields (Task 9). Each carries a `>` note to verify against the real code before asserting.
