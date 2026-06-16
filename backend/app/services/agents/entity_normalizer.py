"""Entity normalizer — maps fuzzy product/system mentions to canonical names.

Handles:
- Exact matches, aliases, and spelling variants
- Fuzzy substring matching for common typos
- Maps canonical names to issue categories for playbook routing
- Returns confidence-scored EntityMatch results
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SystemEntity:
    """A known IT system/product with metadata for routing."""

    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    category: str = "software/other"
    display_name: str = ""
    common_issues: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.canonical_name


@dataclass
class EntityMatch:
    """Result of entity normalization."""

    canonical_name: str
    display_name: str
    category: str
    matched_text: str
    confidence: float
    method: str  # "exact" | "alias" | "fuzzy"
    common_issues: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
#  ENTITY REGISTRY — canonical systems, aliases, and category mappings
# ══════════════════════════════════════════════════════════════════════

_SYSTEM_REGISTRY: list[SystemEntity] = [
    # ── Sixth Sense / Naukri ────────────────────────────────────────
    SystemEntity(
        canonical_name="sixth_sense",
        display_name="Sixth Sense (Naukri)",
        aliases=[
            "sixth sense", "sixthsense", "sixthsenses", "sixth senses",
            "6th sense", "6thsense", "sixth-sense", "naukri",
            "naukri.com", "naukhri", "naukarii", "naukree",
            "sixth sense portal", "sixth sense login",
            "ss portal", "naukri portal",
        ],
        category="access/permissions",
        common_issues=[
            "login-failure", "account-locked", "unhandled-message",
            "otp-issue", "password-reset", "blocked-account",
        ],
    ),
    # ── Microsoft Outlook / Email ───────────────────────────────────
    SystemEntity(
        canonical_name="outlook",
        display_name="Microsoft Outlook",
        aliases=[
            "outlook", "ms outlook", "microsoft outlook", "outlook365",
            "outlook 365", "outlook email", "hotmail", "o365 mail",
            "exchange", "office mail", "outlook web",
        ],
        category="email/outlook",
        common_issues=[
            "not-receiving-emails", "sending-failure", "outlook-slow",
            "outlook-crash", "calendar-sync", "sign-in-problem",
        ],
    ),
    # ── Zoom ────────────────────────────────────────────────────────
    SystemEntity(
        canonical_name="zoom",
        display_name="Zoom",
        aliases=[
            "zoom", "zoom meeting", "zoom call", "zoom app",
            "zoom video", "zoom client", "zoomm",
        ],
        category="video-conferencing/zoom",
        common_issues=[
            "no-audio", "no-video", "cant-join-meeting",
            "sign-in-issue", "screen-share-issue", "zoom-crash",
        ],
    ),
    # ── Microsoft Teams ─────────────────────────────────────────────
    SystemEntity(
        canonical_name="teams",
        display_name="Microsoft Teams",
        aliases=[
            "teams", "ms teams", "microsoft teams", "teams app",
            "teams meeting", "teams call",
        ],
        category="video-conferencing/zoom",
        common_issues=["no-audio", "no-video", "cant-join-meeting", "sign-in-issue"],
    ),
    # ── Intune / Company Portal ─────────────────────────────────────
    SystemEntity(
        canonical_name="intune",
        display_name="Microsoft Intune",
        aliases=[
            "intune", "ms intune", "microsoft intune", "company portal",
            "mdm", "device management", "device compliance",
        ],
        category="device-management/intune",
        common_issues=["non-compliant", "enrollment-failure", "sync-issue"],
    ),
    # ── VPN ─────────────────────────────────────────────────────────
    SystemEntity(
        canonical_name="vpn",
        display_name="VPN",
        aliases=[
            "vpn", "corporate vpn", "cisco vpn", "global protect",
            "globalprotect", "anyconnect", "pulse secure",
        ],
        category="network/connectivity",
        common_issues=["vpn-not-connecting", "vpn-slow", "vpn-disconnecting"],
    ),
    # ── Keka HR ─────────────────────────────────────────────────────
    SystemEntity(
        canonical_name="keka",
        display_name="Keka HR",
        aliases=["keka", "keka hr", "keka portal", "keka app"],
        category="software/other",
        common_issues=["login-failure", "app-crash", "performance-issue"],
    ),
    # ── FreshService ────────────────────────────────────────────────
    SystemEntity(
        canonical_name="freshservice",
        display_name="FreshService",
        aliases=[
            "freshservice", "fresh service", "freshdesk",
            "freshservice portal", "itsm",
        ],
        category="software/other",
        common_issues=["login-failure", "app-crash", "ticket-issue"],
    ),
    # ── 3CX / VoIP ─────────────────────────────────────────────────
    SystemEntity(
        canonical_name="3cx",
        display_name="3CX Phone System",
        aliases=["3cx", "3cx app", "voip", "softphone", "3cx phone"],
        category="network/connectivity",
        common_issues=["3cx-voip-issue", "no-audio", "cant-make-calls"],
    ),
]

# Pre-build lookup indexes for fast matching
_ALIAS_INDEX: dict[str, SystemEntity] = {}
for _entity in _SYSTEM_REGISTRY:
    _ALIAS_INDEX[_entity.canonical_name.lower()] = _entity
    for _alias in _entity.aliases:
        _ALIAS_INDEX[_alias.lower()] = _entity


# ══════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════


def normalize_entity(text: str) -> EntityMatch | None:
    """Attempt to recognize a known product/system in the user's text.

    Strategy (in order):
    1. Exact alias match (highest confidence)
    2. Substring alias match within the text
    3. Fuzzy match for common typos (edit-distance)

    Returns None if no system is recognized above the confidence threshold.
    """
    if not text or not text.strip():
        return None

    text_lower = text.lower().strip()

    # Phase 1: Exact match against full text
    if text_lower in _ALIAS_INDEX:
        entity = _ALIAS_INDEX[text_lower]
        return EntityMatch(
            canonical_name=entity.canonical_name,
            display_name=entity.display_name,
            category=entity.category,
            matched_text=text_lower,
            confidence=1.0,
            method="exact",
            common_issues=entity.common_issues,
        )

    # Phase 2: Substring match — check if any alias appears within the text
    best_substr: EntityMatch | None = None
    best_substr_len = 0

    for alias, entity in _ALIAS_INDEX.items():
        if len(alias) < 3:
            continue  # Skip very short aliases to avoid false positives
        # Word-boundary check: alias must appear as a whole phrase
        pattern = r"(?:^|\s|[^\w])" + re.escape(alias) + r"(?:\s|[^\w]|$)"
        if re.search(pattern, text_lower):
            if len(alias) > best_substr_len:
                best_substr_len = len(alias)
                best_substr = EntityMatch(
                    canonical_name=entity.canonical_name,
                    display_name=entity.display_name,
                    category=entity.category,
                    matched_text=alias,
                    confidence=0.9,
                    method="alias",
                    common_issues=entity.common_issues,
                )

    if best_substr:
        return best_substr

    # Phase 3: Fuzzy match — for typos like "sixthsenses" → "sixthsense"
    best_fuzzy: EntityMatch | None = None
    best_ratio = 0.0

    # Extract candidate words from text (2+ word combinations too)
    words = text_lower.split()
    candidates = list(words)
    for i in range(len(words) - 1):
        candidates.append(f"{words[i]} {words[i + 1]}")
        candidates.append(f"{words[i]}{words[i + 1]}")

    for candidate in candidates:
        if len(candidate) < 3:
            continue
        for alias, entity in _ALIAS_INDEX.items():
            if len(alias) < 3:
                continue
            ratio = SequenceMatcher(None, candidate, alias).ratio()
            if ratio > 0.75 and ratio > best_ratio:
                best_ratio = ratio
                best_fuzzy = EntityMatch(
                    canonical_name=entity.canonical_name,
                    display_name=entity.display_name,
                    category=entity.category,
                    matched_text=candidate,
                    confidence=round(ratio * 0.85, 2),
                    method="fuzzy",
                    common_issues=entity.common_issues,
                )

    if best_fuzzy and best_fuzzy.confidence >= 0.6:
        return best_fuzzy

    return None


def detect_issue_intent(text: str) -> dict[str, str | bool | None]:
    """Detect broad issue intent from user text.

    Returns a dict with keys:
    - intent: login | access | error | performance | crash | install | other
    - is_login_issue: bool
    - is_account_locked: bool
    - has_error_message: bool
    - has_otp_mention: bool
    """
    msg = text.lower()

    result: dict[str, str | bool | None] = {
        "intent": "other",
        "is_login_issue": False,
        "is_account_locked": False,
        "has_error_message": False,
        "has_otp_mention": False,
        "has_unhandled_message": False,
    }

    # Login / Access intent
    login_words = [
        "login", "log in", "log-in", "sign in", "signin", "sign-in",
        "unable to login", "can't login", "cannot login", "can not login",
        "unable to log in", "can't log in", "cannot log in",
        "unable to access", "can't access", "cannot access",
        "authentication", "credential",
    ]
    if any(w in msg for w in login_words):
        result["intent"] = "login"
        result["is_login_issue"] = True

    # Account locked
    lock_words = [
        "locked", "blocked", "disabled", "suspended",
        "account locked", "account blocked", "too many attempts",
        "incorrect password", "wrong password",
    ]
    if any(w in msg for w in lock_words):
        result["is_account_locked"] = True
        if result["intent"] == "other":
            result["intent"] = "access"

    # OTP
    otp_words = ["otp", "one time password", "verification code", "2fa", "mfa"]
    if any(w in msg for w in otp_words):
        result["has_otp_mention"] = True

    # Unhandled message (Sixth Sense specific)
    if "unhandled" in msg or "unhandled message" in msg:
        result["has_unhandled_message"] = True
        result["has_error_message"] = True

    # Error message
    error_words = [
        "error", "error message", "failed", "failure",
        "exception", "not working", "broken",
    ]
    if any(w in msg for w in error_words):
        result["has_error_message"] = True
        if result["intent"] == "other":
            result["intent"] = "error"

    # Performance
    perf_words = ["slow", "hanging", "frozen", "freezing", "taking too long"]
    if any(w in msg for w in perf_words):
        if result["intent"] == "other":
            result["intent"] = "performance"

    # Crash
    crash_words = ["crash", "crashing", "stopped working", "force close"]
    if any(w in msg for w in crash_words):
        if result["intent"] == "other":
            result["intent"] = "crash"

    return result


def get_all_entities() -> list[SystemEntity]:
    """Return all registered system entities."""
    return list(_SYSTEM_REGISTRY)
