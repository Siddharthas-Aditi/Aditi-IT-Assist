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
from app.services.agents.sentiment_analyzer import SentimentAnalyzerService
from app.services.agents.subtype_classifier import classify_subtype
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

# ── Feedback signal lists ─────────────────────────────────────────────────────
# Keep these comprehensive — humans are creative about expressing success/failure.

# Phrases that indicate the previously suggested steps did NOT work.
_NEGATIVE_FEEDBACK = (
    # Explicit failure
    "didn't work", "did not work", "doesn't work", "does not work",
    "not working", "not fixed", "not resolved", "not sorted",
    "still not working", "still not", "still the same", "same issue",
    "same problem", "no change", "nothing changed", "no difference",
    "no effect", "no luck", "not helping", "didn't help", "did not help",
    "that didn't help", "doesn't help", "no joy",
    # Persisting
    "still happening", "still broken", "still there", "issue persists",
    "problem persists", "still having", "still getting",
    "no it didn't", "no it did not", "nope",
    # Already attempted
    "tried that", "already tried", "tried that already", "done that already",
    "already done that", "i tried", "already done",
    # Confusion / can't follow steps
    "don't see that", "can't find that", "can't find it", "i don't see",
    "where is that", "can't find the option", "don't have that option",
    "can't see that tab", "there's no such option", "that option isn't there",
    # Worsened
    "made it worse", "now it's worse", "now worse", "it crashed",
)

# Phrases that indicate the issue IS resolved / found / closed.
_POSITIVE_FEEDBACK = (
    # Classic resolution
    "it worked", "that worked", "works now", "working now", "working fine",
    "it's fixed", "its fixed", "fixed it", "fixed now", "issue fixed",
    "that fixed it", "now it works", "it's working", "its working",
    # Resolved/sorted
    "resolved", "issue resolved", "problem resolved", "all resolved",
    "sorted", "sorted now", "sorted it", "sorted out", "problem solved",
    "all sorted", "that sorted it", "that sorted", "now sorted",
    # Good / OK
    "all good", "looks good", "all fine", "fine now", "ok now",
    "back to normal", "normal now", "back online", "it's back",
    # Found / located the issue (e.g. "found emails in junk")
    "found it", "found them", "found the emails", "found the issue",
    "found the problem", "got it", "got them", "i can see them",
    "can see them now", "they're there", "there they are", "there it is",
    "emails are showing", "mails are showing", "showing now", "showing up now",
    "in junk", "in spam", "mails in junk", "emails in junk",
    "mails are in junk", "emails are in junk", "found in junk",
    "mails are in spam", "emails are in spam", "they were in junk",
    # Progress / figured out
    "figured it out", "i see the issue", "i see what happened",
    "that explains it", "oh i see", "ah i see", "makes sense now",
    "i understand now", "that's why", "ah that's why",
    # Confirmatory closure
    "done", "all done", "completed", "finished",
    "that did it", "yes it worked", "yep that worked", "yeah that worked",
    "thanks that worked", "yes that resolved", "yes that fixed",
)

# Pure gratitude / closure phrases — when steps have already been given, these
# mean the user is done and satisfied, NOT a new problem to troubleshoot.
_GRATITUDE_WORDS = {
    "thank", "thanks", "thank you", "thankyou", "ty", "thx", "tq", "tysm",
    "many thanks", "thanks a lot", "thank you so much", "thanks so much",
    "cheers", "appreciated", "much appreciated", "great thanks", "great thank you",
    "thanks a bunch", "thank you very much", "thanks very much",
}


def _is_gratitude(text: str) -> bool:
    """True when the message is a short pure thank-you with no new issue content."""
    t = text.strip().lower().rstrip("!.? ")
    if not t:
        return False
    if t in _GRATITUDE_WORDS:
        return True
    words = [w for w in t.replace(",", " ").split() if w]
    filler = {"a", "so", "very", "lot", "much", "you", "for", "the", "help",
              "that", "this", "your", "assistance", "support"}
    if len(words) <= 6 and all(w in _GRATITUDE_WORDS or w in filler for w in words):
        return True
    return False


_NEGATION_PREFIXES = {"not", "no", "nope", "didn't", "did not", "hasn't", "haven't",
                      "doesn't", "isn't", "wasn't", "still not", "not yet", "never"}


def _is_negative_feedback(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _NEGATIVE_FEEDBACK)


def _is_positive_feedback(text: str) -> bool:
    """Return True only when a positive phrase is NOT immediately negated.

    Handles cases like 'not resolved', 'still not working', 'emails not in junk'.
    """
    t = text.lower()
    for phrase in _POSITIVE_FEEDBACK:
        idx = t.find(phrase)
        if idx == -1:
            continue
        prefix_words = t[:idx].strip().split()
        last_word = prefix_words[-1] if prefix_words else ""
        two_words = " ".join(prefix_words[-2:]) if len(prefix_words) >= 2 else last_word
        if last_word in _NEGATION_PREFIXES or two_words in _NEGATION_PREFIXES:
            continue  # negated — skip
        return True
    return False


# Greetings / small talk that should be met with a warm welcome, not triage.
_GREETING_WORDS = {
    "hi", "hii", "hiii", "hello", "helo", "hey", "hey", "hiya", "yo",
    "hi there", "hello there", "hey there", "good morning", "good afternoon",
    "good evening", "greetings", "howdy", "morning", "afternoon", "evening",
    "namaste", "hola", "sup", "whatsup", "what's up",
}

# Short affirmations / denials used when confirming our understanding.
_AFFIRM_WORDS = {
    "yes", "yep", "yeah", "yup", "ya", "yas", "correct", "right", "exactly",
    "perfect", "confirmed", "sure", "ok", "okay", "yise", "indeed", "absolutely",
}
_AFFIRM_PHRASES = (
    "that's right", "thats right", "that is correct", "that's correct",
    "thats correct", "you got it", "spot on", "yes please", "go ahead", "correct",
)
_DENY_WORDS = {"no", "nope", "nah", "wrong", "incorrect"}
_DENY_PHRASES = (
    "not exactly", "not right", "that's not", "thats not", "not correct",
    "not quite", "actually no", "that's wrong",
)


def _is_greeting(text: str) -> bool:
    t = text.strip().lower().rstrip("!.? ")
    if not t:
        return False
    if t in _GREETING_WORDS:
        return True
    # Short message that is just a greeting + filler (e.g. "hi there", "hello!!")
    words = [w for w in t.replace(",", " ").split() if w]
    return len(words) <= 3 and all(w in _GREETING_WORDS for w in words)


def _is_affirmation(text: str) -> bool:
    t = text.strip().lower().rstrip("!.? ")
    words = {w for w in t.replace(",", " ").split() if w}
    if words & _AFFIRM_WORDS:
        return True
    return any(p in t for p in _AFFIRM_PHRASES)


def _is_denial(text: str) -> bool:
    t = text.strip().lower().rstrip("!.? ")
    words = {w for w in t.replace(",", " ").split() if w}
    if words & _DENY_WORDS:
        return True
    return any(p in t for p in _DENY_PHRASES)

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

    # ── Step 0a: Post-resolution handling ────────────────────────
    # The previous issue was resolved. Two cases:
    # (a) User just says thanks — close warmly, no new triage.
    #     MUST happen before reset_issue_context() clears suggested_steps.
    # (b) User starts a genuinely new request — reset context so it's treated
    #     as a fresh issue, not a continuation of the old playbook.
    if diag_ctx.issue_resolved:
        if _is_gratitude(user_message):
            return _gratitude_close_message(diag_ctx)
        # Not gratitude → start fresh
        diag_ctx.reset_issue_context()

    # ── Step 0: Greeting / small talk (only when no issue is in flight) ──
    # A real analyst greets back and invites the problem — it does not jump to
    # "which system is affected?".
    in_active_issue = bool(
        diag_ctx.issue_category
        or diag_ctx.awaiting_confirmation
        or diag_ctx.suggested_steps
    )
    if not in_active_issue and _is_greeting(user_message):
        return _greeting_message(diag_ctx)

    # ── Step 1: Entity Normalization (every turn) ────────────────
    entity_match = normalize_entity(user_message)
    # Apply when: no system yet, a more confident match, OR a confident match for
    # a DIFFERENT system (a topic shift — even at equal confidence, e.g. one
    # 0.9 alias to another).
    switches_system = bool(
        entity_match
        and diag_ctx.normalized_system
        and entity_match.canonical_name != diag_ctx.normalized_system
        and entity_match.confidence >= 0.6
    )
    if entity_match and (
        not diag_ctx.normalized_system
        or entity_match.confidence > diag_ctx.entity_confidence
        or switches_system
    ):
        # Topic shift: the user switched to a different system. Drop the stale
        # issue context so the new problem is clarified and confirmed afresh.
        if (
            diag_ctx.normalized_system
            and entity_match.canonical_name != diag_ctx.normalized_system
            and entity_match.confidence >= 0.6
        ):
            logger.info(
                "topic_shift",
                from_system=diag_ctx.normalized_system,
                to_system=entity_match.canonical_name,
            )
            diag_ctx.reset_issue_context()
            diag_ctx.issue_category = None  # re-derived from the new entity below
        _apply_entity_match(diag_ctx, entity_match)
        logger.info(
            "entity_recognized",
            canonical=entity_match.canonical_name,
            matched=entity_match.matched_text,
            confidence=entity_match.confidence,
            method=entity_match.method,
        )

    # ── Step 1b: Sentiment Detection (every turn) ────────────────
    # Detect urgency, frustration, and confusion to tailor responses
    sentiment_analyzer = SentimentAnalyzerService(get_llm_service())
    sentiment = await sentiment_analyzer.analyze(user_message)
    diag_ctx.urgency = sentiment.urgency.value
    diag_ctx.business_impact = (
        "critical"
        if sentiment.urgency.value == "critical"
        else "high"
        if sentiment.urgency.value == "high"
        else "medium"
    )
    logger.info(
        "sentiment_detected",
        urgency=sentiment.urgency.value,
        frustration=sentiment.frustration.value,
        confusion=sentiment.confusion.value,
        confidence=sentiment.confidence,
    )

    # ── Step 2: Intent Detection (every turn) ────────────────────
    intent_result = detect_issue_intent(user_message)
    _apply_intent(diag_ctx, intent_result)

    # ── Step 2b: Resolution feedback handling ────────────────────
    # If we previously presented steps, interpret this turn as feedback before
    # treating it as a new problem. This drives progression and loop control.
    steps_were_given = bool(diag_ctx.suggested_steps) or (
        state.get("conversation_phase") == "confirming"
    )
    if steps_were_given and _is_positive_feedback(user_message):
        diag_ctx.issue_resolved = True
        diag_ctx.last_response_type = "resolved"
        diag_ctx.resolved_steps.extend(diag_ctx.suggested_steps)
        return _resolved_message(diag_ctx)

    # Pure gratitude after steps = user is satisfied; close gracefully.
    if steps_were_given and _is_gratitude(user_message):
        diag_ctx.issue_resolved = True
        diag_ctx.last_response_type = "resolved"
        return _gratitude_close_message(diag_ctx)

    if steps_were_given and _is_negative_feedback(user_message):
        diag_ctx.last_resolution_failed = True
        diag_ctx.mark_last_batch_failed()
        logger.info(
            "resolution_marked_failed",
            failed_count=len(diag_ctx.failed_steps),
            subtype=diag_ctx.issue_subtype,
        )

    # ── Step 2c: Understanding-confirmation response ─────────────
    # If we asked the user to confirm our understanding, interpret this turn as
    # their answer before treating it as new problem detail.
    if diag_ctx.awaiting_confirmation:
        if _is_affirmation(user_message):
            diag_ctx.awaiting_confirmation = False
            diag_ctx.understanding_confirmed = True
            logger.info("understanding_confirmed", subtype=diag_ctx.issue_subtype)
            # Fall through — we now proceed to retrieval/resolution this turn.
        elif _is_denial(user_message):
            # We misunderstood. Drop the assumed specifics and ask openly.
            diag_ctx.awaiting_confirmation = False
            diag_ctx.understanding_confirmed = False
            diag_ctx.symptom = None
            diag_ctx.issue_subtype = None
            diag_ctx.subtype_confidence = 0.0
            diag_ctx.issue_subcategory = None
            diag_ctx.exact_problem_statement = None
            return _open_clarification(diag_ctx)
        else:
            # The user gave more detail instead of yes/no — fold it in and
            # re-confirm with the updated understanding (handled below).
            diag_ctx.awaiting_confirmation = False

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

    # ── Step 3b: Subtype classification (deterministic, grounded) ─
    # Map the symptom onto a concrete subtype (e.g. "mailbox-full") so retrieval
    # and resolution target the right playbook instead of generic first-N steps.
    subtype_text = " ".join(
        p for p in (
            user_message,
            diag_ctx.exact_problem_statement or "",
            diag_ctx.symptom or "",
            diag_ctx.issue_subcategory or "",
        ) if p
    )
    subtype_match = classify_subtype(subtype_text, diag_ctx.issue_category)
    if subtype_match and subtype_match.confidence >= diag_ctx.subtype_confidence:
        subtype_changed = subtype_match.subtype != diag_ctx.issue_subtype
        diag_ctx.issue_subtype = subtype_match.subtype
        diag_ctx.subtype_confidence = subtype_match.confidence
        diag_ctx.issue_subcategory = subtype_match.subtype
        # Keep symptom aligned with the ACTIVE subtype.
        if subtype_changed or not diag_ctx.symptom:
            diag_ctx.symptom = subtype_match.subtype
        # A genuine topic move within the category resets prior tried-step memory
        # so the new subtype's playbook starts fresh.
        if subtype_changed and diag_ctx.suggested_steps:
            diag_ctx.suggested_steps = []
            diag_ctx.failed_steps = []
            diag_ctx.loop_counter = 0
        logger.info(
            "subtype_classified",
            subtype=subtype_match.subtype,
            confidence=subtype_match.confidence,
            matched=subtype_match.matched_keywords,
        )

    # ── Step 4: Playbook-guided clarification decision ───────────
    decision: ClarifyOrAnswerDecision = evaluate_clarify_or_answer(diag_ctx)

    # Never re-clarify when the user just told us the prior steps failed —
    # advance the troubleshooting flow instead of asking the same question.
    if decision.should_clarify and not diag_ctx.last_resolution_failed:
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
            "issue_subtype": diag_ctx.issue_subtype,
            "issue_resolved": False,
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

    # ── Step 5: Confirm understanding BEFORE solving ─────────────
    # We have enough context. Like a real analyst, restate what we think the
    # problem is and wait for the user to confirm before giving a solution.
    # Skipped once confirmed, and skipped while advancing after a failed step.
    if (
        not diag_ctx.understanding_confirmed
        and not diag_ctx.last_resolution_failed
    ):
        diag_ctx.awaiting_confirmation = True
        diag_ctx.last_response_type = "confirm"
        diag_ctx.phase = DiagnosticPhase.CLARIFYING
        question = _confirmation_message(diag_ctx)
        return {
            "current_node": "triage",
            "issue_category": diag_ctx.issue_category,
            "issue_subcategory": diag_ctx.issue_subcategory,
            "issue_subtype": diag_ctx.issue_subtype,
            "issue_resolved": False,
            "severity": state.get("severity") or _infer_severity(diag_ctx),
            "urgency": state.get("urgency") or _infer_urgency(diag_ctx),
            "needs_clarification": True,
            "clarification_question": question,
            "quick_replies": [
                {"label": "Yes, that's right", "value": "yes, that's right"},
                {"label": "No, not quite", "value": "no, not quite"},
            ],
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "messages": [AIMessage(content=question)],
            "audit_trail": [{
                "event": "triage.confirm_understanding",
                "category": diag_ctx.issue_category,
                "subtype": diag_ctx.issue_subtype,
            }],
        }

    diag_ctx.phase = DiagnosticPhase.DIAGNOSING

    audit_entry = {
        "event": "triage.classified",
        "category": diag_ctx.issue_category,
        "subcategory": diag_ctx.issue_subcategory,
        "subtype": diag_ctx.issue_subtype,
        "subtype_confidence": diag_ctx.subtype_confidence,
        "entity": diag_ctx.normalized_system,
        "symptom": diag_ctx.symptom,
        "resolution_failed_feedback": diag_ctx.last_resolution_failed,
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
        "issue_subtype": diag_ctx.issue_subtype,
        "issue_resolved": False,
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


def _resolved_message(diag_ctx: DiagnosticContext) -> dict:
    """Return a closing message when the user confirms the issue is resolved."""
    diag_ctx.phase = DiagnosticPhase.CONFIRMING
    content = (
        "Great — glad that resolved it! 🎉 "
        "If anything else comes up, just start a new chat and I'll be happy to help."
    )
    return {
        "current_node": "triage",
        "issue_category": diag_ctx.issue_category,
        "issue_subcategory": diag_ctx.issue_subcategory,
        "issue_subtype": diag_ctx.issue_subtype,
        "issue_resolved": True,
        "needs_clarification": False,
        "clarification_question": None,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": "resolved",
        "resolution_confirmed": True,
        "messages": [AIMessage(content=content)],
        "audit_trail": [{"event": "triage.resolved", "subtype": diag_ctx.issue_subtype}],
    }


def _gratitude_close_message(diag_ctx: DiagnosticContext) -> dict:
    """Return a warm closing when the user says thanks after receiving steps."""
    diag_ctx.phase = DiagnosticPhase.CONFIRMING
    content = (
        "You're welcome! 😊 Hope that helps sort things out. "
        "If you run into anything else, feel free to start a new chat — I'm always here."
    )
    return {
        "current_node": "triage",
        "issue_category": diag_ctx.issue_category,
        "issue_subcategory": diag_ctx.issue_subcategory,
        "issue_subtype": diag_ctx.issue_subtype,
        "issue_resolved": True,
        "needs_clarification": False,
        "clarification_question": None,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": "resolved",
        "resolution_confirmed": False,
        "messages": [AIMessage(content=content)],
        "audit_trail": [{"event": "triage.gratitude_close", "subtype": diag_ctx.issue_subtype}],
    }


# Natural, system-agnostic fragments describing each subtype, for the
# "let me confirm I understood" message.
_CONFIRM_FRAGMENTS: dict[str, str] = {
    "mailbox-full": "your mailbox is full",
    "not-receiving-emails": "you're not receiving emails",
    "sending-failure": "you can't send emails",
    "outlook-slow": "it's running slowly",
    "outlook-crash": "it won't open or keeps crashing",
    "offline-mode": "it's stuck offline",
    "calendar-sync": "your calendar isn't syncing",
    "search-not-working": "search isn't working",
    "sign-in-problem": "you can't sign in",
    "login-failure": "you're unable to log in",
    "account-locked": "your account is locked",
    "password-expired": "you need a password reset",
    "mfa-not-working": "your multi-factor sign-in isn't working",
    "otp-issue": "you're not receiving your OTP code",
    "unhandled-message": "you're seeing an 'Unhandled Message' error",
    "no-audio": "you can't hear any audio",
    "no-video": "your camera isn't working",
    "cant-join-meeting": "you can't join the meeting",
    "screen-share-issue": "screen sharing isn't working",
    "poor-quality": "the call quality is poor",
    # Network
    "vpn-not-connecting": "your VPN won't connect",
    "wifi-disconnecting": "your Wi-Fi keeps dropping",
    "internet-slow": "your internet is slow",
    "specific-site-unreachable": "you can't reach a particular site or app",
    "3cx-voip-issue": "you're having a VoIP/3CX issue",
    # Intune / device
    "non-compliant": "your device is showing as non-compliant",
    "enrollment-failure": "you can't enrol your device",
    # Camera / audio hardware
    "camera-not-detected": "your camera isn't being detected",
    "microphone-not-working": "your microphone isn't working",
}


def _confirmation_message(diag_ctx: DiagnosticContext) -> str:
    """A natural 'let me confirm I understood' question before solving."""
    system = diag_ctx.affected_system or "IT"
    subtype = (diag_ctx.issue_subtype or "").replace("_", "-").lower()
    detail = _CONFIRM_FRAGMENTS.get(subtype) or diag_ctx.exact_problem_statement
    if detail:
        return (
            f"Got it. Just to make sure I've understood your {system} issue correctly — "
            f"{detail}. Is that right? Once you confirm, I'll walk you through how to fix it."
        )
    return (
        f"Thanks. So I can help with your {system} issue — could you confirm I've "
        f"got the gist of it, and I'll talk you through the fix?"
    )


def _greeting_message(diag_ctx: DiagnosticContext) -> dict:
    """Warm greeting that invites the user to describe their issue."""
    content = (
        "Hi there! 👋 I'm the Aditi IT Support Assistant. I can help with things "
        "like Outlook and email, VPN and network, Zoom/Teams, hardware, and account "
        "or sign-in issues. What can I help you with today?"
    )
    return {
        "current_node": "triage",
        "needs_clarification": True,
        "clarification_question": content,
        "issue_category": None,
        "issue_subtype": None,
        "issue_resolved": False,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": "intake",
        "messages": [AIMessage(content=content)],
        "audit_trail": [{"event": "triage.greeting"}],
    }


def _open_clarification(diag_ctx: DiagnosticContext) -> dict:
    """Ask the user to describe the problem again after we misunderstood."""
    content = (
        "No problem — thanks for putting me right. Could you tell me a bit more "
        "about what's actually happening, so I can point you to the right fix?"
    )
    diag_ctx.clarification_count += 1
    diag_ctx.phase = DiagnosticPhase.CLARIFYING
    return {
        "current_node": "triage",
        "issue_category": diag_ctx.issue_category,
        "issue_subcategory": diag_ctx.issue_subcategory,
        "issue_subtype": diag_ctx.issue_subtype,
        "issue_resolved": False,
        "needs_clarification": True,
        "clarification_question": content,
        "quick_replies": None,
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "messages": [AIMessage(content=content)],
        "audit_trail": [{"event": "triage.understanding_rejected"}],
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
