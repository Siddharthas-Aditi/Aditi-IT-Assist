"""Device-action catalog — the versioned allow-list of what may ever run.

This is the keystone guardrail for autonomous device execution. An agent may
only ever *select an entry by id* from these catalogs; it can never author an
installer, a script body, or an arbitrary command. Every entry maps to an object
that a human has already published and reviewed in Intune (a Win32 app, a
remediation/platform script) or to a small fixed set of benign device actions.

Why this shape
--------------
* **No free-form execution surface.** Because the agent's only lever is a catalog
  id, a prompt-injection payload ("ignore your rules and run this base64…") has
  nowhere to land — the tool args are ids + a device id + an idempotency key, all
  schema-validated, none of which carry a runnable payload.
* **Risk-tiered.** Each entry declares a :class:`RiskTier`; the autonomy policy
  (:mod:`.policy`) uses it to decide whether the AI may run it unattended or must
  route to human approval.
* **Explicit, versioned, PR-reviewed.** ``CATALOG_VERSION`` bumps on any change to
  the set of runnable actions, so audit/analytics can join on it and a reviewer
  sees exactly what capability changed. Nothing is discovered dynamically.
* **Reversibility recorded.** ``reversible`` / ``rollback_ref`` document how an
  action is undone, so operators are never stuck with a one-way change they can't
  walk back.

The Intune identifiers here (``intune_app_id`` / ``intune_script_id``) are the
*published object ids* in the tenant. In dev they are placeholders; the mock MCP
session ignores them. In production they are validated to exist at boot by
``scripts/validate_device_catalog.py`` (see the ADR) so the catalog can never
reference an object that isn't actually deployable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Bump on ANY change to the runnable action set (adds, removals, risk re-tiering).
CATALOG_VERSION = "1.0.0"


class RiskTier(StrEnum):
    """How much blast radius an action carries. Drives the autonomy policy."""

    LOW = "low"  # additive, reversible, no data/security impact (install a dev tool)
    MEDIUM = "medium"  # user-visible or state-changing but recoverable (restart, cache clear)
    HIGH = "high"  # security/config-sensitive or hard to reverse — never autonomous


class ActionKind(StrEnum):
    """The three families of device action the platform can perform."""

    INSTALL_APP = "install_app"
    REMEDIATION = "remediation"
    DEVICE_ACTION = "device_action"


@dataclass(frozen=True, kw_only=True)
class AppCatalogEntry:
    """One installable application, pre-published in Intune."""

    app_id: str  # our stable catalog id, e.g. "python-3.12"
    display_name: str
    publisher: str
    intune_app_id: str  # published Win32/Store app id in the tenant
    risk_tier: RiskTier
    reversible: bool = True
    rollback_ref: str = ""  # how to uninstall / undo (runbook or catalog id)
    description: str = ""


@dataclass(frozen=True, kw_only=True)
class RemediationCatalogEntry:
    """One remediation, backed by a reviewed Intune remediation/platform script.

    The script *body* lives in Intune and is version-controlled + SME-reviewed
    there. We never carry or generate the script text here — only its id.
    """

    remediation_id: str  # our stable catalog id, e.g. "clear-teams-cache"
    display_name: str
    intune_script_id: str  # published remediation script id in the tenant
    risk_tier: RiskTier
    reversible: bool = True
    rollback_ref: str = ""
    description: str = ""


@dataclass(frozen=True, kw_only=True)
class DeviceActionEntry:
    """One benign, built-in Intune device action (no script, no payload)."""

    action_id: str  # e.g. "sync", "restart"
    display_name: str
    graph_action: str  # the managedDevice action name on Graph
    risk_tier: RiskTier
    reversible: bool = True
    description: str = ""


# ── The catalogs ──────────────────────────────────────────────────────────────
# Enumerated, never dynamic. Adding a runnable action is one declaration here plus
# the corresponding published object in Intune. Intune ids are placeholders in dev.

_APPS: tuple[AppCatalogEntry, ...] = (
    AppCatalogEntry(
        app_id="python-3.12",
        display_name="Python 3.12",
        publisher="Python Software Foundation",
        intune_app_id="win32-python-3-12-0000",
        risk_tier=RiskTier.LOW,
        reversible=True,
        rollback_ref="uninstall via Intune app assignment removal",
        description="Python 3.12 runtime for developer machines.",
    ),
    AppCatalogEntry(
        app_id="docker-desktop",
        display_name="Docker Desktop",
        publisher="Docker Inc.",
        intune_app_id="win32-docker-desktop-0000",
        # Docker Desktop enables virtualization + a background service; treat as
        # MEDIUM so it is reviewable, though still catalog-bounded.
        risk_tier=RiskTier.MEDIUM,
        reversible=True,
        rollback_ref="uninstall via Intune app assignment removal",
        description="Docker Desktop for container-based development.",
    ),
    AppCatalogEntry(
        app_id="vscode",
        display_name="Visual Studio Code",
        publisher="Microsoft",
        intune_app_id="win32-vscode-0000",
        risk_tier=RiskTier.LOW,
        reversible=True,
        description="Visual Studio Code editor.",
    ),
    AppCatalogEntry(
        app_id="nodejs-lts",
        display_name="Node.js LTS",
        publisher="OpenJS Foundation",
        intune_app_id="win32-nodejs-lts-0000",
        risk_tier=RiskTier.LOW,
        reversible=True,
        description="Node.js LTS runtime.",
    ),
)

_REMEDIATIONS: tuple[RemediationCatalogEntry, ...] = (
    RemediationCatalogEntry(
        remediation_id="clear-teams-cache",
        display_name="Clear Microsoft Teams cache",
        intune_script_id="remediation-teams-cache-0000",
        risk_tier=RiskTier.LOW,
        reversible=False,  # cache regenerates; nothing to roll back
        description="Clears the Teams cache to fix sign-in / rendering issues.",
    ),
    RemediationCatalogEntry(
        remediation_id="flush-dns",
        display_name="Flush DNS resolver cache",
        intune_script_id="remediation-flush-dns-0000",
        risk_tier=RiskTier.LOW,
        reversible=False,
        description="Runs ipconfig /flushdns to resolve stale DNS entries.",
    ),
    RemediationCatalogEntry(
        remediation_id="restart-print-spooler",
        display_name="Restart Print Spooler service",
        intune_script_id="remediation-print-spooler-0000",
        risk_tier=RiskTier.MEDIUM,
        reversible=True,
        description="Restarts the Windows Print Spooler to clear stuck jobs.",
    ),
    RemediationCatalogEntry(
        remediation_id="reset-winsock",
        display_name="Reset Winsock catalog",
        intune_script_id="remediation-reset-winsock-0000",
        # Touches the network stack and needs a reboot — reviewable, not autonomous.
        risk_tier=RiskTier.HIGH,
        reversible=False,
        description="Resets the Winsock catalog for deep network connectivity faults.",
    ),
)

_DEVICE_ACTIONS: tuple[DeviceActionEntry, ...] = (
    DeviceActionEntry(
        action_id="sync",
        display_name="Sync device with Intune",
        graph_action="syncDevice",
        risk_tier=RiskTier.LOW,
        description="Forces the device to check in and re-apply policy.",
    ),
    DeviceActionEntry(
        action_id="restart",
        display_name="Restart device",
        graph_action="rebootNow",
        risk_tier=RiskTier.MEDIUM,
        description="Reboots the device (user may lose unsaved work).",
    ),
)

APP_CATALOG: dict[str, AppCatalogEntry] = {e.app_id: e for e in _APPS}
REMEDIATION_CATALOG: dict[str, RemediationCatalogEntry] = {
    e.remediation_id: e for e in _REMEDIATIONS
}
DEVICE_ACTION_CATALOG: dict[str, DeviceActionEntry] = {e.action_id: e for e in _DEVICE_ACTIONS}


# ── Accessors ────────────────────────────────────────────────────────────────


def get_app(app_id: str) -> AppCatalogEntry | None:
    return APP_CATALOG.get(app_id)


def get_remediation(remediation_id: str) -> RemediationCatalogEntry | None:
    return REMEDIATION_CATALOG.get(remediation_id)


def get_device_action(action_id: str) -> DeviceActionEntry | None:
    return DEVICE_ACTION_CATALOG.get(action_id)


def resolve(
    kind: ActionKind, ref: str
) -> AppCatalogEntry | RemediationCatalogEntry | DeviceActionEntry | None:
    """Resolve a catalog id to its entry by action kind (None if off-catalog)."""
    match kind:
        case ActionKind.INSTALL_APP:
            return get_app(ref)
        case ActionKind.REMEDIATION:
            return get_remediation(ref)
        case ActionKind.DEVICE_ACTION:
            return get_device_action(ref)
    return None


def app_ids() -> tuple[str, ...]:
    return tuple(APP_CATALOG)


def remediation_ids() -> tuple[str, ...]:
    return tuple(REMEDIATION_CATALOG)


def device_action_ids() -> tuple[str, ...]:
    return tuple(DEVICE_ACTION_CATALOG)


__all__ = [
    "APP_CATALOG",
    "CATALOG_VERSION",
    "DEVICE_ACTION_CATALOG",
    "REMEDIATION_CATALOG",
    "ActionKind",
    "AppCatalogEntry",
    "DeviceActionEntry",
    "RemediationCatalogEntry",
    "RiskTier",
    "app_ids",
    "device_action_ids",
    "get_app",
    "get_device_action",
    "get_remediation",
    "remediation_ids",
    "resolve",
]
