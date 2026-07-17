"""Guardrail facts for device execution — eligibility + consent.

These are the two facts the autonomy policy needs that **must not** come from the
LLM: is the target device actually managed/eligible, and has the device's owner
consented. Both are resolved server-side here from the *device id* alone, so a
caller can't spoof the consent subject by naming a different, consented employee.

* **Eligibility** — a real Intune compliance read over the injected MCP session
  (works against the mock in dev, real Graph in prod). A device that doesn't
  resolve as managed is ineligible; a managed device (compliant *or*
  noncompliant — noncompliance is often what we're remediating) is eligible.
* **Consent** — an active, granted, non-revoked ``RemoteSupportConsent`` for the
  device's **owner** (the primary user resolved from the device record). Device
  execution reuses the remote-support consent artifact so there is one auditable
  consent trail. In dev (``MCP_USE_MOCK``) consent defaults permissive so the
  end-to-end flow is exercisable without seeding a session; production uses the
  DB lookup and is authoritative.

Enforcement happens in the **tool layer** (``DeviceExecutionTool.run`` uses
``DeviceGuardrails.as_tool_provider``), so consent is re-checked on *every*
execution path — autonomous, the device-execution approve endpoint, and the
generic ``/agent-ops`` approval queue — not just at request time. The provider is
self-contained per call (opens its own short DB session), so it is safe to use in
a request handler or a process-wide singleton runtime alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.session import SessionProvider, default_session_provider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

# Compliance states that mean "the device is managed and we may act on it".
_ELIGIBLE_STATES = {"compliant", "noncompliant", "ingraceperiod", "configmanager"}

# Keys the compliance read may use for the device's primary user.
_OWNER_KEYS = ("primary_user", "userPrincipalName", "user_principal_name", "primaryUser")


@dataclass(frozen=True)
class GuardrailFacts:
    """Facts the policy needs that must NOT come from the LLM."""

    device_eligible: bool = False
    consent_present: bool = False
    detail: str = ""
    owner: str = ""


async def _read_device(device_id: str, session_provider: SessionProvider) -> tuple[bool, str, str]:
    """Resolve (eligible, detail, owner_upn) via an Intune compliance read."""
    if not device_id:
        return False, "no device id", ""
    profile = mcp_profiles.get_profile("msgraph")
    if profile is None:
        return False, "msgraph read profile not configured", ""
    session = await session_provider(profile)
    try:
        raw = await session.call_tool("get_device_compliance", {"device_id": device_id})
    except Exception as exc:  # noqa: BLE001 — treat any read failure as ineligible
        logger.warning("device_read_failed", device_id=device_id, error=str(exc))
        return False, f"compliance read failed: {exc}", ""
    finally:
        close = getattr(session, "close", None)
        if close is not None:
            try:
                await close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("device_read_session_close_failed", error=str(exc))
    raw = raw or {}
    owner = next((str(raw[k]) for k in _OWNER_KEYS if raw.get(k)), "")
    state = str(raw.get("compliance_state", "")).lower()
    if not state:
        return False, "device did not resolve as managed", owner
    if state in _ELIGIBLE_STATES:
        return True, f"managed device (compliance={state})", owner
    return False, f"device state not eligible ({state})", owner


async def _consent_present(subject_upn: str, *, mock: bool) -> bool:
    """True iff a granted, non-revoked remote-support consent exists for the subject."""
    if mock:
        # Dev/demo: mirror the app-wide mock pattern so autonomous flow is exercisable.
        return True
    if not subject_upn:
        return False
    from app.core.database import async_session_factory
    from app.models.remote_support import RemoteSupportConsent

    async with async_session_factory() as db:
        row = await db.execute(
            select(RemoteSupportConsent)
            .where(
                RemoteSupportConsent.employee_id == subject_upn,
                RemoteSupportConsent.granted.is_(True),
                RemoteSupportConsent.revoked_at.is_(None),
            )
            .order_by(RemoteSupportConsent.consented_at.desc())
            .limit(1)
        )
        return row.scalar_one_or_none() is not None


class DeviceGuardrails:
    """Resolves :class:`GuardrailFacts` for a target device (+ optional employee)."""

    def __init__(
        self,
        *,
        session_provider: SessionProvider | None = None,
        mock: bool | None = None,
    ) -> None:
        self._provider = session_provider or default_session_provider
        if mock is None:
            from app.core.config import settings

            mock = settings.MCP_USE_MOCK
        self._mock = mock

    async def facts(self, *, device_id: str, employee_id: str = "") -> GuardrailFacts:
        eligible, detail, owner = await _read_device(device_id, self._provider)
        # Consent is checked against the device's server-resolved owner; the
        # caller-supplied employee_id is only a fallback when no owner resolves.
        subject = owner or employee_id
        consent = await _consent_present(subject, mock=self._mock)
        return GuardrailFacts(
            device_eligible=eligible,
            consent_present=consent,
            detail=detail,
            owner=owner,
        )

    def as_tool_provider(
        self,
    ) -> Callable[[str, str, str | None, object], Awaitable[GuardrailFacts]]:
        """Adapt to the tool guardrail-provider signature (kind, ref, device_id, ctx).

        Consent is resolved from the device owner, so the tool enforces it on
        every path even without a caller-supplied employee id.
        """

        async def provider(kind: str, ref: str, device_id: str | None, context: object):
            return await self.facts(device_id=device_id or "")

        return provider


def default_tool_guardrail_provider() -> Callable[..., Awaitable[GuardrailFacts]]:
    """The tool-layer guardrail provider used when none is injected."""
    return DeviceGuardrails().as_tool_provider()


__all__ = ["DeviceGuardrails", "GuardrailFacts", "default_tool_guardrail_provider"]
