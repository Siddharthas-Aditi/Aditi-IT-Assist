"""Issue subtype classification — deterministic, grounded sub-topic mapping.

The triage node classifies a broad *category* (e.g. ``email/outlook``). That is
not specific enough to retrieve the right knowledge: an "inbox full" problem and
a "can't sign in" problem live in the same category but need completely different
playbooks. Without a subtype, the resolver falls back to "first N steps of the
first article", which is how "my inbox is full" ended up being answered with
"check Work Offline / connect VPN" (or, worse, cross-domain password/Windows
Update advice leaking in from other articles).

This module maps a free-text symptom onto a concrete *subtype* using ordered,
weighted keyword rules. It is intentionally deterministic (no LLM dependency) so
it works in the keyword-only dev environment and is fully unit-testable. When an
LLM is available the triage node may still refine the subtype, but the rules
here are the floor that prevents cross-domain mistakes.

Design goals:
- Specific multi-word phrases beat generic single words ("inbox is full" beats
  a stray "full").
- Anti-keywords suppress false positives ("not full" should not match
  ``mailbox-full``).
- Returns the matched keywords for observability / debugging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubtypeRule:
    """A single subtype matching rule.

    ``keywords`` are matched as case-insensitive substrings against the
    normalized text. Multi-word phrases carry more weight automatically because
    they are stronger evidence. ``anti_keywords`` veto the rule entirely.
    """

    subtype: str
    keywords: tuple[str, ...]
    anti_keywords: tuple[str, ...] = ()
    base_weight: float = 1.0


@dataclass
class SubtypeMatch:
    """Result of subtype classification."""

    subtype: str
    confidence: float
    category: str
    matched_keywords: list[str] = field(default_factory=list)
    score: float = 0.0


# ======================================================================
#  RULE TABLES (per category)
# ======================================================================
#
# Order matters only for tie-breaking — the scorer prefers the highest score,
# then the earliest rule. Put the most specific / highest-signal subtypes first.

_OUTLOOK_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="mailbox-full",
        keywords=(
            "inbox is full",
            "inbox full",
            "mailbox is full",
            "mailbox full",
            "mailbox storage",
            "storage full",
            "storage is full",
            "out of space",
            "no space",
            "over quota",
            "quota",
            "over the limit",
            "over limit",
            "exceeded",
            "mailbox size",
            "mailbox is almost full",
            "almost full",
            "reduce mailbox",
            "clean up mailbox",
            "cleanup mailbox",
            "free up space",
            "98%",
            "99%",
            "100% full",
        ),
        anti_keywords=("not full", "isn't full", "is not full"),
    ),
    SubtypeRule(
        subtype="sending-failure",
        keywords=(
            "can't send",
            "cannot send",
            "can not send",
            "unable to send",
            "not sending",
            "won't send",
            "will not send",
            "stuck in outbox",
            "stuck in the outbox",
            "stuck in my outbox",
            "emails not going out",
            "send failed",
            "sending failed",
            "failed to send",
        ),
    ),
    SubtypeRule(
        subtype="not-receiving-emails",
        keywords=(
            "not receiving",
            "no new emails",
            "not getting emails",
            "not getting any emails",
            "emails not coming",
            "stopped receiving",
            "missing emails",
            "missing email",
            "no emails",
            "no incoming",
            "not coming through",
            "emails not arriving",
            "not arriving",
        ),
        anti_keywords=("inbox full", "mailbox full"),
    ),
    SubtypeRule(
        subtype="offline-mode",
        keywords=(
            "work offline",
            "working offline",
            "offline mode",
            "shows offline",
            "says offline",
            "disconnected from server",
            "outlook is offline",
        ),
    ),
    SubtypeRule(
        subtype="outlook-crash",
        keywords=(
            "crash",
            "crashing",
            "keeps closing",
            "keeps crashing",
            "won't open",
            "will not open",
            "not opening",
            "doesn't open",
            "closes by itself",
            "shuts down",
        ),
    ),
    SubtypeRule(
        subtype="outlook-slow",
        keywords=(
            "slow",
            "sluggish",
            "lagging",
            "laggy",
            "freezes",
            "freezing",
            "hangs",
            "hanging",
            "not responding",
            "takes forever",
            "very slow",
        ),
    ),
    SubtypeRule(
        subtype="calendar-sync",
        keywords=(
            "calendar",
            "meeting not showing",
            "appointment not showing",
            "calendar not syncing",
            "meetings missing",
            "invites not showing",
        ),
    ),
    SubtypeRule(
        subtype="search-not-working",
        keywords=(
            "search not working",
            "can't search",
            "cannot search",
            "search isn't",
            "search returns nothing",
            "search broken",
        ),
    ),
    SubtypeRule(
        subtype="rule-issue",
        keywords=(
            "mail rule",
            "email rule",
            "rules moving",
            "rule is moving",
            "auto move",
            "auto-move",
            "filter moving",
        ),
    ),
    SubtypeRule(
        subtype="addin-issue",
        keywords=("add-in", "add in", "addin", "plugin", "add-ins", "addins"),
    ),
    SubtypeRule(
        subtype="sign-in-problem",
        keywords=(
            "can't sign in",
            "cannot sign in",
            "can't log in",
            "cannot log in",
            "sign in",
            "sign-in",
            "signin",
            "login",
            "log in",
            "password prompt",
            "keeps asking for password",
            "authentication",
            "credentials",
        ),
    ),
)

# Access / login family — used to keep password/lockout advice OUT of email flows
# unless the user is genuinely in this category.
_ACCESS_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="account-locked",
        keywords=(
            "account locked",
            "account is locked",
            "locked out",
            "blocked",
            "account blocked",
            "too many attempts",
            "temporarily locked",
        ),
    ),
    SubtypeRule(
        subtype="password-expired",
        keywords=(
            "password expired",
            "reset password",
            "reset my password",
            "forgot password",
            "change password",
            "password reset",
        ),
    ),
    SubtypeRule(
        subtype="mfa-not-working",
        keywords=("mfa", "2fa", "two factor", "two-factor", "otp", "verification code"),
    ),
    SubtypeRule(
        subtype="access-denied-app",
        keywords=("access denied", "no access", "permission denied", "not authorized"),
    ),
    SubtypeRule(
        subtype="sso-failure",
        keywords=("sso", "single sign", "single sign-on"),
    ),
    SubtypeRule(
        subtype="unhandled-message",
        keywords=("unhandled message", "unhandled exception"),
    ),
    SubtypeRule(
        subtype="otp-issue",
        keywords=("otp not", "no otp", "didn't get otp", "otp not received", "code not received"),
    ),
    SubtypeRule(
        subtype="login-failure",
        keywords=(
            "unable to login",
            "unable to log in",
            "can't login",
            "cannot login",
            "can't log in",
            "cannot log in",
            "login failed",
            "login issue",
            "login problem",
            "can't sign in",
            "cannot sign in",
            "sign in",
            "sign-in",
            "login",
            "log in",
        ),
    ),
    # -- Ruddr ----------------------------------------------------------
    SubtypeRule(
        subtype="ruddr-account-missing",
        keywords=(
            "ruddr account missing",
            "no ruddr account",
            "ruddr not set up",
            "ruddr not created",
            "ruddr access",
            "no access to ruddr",
            "ruddr not working",
            "ruddr account not",
        ),
    ),
    SubtypeRule(
        subtype="ruddr-account-locked",
        keywords=(
            "ruddr locked",
            "ruddr disabled",
            "ruddr account locked",
            "ruddr account disabled",
            "ruddr blocked",
            "ruddr suspended",
        ),
    ),
    # -- New Joiner -----------------------------------------------------
    SubtypeRule(
        subtype="new-joiner-setup",
        keywords=(
            "new joiner",
            "just joined",
            "first day",
            "joining today",
            "email not created",
            "account not set up",
            "not provisioned",
            "onboarding",
            "new employee",
            "laptop not received",
            "tools not provisioned",
            "access on day one",
            "day 1",
        ),
    ),
    # -- License / Tool Access ------------------------------------------
    SubtypeRule(
        subtype="license-request",
        keywords=(
            "need license",
            "request license",
            "license request",
            "need access to",
            "requesting access",
            "tool access",
            "software license",
            "need copilot",
            "need github",
            "need linkedin recruiter",
            "need keeper",
            "need tool",
            "requesting tool",
            "software request",
        ),
    ),
    # -- Alias / Shared Mailbox -----------------------------------------
    SubtypeRule(
        subtype="shared-mailbox-access",
        keywords=(
            "shared mailbox",
            "shared inbox",
            "group mailbox",
            "can't access mailbox",
            "shared email",
            "functional mailbox",
            "team mailbox",
        ),
    ),
    SubtypeRule(
        subtype="alias-update",
        keywords=(
            "alias",
            "email alias",
            "add alias",
            "remove alias",
            "create alias",
            "secondary email",
            "smtp alias",
        ),
    ),
)

_ZOOM_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="no-audio",
        keywords=("no audio", "can't hear", "cannot hear", "no sound", "mic not", "microphone"),
    ),
    SubtypeRule(
        subtype="no-video", keywords=("camera not", "no video", "video not working", "webcam")
    ),
    SubtypeRule(
        subtype="cant-join-meeting",
        keywords=("can't join", "cannot join", "unable to join", "won't let me join"),
    ),
    SubtypeRule(
        subtype="screen-share-issue", keywords=("screen share", "screen sharing", "can't share")
    ),
    SubtypeRule(
        subtype="poor-quality",
        keywords=("poor quality", "choppy", "laggy", "freezing", "buffering"),
    ),
    SubtypeRule(subtype="zoom-crash", keywords=("crash", "crashing", "keeps closing")),
    SubtypeRule(subtype="sign-in-issue", keywords=("sign in", "sign-in", "login", "log in")),
)

_INTUNE_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="non-compliant",
        keywords=("non-compliant", "not compliant", "compliance", "device not compliant"),
    ),
    SubtypeRule(
        subtype="enrollment-failure",
        keywords=("enroll", "enrollment", "can't enroll", "enrollment failed"),
    ),
    SubtypeRule(subtype="sync-issue", keywords=("not syncing", "won't sync", "sync failed")),
    SubtypeRule(
        subtype="app-deployment",
        keywords=("app won't install", "app not installing", "company portal app"),
    ),
    SubtypeRule(
        subtype="conditional-access-blocked",
        keywords=("blocked from", "conditional access", "can't access office"),
    ),
)

_CAMERA_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(subtype="camera-black-screen", keywords=("black screen", "no image", "blank")),
    SubtypeRule(
        subtype="camera-not-detected",
        keywords=("not detected", "no camera found", "camera missing"),
    ),
    SubtypeRule(
        subtype="camera-permission-denied",
        keywords=("permission denied", "no permission", "blocked"),
    ),
    SubtypeRule(
        subtype="camera-in-use-by-another-app", keywords=("in use", "another app", "already in use")
    ),
    SubtypeRule(subtype="camera-poor-quality", keywords=("blurry", "poor quality", "grainy")),
)

_NETWORK_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="vpn-not-connecting",
        keywords=("vpn won't connect", "vpn not connecting", "can't connect to vpn", "vpn failed"),
    ),
    SubtypeRule(
        subtype="wifi-disconnecting", keywords=("wifi", "wi-fi", "keeps dropping", "disconnecting")
    ),
    SubtypeRule(
        subtype="internet-slow", keywords=("internet slow", "slow internet", "slow connection")
    ),
    SubtypeRule(
        subtype="specific-site-unreachable",
        keywords=("can't reach", "site not loading", "page won't load"),
    ),
    SubtypeRule(subtype="3cx-voip-issue", keywords=("3cx", "voip", "softphone")),
)

_AUDIO_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="voice-breaks-during-call",
        keywords=(
            "voice breaks",
            "voice breaking",
            "audio cutting",
            "cutting out",
            "audio drops",
            "voice drops",
            "choppy audio",
            "breaking up",
            "robotic voice",
            "voice is breaking",
            "breaks during call",
            "audio breaking",
            "sound cutting",
            "voice cutting",
        ),
    ),
    SubtypeRule(
        subtype="candidate-cannot-hear",
        keywords=(
            "candidate cannot hear",
            "candidate can't hear",
            "they can't hear me",
            "no one can hear",
            "they can't hear",
            "other person can't hear",
            "interviewer can't hear",
            "candidate cannot hear me",
            "can't hear me",
            "cannot hear me",
        ),
    ),
    SubtypeRule(
        subtype="no-audio-output",
        keywords=("no sound", "no audio", "can't hear anything", "speakers not"),
    ),
    SubtypeRule(
        subtype="microphone-not-working",
        keywords=("mic not working", "microphone not", "mic isn't", "mic not detected"),
    ),
    SubtypeRule(
        subtype="headset-not-detected",
        keywords=("headset not detected", "headset not", "headphones not"),
    ),
    SubtypeRule(subtype="audio-crackling", keywords=("crackling", "static", "distorted")),
    SubtypeRule(subtype="bluetooth-audio-issue", keywords=("bluetooth", "won't pair")),
)

_LAPTOP_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="battery-not-charging",
        keywords=(
            "not charging",
            "won't charge",
            "wont charge",
            "battery not charging",
            "plugged in not charging",
            "not charging when plugged",
            "battery stuck",
            "battery percentage not",
        ),
    ),
    SubtypeRule(
        subtype="laptop-wont-power-on",
        keywords=(
            "won't turn on",
            "wont turn on",
            "not turning on",
            "won't power on",
            "wont power on",
            "not powering on",
            "won't boot",
            "wont boot",
            "no display",
            "does not turn on",
            "doesn't turn on",
            "dead laptop",
            "power button",
        ),
        anti_keywords=("monitor", "external"),
    ),
    SubtypeRule(
        subtype="external-monitor-not-detected",
        keywords=(
            "external monitor",
            "second monitor",
            "second screen",
            "monitor not detected",
            "monitor not detecting",
            "display not detected",
            "dual monitor",
            "extend display",
            "hdmi not",
            "docking station monitor",
        ),
    ),
    SubtypeRule(
        subtype="keyboard-not-working",
        keywords=(
            "keyboard not working",
            "keyboard is not working",
            "keyboard not responding",
            "keys not responding",
            "keys not working",
            "typing wrong",
            "wrong characters",
            "keyboard stopped",
            "keys stuck",
            "keyboard isn't",
        ),
        anti_keywords=("on-screen keyboard works",),
    ),
    SubtypeRule(
        subtype="trackpad-not-working",
        keywords=(
            "trackpad",
            "track pad",
            "touchpad",
            "cursor moving",
            "cursor jumping",
            "cursor keeps jumping",
            "gestures not",
            "pad not responding",
        ),
    ),
)

_PERFORMANCE_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="slow-performance",
        keywords=(
            "slow",
            "very slow",
            "running slow",
            "laggy",
            "lagging",
            "freezing",
            "freezes",
            "hangs",
            "sluggish",
            "takes forever",
            "poor performance",
        ),
    ),
)

_WINDOWS_UPDATE_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="windows-update-failure",
        keywords=(
            "windows update",
            "update failed",
            "update stuck",
            "update error",
            "won't update",
            "update not installing",
            "stuck installing update",
            "check for updates",
            "install updates",
            "update loop",
        ),
    ),
)

# Combined catch-all for the generic "hardware/other" bucket so it no longer
# aliases audio-only rules (the old cross-family misclassification bug).
_HARDWARE_OTHER_RULES: tuple[SubtypeRule, ...] = _LAPTOP_RULES + _AUDIO_RULES + _CAMERA_RULES

# Map a normalized category to its rule table.
_CATEGORY_RULES: dict[str, tuple[SubtypeRule, ...]] = {
    "email/outlook": _OUTLOOK_RULES,
    "access/permissions": _ACCESS_RULES,
    "access/sixth_sense": _ACCESS_RULES,
    "access/ruddr": _ACCESS_RULES,
    "video-conferencing/zoom": _ZOOM_RULES,
    "video-conferencing/teams": _ZOOM_RULES,
    "device-management/intune": _INTUNE_RULES,
    "hardware/camera": _CAMERA_RULES,
    "hardware/audio": _AUDIO_RULES,
    "hardware/laptop": _LAPTOP_RULES,
    "hardware/other": _HARDWARE_OTHER_RULES,
    "system/performance": _PERFORMANCE_RULES,
    "software/windows-update": _WINDOWS_UPDATE_RULES,
    "network/connectivity": _NETWORK_RULES,
    "software/other": _ACCESS_RULES,
}


def _normalize(text: str) -> str:
    """Lowercase and collapse punctuation/whitespace for stable matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9%\s'\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_subtype(text: str, category: str | None) -> SubtypeMatch | None:
    """Classify the issue subtype within a category from free text.

    Args:
        text: The user's free-text symptom description (any turn's content).
        category: The broad issue category already identified by triage.

    Returns:
        The best ``SubtypeMatch`` or ``None`` if nothing matched / no rules
        exist for the category. ``None`` means "stay generic" -- the caller
        should then ask a clarifying question rather than guess.
    """
    if not category:
        return None
    rules = _CATEGORY_RULES.get(category)
    if not rules:
        return None

    norm = _normalize(text)
    if not norm:
        return None

    best: SubtypeMatch | None = None
    for rule in rules:
        if any(anti in norm for anti in rule.anti_keywords):
            continue

        matched: list[str] = []
        score = 0.0
        for kw in rule.keywords:
            if kw in norm:
                matched.append(kw)
                # Multi-word phrases are stronger signals than single words.
                word_count = kw.count(" ") + 1
                score += rule.base_weight * (1.0 + 0.6 * (word_count - 1))

        if not matched:
            continue

        # Confidence grows with evidence strength but is capped -- a single
        # generic word should stay in the "medium" band, while a specific
        # multi-word phrase reaches "high".
        confidence = min(0.95, 0.55 + 0.18 * score)
        if best is None or score > best.score:
            best = SubtypeMatch(
                subtype=rule.subtype,
                confidence=round(confidence, 3),
                category=category,
                matched_keywords=matched,
                score=round(score, 3),
            )

    return best


def known_subtypes(category: str | None) -> list[str]:
    """Return the list of subtypes the classifier knows for a category."""
    if not category:
        return []
    return [r.subtype for r in _CATEGORY_RULES.get(category, ())]
