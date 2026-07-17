"""Intune / device compliance + enrollment specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists._progression import compose_specialist_output

if TYPE_CHECKING:
    from app.services.agents.specialists.base import (
        SpecialistInput,
        SpecialistOutput,
    )

_SPEC = AGENT_REGISTRY.get("device_intune")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("device_intune not registered as a SpecialistAgentSpec")


_OPENERS = {
    "non-compliant": (
        "If your device is showing as non-compliant, Intune is usually "
        "waiting on a check-in or a recent policy update. Let's run it."
    ),
    "enrollment-failure": (
        "Enrollment hiccups are usually a sign-in or work-account state "
        "issue. We'll walk it through cleanly."
    ),
}


class DeviceIntuneSpecialist:
    """Specialist agent for Intune compliance + device enrollment."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        ctx = inp.diag_ctx
        return (ctx.issue_category or "") in self.spec.categories or (
            ctx.normalized_system or ""
        ) in self.spec.systems

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        return compose_specialist_output(
            inp,
            specialist_name="device_intune",
            openers=_OPENERS,
        )
