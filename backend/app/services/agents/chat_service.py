"""Chat service — orchestrates the support conversation flow."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.auth import User
from app.schemas.chat import (
    ChatDebugInfo,
    ChatMessageResponse,
    QuickReplyOption,
    ResolutionStepSchema,
    TicketRef,
)
from app.services.agents.context_summarizer import ContextSummarizerService
from app.services.agents.conversation_messages import generate_ticket_created
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.escalation_policy import (
    GATHER_PROBLEM_PROMPT,
    handoff_context_sufficient,
)
from app.services.agents.intent_classifier import ConversationIntent
from app.services.agents.llm_intent import classify_intent_with_llm
from app.services.agents.registry import AGENT_REGISTRY, find_specialist_for
from app.services.agents.session_store import ChatSession, get_session_store
from app.services.llm_service import get_llm_service
from app.services.support_session_service import SupportSessionService
from app.services.ticket_service import TicketService

if TYPE_CHECKING:
    from app.schemas.chat import SessionDetail, SessionSummary, WaitingStatusResponse

logger = get_logger(__name__)


class SessionOwnershipError(PermissionError):
    """Raised when a caller references a chat session they do not own (IDOR)."""


# Session state, the created-ticket idempotency record, and the waiting-start
# timestamp all live in the SessionStore now (see session_store.py) — bound to
# the owning user, bounded/TTL'd, and Redis-durable when configured. The old
# process-local dicts were an IDOR + memory-leak + multi-worker liability.

# After this many seconds of waiting without a specialist joining, we surface
# a fallback message offering async ticket/email resolution. Bound from the
# shared freshness knob (LIVE_WAIT_TIMEOUT_SECONDS) so the employee-side
# fallback and the specialist queue's waiting_state
# (specialist_queue_service.waiting_info) can never disagree.
WAIT_TIMEOUT_SECONDS: int = settings.LIVE_WAIT_TIMEOUT_SECONDS  # default 15 min


class ChatService:
    """Service for managing support chat sessions.

    Orchestrates the LangGraph workflow invocation, maintains session
    continuity across multiple turns, and formats responses for the API layer.

    Ticket persistence and live-agent handoff happen HERE (the service layer),
    not in the workflow nodes — nodes stay side-effect free and only prepare a
    ticket *draft*. A real ticket is created only on explicit user confirmation.
    """

    def __init__(
        self,
        ticket_service: TicketService | None = None,
        support_session_service: SupportSessionService | None = None,
    ) -> None:
        # Optional so workflow-only/unit contexts can run without a DB; ticket
        # creation simply degrades to "offer only" when no ticket_service.
        self.ticket_service = ticket_service
        self.support_session_service = support_session_service
        self._store = get_session_store()

    async def _load_owned(self, session_id: str, user_id: str | None) -> ChatSession | None:
        """Load a session, enforcing ownership.

        Returns None when the session doesn't exist yet. Raises
        :class:`SessionOwnershipError` when it exists but belongs to a
        different user — this both prevents reading another user's
        conversation (disclosure) and prevents clobbering it (a fresh turn
        under the same id). uuid4 session ids make collisions astronomically
        unlikely; this closes the deliberate-guess (IDOR) path.
        """
        session = await self._store.load(session_id)
        if session is None:
            return None
        if user_id and session.user_id and session.user_id != user_id:
            logger.warning(
                "chat_session_ownership_denied",
                session_id=session_id,
                owner=session.user_id,
                requester=user_id,
            )
            raise SessionOwnershipError("Session does not belong to the requesting user")
        return session

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        user_id: str = "dev-user",
        *,
        user_name: str | None = None,
        user_email: str | None = None,
        requester: User | None = None,
        include_debug: bool = False,
    ) -> ChatMessageResponse:
        """Process a user message through the agent workflow.

        Args:
            session_id: Support session identifier
            user_message: The user's message text
            user_id: The authenticated user's ID
            include_debug: Attach the developer trace (IT/admin roles only).

        Returns:
            ChatMessageResponse with AI response and metadata
        """
        logger.info(
            "process_message",
            session_id=session_id,
            message_length=len(user_message),
        )

        try:
            session = await self._load_owned(session_id, user_id)
            if session is None:
                session = ChatSession(user_id=user_id, state={})
            result = await self._invoke_workflow(
                session_id,
                session,
                user_message,
                user_id,
                user_name=user_name,
                user_email=user_email,
            )
            ticket_ref = await self._handle_ticketing(session, result, requester)
            # Persist the whole envelope (state + ticket idempotency) once the
            # turn succeeded — never mid-turn (a failed ainvoke must not leave a
            # half-updated session behind for the next turn).
            session.state = result
            await self._store.save(session_id, session)
            ticket_created_message = None
            if ticket_ref is not None:
                diag_ctx = DiagnosticContext.from_dict(result.get("diagnostic_context") or {})
                ticket_created_message = await generate_ticket_created(
                    ticket_ref.ticket_number, diag_ctx
                )
            response = self._format_response(
                session_id,
                result,
                ticket_ref=ticket_ref,
                include_debug=include_debug,
                ticket_created_message=ticket_created_message,
            )
            await self._persist_support_session_turn(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                response=response,
                state=result,
                envelope=session,
            )
            return response
        except SessionOwnershipError:
            # Don't disclose that the session exists — same generic error.
            return self._error_response(session_id)
        except Exception as e:
            logger.error("process_message_error", error=str(e), session_id=session_id)
            return self._error_response(session_id)

    async def _invoke_workflow(
        self,
        session_id: str,
        session: ChatSession,
        user_message: str,
        user_id: str,
        *,
        user_name: str | None = None,
        user_email: str | None = None,
    ) -> dict:
        """Invoke the LangGraph workflow with session continuity.

        If the session already exists, resumes with accumulated messages
        and state. Otherwise, creates a fresh session. Does NOT persist —
        the caller saves the envelope after a successful turn.
        """
        from app.workflows.graph import build_support_workflow

        # Resume existing session or create new one
        if session.state:
            # Work on a COPY of the stored state: the caller only persists after
            # a successful ainvoke. Mutating the stored dict in place meant a
            # mid-turn workflow error left the session half-updated (message
            # appended, turn bumped, resolution fields cleared), so the NEXT turn
            # resumed from corrupted state.
            state = dict(session.state)
            # Append new human message and increment turn count
            state["messages"] = state["messages"] + [HumanMessage(content=user_message)]
            state["turn_count"] = state.get("turn_count", 0) + 1

            # ALWAYS preserve diagnostic_context and issue_category across turns.
            # Only reset them if the user is clearly starting a new topic (detected
            # by the triage node, not by the chat service).
            state["needs_clarification"] = False
            state["clarification_question"] = None
            state["quick_replies"] = None

            # NOTE: We no longer reset issue_category or diagnostic_context here.
            # The triage node handles topic-shift detection internally. Resetting
            # context here was the root cause of the "Sixth Sense" conversation
            # failure — context was lost between the first and second message.

            # Reset retrieval/resolution state for the new turn
            state["knowledge_results"] = []
            state["knowledge_confidence"] = 0.0
            state["knowledge_citations"] = []
            state["retrieval_trace"] = None
            state["resolution_steps"] = []
            state["resolution_confidence"] = 0.0
            state["confidence_breakdown"] = None
            state["should_escalate"] = False
            state["escalation_confirmed"] = False
            state["escalation_reason"] = None
            # BUGFIX #1: Do NOT reset issue_resolved here — it must persist via
            # diagnostic_context so the triage node can detect post-resolution context
            # and call reset_issue_context() for new issues. Resetting it here breaks
            # the "I have another issue" detection.
            # state["issue_resolved"] = False  ← REMOVED
            state["ticket_draft"] = None
            state["ticket_offered"] = False
            state["ticket_created"] = False
            # Start a fresh per-turn audit trail. The state channel uses an
            # `operator.add` reducer, so nodes append to this within the turn;
            # resetting here keeps it to one turn's trace (no unbounded growth
            # across a long conversation).
            state["audit_trail"] = []
        else:
            state = {
                "messages": [HumanMessage(content=user_message)],
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "issue_category": None,
                "issue_subcategory": None,
                "issue_subtype": None,
                "severity": None,
                "urgency": None,
                "impact": None,
                "knowledge_results": [],
                "knowledge_confidence": 0.0,
                "knowledge_citations": [],
                "knowledge_published_only": True,
                "retrieval_trace": None,
                "resolution_steps": [],
                "resolution_confidence": 0.0,
                "confidence_breakdown": None,
                "steps_attempted": [],
                "should_escalate": False,
                "escalation_confirmed": False,
                "ticket_offered": False,
                "escalation_reason": None,
                "handoff_summary": None,
                "ticket_draft": None,
                "ticket_created": False,
                "current_node": "start",
                "turn_count": 1,
                "needs_clarification": False,
                "clarification_question": None,
                "quick_replies": None,
                "diagnostic_context": None,
                "conversation_phase": None,
                "resolution_confirmed": None,
                "audit_trail": [],
            }

        graph = build_support_workflow()
        result = await graph.ainvoke(state)

        # NEW: Compress context every 10 turns to prevent LLM prompt bloat
        turn_count = result.get("turn_count", 0)
        summarizer = ContextSummarizerService(get_llm_service())
        if summarizer.should_summarize(turn_count):
            diagnostic_context = result.get("diagnostic_context")
            if diagnostic_context:
                try:
                    # `diagnostic_context` on the workflow state is the SERIALIZED
                    # dict (DiagnosticContext.to_dict()); the summarizer needs the
                    # object (it reads .get_filled_slots()/.issue_subtype/...).
                    # Passing the dict raised AttributeError every time, so this
                    # whole feature was silently dead. Rehydrate first, then write
                    # the summary back onto the state dict.
                    diag_obj = DiagnosticContext.from_dict(diagnostic_context)
                    summary = await summarizer.summarize(diag_obj)
                    diagnostic_context["conversation_summary"] = summary.issue_one_liner
                    logger.info(
                        "context_summarized",
                        turn_count=turn_count,
                        summary_preview=summary.issue_one_liner[:80],
                    )
                except Exception as e:
                    logger.warning(
                        "context_summarization_failed",
                        error=str(e),
                        turn_count=turn_count,
                    )

        # The caller persists the envelope (state + ticket) after this returns.

        # If the workflow detected a NEW_TOPIC this turn (triage reset the
        # diagnostic context), drop the session's cached ticket reference.
        # The OLD ticket remains in the database; the reference is only for
        # idempotency of the *current* escalation flow. The new issue, if it
        # ever escalates, gets its own ticket.
        diag = result.get("diagnostic_context") or {}
        if diag.get("last_response_type") == "new_topic" and session.ticket is not None:
            session.ticket = None
            logger.info("session_ticket_cache_cleared_on_new_topic", session_id=session_id)

        return result

    def _format_response(
        self,
        session_id: str,
        result: dict,
        *,
        ticket_ref: TicketRef | None = None,
        include_debug: bool = False,
        ticket_created_message: str | None = None,
    ) -> ChatMessageResponse:
        """Format workflow result into API response."""
        messages = result.get("messages", [])
        content = (
            "Thank you for contacting Aditi IT Support. "
            "I'm processing your request — one moment please."
        )
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) or (hasattr(msg, "type") and msg.type == "ai"):
                content = msg.content
                break

        # A ticket was just created (explicit-confirm path) → replace the interim
        # workflow message with a definitive, accurate confirmation citing the
        # real ticket number. Never claim a ticket exists unless one does.
        if ticket_ref is not None:
            content = ticket_created_message or (
                f"✅ I've created support ticket **{ticket_ref.ticket_number}** and I'm "
                f"sharing our full conversation with the IT specialist — including what you "
                f"asked, what I understood, and the steps we already tried — so they can "
                f"continue without asking you to repeat everything.\n\n"
                f"You'll stay in this chat; a specialist will pick it up shortly. Is there "
                f"anything else I can help you with in the meantime?"
            )

        steps = [
            ResolutionStepSchema(
                step_number=step.get("step_number", 0),
                instruction=step.get("instruction", ""),
                details=step.get("details"),
            )
            for step in result.get("resolution_steps", [])
        ]

        # Build quick-reply options if present
        quick_replies = None
        raw_replies = result.get("quick_replies")
        if raw_replies:
            quick_replies = [
                QuickReplyOption(label=r["label"], value=r["value"]) for r in raw_replies
            ]

        debug = self._build_debug(result) if include_debug else None

        return ChatMessageResponse(
            session_id=session_id,
            message_id=str(uuid4()),
            content=content,
            confidence_score=result.get("resolution_confidence", 0) or 0.0,
            issue_category=result.get("issue_category"),
            issue_subtype=result.get("issue_subtype"),
            resolution_steps=steps,
            # Once a ticket exists, stop prompting for escalation — show the
            # ticket instead. The "Connect" CTA is driven by escalation_offered.
            requires_escalation=bool(result.get("should_escalate")) and ticket_ref is None,
            escalation_offered=bool(result.get("ticket_offered")) and ticket_ref is None,
            ticket=ticket_ref,
            # Deduplicate: the triage node returns the confirmation question in
            # BOTH the AIMessage (→ content) and clarification_question. Only
            # surface the follow-up box when it adds new information.
            follow_up_question=(
                result.get("clarification_question")
                if result.get("clarification_question") != content
                else None
            ),
            quick_replies=quick_replies,
            conversation_phase=result.get("conversation_phase"),
            resolved=bool(result.get("issue_resolved")),
            debug=debug,
        )

    # ── Ticketing / live-agent handoff ───────────────────────────────

    async def _handle_ticketing(
        self, session: ChatSession, result: dict, requester: User | None
    ) -> TicketRef | None:
        """Create a real ticket when (and only when) escalation is confirmed.

        Idempotent per session: if a ticket already exists AND this turn ALSO
        wants to escalate (re-click of "Connect with a specialist"), the same
        ticket is returned. On turns where the workflow is NOT escalating, the
        cached ticket is NOT returned — otherwise the format-response layer
        would override every subsequent reply with the "ticket created" banner
        even when the user is asking a new question. That was the second bug
        in the ITA-000006 transcript.

        Three layers of defense against unwanted ticket creation:

        1. ``escalation_confirmed`` must be True — only the workflow's
           escalation node sets this, and only when the user's intent
           classified as ESCALATE_REQUEST or (CONFIRM + prior offer).
        2. **Belt-and-suspenders intent guard** — we independently re-classify
           the user's last message and check the offer-required rule for
           CONFIRM. See :meth:`_user_intent_authorizes_ticket`.
        3. **Per-turn caching** — once a ticket exists, we only re-surface it
           when this turn is also requesting escalation.
        """
        existing = session.ticket
        wants_escalation_this_turn = bool(
            result.get("escalation_confirmed")
            or ((result.get("diagnostic_context") or {}).get("live_agent_requested"))
        )

        # Idempotency for re-clicks: return the existing ticket only when this
        # turn is also asking to escalate. Otherwise the conversation moves on.
        if existing and wants_escalation_this_turn:
            return TicketRef(**existing)
        if existing:
            return None

        # Only persist on EXPLICIT confirmation (typed yes after offer, or
        # explicit "connect me with a specialist"). A bare escalation offer
        # must not create a ticket.
        if not result.get("escalation_confirmed"):
            return None

        # Defense in depth: re-verify the user's last message expresses an
        # escalation/confirmation intent.
        if not await self._user_intent_authorizes_ticket(result):
            logger.warning(
                "ticket_creation_blocked_by_intent_guard",
                session_id=session.state.get("session_id"),
                reason="last user message did not classify as CONFIRM/ESCALATE_REQUEST",
            )
            return None

        draft = result.get("ticket_draft")
        if not (draft and self.ticket_service and requester):
            # Confirmed but we can't persist (no DB/user) — degrade to offer.
            return None

        return await self._persist_and_queue(
            result.get("session_id"), session, draft, requester, state=result
        )

    @staticmethod
    async def _user_intent_authorizes_ticket(result: dict) -> bool:
        """Return True iff the user's last message classifies as a ticket-grant intent.

        Walks the workflow's message list, finds the most recent human turn,
        and runs the typed ConversationIntent classifier on it.

        * ``ESCALATE_REQUEST`` always authorizes — explicit human ask.
        * ``CONFIRM`` only authorizes when escalation was actually offered to
          the user in a prior turn (``escalation_offered_in_session`` on the
          diagnostic context, or ``ticket_offered`` on the current result).
          Without that prior offer, a bare "yes" can mean "yes I have this
          issue" (confirm-understanding), which must NOT spawn a ticket.
        * Everything else (NEW_TOPIC, GRATITUDE, REPEAT_OR_SIMPLIFY,
          CONTINUE, ...) blocks ticket creation.
        """
        last_user_text = ""
        for msg in reversed(result.get("messages", []) or []):
            if isinstance(msg, HumanMessage) or (hasattr(msg, "type") and msg.type == "human"):
                last_user_text = getattr(msg, "content", "") or ""
                break
        if not last_user_text:
            # No human message visible (workflow-internal call) — fall back to
            # trusting escalation_confirmed alone. This path is exercised by
            # the unit tests with synthetic state.
            return True
        intent = await classify_intent_with_llm(
            last_user_text,
            awaiting_confirmation=True,
            has_active_issue=True,
            steps_given=True,
        )
        if intent.intent is ConversationIntent.ESCALATE_REQUEST:
            return True
        if intent.intent is ConversationIntent.CONFIRM:
            diag = result.get("diagnostic_context") or {}
            return bool(
                diag.get("escalation_offered_in_session")
                or diag.get("live_agent_requested")
                or result.get("ticket_offered")
            )
        return False

    async def request_live_agent(
        self, session_id: str, requester: User
    ) -> tuple[str, TicketRef | None]:
        """Explicit 'Connect with a specialist' action from the UI.

        Guarantees the ticket-before-handoff invariant: ensures a ticket exists
        (creating one from the session's drafted context, or a minimal draft if
        none), queues it for a human, and returns a confirmation message + ref.
        Idempotent: repeated clicks reuse the same ticket.

        No-direct-connect policy (defense-in-depth): if we have a known session
        whose AI conversation never reached an escalation offer AND lacks a
        minimally-useful problem statement, we do NOT create a ticket — we ask
        the user to describe the issue first and return ``ticket=None``. The
        frontend only surfaces the "Connect" CTA after an offer, so this guard
        only trips on direct/cold API calls; it never blocks the normal flow.
        """
        if self.ticket_service is None:
            raise ValueError("Live-agent handoff is unavailable (no ticket backend).")

        try:
            session = await self._load_owned(session_id, str(requester.id))
        except SessionOwnershipError:
            # Foreign/guessed session id — never act on someone else's session.
            return (GATHER_PROBLEM_PROMPT, None)

        if session and session.ticket:
            ref = TicketRef(**session.ticket)
            return (
                f"You're already in the queue — ticket **{ref.ticket_number}** is with "
                f"our IT specialists and they'll follow up shortly.",
                ref,
            )

        state = session.state if session else {}
        if state and not self._handoff_allowed(state):
            return (GATHER_PROBLEM_PROMPT, None)

        if session is None:
            session = ChatSession(user_id=str(requester.id), state={})
        draft = state.get("ticket_draft") or self._minimal_draft(state, requester)
        ref = await self._persist_and_queue(
            session_id, session, draft, requester, state=state or None
        )
        await self._create_handoff_offer(ref.ticket_id)

        # Record the waiting start time for timeout tracking, then persist.
        session.waiting_since = datetime.now(UTC)
        await self._store.save(session_id, session)
        await self._sync_support_envelope(session_id, str(requester.id), state, session)

        # Phrase the confirmation via the LLM (same generator used by the
        # AI-first escalation path) so both routes to a ticket sound like the
        # same assistant. Falls back to byte-identical canned wording when the
        # LLM is unavailable — see conversation_messages._fallback_ticket_created.
        diag_ctx = DiagnosticContext.from_dict((state or {}).get("diagnostic_context") or {})
        confirmation = await generate_ticket_created(ref.ticket_number, diag_ctx)

        return (confirmation, ref)

    async def cancel_waiting(self, session_id: str, requester: User) -> str:
        """Cancel the user's waiting state for a live specialist.

        The ticket remains open for async follow-up, but the user is no
        longer in the active live-connection queue.
        """
        try:
            session = await self._load_owned(session_id, str(requester.id))
        except SessionOwnershipError:
            session = None

        if session is None or not session.ticket:
            return (
                "You're not currently waiting for a specialist. "
                "I'm here to help — describe your issue and I'll assist you."
            )

        session.waiting_since = None
        await self._store.save(session_id, session)
        ticket_number = session.ticket.get("ticket_number", "")
        return (
            f"I've cancelled the live connection request. Your ticket "
            f"**{ticket_number}** is still open and our team will follow up "
            f"asynchronously via email. Feel free to continue chatting with me "
            f"or describe a new issue."
        )

    async def get_waiting_status(self, session_id: str, requester: User) -> "WaitingStatusResponse":
        """Check waiting status with specialist-unavailable fallback.

        After WAIT_TIMEOUT_SECONDS (default 15 minutes), the system
        signals that no specialist is immediately available and suggests
        a ticket/email fallback path.
        """
        from app.schemas.chat import WaitingStatusResponse

        try:
            session = await self._load_owned(session_id, str(requester.id))
        except SessionOwnershipError:
            session = None

        ticket_cache = session.ticket if session else None
        waiting_start = session.waiting_since if session else None

        if not ticket_cache or not waiting_start:
            return WaitingStatusResponse(
                session_id=session_id,
                waiting=False,
                specialist_available=True,
            )

        waited_seconds = int((datetime.now(UTC) - waiting_start).total_seconds())
        specialist_available = waited_seconds < WAIT_TIMEOUT_SECONDS

        fallback_message = None
        if not specialist_available:
            fallback_message = (
                "It's been a while and no specialist is available right now. "
                f"Your ticket **{ticket_cache['ticket_number']}** is still "
                "active and our team will follow up via email. You can also "
                "try again later or continue troubleshooting with me."
            )

        handoff_state = await self._derive_handoff_state(
            ticket_cache, requester, specialist_available
        )

        return WaitingStatusResponse(
            session_id=session_id,
            waiting=True,
            ticket_number=ticket_cache.get("ticket_number"),
            waited_seconds=waited_seconds,
            specialist_available=specialist_available,
            fallback_message=fallback_message,
            handoff_state=handoff_state,
        )

    async def _derive_handoff_state(
        self, ticket_cache: dict, requester: User, specialist_available: bool
    ) -> Literal["connecting", "busy", "connected", "fallback"]:
        """Fine-grained handoff-offer state for the waiting-status poll.

        "connected" once a live specialist-chat session exists; otherwise
        derived from the active :class:`LiveHandoffOffer` (Task 6): no offer
        yet → "fallback" past the wait timeout else "busy"; "broadened"
        (offer opened to all Available specialists) → "busy"; a live targeted
        offer → "connecting". Best-effort: a DB/lookup failure degrades to the
        safe "connecting" default rather than breaking the waiting-status poll.
        """
        if self.ticket_service is None:
            return "connecting"
        try:
            ticket_uuid = uuid.UUID(ticket_cache["ticket_id"])
        except (KeyError, ValueError, TypeError):
            return "connecting"

        try:
            from app.services.specialist_chat_service import SpecialistChatService
            from app.services.specialist_handoff_service import HandoffService

            db = self.ticket_service.db
            live = await SpecialistChatService(db).get_active_for_participant(requester.id)
            if live is not None:
                return "connected"
            offer = await HandoffService(db).active_offer_for(ticket_uuid)
            if offer is None:
                return "fallback" if not specialist_available else "busy"
            if offer.state == "broadened":
                return "busy"
            return "connecting"
        except Exception:
            logger.warning(
                "handoff_state_derivation_failed",
                ticket_id=str(ticket_uuid),
                exc_info=True,
            )
            return "connecting"

    @staticmethod
    def _handoff_allowed(state: dict) -> bool:
        """Whether a known session has enough context to hand off to a human.

        Allowed when the AI already drafted/offered escalation (the only way
        the UI surfaces the CTA) OR the diagnostic context clears the shared
        handoff bar. A present ``ticket_draft`` is itself proof the workflow
        reached an offer, since only the ticketing node builds one.
        """
        diag_dict = state.get("diagnostic_context") or {}
        if (
            state.get("ticket_draft")
            or state.get("ticket_offered")
            or diag_dict.get("escalation_offered_in_session")
        ):
            return True
        diag = DiagnosticContext.from_dict(diag_dict)
        return handoff_context_sufficient(diag)

    async def _persist_and_queue(
        self,
        session_id: str,
        session: ChatSession,
        draft: dict,
        requester: User,
        *,
        state: dict | None = None,
    ) -> TicketRef:
        """Create the ticket from a draft, queue it, and snapshot escalation context.

        Linked-artifact model (see docs/architecture/chat-escalation-artifacts.md):
        a ticket is the parent operational object; the full conversation context
        is preserved in TWO immutable, linked records (transcript snapshot +
        escalation context) created here — NOT shoved into the ticket description.

        NOTE: the durable ``support_sessions`` row is synced per-turn by
        :meth:`_persist_support_session_turn`; we set ``ticket.session_id`` when
        the session id is a valid UUID. Full conversation detail for specialists
        still lives in escalation artifacts (transcript snapshot + context).
        """
        svc = self.ticket_service
        assert svc is not None  # guarded by callers

        session_uuid = None
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            session_uuid = None

        ticket = await svc.create_ticket(
            requester=requester,
            title=draft.get("title") or "IT Support Request",
            description=draft.get("description") or "Escalated from support chat.",
            priority=draft.get("priority", "medium"),
            category=draft.get("category"),
            source="chat",
            session_id=session_uuid,
            ai_summary=draft.get("problem_statement") or draft.get("conversation_summary"),
        )
        # Ticket-before-handoff: create first, THEN queue for a human.
        await svc.request_live_agent(ticket.id, requester)

        # Best-effort governed web research (B2): only for KB-insufficient
        # escalations, never for a bare "connect me with a human" request.
        # Must run before the artifacts snapshot so any findings are captured
        # in the escalation context; a failure here never blocks the ticket.
        await self._maybe_run_web_research(session_id, state)

        # Capture the immutable transcript snapshot + structured escalation
        # context BEFORE commit so all three persist atomically. Resolve the
        # session state from the caller (preferred) or the in-memory store.
        await self._create_escalation_artifacts(session_id, ticket, requester, state)

        await svc.db.commit()

        ref = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
            "priority": ticket.priority,
            "live_agent_requested": True,
        }
        # Idempotency record lives on the session envelope now (Redis-durable
        # when configured), so a restart or a second worker won't mint a
        # duplicate ticket. The caller persists the envelope.
        session.ticket = ref
        logger.info(
            "chat_ticket_created",
            session_id=session_id,
            ticket_number=ticket.ticket_number,
        )
        return TicketRef(**ref)

    async def _create_handoff_offer(self, ticket_id: str) -> None:
        """Route the freshly-queued ticket to an Available specialist.

        Best-effort: this is offer-lifecycle bookkeeping (see
        ``specialist_handoff_service.HandoffService``), not the queue itself —
        a failure here must never block the handoff. If routing is
        unavailable the ticket still sits in the claimable queue and the
        periodic sweeper drives re-offer/broaden/fallback from a cold start.
        """
        svc = self.ticket_service
        assert svc is not None  # guarded by callers
        try:
            from app.services.specialist_handoff_service import HandoffService

            ticket_obj = await svc._get_ticket(uuid.UUID(ticket_id))
            if ticket_obj is not None:
                await HandoffService(svc.db).create_offer(ticket_obj)
                await svc.db.commit()
        except Exception:
            logger.warning("handoff_offer_create_failed", ticket_id=ticket_id, exc_info=True)
            await svc.db.rollback()

    async def _maybe_run_web_research(self, session_id: str, state: dict | None) -> None:
        """Best-effort governed web research at a KB-insufficient escalation.

        Populates ``state["web_research_findings"]`` so it flows into the
        escalation context for the specialist; never raises — a failure here
        must never block the ticket/handoff already in flight (the ticket is
        created before this runs). Only triggers when a real KB attempt was
        made (steps tried, or retrieval ran) — NOT for a bare "connect me
        with a human" request with no KB attempt, which is a policy-gated
        no-op by design (see docs/architecture/chat-to-live-handoff.md).
        """
        if not state:
            return
        diag = state.get("diagnostic_context") or {}
        # KB-insufficient = a real KB attempt happened (steps tried, or KB
        # retrieval actually ran), NOT a bare "I want a human" with no attempt.
        #
        # NOTE: `state["knowledge_results"]` is seeded to `[]` at the start of
        # EVERY turn (see the turn-reset block above ~line 205 and the fresh-
        # session initializer ~line 241), so `is not None` is always True and
        # can never distinguish "retrieval ran and found nothing" from
        # "retrieval never ran this turn". `retrieval_trace` is the correct
        # signal: it is seeded `None` per turn and is ONLY ever set by
        # `retrieval_node` (see app/workflows/nodes/retrieval.py), which
        # always returns a non-empty dict (keys: kept/rejected/top_relevance/
        # has_subtype_match) — truthy even when zero articles were found. So
        # `retrieval_trace` is truthy iff retrieval actually ran this turn.
        kb_attempted = bool(
            diag.get("failed_steps")
            or diag.get("suggested_steps")
            or state.get("retrieval_trace")
            or state.get("knowledge_results")
        )
        bare_human_request = bool(diag.get("live_agent_requested")) and not kb_attempted
        if bare_human_request:
            return
        try:
            from app.services.agents.web_research import build_default_web_research_agent

            svc = self.ticket_service
            agent = build_default_web_research_agent(svc.db) if svc else None
            if agent is None:
                return
            query = diag.get("exact_problem_statement") or state.get("symptom") or ""
            if not query:
                return
            supervisor_decision = state.get("supervisor_decision") or {}
            issue_category = state.get("issue_category") or diag.get("issue_category")
            specialist_name = (
                supervisor_decision.get("specialist") or supervisor_decision.get("agent") or ""
            )
            if specialist_name not in AGENT_REGISTRY:
                # Not a routed/valid registry specialist (e.g. the caller only
                # set issue_category, or the routed name is a slash-form
                # category, not a registry name) — resolve one from the
                # category so the policy check in `agent.research()` isn't a
                # silent no-op. Still a safe no-op if nothing matches.
                resolved = find_specialist_for(category=issue_category)
                specialist_name = resolved.name if resolved else ""
            outcome = await agent.research(
                query=query,
                specialist_name=specialist_name,
                category=issue_category,
                subtype=diag.get("issue_subtype"),
                system=diag.get("normalized_system"),
                session_id=session_id,
            )
            state["web_research_findings"] = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "trust_tier": r.trust_level.value,
                    "provider": settings.WEB_SEARCH_PROVIDER,
                }
                for r in outcome.results
            ]
        except Exception as exc:  # never block handoff
            logger.warning("web_research_trigger_failed", session_id=session_id, error=str(exc))

    async def _create_escalation_artifacts(
        self,
        session_id: str,
        ticket,
        requester: User,
        state: dict | None,
    ) -> None:
        """Create the transcript snapshot + escalation context for this ticket.

        Best-effort and non-fatal: a failure here must never block ticket
        creation / handoff (the ticket already exists at this point).
        """
        svc = self.ticket_service
        if svc is None:
            return
        try:
            from app.services.escalation_service import EscalationService

            resolved_state = state
            await EscalationService(svc.db).create_escalation_artifacts(
                ticket=ticket,
                chat_session_id=session_id,
                state=resolved_state,
                requester=requester,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "escalation_artifacts_creation_failed",
                session_id=session_id,
                ticket_number=getattr(ticket, "ticket_number", None),
                error=str(exc),
            )

    @staticmethod
    def _minimal_draft(state: dict, requester: User) -> dict:
        """Build a minimal ticket draft when the session has no drafted context."""
        diag = state.get("diagnostic_context") or {}
        category = state.get("issue_category") or "other"
        problem = (
            diag.get("exact_problem_statement")
            or "Employee requested a live IT specialist from the support chat."
        )
        return {
            "title": f"Live support request - {category}",
            "description": (
                f"## Requested By\n{requester.full_name} ({requester.email})\n\n"
                f"## Problem\n{problem}"
            ),
            "category": category,
            "priority": "high",
            "problem_statement": problem,
        }

    @staticmethod
    def _build_debug(result: dict) -> ChatDebugInfo:
        """Assemble the developer trace from workflow state (IT/admin only)."""
        diag = result.get("diagnostic_context") or {}
        return ChatDebugInfo(
            normalized_system=diag.get("normalized_system"),
            issue_subtype=result.get("issue_subtype") or diag.get("issue_subtype"),
            subtype_confidence=diag.get("subtype_confidence", 0.0) or 0.0,
            conversation_phase=result.get("conversation_phase"),
            loop_counter=diag.get("loop_counter", 0) or 0,
            suggested_steps=diag.get("suggested_steps", []) or [],
            failed_steps=diag.get("failed_steps", []) or [],
            confidence_breakdown=result.get("confidence_breakdown"),
            retrieval_trace=result.get("retrieval_trace"),
            escalation_reason=result.get("escalation_reason") or diag.get("escalation_reason"),
            routed_specialist=(result.get("supervisor_decision") or {}).get("specialist")
            or (result.get("supervisor_decision") or {}).get("agent"),
            retrieval_source=(result.get("retrieval_trace") or {}).get("source"),
            citations=result.get("knowledge_citations") or [],
        )

    async def _persist_support_session_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        user_message: str,
        response: ChatMessageResponse,
        state: dict,
        envelope: ChatSession,
    ) -> None:
        """Mirror a successful chat turn into durable support_sessions/messages."""
        if self.support_session_service is None or self.ticket_service is None:
            return
        try:
            await self.support_session_service.sync_turn(
                session_id,
                user_id,
                user_message=user_message,
                assistant_message=response.content,
                assistant_message_id=response.message_id,
                state=state,
                envelope=envelope,
            )
            await self.ticket_service.db.commit()
        except Exception as exc:  # noqa: BLE001 — persistence must never break chat
            logger.warning(
                "support_session_sync_failed",
                session_id=session_id,
                error=str(exc),
            )
            await self.ticket_service.db.rollback()

    async def _sync_support_envelope(
        self,
        session_id: str,
        user_id: str,
        state: dict,
        envelope: ChatSession,
    ) -> None:
        if self.support_session_service is None or self.ticket_service is None:
            return
        try:
            await self.support_session_service.sync_envelope(
                session_id,
                user_id,
                state=state,
                envelope=envelope,
            )
            await self.ticket_service.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "support_session_envelope_sync_failed",
                session_id=session_id,
                error=str(exc),
            )
            await self.ticket_service.db.rollback()

    async def list_sessions(self, user_id: str, *, limit: int = 50) -> list["SessionSummary"]:
        """Return durable session summaries for the authenticated user."""
        if self.support_session_service is None:
            return []
        try:
            return await self.support_session_service.list_sessions(user_id, limit=limit)
        except Exception as exc:  # noqa: BLE001 — never break the list endpoint
            logger.warning("list_sessions_failed", user_id=user_id, error=str(exc))
            return []

    async def get_session_detail(self, session_id: str, user_id: str) -> "SessionDetail | None":
        """Return session detail with message history for the owner."""
        if self.support_session_service is None:
            return None
        try:
            return await self.support_session_service.get_session(session_id, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_session_detail_failed",
                session_id=session_id,
                user_id=user_id,
                error=str(exc),
            )
            return None

    def _error_response(self, session_id: str) -> ChatMessageResponse:
        """Generate error response when workflow fails."""
        return ChatMessageResponse(
            session_id=session_id,
            message_id=str(uuid4()),
            content=(
                "I apologize for the inconvenience. I'm experiencing a temporary "
                "technical issue. Please try again in a moment, or contact our IT "
                "support team directly at it-support@aditiconsulting.com for "
                "immediate assistance."
            ),
            confidence_score=0.0,
            requires_escalation=True,
        )


# Factory for dependency injection
def get_chat_service(db: AsyncSession | None = None) -> ChatService:
    """Create a ChatService instance.

    Wired in the API layer via `get_chat_service_dep` (injects a DB session so
    tickets and durable session rows can be persisted). Callable bare in
    tests/non-DB contexts, where it degrades to offer-only escalation.
    """
    if db is None:
        return ChatService()
    return ChatService(
        TicketService(db),
        SupportSessionService(db),
    )
