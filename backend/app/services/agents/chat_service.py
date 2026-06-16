"""Chat service — orchestrates the support conversation flow."""

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.core.logging import get_logger
from app.schemas.chat import ChatMessageResponse, QuickReplyOption, ResolutionStepSchema

logger = get_logger(__name__)

# In-memory session store (dev/single-server; production → Redis or DB)
_sessions: dict[str, dict] = {}


class ChatService:
    """Service for managing support chat sessions.

    Orchestrates the LangGraph workflow invocation, maintains session
    continuity across multiple turns, and formats responses for the API layer.
    """

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        user_id: str = "dev-user",
    ) -> ChatMessageResponse:
        """Process a user message through the agent workflow.

        Args:
            session_id: Support session identifier
            user_message: The user's message text
            user_id: The authenticated user's ID

        Returns:
            ChatMessageResponse with AI response and metadata
        """
        logger.info(
            "process_message",
            session_id=session_id,
            message_length=len(user_message),
        )

        try:
            result = await self._invoke_workflow(session_id, user_message, user_id)
            return self._format_response(session_id, result)
        except Exception as e:
            logger.error("process_message_error", error=str(e), session_id=session_id)
            return self._error_response(session_id)

    async def _invoke_workflow(
        self,
        session_id: str,
        user_message: str,
        user_id: str,
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
            was_clarification_turn = state.get("needs_clarification", False)
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
            state["resolution_steps"] = []
            state["resolution_confidence"] = 0.0
            state["should_escalate"] = False
            state["escalation_reason"] = None
            state["ticket_draft"] = None
            state["ticket_created"] = False
        else:
            state = {
                "messages": [HumanMessage(content=user_message)],
                "session_id": session_id,
                "user_id": user_id,
                "issue_category": None,
                "issue_subcategory": None,
                "severity": None,
                "urgency": None,
                "impact": None,
                "knowledge_results": [],
                "knowledge_confidence": 0.0,
                "knowledge_citations": [],
                "knowledge_published_only": True,
                "resolution_steps": [],
                "resolution_confidence": 0.0,
                "steps_attempted": [],
                "should_escalate": False,
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

        # Persist session state for future turns
        _sessions[session_id] = result

        return result

    def _format_response(self, session_id: str, result: dict) -> ChatMessageResponse:
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

        return ChatMessageResponse(
            session_id=session_id,
            message_id=str(uuid4()),
            content=content,
            confidence_score=result.get("resolution_confidence", 0),
            issue_category=result.get("issue_category"),
            resolution_steps=steps,
            requires_escalation=result.get("should_escalate", False),
            follow_up_question=result.get("clarification_question"),
            quick_replies=quick_replies,
            conversation_phase=result.get("conversation_phase"),
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
def get_chat_service() -> ChatService:
    """Create a ChatService instance."""
    return ChatService()

