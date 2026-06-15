"""Ingestion parser profiles package."""

from app.services.ingestion.profiles.base import ParserProfile
from app.services.ingestion.profiles.it_support import IT_SUPPORT_PROFILE
from app.services.ingestion.profiles.registry import (
    DEFAULT_PROFILE_NAME,
    detect_profile,
    get_profile,
    list_profiles,
    register_profile,
)

__all__ = [
    "ParserProfile",
    "IT_SUPPORT_PROFILE",
    "DEFAULT_PROFILE_NAME",
    "detect_profile",
    "get_profile",
    "list_profiles",
    "register_profile",
]
