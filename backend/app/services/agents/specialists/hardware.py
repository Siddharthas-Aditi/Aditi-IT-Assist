"""Hardware specialist — camera, microphone, headset, on-device peripherals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists._progression import compose_specialist_output

if TYPE_CHECKING:
    from app.services.agents.specialists.base import (
        SpecialistInput,
        SpecialistOutput,
    )

_SPEC = AGENT_REGISTRY.get("hardware")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("hardware not registered as a SpecialistAgentSpec")


_OPENERS = {
    "camera-not-detected": (
        "If your camera isn't detected, it's usually a privacy permission "
        "or another app holding it. Let's check those first."
    ),
    "microphone-not-working": (
        "Mic issues are almost always a default-device pick or a privacy "
        "permission — easy fixes coming up."
    ),
    "no-audio": (
        "Let's check which output device your machine is sending sound to "
        "and that the right one is selected and unmuted."
    ),
}


class HardwareSpecialist:
    """Specialist agent for on-device hardware (camera, audio, peripherals)."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        ctx = inp.diag_ctx
        return (ctx.issue_category or "") in self.spec.categories or (
            ctx.normalized_system or ""
        ) in self.spec.systems

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        return compose_specialist_output(
            inp,
            specialist_name="hardware",
            openers=_OPENERS,
        )
