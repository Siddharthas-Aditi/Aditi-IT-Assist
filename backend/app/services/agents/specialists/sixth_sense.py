"""Sixth Sense (Naukri) specialist — login, account, OTP, unhandled message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists._progression import compose_specialist_output

if TYPE_CHECKING:
    from app.services.agents.specialists.base import (
        SpecialistInput,
        SpecialistOutput,
    )

_SPEC = AGENT_REGISTRY.get("sixth_sense")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("sixth_sense not registered as a SpecialistAgentSpec")


_OPENERS = {
    "login-failure": (
        "Let's get your Sixth Sense sign-in working. The usual culprits "
        "are a saved-but-stale credential or a one-time auth blip."
    ),
    "account-locked": (
        "Sixth Sense locks accounts after a few failed sign-ins. Let's "
        "verify the lock and the path to unlock."
    ),
    "otp-issue": (
        "OTP delivery to Sixth Sense uses the email/phone we have on file. "
        "Let's confirm both are current and the code isn't hitting spam."
    ),
    "unhandled-message": (
        "An 'Unhandled Message' error in Sixth Sense usually clears with "
        "a fresh session + cache. Quick fix coming up."
    ),
}


class SixthSenseSpecialist:
    """Specialist agent for Sixth Sense / Naukri access issues."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        ctx = inp.diag_ctx
        return (
            (ctx.issue_category or "") in self.spec.categories
            or (ctx.normalized_system or "") in self.spec.systems
        )

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        return compose_specialist_output(
            inp,
            specialist_name="sixth_sense",
            openers=_OPENERS,
        )
