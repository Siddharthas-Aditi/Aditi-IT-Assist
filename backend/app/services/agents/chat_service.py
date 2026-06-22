"""Chat service — orchestrates the support conversation flow."""

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.agents.intent_classifier import ConversationIntent
from app.services.agents.llm_intent import classify_intent_with_llm
from app.services.llm_service import get_llm_service
from app.services.ticket_service import TicketService

logger = get_logger(__name__)

# In-memory session store (dev/single-server; production → Redis or DB)
_sessions: dict[str, dict] = {}

# Idempotency map: session_id → created ticket reference (dict form of TicketRef).
# Ensures multi-turn escalation / repeated "Connect" clicks reuse one ticket
# instead of spawning duplicates. Production: persist alongside the session.
_session_tickets: dict[str, dict] = {}


class ChatService:
    """Service for managing support chat sessions.

    Orchestrates the LangGraph workflow invocation, maintains session
    continuity across multiple turns, and formats responses for the API layer.

    Ticket persistence and live-agent handoff happen HERE (the service layer),
    not in the workflow nodes — nodes stay side-effect free and only prepare a
    ticket *draft*. A real ticket is created only on explicit user confirmation.
    """

    def __init__(self, ticket_service: TicketService | None = None) -> None:
        # Optional so workflow-only/unit contexts can run without a DB; ticket
        # creation simply degrades to "offer only" when no ticket_service.
        self.ticket_service = ticket_service

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
            result = await self._invoke_workflow(
                session_id, user_message, user_id,
                user_name=user_name, user_email=user_email,
            )
            ticket_ref = await self._handle_ticketing(session_id, result, requester)
            return self._format_response(
                session_id, result, ticket_ref=ticket_ref, include_debug=include_debug
            )
        except Exception as e:
            logger.error("process_message_error", error=str(e), session_id=session_id)
            return self._error_response(session_id)

    async def _invoke_workflow(
        self,
        session_id: str,
        user_message: str,
        user_id: str,
        *,
        user_name: str | None = None,
        user_email: str | None = None,
    ) -> dict:
        """Invoke the LangGraph workflow with session continuity.

        If the session already exists, resumes with accumulated messages
        and state. Otherwise, creates a fresh session.
        """
        from app.workflows.graph import build_support_workflow

        # Resume existing session or create new one
        if session_id in _sessions:
            state = _sessions[session_id]
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
                    summary = await summarizer.summarize(diagnostic_context)
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

        # Persist session state for future turns
        _sessions[session_id] = result

        # If the workflow detected a NEW_TOPIC this turn (triage reset the
        # diagnostic context), drop the session's cached ticket reference.
        # The OLD ticket remains in the database; the cache is only for
        # idempotency of the *current* escalation flow. The new issue, if it
        # ever escalates, gets its own ticket.
        diag = result.get("diagnostic_context") or {}
        if diag.get("last_response_type") == "new_topic":
            _session_tickets.pop(session_id, None)
            logger.info("session_ticket_cache_cleared_on_new_topic",
                        session_id=session_id)

        return result

    def _format_response(
        self,
        session_id: str,
        result: dict,
        *,
        ticket_ref: TicketRef | None = None,
        include_debug: bool = False,
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
            content = (
                f"✅ I've created ticket **{ticket_ref.ticket_number}** and handed it to "
                f"our IT specialists. They have the full context of our conversation and "
                f"the steps we tried, and will follow up with you directly.\n\n"
                f"Is there anything else I can help you with in the meantime?"
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
                QuickReplyOption(label=r["label"], value=r["value"])
                for r in raw_replies
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
            follow_up_question=result.get("clarification_question"),
            quick_replies=quick_replies,
            conversation_phase=result.get("conversation_phase"),
            resolved=bool(result.get("issue_resolved")),
            debug=debug,
        )

    # ── Ticketing / live-agent handoff ───────────────────────────────

    async def _handle_ticketing(
        self, session_id: str, result: dict, requester: User | None
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
        existing = _session_tickets.get(session_id)
        wants_escalation_this_turn = bool(
            result.get("escalation_confirmed")
            or (
                (result.get("diagnostic_context") or {}).get("live_agent_requested")
            )
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
                session_id=session_id,
                reason="last user message did not classify as CONFIRM/ESCALATE_REQUEST",
            )
            return None

        draft = result.get("ticket_draft")
        if not (draft and self.ticket_service and requester):
            # Confirmed but we can't persist (no DB/user) — degrade to offer.
            return None

        return await self._persist_and_queue(session_id, draft, requester)

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
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
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
    ) -> tuple[str, TicketRef]:
        """Explicit 'Connect with a specialist' action from the UI.

        Guarantees the ticket-before-handoff invariant: ensures a ticket exists
        (creating one from the session's drafted context, or a minimal draft if
        none), queues it for a human, and returns a confirmation message + ref.
        Idempotent: repeated clicks reuse the same ticket.
        """
        if self.ticket_service is None:
            raise ValueError("Live-agent handoff is unavailable (no ticket backend).")

        existing = _session_tickets.get(session_id)
        if existing:
            ref = TicketRef(**existing)
            return (
                f"You're already in the queue — ticket **{ref.ticket_number}** is with "
                f"our IT specialists and they'll follow up shortly.",
                ref,
            )

        state = _sessions.get(session_id) or {}
        draft = state.get("ticket_draft") or self._minimal_draft(state, requester)
        ref = await self._persist_and_queue(session_id, draft, requester)
        return (
            f"✅ I've created ticket **{ref.ticket_number}** and connected it to our IT "
            f"specialists. They'll review the conversation and follow up with you directly.",
            ref,
        )

    async def _persist_and_queue(
        self, session_id: str, draft: dict, requester: User
    ) -> TicketRef:
        """Create the ticket from a draft and queue it for a live agent."""
        svc = self.ticket_service
        assert svc is not None  # guarded by callers

        # NOTE: chat sessions are currently in-memory only (no `chat_sessions`
        # row), so we must NOT set ticket.session_id — it's an FK to a persisted
        # session and would violate the constraint. The conversation context is
        # captured in the description/ai_summary instead. (When chat sessions are
        # persisted, pass `session_id=_coerce_uuid(session_id)` here.)
        ticket = await svc.create_ticket(
            requester=requester,
            title=draft.get("title") or "IT Support Request",
            description=draft.get("description") or "Escalated from support chat.",
            priority=draft.get("priority", "medium"),
            category=draft.get("category"),
            source="chat",
            ai_summary=draft.get("problem_statement") or draft.get("conversation_summary"),
        )
        # Ticket-before-handoff: create first, THEN queue for a human.
        await svc.request_live_agent(ticket.id, requester)
        await svc.db.commit()

        ref = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
            "priority": ticket.priority,
            "live_agent_requested": True,
        }
        _session_tickets[session_id] = ref
        logger.info(
            "chat_ticket_created",
            session_id=session_id,
            ticket_number=ticket.ticket_number,
        )
        return TicketRef(**ref)

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
    tickets can be persisted). Callable bare in tests/non-DB contexts, where it
    degrades to offer-only escalation.
    """
    return ChatService(TicketService(db) if db is not None else None)

