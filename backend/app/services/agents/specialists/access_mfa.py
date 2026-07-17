"""Access / MFA specialist — account locks, password resets, MFA, OTP.

Owns ``access/permissions`` for AD / M365 / Okta. Sub-agents (declared in
the registry) cover ``account-locked``, ``mfa-not-working``, ``otp-issue``,
``password-expired``. Logic delegates to the shared
:func:`compose_specialist_output` helper — this file's value is the
subtype → opener map.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists._progression import compose_specialist_output

if TYPE_CHECKING:
    from app.services.agents.specialists.base import (
        SpecialistInput,
        SpecialistOutput,
    )

_SPEC = AGENT_REGISTRY.get("access_mfa")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("access_mfa not registered as a SpecialistAgentSpec")


# Natural, subtype-specific openers — never leak the slug to the user.
_OPENERS = {
    "account-locked": (
        "Looks like your account is locked. A handful of failed sign-ins "
        "or a policy trigger is the usual cause; let's get you back in."
    ),
    "mfa-not-working": (
        "If your multi-factor sign-in is misbehaving, the fastest path is "
        "to walk through what your authenticator is showing."
    ),
    "otp-issue": (
        "Sounds like the one-time code isn't arriving or isn't accepted. "
        "Most fixes here are quick once we know where it's getting stuck."
    ),
    "password-expired": (
        "If your password just expired (or you suspect it has), the steps "
        "below will get you reset and back in."
    ),
}


class AccessMfaSpecialist:
    """Specialist agent for account access, MFA, password, and OTP issues."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        ctx = inp.diag_ctx
        return (ctx.issue_category or "") in self.spec.categories or (
            ctx.normalized_system or ""
        ) in self.spec.systems

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        return compose_specialist_output(
            inp,
            specialist_name="access_mfa",
            openers=_OPENERS,
        )
