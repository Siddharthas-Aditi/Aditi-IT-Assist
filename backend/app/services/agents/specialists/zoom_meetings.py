"""Zoom + Teams meetings specialist — audio, video, screen share, joining."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists._progression import compose_specialist_output

if TYPE_CHECKING:
    from app.services.agents.specialists.base import (
        SpecialistInput,
        SpecialistOutput,
    )

_SPEC = AGENT_REGISTRY.get("zoom_meetings")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("zoom_meetings not registered as a SpecialistAgentSpec")


_OPENERS = {
    "no-audio": (
        "If you can't hear anyone (or they can't hear you), it's almost "
        "always an output/input device pick — let's check the right device "
        "is selected."
    ),
    "no-video": (
        "Camera not coming on? Usually it's another app holding the lens "
        "or the wrong device picked in the meeting."
    ),
    "cant-join-meeting": (
        "Let's get you into the meeting. We'll check the link, the client "
        "version, and your network in that order."
    ),
    "screen-share-issue": (
        "Screen sharing usually fails on a permissions prompt or a client "
        "that needs a refresh. Quick fixes coming up."
    ),
    "poor-quality": (
        "If audio is breaking up or video is freezing, it's usually network "
        "or background apps. We'll narrow it down."
    ),
}


class ZoomMeetingsSpecialist:
    """Specialist agent for Zoom + Teams meeting issues."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        ctx = inp.diag_ctx
        return (ctx.issue_category or "") in self.spec.categories or (
            ctx.normalized_system or ""
        ) in self.spec.systems

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        return compose_specialist_output(
            inp,
            specialist_name="zoom_meetings",
            openers=_OPENERS,
        )
