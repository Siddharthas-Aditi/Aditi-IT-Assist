"""Parser profile registry.

Profiles are registered here.  Detection logic selects the most appropriate
profile for an uploaded document automatically.  A human can also override
the profile explicitly via the API.

Adding a new profile:
1. Create ``profiles/my_new_profile.py``
2. Import and register it here
3. No changes to any extraction code needed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.ingestion.profiles.it_support import IT_SUPPORT_PROFILE

if TYPE_CHECKING:
    from app.services.ingestion.profiles.base import ParserProfile

logger = logging.getLogger(__name__)

# ── Profile registry ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, ParserProfile] = {
    IT_SUPPORT_PROFILE.name: IT_SUPPORT_PROFILE,
}

DEFAULT_PROFILE_NAME = IT_SUPPORT_PROFILE.name


def register_profile(profile: ParserProfile) -> None:
    """Register a new profile.  Overwrites if the name already exists."""
    _REGISTRY[profile.name] = profile
    logger.info("Registered parser profile: %s v%s", profile.name, profile.version)


def get_profile(name: str) -> ParserProfile:
    """Return the named profile, falling back to the default."""
    profile = _REGISTRY.get(name)
    if profile is None:
        logger.warning("Unknown parser profile '%s'; falling back to default.", name)
        return _REGISTRY[DEFAULT_PROFILE_NAME]
    return profile


def list_profiles() -> list[str]:
    """Return names of all registered profiles."""
    return list(_REGISTRY.keys())


def detect_profile(text: str) -> ParserProfile:
    """Auto-detect the best profile for *text* using detection criteria.

    Each profile specifies keyword_signals and min_keyword_matches.
    The profile with the most keyword hits wins.  Falls back to default
    if no profile meets its threshold.
    """
    text_lower = text.lower()
    best_name = DEFAULT_PROFILE_NAME
    best_hits = 0

    for name, profile in _REGISTRY.items():
        if not profile.detection.keyword_signals:
            continue
        hits = sum(1 for kw in profile.detection.keyword_signals if kw in text_lower)
        if hits >= profile.detection.min_keyword_matches and hits > best_hits:
            best_hits = hits
            best_name = name

    return _REGISTRY[best_name]
