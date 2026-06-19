"""Network / VPN specialist — VPN, Wi-Fi, internet, 3CX VoIP.

This specialist is one of the two that the registry allows web-fallback
for. Phase 2 will wire the controlled web-research agent in when the KB
runs dry; for now we lean on the same grounded-step pattern as the rest.
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

_SPEC = AGENT_REGISTRY.get("network_vpn")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError("network_vpn not registered as a SpecialistAgentSpec")


_OPENERS = {
    "vpn-not-connecting": (
        "If the VPN won't connect, we'll work through the client status, "
        "your network, and the last successful sign-in in that order."
    ),
    "wifi-disconnecting": (
        "Wi-Fi drops are usually a driver / power-management thing or the "
        "AP itself. Let's narrow it down."
    ),
    "internet-slow": (
        "Slow internet could be your link, DNS, or a heavy app. The next "
        "few checks will isolate which one."
    ),
    "specific-site-unreachable": (
        "If only one site or app is unreachable, the fix is usually DNS, "
        "proxy, or a corporate filter rule — quick to confirm."
    ),
    "3cx-voip-issue": (
        "3CX hiccups are most often a softphone-state issue. Let's restart "
        "it cleanly and confirm your SIP registration."
    ),
}


class NetworkVpnSpecialist:
    """Specialist agent for VPN, Wi-Fi, internet, and 3CX VoIP."""

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
            specialist_name="network_vpn",
            openers=_OPENERS,
        )
