"""Triage Agent Node — entity-aware, intent-driven diagnostic classification.

This upgraded triage node:
1. Runs entity normalization to recognize products/systems (even misspelled)
2. Detects intent (login, access, error, performance, etc.)
3. Routes to the correct entity-specific playbook when available
4. Falls back to category-level playbooks for general issues
5. Asks playbook-guided clarification questions before proceeding
"""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.agents.diagnostic_engine import (
    ClarifyOrAnswerDecision,
    evaluate_clarify_or_answer,
    extract_slots_from_message,
    update_context_from_extraction,
)
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.entity_normalizer import (
    EntityMatch,
    detect_issue_intent,
    normalize_entity,
)
from app.services.agents.playbooks import get_playbook, get_playbook_for_entity  # noqa: F401
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

ISSUE_CATEGORIES = [
    "email/outlook",
    "video-conferencing/zoom",
    "device-management/intune",
    "hardware/camera",
    "hardware/audio",
    "hardware/other",
    "software/other",
    "network/connectivity",
    "access/permissions",
    "access/sixth_sense",
    "other",
]

CLASSIFICATION_PROMPT = """You are a professional IT support classification specialist at Aditi Consulting.
Analyze the user's message and classify their IT issue.

Categories:
- email/outlook, video-conferencing/zoom, device-management/intune
- hardware/camera, hardware/audio, hardware/other, software/other
- network/connectivity, access/permissions, access/sixth_sense, other

{entity_hint}

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

has_specific_symptom=true for clear problems like "unable to login", "account locked".
has_specific_symptom=false for vague like "having an issue", "not working".

User message: {user_message}"""


async def triage_node(state: WorkflowState) -> dict:
    """Entity-aware, intent-driven triage node.

    Flow:
    1. Extract latest user message
    2. Run entity normalization (recognize product/system)
    3. Detect issue intent (login, error, access, etc.)
    4. If first classification: classify with entity + intent context
    5. If follow-up: extract slots from user response
    6. Evaluate playbook: enough context → proceed, else → clarify
    """
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

    # ── Step 1: Entity Normalization (every turn) ────────────────
    entity_match = normalize_entity(user_message)
    if entity_match and (
        not diag_ctx.normalized_system
        or entity_match.confidence > diag_ctx.entity_confidence
    ):
        _apply_entity_match(diag_ctx, entity_match)
        logger.info(
            "entity_recognized",
            canonical=entity_match.canonical_name,
            matched=entity_match.matched_text,
            confidence=entity_match.confidence,
            method=entity_match.method,
        )

    # ── Step 2: Intent Detection (every turn) ────────────────────
    intent_result = detect_issue_intent(user_message)
    _apply_intent(diag_ctx, intent_result)

    # ── Step 3: Classification or Slot Extraction ────────────────
    if diag_ctx.issue_category is None:
        classification = await _classify_issue(user_message, diag_ctx)
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

    # ── Step 4: Playbook-guided clarification decision ───────────
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
            "entity": diag_ctx.normalized_system,
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
        "entity": diag_ctx.normalized_system,
        "symptom": diag_ctx.symptom,
        "intent_flags": {
            "login": diag_ctx.login_issue_flag,
            "locked": diag_ctx.blocked_account_flag,
            "otp": diag_ctx.otp_issue_flag,
            "unhandled": diag_ctx.unhandled_message_flag,
        },
        "confidence": diag_ctx.classification_confidence,
        "slots_filled": list(diag_ctx.get_filled_slots().keys()),
        "clarification_rounds": diag_ctx.clarification_count,
    }

    return {
        "current_node": "triage",
        "issue_category": diag_ctx.issue_category,
        "issue_subcategory": diag_ctx.issue_subcategory,
        "severity": state.get("severity") or _infer_severity(diag_ctx),
        "urgency": state.get("urgency") or _infer_urgency(diag_ctx),
        "needs_clarification": False,
        "clarification_question": None,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "audit_trail": [audit_entry],
    }


# ══════════════════════════════════════════════════════════════════════
#  ENTITY + INTENT HELPERS
# ══════════════════════════════════════════════════════════════════════


def _apply_entity_match(ctx: DiagnosticContext, match: EntityMatch) -> None:
    """Apply a recognized entity to the diagnostic context."""
    ctx.normalized_system = match.canonical_name
    ctx.raw_system_mention = match.matched_text
    ctx.entity_confidence = match.confidence
    ctx.affected_system = match.display_name

    entity_playbook = get_playbook_for_entity(match.canonical_name)
    if entity_playbook:
        ctx.issue_category = entity_playbook.category


def _apply_intent(ctx: DiagnosticContext, intent: dict) -> None:
    """Apply detected intent flags to the diagnostic context."""
    if intent.get("is_login_issue"):
        ctx.login_issue_flag = True
        if not ctx.symptom:
            ctx.symptom = "login-failure"
        if not ctx.issue_subcategory:
            ctx.issue_subcategory = "login-failure"

    if intent.get("is_account_locked"):
        ctx.blocked_account_flag = "yes"
        if not ctx.symptom:
            ctx.symptom = "account-locked"

    if intent.get("has_otp_mention"):
        ctx.otp_issue_flag = True
        if not ctx.symptom:
            ctx.symptom = "otp-issue"

    if intent.get("has_unhandled_message"):
        ctx.unhandled_message_flag = True
        if not ctx.symptom:
            ctx.symptom = "unhandled-message"
        if not ctx.error_message:
            ctx.error_message = "Unhandled Message"


def _infer_severity(ctx: DiagnosticContext) -> str:
    """Infer issue severity from diagnostic context."""
    if ctx.blocked_account_flag == "yes" or ctx.login_issue_flag:
        return "high"
    return "medium"


def _infer_urgency(ctx: DiagnosticContext) -> str:
    """Infer urgency from diagnostic context."""
    if ctx.login_issue_flag or ctx.blocked_account_flag == "yes":
        return "high"
    return "medium"


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


async def _classify_issue(message: str, diag_ctx: DiagnosticContext) -> dict:
    """Classify an IT issue with entity-aware LLM + keyword fallback."""
    # If entity normalization already set the category, use it directly
    if diag_ctx.normalized_system and diag_ctx.issue_category:
        return _entity_based_classification(message, diag_ctx)

    llm = get_llm_service()
    entity_hint = ""
    if diag_ctx.normalized_system:
        entity_hint = (
            f"IMPORTANT: The user is referring to '{diag_ctx.affected_system}' "
            f"(canonical: {diag_ctx.normalized_system}). "
            f"Use the category '{diag_ctx.issue_category or 'access/permissions'}' "
            f"for this system."
        )

    if llm.is_available:
        try:
            prompt = CLASSIFICATION_PROMPT.format(
                user_message=message,
                entity_hint=entity_hint,
            )
            result = await llm.complete_json(prompt, system_prompt=TRIAGE_SYSTEM_PROMPT)
            if result and "category" in result:
                if result["category"] not in ISSUE_CATEGORIES:
                    result["category"] = diag_ctx.issue_category or "other"
                result["_method"] = "llm"
                return result
        except Exception as e:
            logger.warning("triage_llm_fallback", error=str(e))

    return _keyword_classify(message, diag_ctx)


def _entity_based_classification(message: str, diag_ctx: DiagnosticContext) -> dict:
    """Build classification from entity normalization results."""
    has_symptom = bool(
        diag_ctx.symptom
        or diag_ctx.login_issue_flag
        or diag_ctx.blocked_account_flag
        or diag_ctx.otp_issue_flag
        or diag_ctx.unhandled_message_flag
    )
    return {
        "category": diag_ctx.issue_category or "other",
        "subcategory": diag_ctx.issue_subcategory or diag_ctx.symptom,
        "severity": _infer_severity(diag_ctx),
        "urgency": _infer_urgency(diag_ctx),
        "has_specific_symptom": has_symptom,
        "symptom": diag_ctx.symptom,
        "confidence": max(diag_ctx.entity_confidence * 0.9, 0.7),
        "_method": "entity",
    }


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
    return any(s in msg_lower for s in _SYMPTOM_WORDS) and len(message.split()) > 3


def _keyword_classify(message: str, diag_ctx: DiagnosticContext | None = None) -> dict:
    """Deterministic keyword-based classification fallback.

    Enhanced to check entity normalization results first.
    """
    # If entity normalization already identified the system, use that
    if diag_ctx and diag_ctx.normalized_system and diag_ctx.issue_category:
        return _entity_based_classification(message, diag_ctx)

    message_lower = message.lower()
    has_symptom = _has_specific_symptom(message)

    # Check for known product mentions via entity normalization
    entity = normalize_entity(message)
    if entity:
        if diag_ctx:
            _apply_entity_match(diag_ctx, entity)
            intent = detect_issue_intent(message)
            _apply_intent(diag_ctx, intent)
            return _entity_based_classification(message, diag_ctx)
        return {
            "category": entity.category,
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": entity.confidence * 0.85,
            "_method": "entity_keyword",
        }

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
