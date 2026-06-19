"""Specialist agent implementations.

Each specialist module exports a single ``Specialist`` class implementing the
:class:`app.services.agents.specialists.base.SpecialistAgent` protocol. The
supervisor (:mod:`app.services.agents.supervisor`) decides *which* specialist
to invoke based on the agent registry; this package provides the *how*.

Phase 1 scope: all seven specialists declared in the registry now have real
``handle()`` implementations. Outlook was the reference; the others use the
shared :mod:`._progression` helper and ship as small files with only their
subtype → opener map differing.

The :data:`SPECIALIST_REGISTRY` mapping below is what the supervisor's
dispatch node looks up by name. New specialists drop in here and the
supervisor picks them up automatically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.specialists.access_mfa import AccessMfaSpecialist
from app.services.agents.specialists.device_intune import DeviceIntuneSpecialist
from app.services.agents.specialists.hardware import HardwareSpecialist
from app.services.agents.specialists.network_vpn import NetworkVpnSpecialist
from app.services.agents.specialists.outlook import OutlookSpecialist
from app.services.agents.specialists.sixth_sense import SixthSenseSpecialist
from app.services.agents.specialists.zoom_meetings import ZoomMeetingsSpecialist

if TYPE_CHECKING:
    from app.services.agents.specialists.base import SpecialistAgent

# Name → instance. Each specialist is stateless (no per-session state on the
# instance), so a module-level singleton is fine.
SPECIALIST_REGISTRY: dict[str, SpecialistAgent] = {
    "outlook": OutlookSpecialist(),
    "access_mfa": AccessMfaSpecialist(),
    "zoom_meetings": ZoomMeetingsSpecialist(),
    "device_intune": DeviceIntuneSpecialist(),
    "sixth_sense": SixthSenseSpecialist(),
    "hardware": HardwareSpecialist(),
    "network_vpn": NetworkVpnSpecialist(),
}


def get_specialist(name: str) -> SpecialistAgent | None:
    """Lookup by registry name. Returns None if no specialist owns ``name``."""
    return SPECIALIST_REGISTRY.get(name)


__all__ = ["SPECIALIST_REGISTRY", "get_specialist"]

