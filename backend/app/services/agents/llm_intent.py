"""LLM-backed conversational intent + slot understanding.

Drop-in upgrade for the keyword-based :mod:`intent_classifier`. Same
:class:`IntentClassification` return shape so the rest of the workflow is
unchanged — only the *understanding* layer becomes adaptive.

Why this exists
---------------
Keyword rules are deterministic but brittle: every new phrasing requires a
code change. That's the right trade-off for the **safety** layer (ticket
creation, web-fallback policy, KB write-gating) but the wrong one for the
**understanding** layer, where the user expects ChatGPT-quality
comprehension. This module gives us the latter without surrendering the
former.

Hybrid contract
---------------
1. :func:`classify_intent_with_llm` calls the LLM with a strict JSON schema.
2. If the LLM is unavailable / errors / returns low-confidence output, fall
   back to the deterministic :func:`intent_classifier.classify_intent`.
3. The fallback also runs **alongside** as a sanity check: if the keyword
   layer detects a high-priority NEW_TOPIC or ESCALATE_REQUEST and the LLM
   disagrees, the keyword answer wins. This preserves the bug fixes we
   already proved with tests — the LLM cannot regress a safety guarantee.
4. The result carries the same ``version`` field, plus a ``method``
   metadata bit (``"llm"`` / ``"keyword"`` / ``"hybrid"``) for the audit
   trail.

Why JSON-only output
--------------------
The LLM is asked to emit one JSON object with fixed keys: ``intent``,
``confidence``, ``rationale``, ``slot_hints``. The intent value is
constrained to the same enum the keyword classifier produces. No prose,
no markdown — easy to parse, easy to log, easy to replay.

Token cost
----------
One small call per user turn. ~150-300 input tokens, ~80-150 output. At
$0.15/$0.60 per million for GPT-4o-mini this is ~$0.00006 per turn — about
$6/100k turns. The deterministic fallback covers the rest if LLM is
disabled.

What this module does NOT do
----------------------------
* Issue classification (which IT system). That's the entity normalizer.
* Subtype classification. That's the subtype_classifier (also keyword
  today; same hybrid migration applies — see Phase 2).
* Routing decisions. That's the supervisor.
* Generating user replies. That's the specialist.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.agents.intent_classifier import (
    CLASSIFIER_VERSION as _KEYWORD_VERSION,
)
from app.services.agents.intent_classifier import (
    ConversationIntent,
    IntentClassification,
)
from app.services.agents.intent_classifier import (
    classify_intent as classify_intent_keywords,
)
from app.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)

LLM_INTENT_VERSION = "1.0.0"


# Intents the LLM must pick from. Mirrors :class:`ConversationIntent`.
_INTENT_ENUM = sorted(i.value for i in ConversationIntent)

_SYSTEM_PROMPT = (
    "You are the conversation-intent classifier for an enterprise IT support assistant. "
    "Given a user message and a small amount of conversation context, classify the user's "
    "*conversational move* — what they are doing with this turn, NOT which IT issue they have. "
    "Respond with valid JSON ONLY (no prose, no markdown). Be precise: if a message both "
    "describes a problem AND switches topic, prefer NEW_TOPIC; if a message says yes/no AND "
    "asks for a human, prefer ESCALATE_REQUEST."
)


def _build_prompt(
    message: str,
    *,
    has_active_issue: bool,
    awaiting_confirmation: bool,
    steps_given: bool,
    issue_resolved: bool,
) -> str:
    """Compose the classification prompt with the same flags the keyword layer reads."""
    return f"""Classify the user's conversational intent.

CONTEXT FLAGS (read carefully — these determine which intents are valid)
  has_active_issue:      {has_active_issue}   (True iff an issue is already being diagnosed
                                in this session; False on a fresh session)
  awaiting_confirmation: {awaiting_confirmation} (we just asked a yes/no question)
  steps_given:           {steps_given}        (we already suggested troubleshooting steps)
  issue_resolved:        {issue_resolved}     (a previous issue was already resolved)

HARD RULES (override anything else)
  • If has_active_issue is False AND issue_resolved is False, the user is
    describing their problem for the first time — the intent is CONTINUE
    unless they are explicitly asking for a human (escalate_request),
    greeting ("hi"), or doing pure small-talk ("how are you").
  • NEW_TOPIC requires has_active_issue=True. It means the user is dropping
    the CURRENT issue and starting a DIFFERENT one. A first-turn problem
    description (no matter how detailed) is NEVER NEW_TOPIC.
  • CONFIRM / DENY require awaiting_confirmation=True.
  • POSITIVE_FEEDBACK / NEGATIVE_FEEDBACK require steps_given=True.

USER MESSAGE
  {message!r}

INTENT TAXONOMY (pick exactly one)
  continue            — DEFAULT. The user is describing a problem (first time
                        or follow-up), giving slot detail, answering an open
                        question. THIS is what an initial "I need help with
                        outlook, my mailbox is full and I am unable to get
                        new mail" classifies as — it's a problem description.
  new_topic           — Only valid mid-flow. The user is explicitly leaving
                        the CURRENT issue and asking about something ELSE.
                        Signals: "another problem", "different issue",
                        "wait, also", "btw I also have", "switch topic".
                        NOT a fresh problem description.
  escalate_request    — Explicit human/specialist/ticket request:
                        "talk to a human", "connect me with a specialist",
                        "raise a ticket", "I want a real person".
  confirm             — "yes" / "that's right" — only when awaiting_confirmation.
  deny                — "no" / "not quite" — only when awaiting_confirmation.
  positive_feedback   — "it worked" / "fixed it" — only when steps_given.
  negative_feedback   — "didn't work" / "still broken" — only when steps_given.
  repeat_or_simplify  — "can you explain again", "in plain English",
                        "I'm confused".
  greeting            — "hi" / "hello" alone — only when has_active_issue=False.
  gratitude           — "thanks" / "thank you" — pure wrap-up.
  small_talk          — "how are you" / "lol" / "ok cool" — content-free filler.

OUTPUT JSON
{{
  "intent": "<one of: {", ".join(_INTENT_ENUM)}>",
  "confidence": 0.0-1.0,
  "rationale": "<short, ≤ 20 words; cite which rule applied>",
  "slot_hints": {{ "affected_system": "<system or null>", "issue_summary": "<one-line or null>" }}
}}"""


@dataclass(frozen=True)
class _LLMIntentRaw:
    """Parsed-but-not-yet-resolved LLM output. Internal."""

    intent: ConversationIntent | None
    confidence: float
    rationale: str
    slot_hints: dict


def _parse_llm_output(payload: dict) -> _LLMIntentRaw:
    """Defensively parse LLM JSON into a typed value. Unknown intents → None."""
    raw_intent = (payload.get("intent") or "").strip().lower()
    try:
        intent = ConversationIntent(raw_intent) if raw_intent else None
    except ValueError:
        intent = None
    try:
        conf = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    raw_hints = payload.get("slot_hints")
    slot_hints = raw_hints if isinstance(raw_hints, dict) else {}
    return _LLMIntentRaw(
        intent=intent,
        confidence=max(0.0, min(1.0, conf)),
        rationale=str(payload.get("rationale") or "")[:200],
        slot_hints=slot_hints,
    )


# Safety-priority intents — if the keyword layer says one of these with high
# confidence, the LLM is overruled. These are the bug-class fixes
# (ITA-000007 NEW_TOPIC, explicit ESCALATE_REQUEST) we proved with tests and
# refuse to regress.
_SAFETY_OVERRIDE_INTENTS = frozenset(
    {
        ConversationIntent.NEW_TOPIC,
        ConversationIntent.ESCALATE_REQUEST,
    }
)

# Below this LLM confidence, fall back to keywords entirely.
_LLM_CONFIDENCE_FLOOR = 0.5

# LLM call timeout — keep tight; the keyword fallback is fast.
_LLM_TIMEOUT_SECONDS = 4.0


async def classify_intent_with_llm(
    message: str,
    *,
    has_active_issue: bool = False,
    awaiting_confirmation: bool = False,
    steps_given: bool = False,
    issue_resolved: bool = False,
    llm: LLMService | None = None,
) -> IntentClassification:
    """LLM-first intent classification with deterministic fallback + safety overrides.

    Returns an :class:`IntentClassification` (same shape the keyword layer
    produces) so callers don't need to know which path served the answer.
    The ``matched`` field encodes the method (``"llm:<rationale>"`` or
    ``"keyword:<phrase>"`` or ``"hybrid:llm+keyword_override"``).

    Decision rules (deterministic):

    1. Run the keyword classifier first (cheap, sync). If it returns
       ``NEW_TOPIC`` or ``ESCALATE_REQUEST`` with high confidence, return that
       immediately — these are the safety-critical bug-class fixes we
       cannot regress.
    2. Otherwise, if the LLM is available, call it with a strict JSON
       schema. On success above the confidence floor, return the LLM answer.
    3. On LLM error / timeout / unknown intent / low confidence, return the
       keyword answer.
    """
    llm = llm or get_llm_service()

    # Step 1 — safety override path
    keyword_result = classify_intent_keywords(
        message,
        has_active_issue=has_active_issue,
        awaiting_confirmation=awaiting_confirmation,
        steps_given=steps_given,
        issue_resolved=issue_resolved,
    )
    if keyword_result.intent in _SAFETY_OVERRIDE_INTENTS and keyword_result.confidence >= 0.85:
        return IntentClassification(
            intent=keyword_result.intent,
            confidence=keyword_result.confidence,
            matched=f"keyword:{keyword_result.matched}",
            alternates=keyword_result.alternates,
            version=f"llm-{LLM_INTENT_VERSION}+kw-{_KEYWORD_VERSION}",
        )

    # Step 2 — LLM call
    if not llm.is_available:
        return _wrap_keyword_for_audit(keyword_result, "keyword:llm-unavailable")

    prompt = _build_prompt(
        message,
        has_active_issue=has_active_issue,
        awaiting_confirmation=awaiting_confirmation,
        steps_given=steps_given,
        issue_resolved=issue_resolved,
    )
    try:
        payload = await asyncio.wait_for(
            llm.complete_json(prompt, system_prompt=_SYSTEM_PROMPT),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("llm_intent_timeout", message_preview=message[:80])
        return _wrap_keyword_for_audit(keyword_result, "keyword:llm-timeout")
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_intent_error", error=str(exc), message_preview=message[:80])
        return _wrap_keyword_for_audit(keyword_result, "keyword:llm-error")

    raw = _parse_llm_output(payload)
    if raw.intent is None or raw.confidence < _LLM_CONFIDENCE_FLOOR:
        logger.info(
            "llm_intent_low_confidence_fallback",
            llm_intent=raw.intent.value if raw.intent else None,
            llm_confidence=raw.confidence,
            keyword_intent=keyword_result.intent.value,
        )
        return _wrap_keyword_for_audit(keyword_result, "keyword:llm-lowconf")

    # ── Structural validity guard ──────────────────────────────────────
    # Some intents are only valid in specific conversation states. The LLM
    # can pattern-match on surface features (e.g. seeing the word "another"
    # or "now" in a first-turn message) and pick an intent that's
    # structurally impossible. We catch those here and fall back to the
    # keyword classifier (which respects the same context flags).
    #
    # This is what stops "I need help with outlook, my mailbox is full" on
    # turn 1 from being classified NEW_TOPIC just because the prompt example
    # happened to look similar.
    invalid_intent_reason: str | None = None
    if raw.intent is ConversationIntent.NEW_TOPIC and not has_active_issue:
        invalid_intent_reason = "newtopic-without-active-issue"
    elif (
        raw.intent in (ConversationIntent.CONFIRM, ConversationIntent.DENY)
        and not awaiting_confirmation
    ):
        invalid_intent_reason = "confirm-or-deny-without-question"
    elif (
        raw.intent
        in (
            ConversationIntent.POSITIVE_FEEDBACK,
            ConversationIntent.NEGATIVE_FEEDBACK,
        )
        and not steps_given
    ):
        invalid_intent_reason = "feedback-without-steps"
    elif raw.intent is ConversationIntent.GREETING and has_active_issue:
        invalid_intent_reason = "greeting-during-active-issue"

    if invalid_intent_reason is not None:
        logger.info(
            "llm_intent_structurally_invalid",
            llm_intent=raw.intent.value,
            reason=invalid_intent_reason,
            llm_confidence=raw.confidence,
            keyword_intent=keyword_result.intent.value,
        )
        return _wrap_keyword_for_audit(
            keyword_result, f"keyword:llm-invalid-{invalid_intent_reason}"
        )

    # Step 3 — hybrid override: if keywords found a safety intent at any
    # confidence, prefer that. The LLM may have missed it on a borderline
    # phrasing, and we'd rather over-respect the user's "stop, new topic"
    # than under-respect it.
    if keyword_result.intent in _SAFETY_OVERRIDE_INTENTS:
        logger.info(
            "llm_intent_safety_override",
            llm_intent=raw.intent.value,
            keyword_intent=keyword_result.intent.value,
        )
        return IntentClassification(
            intent=keyword_result.intent,
            confidence=keyword_result.confidence,
            matched=f"hybrid:llm-{raw.intent.value}+kw-override-{keyword_result.matched}",
            alternates=tuple({raw.intent, *keyword_result.alternates} - {keyword_result.intent}),
            version=f"llm-{LLM_INTENT_VERSION}+kw-{_KEYWORD_VERSION}",
        )

    return IntentClassification(
        intent=raw.intent,
        confidence=raw.confidence,
        matched=f"llm:{raw.rationale}",
        alternates=(keyword_result.intent,) if keyword_result.intent is not raw.intent else (),
        version=f"llm-{LLM_INTENT_VERSION}+kw-{_KEYWORD_VERSION}",
    )


def _wrap_keyword_for_audit(
    keyword_result: IntentClassification,
    reason: str,
) -> IntentClassification:
    """Return the keyword result but tag the audit trail with WHY we fell back."""
    return IntentClassification(
        intent=keyword_result.intent,
        confidence=keyword_result.confidence,
        matched=f"{reason}:{keyword_result.matched}",
        alternates=keyword_result.alternates,
        version=f"llm-{LLM_INTENT_VERSION}+kw-{_KEYWORD_VERSION}",
    )


__all__ = [
    "LLM_INTENT_VERSION",
    "classify_intent_with_llm",
]
