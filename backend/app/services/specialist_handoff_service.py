"""Live-handoff offer lifecycle: routing + decision (pure) and the DB service.

Pure functions (`rank_candidates`, `decide_next`) hold all the policy and are
unit-tested without I/O. `HandoffService` applies them against the DB and is
driven by both the escalation path (create the first offer) and the periodic
sweeper (advance expired offers).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.live_handoff import LiveHandoffOffer
from app.models.ticket import Ticket
from app.services.specialist_presence_service import PresenceService

if TYPE_CHECKING:
    import uuid

logger = get_logger(__name__)

_ACTIVE_OFFER_STATES = ("offered", "broadened")


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


class HandoffService:
    """DB-backed offer lifecycle: create the first targeted offer, accept it on
    claim, and advance active offers on each sweeper pass. Does not commit —
    callers own the transaction (escalation path / sweeper wrapper).
    """

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

    async def _latest_offer_for(self, ticket_id: uuid.UUID) -> LiveHandoffOffer | None:
        stmt = (
            select(LiveHandoffOffer)
            .where(LiveHandoffOffer.ticket_id == ticket_id)
            .order_by(LiveHandoffOffer.offered_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def accept(self, ticket_id: uuid.UUID, *, specialist) -> LiveHandoffOffer:
        offer = await self.active_offer_for(ticket_id)
        if offer is not None:
            offer.state = "accepted"
            offer.offered_to = specialist.id
            await self.db.flush()
            return offer
        # No active offer — check whether this is a repeat call by the specialist
        # who already accepted (idempotent), vs. a genuine conflict/missing offer.
        latest = await self._latest_offer_for(ticket_id)
        if latest is not None and latest.state == "accepted" and latest.offered_to == specialist.id:
            return latest
        raise PermissionError("No active handoff offer for this ticket")

    async def advance_once(self, *, now: datetime | None = None) -> dict[str, int]:
        ts = now or datetime.now(UTC)
        counts = {"reoffered": 0, "broadened": 0, "fallback": 0, "held": 0, "terminalized": 0}
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
                # Claimed/accepted already → terminalize. This MUST be counted:
                # the sweeper wrapper only commits when a non-"held" counter is
                # non-zero, so an uncounted mutation here is rolled back every
                # pass and the offer stays "offered" forever — surfacing a
                # phantom offer for an already-claimed ticket.
                offer.state = "accepted"
                counts["terminalized"] += 1
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
