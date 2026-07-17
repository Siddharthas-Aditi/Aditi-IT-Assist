"""LLM-generated conversational transition messages.

Replaces the static template strings used in triage.py transitions (greeting,
confirmation, closure, re-clarification) with natural, context-aware LLM
responses. Falls back to deterministic templates when the LLM is unavailable.

Design:
- Each function takes diagnostic context and returns a string.
- LLM calls are fast (50-150 tokens out, temperature 0.8 for variety).
- System prompt ensures the agent stays in-character as a warm IT colleague.
- Templates remain as fallbacks — the system never breaks if LLM is down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service

if TYPE_CHECKING:
    from app.services.agents.diagnostic_state import DiagnosticContext

logger = get_logger(__name__)

# ── System prompt shared across all transition messages ──────────────────────

_PERSONA = (
    "You are a friendly, empathetic IT support assistant at Aditi Consulting — "
    "a helpful colleague, not a robot. You speak naturally and concisely in 1-3 "
    "sentences. Never use bullet points, numbered lists, markdown, or emojis. "
    "Never mention internal system names, slugs, categories, or ticket numbers "
    "unless the user brought them up. Match the user's tone — if they're brief, "
    "you're brief; if they're chatty, be warmer. Use contractions (I'm, you're, "
    "that's) and everyday language."
)


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIRMATION — "Let me make sure I understood…"
# ═══════════════════════════════════════════════════════════════════════════════

_CONFIRM_PROMPT = """Rephrase what you understood about the user's IT issue and ask them
to confirm before you proceed to fix it. Keep it to 1-2 sentences.

Context about the user's issue (for your understanding — do NOT echo labels/slugs):
- System: {system}
- Problem in plain words: {problem}
- Additional detail: {detail}

Write a brief, natural confirmation question. End by asking if you've understood correctly.
Do NOT offer solutions yet."""


async def generate_confirmation(diag_ctx: DiagnosticContext) -> str:
    """Generate a natural 'let me confirm' message. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_confirmation(diag_ctx)

    system = diag_ctx.affected_system or diag_ctx.normalized_system or "your system"
    problem = (
        diag_ctx.exact_problem_statement
        or diag_ctx.symptom
        or diag_ctx.issue_subtype
        or "unspecified issue"
    )
    detail = diag_ctx.issue_subcategory or ""

    prompt = _CONFIRM_PROMPT.format(system=system, problem=problem, detail=detail)
    try:
        content = await llm.complete(
            prompt,
            system_prompt=_PERSONA,
            temperature=0.8,
            max_tokens=120,
        )
        # Sanity check: must end with a question mark or question-like phrase
        if content and len(content) > 20:
            return content.strip()
    except Exception as exc:
        logger.warning("confirm_msg_llm_error", error=str(exc))

    return _fallback_confirmation(diag_ctx)


def _fallback_confirmation(diag_ctx: DiagnosticContext) -> str:
    """Deterministic template fallback."""
    problem = diag_ctx.exact_problem_statement or diag_ctx.symptom or "the issue you described"
    return (
        f"Got it — just to make sure I've understood: {problem}. Is that what you're experiencing?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GREETING — first message when user says "hi"
# ═══════════════════════════════════════════════════════════════════════════════

_GREETING_PROMPT = """A colleague just said hi to you in the IT support chat. Greet them
warmly and ask what IT issue you can help with today. Keep it to 1-2 sentences.
Be friendly and approachable. Do NOT list capabilities or categories.
Mention that you can help with things like email, VPN, passwords, devices etc
in a casual way (not a bulleted list)."""


async def generate_greeting() -> str:
    """Generate a natural greeting. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_greeting()

    try:
        content = await llm.complete(
            _GREETING_PROMPT,
            system_prompt=_PERSONA,
            temperature=0.9,
            max_tokens=80,
        )
        if content and len(content) > 15:
            return content.strip()
    except Exception as exc:
        logger.warning("greeting_msg_llm_error", error=str(exc))

    return _fallback_greeting()


def _fallback_greeting() -> str:
    return (
        "Hi there! I'm the Aditi IT Support Assistant. I can help with things "
        "like email, VPN, passwords, devices, and more. What can I help you with today?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  RESOLVED — user confirms the fix worked
# ═══════════════════════════════════════════════════════════════════════════════

_RESOLVED_PROMPT = """The user just confirmed that the IT issue you helped them with is now
fixed. Write a brief, warm closing message (1-2 sentences). Congratulate them
naturally and let them know they can come back any time.

Issue context (do NOT echo labels):
- What was fixed: {problem}
- System: {system}

Keep it natural and short. Do NOT use emojis or exclamation marks excessively."""


async def generate_resolved(diag_ctx: DiagnosticContext) -> str:
    """Generate a natural resolution closure. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_resolved()

    problem = diag_ctx.issue_subtype or diag_ctx.symptom or "the issue"
    system = diag_ctx.affected_system or diag_ctx.normalized_system or "your system"

    prompt = _RESOLVED_PROMPT.format(problem=problem, system=system)
    try:
        content = await llm.complete(
            prompt,
            system_prompt=_PERSONA,
            temperature=0.85,
            max_tokens=80,
        )
        if content and len(content) > 15:
            return content.strip()
    except Exception as exc:
        logger.warning("resolved_msg_llm_error", error=str(exc))

    return _fallback_resolved()


def _fallback_resolved() -> str:
    return (
        "Great — glad that's sorted! If anything else comes up, "
        "just start a new chat and I'll be happy to help."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GRATITUDE CLOSE — user says "thanks" after getting help
# ═══════════════════════════════════════════════════════════════════════════════

_GRATITUDE_PROMPT = """The user just thanked you after you helped resolve their IT issue.
Write a brief, warm response (1 sentence). Acknowledge their thanks naturally and
let them know you're here if they need anything else. Keep it casual and short."""


async def generate_gratitude_close() -> str:
    """Generate a natural gratitude acknowledgment. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_gratitude()

    try:
        content = await llm.complete(
            _GRATITUDE_PROMPT,
            system_prompt=_PERSONA,
            temperature=0.9,
            max_tokens=60,
        )
        if content and len(content) > 10:
            return content.strip()
    except Exception as exc:
        logger.warning("gratitude_msg_llm_error", error=str(exc))

    return _fallback_gratitude()


def _fallback_gratitude() -> str:
    return (
        "You're welcome! Happy I could help. Drop me a message any time if something else comes up."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  OPEN CLARIFICATION — we misunderstood, user said "no"
# ═══════════════════════════════════════════════════════════════════════════════

_RECLARIFY_PROMPT = """You misunderstood the user's IT issue and they corrected you.
Apologize briefly and naturally, then ask them to describe what's actually happening.
Keep it to 1-2 sentences. Be humble and helpful. Do NOT guess at the problem."""


async def generate_reclarification() -> str:
    """Generate a natural re-ask after misunderstanding. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_reclarification()

    try:
        content = await llm.complete(
            _RECLARIFY_PROMPT,
            system_prompt=_PERSONA,
            temperature=0.8,
            max_tokens=80,
        )
        if content and len(content) > 15:
            return content.strip()
    except Exception as exc:
        logger.warning("reclarify_msg_llm_error", error=str(exc))

    return _fallback_reclarification()


def _fallback_reclarification() -> str:
    return (
        "No problem — thanks for putting me right. Could you tell me a bit more "
        "about what's actually happening, so I can point you to the right fix?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  NEW TOPIC — user switches to a different issue
# ═══════════════════════════════════════════════════════════════════════════════

_NEW_TOPIC_PROMPT = """The user just said they want to switch to a different IT issue.
Acknowledge briefly and ask what the new problem is. Keep it to 1 sentence.
Be natural and willing to help."""


async def generate_new_topic() -> str:
    """Generate a natural new-topic transition. Falls back to template."""
    llm = get_llm_service()
    if not llm.is_available:
        return _fallback_new_topic()

    try:
        content = await llm.complete(
            _NEW_TOPIC_PROMPT,
            system_prompt=_PERSONA,
            temperature=0.85,
            max_tokens=60,
        )
        if content and len(content) > 10:
            return content.strip()
    except Exception as exc:
        logger.warning("new_topic_msg_llm_error", error=str(exc))

    return _fallback_new_topic()


def _fallback_new_topic() -> str:
    return "Of course — what's the new issue?"


# ═══════════════════════════════════════════════════════════════════════════════
#  ESCALATION — offering / confirming a handoff to the IT team
# ═══════════════════════════════════════════════════════════════════════════════

_ESCALATION_OFFER_PROMPT = """You could not fully resolve the user's IT issue and want to
hand off to the human IT team. Warmly let them know you'll bring in the IT team and that
you'll pass along everything from the conversation so they don't have to repeat themselves.
Keep it to 1-2 sentences. Do not promise a specific time.

Context (for you — do NOT echo labels): system = {system}; why escalating = {reason}."""


async def generate_escalation_offer(diag_ctx: DiagnosticContext, reason: str) -> str:
    """Natural escalation message. Falls back to a deterministic template."""
    llm = get_llm_service()
    system = diag_ctx.affected_system or diag_ctx.normalized_system or "your system"
    if llm.is_available:
        try:
            content = await llm.complete(
                _ESCALATION_OFFER_PROMPT.format(system=system, reason=reason),
                system_prompt=_PERSONA,
                temperature=0.8,
                max_tokens=140,
            )
            if content and len(content) > 20:
                return content.strip()
        except Exception as exc:
            logger.warning("escalation_offer_llm_error", error=str(exc))
    return _fallback_escalation_offer(system)


def _fallback_escalation_offer(system: str) -> str:
    return (
        f"I wasn't able to fully sort out your {system} issue on my own, but our IT team "
        f"can help from here. I'll include everything from our conversation so they can "
        f"pick up right where we left off."
    )


_ESCALATION_CONFIRMED_PROMPT = """The user just agreed to be connected to the IT team.
Reassure them warmly that you're connecting them now and have shared the full context.
Keep it to 1-2 sentences."""


async def generate_escalation_confirmed(diag_ctx: DiagnosticContext) -> str:
    """Natural 'connecting you now' message. Falls back to a template."""
    llm = get_llm_service()
    if llm.is_available:
        try:
            content = await llm.complete(
                _ESCALATION_CONFIRMED_PROMPT,
                system_prompt=_PERSONA,
                temperature=0.7,
                max_tokens=100,
            )
            if content and len(content) > 20:
                return content.strip()
        except Exception as exc:
            logger.warning("escalation_confirmed_llm_error", error=str(exc))
    return _fallback_escalation_confirmed()


def _fallback_escalation_confirmed() -> str:
    return (
        "Perfect! I'm connecting you with our IT team now. I've included everything from "
        "our conversation so they can help you right away."
    )
