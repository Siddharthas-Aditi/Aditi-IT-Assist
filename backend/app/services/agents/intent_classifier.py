"""Conversational intent classification.

This module gives the chat workflow a **typed, versioned, deterministic** view of
what the user is *doing* with their message — independent of the IT issue
classification (which entity, which subtype). It is the missing layer that lets
the agent behave like a real analyst: tell apart "yes, fix that" from "I have
another problem" from "talk to a human" from "thanks, all sorted".

Why this exists
---------------
The old chat workflow conflated three different signals:

1. Whether the message describes a new IT *issue* (handled by triage / entity).
2. Whether the user is providing *feedback* on the steps we just gave them.
3. Whether the user wants to *navigate* the conversation (new topic, escalate,
   small-talk, end the chat).

When (2) and (3) bled into (1), broad substring matching like
``"help" in user_message`` could mark an unrelated message as
"escalation_confirmed=True" and silently spawn a ticket. The reproducer that
prompted this module: after a resolved mailbox-full flow, the user typed
"I have another problem" and the workflow created ticket ITA-000007 instead
of asking what the new issue was.

Contract
--------
``classify_intent(message, *, has_active_issue, awaiting_confirmation,
steps_given)`` returns an :class:`IntentClassification` with:

- ``intent``  — the single best :class:`ConversationIntent` for this turn
- ``confidence``  — 0..1 deterministic score
- ``matched``  — the rule/keyword that matched (for the debug trace)
- ``version``  — classifier version (bump on every rule change so analytics
  joins remain reproducible)

Design notes
------------
* **Deterministic first.** All decisions are pure-function rule matches on the
  normalized message; no LLM call. This keeps the layer cheap, testable, and
  predictable in CI / golden conversations.
* **Context-aware.** The same words mean different things mid-flow vs at the
  start (e.g. "yes" right after a confirm-understanding question is `CONFIRM`;
  on a fresh session it's `CONTINUE`). The caller passes the relevant context
  flags rather than the classifier reaching into shared state.
* **Single intent per turn.** We return the highest-priority match; the priority
  order is encoded in :data:`_PRIORITY` and is the contract the workflow
  depends on.
* **No silent expansions.** Adding a new keyword bumps :data:`CLASSIFIER_VERSION`;
  golden-conversation tests pin the version they were authored against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

# Bump on every change to the rules or priorities below. Golden-conversation
# tests record this so a behavior shift is visible in diff review.
CLASSIFIER_VERSION = "1.0.0"


class ConversationIntent(StrEnum):
    """What the user is *doing* with this turn, independent of IT classification.

    These are the conversational moves the agent must distinguish to respond
    naturally. They are deliberately coarse — sub-classification (which IT
    issue, which subtype) belongs to the entity/subtype layers, not here.
    """

    # The user is starting a new, unrelated issue mid-conversation.
    # Example: "I have another problem", "different issue now", "wait, also".
    # Workflow MUST reset the diagnostic context before triage runs.
    NEW_TOPIC = "new_topic"

    # The user is answering "yes" to something the agent asked (confirm
    # understanding, accept escalation, continue).
    CONFIRM = "confirm"

    # The user is answering "no" / pushing back on the agent's assumption.
    DENY = "deny"

    # The user is reporting that the steps we suggested did NOT work.
    NEGATIVE_FEEDBACK = "negative_feedback"

    # The user is reporting that the steps we suggested DID work / issue fixed.
    POSITIVE_FEEDBACK = "positive_feedback"

    # The user is explicitly asking for a human / ticket / specialist.
    ESCALATE_REQUEST = "escalate_request"

    # Greeting at the start of a session ("hi", "hello").
    GREETING = "greeting"

    # Pure thank-you / wrap-up after help was given.
    GRATITUDE = "gratitude"

    # User wants the agent to repeat / simplify the previous explanation.
    REPEAT_OR_SIMPLIFY = "repeat_or_simplify"

    # Off-topic chit-chat that doesn't fit any of the above and isn't an issue
    # description either ("how are you", "lol", "ok cool").
    SMALL_TALK = "small_talk"

    # Default: the message contributes to the active issue (problem detail,
    # follow-up info, new symptom). Triage handles it from here.
    CONTINUE = "continue"


@dataclass(frozen=True)
class IntentClassification:
    """A single classification result with provenance for the debug trace."""

    intent: ConversationIntent
    confidence: float
    matched: str = ""  # the keyword / rule label that triggered the match
    version: str = CLASSIFIER_VERSION
    # Secondary intents that also matched, in priority order. Useful for
    # observability and for callers who want to disambiguate (e.g. "yes,
    # connect me" matches both CONFIRM and ESCALATE_REQUEST).
    alternates: tuple[ConversationIntent, ...] = field(default_factory=tuple)


# ── Rule data ────────────────────────────────────────────────────────────────
# Keep each set focused. Negation handling is performed separately so we don't
# need to enumerate negated variants.

# Explicit "I'm switching topic" phrases. These are the **distinguishing**
# markers — anything more ambiguous (e.g. bare "also") must NOT be here, since
# false-positives drop the user's active diagnostic context.
_NEW_TOPIC_PHRASES: tuple[str, ...] = (
    "another problem", "an another problem", "another issue", "another question",
    "different problem", "different issue", "different question", "new problem",
    "new issue", "new question", "one more problem", "one more issue",
    "one more question", "one more thing", "something else",
    "i have another", "i've got another", "ive got another",
    "i have a different", "i have a new",
    "also having", "also having an issue", "also have an issue",
    "another thing", "by the way i", "btw i have",
    "switch topic", "change topic", "unrelated", "separate issue",
    "next problem", "next issue",
)

# Asking the agent to repeat / simplify (NOT a new problem).
_SIMPLIFY_PHRASES: tuple[str, ...] = (
    "explain again", "say that again", "can you repeat", "repeat that",
    "didn't get that", "didn't catch that", "don't follow", "i don't follow",
    "simpler", "simpler explanation", "easier", "easier way", "break it down",
    "step by step", "step-by-step", "in plain english", "plain english",
    "can you simplify", "simplify that", "more clearly", "more detail",
    "not clear", "unclear", "i'm confused", "im confused", "i am confused",
    "confusing",
)

# Explicit human / ticket request.
_ESCALATE_PHRASES: tuple[str, ...] = (
    "connect me with a specialist", "connect me with a human", "connect me with an agent",
    "connect with a specialist", "connect with a human", "connect with an agent",
    "connect to a specialist", "connect to a human",
    "talk to a human", "talk to a person", "talk to a specialist",
    "talk to an agent", "talk to someone", "speak to a human",
    "speak to a person", "speak to a specialist", "speak to an agent",
    "speak to someone",
    "create a ticket", "raise a ticket", "open a ticket", "log a ticket",
    "file a ticket", "create ticket", "raise ticket",
    "i need a human", "i want a human", "i'd like a human",
    "i need help from", "escalate this", "escalate to",
    "real person", "live agent", "live person", "it team",
    "human support", "human agent",
)
# Single-word escalation tokens (require whole-word match to avoid matching
# "another" → "agent" → false positive).
_ESCALATE_WORDS: frozenset[str] = frozenset({
    "escalate", "specialist", "agent", "human",
})

# Affirmation tokens for use ONLY when the agent just asked yes/no.
_AFFIRM_WORDS: frozenset[str] = frozenset({
    "yes", "yep", "yeah", "yup", "ya", "yas", "correct", "right",
    "exactly", "perfect", "confirmed", "sure", "ok", "okay", "indeed",
    "absolutely", "affirmative", "fine", "alright",
})
_AFFIRM_PHRASES: tuple[str, ...] = (
    "that's right", "thats right", "that is correct", "that's correct",
    "thats correct", "you got it", "spot on", "yes please", "go ahead",
    "please do", "do it", "sounds good", "sounds great",
)

_DENY_WORDS: frozenset[str] = frozenset({"no", "nope", "nah", "wrong", "incorrect", "negative"})
_DENY_PHRASES: tuple[str, ...] = (
    "not exactly", "not right", "that's not", "thats not", "not correct",
    "not quite", "actually no", "that's wrong", "thats wrong",
    "not really", "not what i meant",
)

_GREETING_WORDS: frozenset[str] = frozenset({
    "hi", "hii", "hiii", "hello", "helo", "hey", "hiya", "yo",
    "howdy", "morning", "afternoon", "evening", "greetings",
    "namaste", "hola", "sup",
})
_GREETING_PHRASES: tuple[str, ...] = (
    "hi there", "hello there", "hey there", "good morning",
    "good afternoon", "good evening", "what's up", "whats up",
)

_GRATITUDE_WORDS: frozenset[str] = frozenset({
    "thanks", "thank", "thankyou", "ty", "thx", "tq", "tysm",
    "cheers", "appreciated",
})
_GRATITUDE_PHRASES: tuple[str, ...] = (
    "thank you", "thank you so much", "thanks so much", "thanks a lot",
    "thanks a bunch", "many thanks", "much appreciated", "thanks very much",
    "thank you very much", "really appreciate",
)

# Negative feedback phrases (the steps did not work).
_NEGATIVE_FEEDBACK_PHRASES: tuple[str, ...] = (
    "didn't work", "did not work", "doesn't work", "does not work",
    "not working", "not fixed", "not resolved", "not sorted",
    "still not working", "still not", "still the same", "same issue",
    "same problem", "no change", "nothing changed", "no difference",
    "no effect", "no luck", "not helping", "didn't help", "did not help",
    "that didn't help", "doesn't help", "no joy",
    "still happening", "still broken", "still there", "issue persists",
    "problem persists", "still having", "still getting",
    "tried that", "already tried", "tried that already", "done that already",
    "already done that", "don't see that", "can't find that", "can't find it",
    "don't have that option", "made it worse", "now it's worse",
)

# Positive feedback phrases (the steps worked / problem resolved).
_POSITIVE_FEEDBACK_PHRASES: tuple[str, ...] = (
    "it worked", "that worked", "works now", "working now", "working fine",
    "it's fixed", "its fixed", "fixed it", "fixed now", "issue fixed",
    "that fixed it", "now it works", "it's working", "its working",
    "resolved", "issue resolved", "problem resolved", "all resolved",
    "sorted", "sorted now", "sorted it", "sorted out", "problem solved",
    "all sorted", "that sorted it", "now sorted",
    "all good", "looks good", "all fine", "fine now", "ok now",
    "back to normal", "normal now", "back online", "it's back",
    "found it", "found them", "found the emails", "found the issue",
    "got it", "got them", "i can see them", "can see them now",
    "showing now", "showing up now",
    "figured it out", "that did it", "yes it worked", "yep that worked",
    "thanks that worked", "yes that resolved", "yes that fixed",
)

# Negation prefixes to recognize "not resolved", "still not working", etc.
_NEGATION_PREFIXES: frozenset[str] = frozenset({
    "not", "no", "nope", "didn't", "did not", "hasn't", "haven't",
    "doesn't", "isn't", "wasn't", "still not", "not yet", "never",
})

# Small-talk fillers — short utterances with no actionable content.
_SMALL_TALK_PHRASES: tuple[str, ...] = (
    "how are you", "how's it going", "hows it going", "what can you do",
    "who are you", "what are you", "are you a bot", "are you human",
    "lol", "haha", "hmm", "hm", "interesting", "i see", "got it",
    "ok cool", "okay cool", "alright cool", "cool", "nice", "great",
)

# Priority order — highest priority intent wins when multiple match.
# Rationale: explicit human-facing navigation (escalate, new topic) beats
# feedback / continuation, because misclassifying those as CONTINUE silently
# loses user intent. CONFIRM beats GREETING because a one-word "ok" mid-flow
# means yes, not hello.
_PRIORITY: tuple[ConversationIntent, ...] = (
    ConversationIntent.ESCALATE_REQUEST,
    ConversationIntent.NEW_TOPIC,
    ConversationIntent.NEGATIVE_FEEDBACK,
    ConversationIntent.POSITIVE_FEEDBACK,
    ConversationIntent.REPEAT_OR_SIMPLIFY,
    ConversationIntent.DENY,
    ConversationIntent.CONFIRM,
    ConversationIntent.GRATITUDE,
    ConversationIntent.GREETING,
    ConversationIntent.SMALL_TALK,
    ConversationIntent.CONTINUE,
)


# ── Pure helpers ────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lower-case, strip surrounding punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", text)}


def _has_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    """Return the first phrase from ``phrases`` that appears in ``text``, else None."""
    for p in phrases:
        if p in text:
            return p
    return None


def _phrase_not_negated(text: str, phrase: str) -> bool:
    """True iff ``phrase`` occurs in ``text`` AND is not immediately negated.

    Catches "not resolved", "still not working", "didn't fix it". The check
    looks one and two tokens back; that's sufficient for the negation patterns
    English support tickets use in practice.
    """
    idx = text.find(phrase)
    if idx == -1:
        return False
    prefix_tokens = text[:idx].strip().split()
    last = prefix_tokens[-1] if prefix_tokens else ""
    last_two = " ".join(prefix_tokens[-2:]) if len(prefix_tokens) >= 2 else last
    return last not in _NEGATION_PREFIXES and last_two not in _NEGATION_PREFIXES


# ── Individual detectors (each returns ``(matched_label, confidence)`` or None)

def _detect_new_topic(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _NEW_TOPIC_PHRASES)
    if p:
        return (p, 0.95)
    return None


def _detect_simplify(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _SIMPLIFY_PHRASES)
    if p:
        return (p, 0.9)
    return None


def _detect_escalate(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _ESCALATE_PHRASES)
    if p:
        return (p, 0.95)
    tokens = _token_set(text)
    hits = tokens & _ESCALATE_WORDS
    if hits:
        # Whole-word match — "agent" is in the message as its own token.
        return (next(iter(hits)), 0.85)
    return None


def _detect_negative_feedback(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _NEGATIVE_FEEDBACK_PHRASES)
    if p:
        return (p, 0.9)
    return None


def _detect_positive_feedback(text: str) -> tuple[str, float] | None:
    for p in _POSITIVE_FEEDBACK_PHRASES:
        if p in text and _phrase_not_negated(text, p):
            return (p, 0.9)
    return None


def _detect_gratitude(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _GRATITUDE_PHRASES)
    if p:
        return (p, 0.95)
    tokens = _token_set(text)
    if tokens & _GRATITUDE_WORDS:
        # Short pure-thanks message ("thanks!", "ty so much")
        filler = {"a", "so", "very", "lot", "much", "you", "for", "the",
                  "help", "that", "this", "your", "assistance", "support"}
        if len(tokens) <= 6 and all(t in _GRATITUDE_WORDS or t in filler for t in tokens):
            return ("thanks", 0.9)
    return None


def _detect_greeting(text: str) -> tuple[str, float] | None:
    if _has_phrase(text, _GREETING_PHRASES):
        return ("greeting-phrase", 0.95)
    tokens = _token_set(text)
    if tokens and tokens <= _GREETING_WORDS:
        return (next(iter(tokens)), 0.95)
    return None


def _detect_confirm(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _AFFIRM_PHRASES)
    if p:
        return (p, 0.95)
    tokens = _token_set(text)
    # Strict: a bare affirmation token wins only if the WHOLE message is
    # affirmation tokens (short reply like "yes" or "yes please"). This
    # prevents "ok cool" or "yes that didn't work" from being misread.
    if tokens and tokens <= _AFFIRM_WORDS:
        return (next(iter(tokens)), 0.9)
    return None


def _detect_deny(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _DENY_PHRASES)
    if p:
        return (p, 0.9)
    tokens = _token_set(text)
    if tokens and tokens <= _DENY_WORDS:
        return (next(iter(tokens)), 0.9)
    return None


def _detect_small_talk(text: str) -> tuple[str, float] | None:
    p = _has_phrase(text, _SMALL_TALK_PHRASES)
    if p:
        return (p, 0.7)
    return None


# ── Public API ──────────────────────────────────────────────────────────────


def classify_intent(
    message: str,
    *,
    has_active_issue: bool = False,
    awaiting_confirmation: bool = False,
    steps_given: bool = False,
    issue_resolved: bool = False,
) -> IntentClassification:
    """Classify a user message into a :class:`ConversationIntent`.

    Args:
        message: Raw user text for this turn.
        has_active_issue: True if a diagnostic context with an issue category
            is already populated for the session.
        awaiting_confirmation: True iff the previous agent turn asked the user
            a yes/no question. Promotes CONFIRM/DENY when set; demotes them
            when not (so a bare "yes" on first turn is CONTINUE, not CONFIRM).
        steps_given: True iff we already presented troubleshooting steps in
            this issue. Promotes positive/negative-feedback recognition.
        issue_resolved: True iff the user already confirmed the prior issue
            was fixed. NEW_TOPIC is strongly expected when this is set.

    Returns:
        An :class:`IntentClassification`. ``intent`` is the single best match;
        ``alternates`` lists secondary matches in priority order.

    The function is pure: no IO, no exceptions for normal input. Empty / blank
    input returns ``SMALL_TALK`` with low confidence (the agent should ask the
    user to say more).
    """
    norm = _normalize(message)
    if not norm:
        return IntentClassification(
            intent=ConversationIntent.SMALL_TALK,
            confidence=0.2,
            matched="empty",
        )

    # Strip trailing punctuation for cleaner phrase matches.
    norm = norm.rstrip(".!?,;: ")

    # Run every detector. Each returns (matched_label, confidence) or None.
    detections: dict[ConversationIntent, tuple[str, float]] = {}

    if hit := _detect_new_topic(norm):
        detections[ConversationIntent.NEW_TOPIC] = hit
    if hit := _detect_escalate(norm):
        detections[ConversationIntent.ESCALATE_REQUEST] = hit
    if hit := _detect_simplify(norm):
        detections[ConversationIntent.REPEAT_OR_SIMPLIFY] = hit
    if steps_given:
        if hit := _detect_negative_feedback(norm):
            detections[ConversationIntent.NEGATIVE_FEEDBACK] = hit
        if hit := _detect_positive_feedback(norm):
            detections[ConversationIntent.POSITIVE_FEEDBACK] = hit
    if hit := _detect_gratitude(norm):
        detections[ConversationIntent.GRATITUDE] = hit
    if hit := _detect_greeting(norm):
        detections[ConversationIntent.GREETING] = hit
    if awaiting_confirmation:
        if hit := _detect_confirm(norm):
            detections[ConversationIntent.CONFIRM] = hit
        if hit := _detect_deny(norm):
            detections[ConversationIntent.DENY] = hit
    if hit := _detect_small_talk(norm):
        detections[ConversationIntent.SMALL_TALK] = hit

    # Context-dependent demotions / promotions ────────────────────────
    # If an issue is in flight and the user types something that looks like
    # a greeting ("hey"), keep it as CONTINUE — they're not starting fresh.
    # Exception: explicit NEW_TOPIC always wins.
    if (
        has_active_issue
        and ConversationIntent.GREETING in detections
        and ConversationIntent.NEW_TOPIC not in detections
        and ConversationIntent.ESCALATE_REQUEST not in detections
    ):
        detections.pop(ConversationIntent.GREETING, None)

    # If the prior issue was already resolved and the user is now writing more
    # than a small ack, lean toward NEW_TOPIC (unless they explicitly thanked).
    if issue_resolved and ConversationIntent.GRATITUDE not in detections:
        # 4+ tokens after a resolved issue: probably a new request.
        tokens = _token_set(norm)
        if (
            len(tokens) >= 4
            and ConversationIntent.NEW_TOPIC not in detections
            and ConversationIntent.ESCALATE_REQUEST not in detections
        ):
            detections[ConversationIntent.NEW_TOPIC] = ("post-resolution-new-issue", 0.7)

    # Resolve by priority ────────────────────────────────────────────
    for candidate in _PRIORITY:
        if candidate in detections:
            label, conf = detections[candidate]
            alternates = tuple(
                i for i in _PRIORITY if i in detections and i is not candidate
            )
            return IntentClassification(
                intent=candidate,
                confidence=conf,
                matched=label,
                alternates=alternates,
            )

    # Nothing matched → user is continuing the active flow (problem detail,
    # answer to a slot question, etc.). Triage handles it from here.
    return IntentClassification(
        intent=ConversationIntent.CONTINUE,
        confidence=0.5,
        matched="default",
    )


__all__ = [
    "CLASSIFIER_VERSION",
    "ConversationIntent",
    "IntentClassification",
    "classify_intent",
]
