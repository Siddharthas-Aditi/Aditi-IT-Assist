"""Diagnostic engine — clarify-or-answer policy and slot extraction.

This module is the brain of the multi-turn diagnostic conversation.
It decides:
- Whether to ask a follow-up question or proceed to answer
- Which question to ask next (using playbooks)
- How to extract slot values from user messages
- When to transition between conversation phases
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.playbooks import ClarificationOption, get_playbook
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

# ── Slot Extraction ──────────────────────────────────────────────────

SLOT_EXTRACTION_PROMPT = """You are analyzing a user's response in an IT support conversation.
The user is describing an IT issue. Extract structured information from their message.

Current known context:
{current_context}

The user just said: "{user_message}"

Extract the following fields if present in the message (respond with JSON only):
{{
  "symptom": "<specific symptom described, e.g. 'not receiving emails', 'black screen'>",
  "issue_subcategory": "<refined issue type if identifiable>",
  "exact_problem_statement": "<the user's complete problem in one sentence>",
  "affected_system": "<specific app/device mentioned, e.g. 'Outlook', 'Zoom', 'MacBook'>",
  "device_type": "<laptop/desktop/mobile/tablet if mentioned>",
  "platform_os": "<Windows/Mac/iOS/Android if mentioned>",
  "error_message": "<exact error text if quoted>",
  "duration": "<how long the issue has been occurring if mentioned>",
  "urgency": "<low/medium/high if the user indicates time pressure>",
  "others_affected": "<true/false if the user says others have the same issue>",
  "vpn_status": "<connected/disconnected/not applicable if mentioned>",
  "steps_already_tried": ["<list of things the user says they already tried>"],
  "live_agent_requested": false
}}

IMPORTANT:
- Only include fields where you found clear evidence in the message
- Set live_agent_requested=true ONLY if the user explicitly asks for a human/live agent
- For fields not found, use null
- Do NOT guess or infer — only extract what's clearly stated
- Respond with valid JSON only, no explanation"""


async def extract_slots_from_message(
    message: str,
    current_context: DiagnosticContext,
    category: str | None = None,
) -> dict:
    """Extract diagnostic slots from a user message using LLM or pattern matching.

    Returns a dict of slot_name -> value for all slots found in the message.
    """
    llm = get_llm_service()

    if llm.is_available:
        try:
            return await _llm_extract_slots(message, current_context, llm)
        except Exception as e:
            logger.warning("slot_extraction_llm_fallback", error=str(e))

    # Fallback: pattern-based extraction
    return _pattern_extract_slots(message, category)


async def _llm_extract_slots(
    message: str,
    context: DiagnosticContext,
    llm: object,
) -> dict:
    """Use LLM for intelligent slot extraction."""
    from app.services.llm_service import LLMService

    assert isinstance(llm, LLMService)

    context_summary = ", ".join(
        f"{k}={v}" for k, v in context.get_filled_slots().items()
    ) or "none yet"

    prompt = SLOT_EXTRACTION_PROMPT.format(
        current_context=context_summary,
        user_message=message,
    )

    result = await llm.complete_json(prompt)

    # Filter out null/empty values
    extracted: dict = {}
    for key, value in result.items():
        if value is None or value == "" or value == []:
            continue
        if key == "others_affected" and isinstance(value, str):
            extracted[key] = value.lower() == "true"
        else:
            extracted[key] = value

    return extracted


def _pattern_extract_slots(message: str, category: str | None = None) -> dict:
    """Pattern-based slot extraction when LLM is unavailable."""
    msg_lower = message.lower()
    extracted: dict = {}

    # Detect explicit live agent request
    agent_phrases = [
        "talk to a human", "live agent", "speak to someone",
        "real person", "human support", "transfer me", "escalate",
    ]
    if any(phrase in msg_lower for phrase in agent_phrases):
        extracted["live_agent_requested"] = True
        return extracted

    # Detect platform/OS
    if "windows" in msg_lower:
        extracted["platform_os"] = "Windows"
    elif "mac" in msg_lower or "macos" in msg_lower or "macbook" in msg_lower:
        extracted["platform_os"] = "Mac"

    # Detect device type
    if "laptop" in msg_lower:
        extracted["device_type"] = "laptop"
    elif "desktop" in msg_lower:
        extracted["device_type"] = "desktop"
    elif "phone" in msg_lower or "mobile" in msg_lower:
        extracted["device_type"] = "mobile"

    # For option-chip selections, map to subcategory/symptom
    playbook = get_playbook(category) if category else None
    if playbook:
        for q in playbook.questions:
            for opt in q.options:
                if opt.label.lower() == msg_lower.strip() or opt.value == msg_lower.strip():
                    extracted[q.slot] = opt.value
                    break

    # Generic symptom extraction
    if not extracted.get("symptom") and len(message.split()) > 3:
        extracted["exact_problem_statement"] = message.strip()
        # Try to find common symptom keywords
        symptom_map = {
            "not receiving": "not-receiving-emails",
            "can't send": "sending-failure",
            "slow": "performance-issue",
            "crash": "app-crash",
            "black screen": "camera-black-screen",
            "no audio": "no-audio",
            "can't hear": "no-audio",
            "can't join": "cant-join-meeting",
            "locked": "account-locked",
            "non-compliant": "non-compliant",
            "won't connect": "vpn-not-connecting",
        }
        for pattern, symptom in symptom_map.items():
            if pattern in msg_lower:
                extracted["symptom"] = symptom
                break

    return extracted


# ── Clarify-or-Answer Decision ──────────────────────────────────────


class ClarifyOrAnswerDecision:
    """The result of the clarify-or-answer policy evaluation."""

    def __init__(
        self,
        should_clarify: bool,
        question: str | None = None,
        options: list[ClarificationOption] | None = None,
        reason: str = "",
    ):
        self.should_clarify = should_clarify
        self.question = question
        self.options = options or []
        self.reason = reason


def evaluate_clarify_or_answer(context: DiagnosticContext) -> ClarifyOrAnswerDecision:
    """Decide whether to ask a follow-up or proceed to retrieval/resolution.

    This is the core policy function. It checks:
    1. Has the user requested a live agent? → escalate
    2. Have we hit max clarifications? → proceed with what we have
    3. Does the playbook say we have enough context? → proceed
    4. Otherwise → ask the next most important question
    """
    # User wants a human — don't ask more questions
    if context.live_agent_requested:
        return ClarifyOrAnswerDecision(
            should_clarify=False,
            reason="user_requested_agent",
        )

    # Max clarifications reached — proceed with available context
    if context.clarification_count >= context.max_clarifications:
        return ClarifyOrAnswerDecision(
            should_clarify=False,
            reason="max_clarifications_reached",
        )

    # Check playbook for context sufficiency
    playbook = get_playbook(context.issue_category or "other")
    filled = context.get_filled_slots()

    if playbook.has_enough_context(filled):
        return ClarifyOrAnswerDecision(
            should_clarify=False,
            reason="sufficient_context",
        )

    # Context is insufficient — get next question from playbook
    next_q = playbook.get_next_question(filled, context.clarification_count)

    if next_q is None:
        # No more questions to ask — proceed anyway
        return ClarifyOrAnswerDecision(
            should_clarify=False,
            reason="no_more_questions",
        )

    return ClarifyOrAnswerDecision(
        should_clarify=True,
        question=next_q.question,
        options=next_q.options,
        reason=f"missing_slot:{next_q.slot}",
    )


# ── Phase Transitions ────────────────────────────────────────────────


def determine_next_phase(context: DiagnosticContext) -> DiagnosticPhase:
    """Determine what phase the conversation should move to."""
    if context.live_agent_requested or context.should_escalate():
        return DiagnosticPhase.ESCALATING

    if context.resolution_attempts > 0 and context.resolution_confidence >= 0.5:
        return DiagnosticPhase.CONFIRMING

    if context.has_enough_context():
        return DiagnosticPhase.DIAGNOSING

    if context.clarification_count >= context.max_clarifications:
        return DiagnosticPhase.DIAGNOSING  # Best effort with what we have

    return DiagnosticPhase.CLARIFYING


def update_context_from_extraction(
    context: DiagnosticContext,
    extracted: dict,
) -> DiagnosticContext:
    """Update diagnostic context with newly extracted slots."""
    for key, value in extracted.items():
        if key == "steps_already_tried" and isinstance(value, list):
            context.steps_already_tried.extend(value)
        elif key == "live_agent_requested" and value:
            context.live_agent_requested = True
        elif key == "others_affected":
            context.others_affected = bool(value)
        elif hasattr(context, key) and value:
            setattr(context, key, value)

    # Update subcategory from symptom if not set
    if context.symptom and not context.issue_subcategory:
        context.issue_subcategory = context.symptom

    return context
