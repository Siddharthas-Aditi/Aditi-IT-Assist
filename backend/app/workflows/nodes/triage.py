"""Triage Agent Node - multi-turn diagnostic classification."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.agents.diagnostic_engine import (
    ClarifyOrAnswerDecision,
    evaluate_clarify_or_answer,
    extract_slots_from_message,
    update_context_from_extraction,
)
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.playbooks import get_playbook  # noqa: F401
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

ISSUE_CATEGORIES = [
    "email/outlook",
    "video-conferencing/zoom",
    "device-management/intune",
    "hardware/camera",
    "hardware/other",
    "software/other",
    "network/connectivity",
    "access/permissions",
    "other",
]

CLASSIFICATION_PROMPT = """You are a professional IT support classification specialist at Aditi Consulting.
Analyze the user's message and classify their IT issue.

Categories:
- email/outlook, video-conferencing/zoom, device-management/intune
- hardware/camera, hardware/other, software/other
- network/connectivity, access/permissions, other

Respond ONLY with valid JSON:
{{
  "category": "<category>",
  "subcategory": "<specific type or null>",
  "severity": "low|medium|high|critical",
  "urgency": "low|medium|high",
  "has_specific_symptom": true|false,
  "symptom": "<symptom or null>",
  "confidence": 0.85
}}

has_specific_symptom=true for clear problems like "not syncing emails", "no audio in Zoom".
has_specific_symptom=false for vague like "Outlook issue", "Zoom not working".

User message: {user_message}"""


async def triage_node(state: WorkflowState) -> dict:
    """Multi-turn diagnostic triage node."""
    logger.info("triage_node_start", session_id=state.get("session_id"))

    messages = state.get("messages", [])
    if not messages:
        return _welcome_message()

    user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_message = msg.content
            break

    if not user_message:
        return _welcome_message()

    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})

    if diag_ctx.issue_category is None:
        classification = await _classify_issue(user_message)
        diag_ctx.issue_category = classification.get("category")
        diag_ctx.classification_confidence = classification.get("confidence", 0.0)

        if classification.get("has_specific_symptom") and classification.get("symptom"):
            diag_ctx.symptom = classification["symptom"]
            diag_ctx.issue_subcategory = classification.get("subcategory")
            diag_ctx.exact_problem_statement = user_message

        if classification.get("subcategory"):
            diag_ctx.issue_subcategory = classification["subcategory"]
    else:
        extracted = await extract_slots_from_message(
            user_message, diag_ctx, diag_ctx.issue_category
        )
        diag_ctx = update_context_from_extraction(diag_ctx, extracted)

        if not diag_ctx.symptom and not diag_ctx.exact_problem_statement:
            diag_ctx.exact_problem_statement = user_message

    decision: ClarifyOrAnswerDecision = evaluate_clarify_or_answer(diag_ctx)

    if decision.should_clarify:
        diag_ctx.clarification_count += 1
        diag_ctx.phase = DiagnosticPhase.CLARIFYING

        quick_replies = [
            {"label": opt.label, "value": opt.value}
            for opt in decision.options
        ] if decision.options else None

        audit_entry = {
            "event": "triage.clarification_requested",
            "category": diag_ctx.issue_category,
            "reason": decision.reason,
            "clarification_count": diag_ctx.clarification_count,
        }

        return {
            "current_node": "triage",
            "issue_category": diag_ctx.issue_category,
            "issue_subcategory": diag_ctx.issue_subcategory,
            "severity": state.get("severity") or "medium",
            "urgency": state.get("urgency") or "medium",
            "needs_clarification": True,
            "clarification_question": decision.question,
            "quick_replies": quick_replies,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "messages": [AIMessage(content=decision.question)],
            "audit_trail": [audit_entry],
        }

    diag_ctx.phase = DiagnosticPhase.DIAGNOSING

    audit_entry = {
        "event": "triage.classified",
        "category": diag_ctx.issue_category,
        "subcategory": diag_ctx.issue_subcategory,
        "symptom": diag_ctx.symptom,
        "confidence": diag_ctx.classification_confidence,
        "slots_filled": list(diag_ctx.get_filled_slots().keys()),
        "clarification_rounds": diag_ctx.clarification_count,
    }

    return {
        "current_node": "triage",
        "issue_category": diag_ctx.issue_category,
        "issue_subcategory": diag_ctx.issue_subcategory,
        "severity": state.get("severity") or "medium",
        "urgency": state.get("urgency") or "medium",
        "needs_clarification": False,
        "clarification_question": None,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "audit_trail": [audit_entry],
    }


def _welcome_message() -> dict:
    """Return the initial welcome message."""
    return {
        "current_node": "triage",
        "needs_clarification": True,
        "clarification_question": (
            "Hello! I'm your Aditi IT Support assistant. "
            "I'm here to help resolve your IT issue quickly. "
            "Please describe what's happening."
        ),
        "messages": [
            AIMessage(
                content=(
                    "Hello! I'm your Aditi IT Support assistant. "
                    "I'm here to help resolve your IT issue quickly. "
                    "Please describe what's happening."
                )
            )
        ],
    }


TRIAGE_SYSTEM_PROMPT = (
    "You are a professional IT support triage specialist at Aditi Consulting. "
    "Respond ONLY with valid JSON as specified. No explanation, no markdown fences."
)


async def _classify_issue(message: str) -> dict:
    """Classify an IT issue with LLM + keyword fallback."""
    llm = get_llm_service()

    if llm.is_available:
        try:
            prompt = CLASSIFICATION_PROMPT.format(user_message=message)
            result = await llm.complete_json(prompt, system_prompt=TRIAGE_SYSTEM_PROMPT)
            if result and "category" in result:
                if result["category"] not in ISSUE_CATEGORIES:
                    result["category"] = "other"
                result["_method"] = "llm"
                return result
        except Exception as e:
            logger.warning("triage_llm_fallback", error=str(e))

    return _keyword_classify(message)


_SYMPTOM_WORDS = [
    "sync", "syncing", "slow", "crash", "crashing", "audio", "video",
    "camera", "hear", "sound", "connect", "login", "locked", "complian",
    "enroll", "install", "send", "receive", "open", "load", "update",
    "calendar", "password", "reset", "access", "denied", "missing",
    "black screen", "freeze", "hang", "drop", "disconnect", "not starting",
    "not working properly", "error", "failed", "timeout",
]


def _has_specific_symptom(message: str) -> bool:
    """Check if the message contains a specific actionable symptom."""
    msg_lower = message.lower()
    return any(s in msg_lower for s in _SYMPTOM_WORDS) and len(message.split()) > 4


def _keyword_classify(message: str) -> dict:
    """Deterministic keyword-based classification fallback."""
    message_lower = message.lower()
    has_symptom = _has_specific_symptom(message)

    if any(w in message_lower for w in ["outlook", "email", "mail", "inbox", "calendar"]):
        return {
            "category": "email/outlook",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["zoom", "video call", "meeting", "teams"]):
        return {
            "category": "video-conferencing/zoom",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["intune", "compliance", "non-compliant", "mdm"]):
        return {
            "category": "device-management/intune",
            "subcategory": None,
            "severity": "high",
            "urgency": "high",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.90 if has_symptom else 0.65,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["camera", "webcam", "video device"]):
        return {
            "category": "hardware/camera",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["vpn", "wifi", "wi-fi", "internet", "network"]):
        return {
            "category": "network/connectivity",
            "subcategory": None,
            "severity": "high",
            "urgency": "high",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["password", "login", "mfa", "locked", "access denied"]):
        return {
            "category": "access/permissions",
            "subcategory": None,
            "severity": "high",
            "urgency": "high",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(w in message_lower for w in ["keka", "freshservice", "install", "software", "app"]):
        return {
            "category": "software/other",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.80 if has_symptom else 0.5,
            "_method": "keyword",
        }
    else:
        return {
            "category": "other",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.3,
            "_method": "keyword",
        }
