"""Microsoft Intune Remote Help provider — honest Graph-backed orchestration.

Decision record: ``docs/architecture/remote-support-decision.md``.

What Microsoft actually exposes (verified 2026-07):
    * There is **no public Graph API that creates an attended Remote Help
      session**. Sessions are launched from the Intune admin center
      (device ▸ *New remote assistance session*) or the Remote Help client,
      with an in-app code exchange between helper and sharer.
    * Graph *does* expose tenant Remote Help configuration
      (``GET /beta/deviceManagement/remoteAssistanceSettings``) and managed
      device records (``GET /v1.0/deviceManagement/managedDevices``), which
      we use for health checks and device-eligibility validation.

So this adapter does exactly — and only — what the platform can truthfully
do:
    * ``validate_prerequisites`` / ``health_check`` — real Graph reads
      (client-credential flow against the app registration configured via
      ``REMOTE_HELP_TENANT_ID`` / ``REMOTE_HELP_CLIENT_ID`` /
      ``REMOTE_HELP_CLIENT_SECRET``).
    * ``create_session`` — mints an internal correlation id, returns the
      helper a deterministic Intune admin-center launch URL (device blade
      when we can resolve the employee's managed device, dashboard
      otherwise) and the employee clear Remote Help join instructions.
      No fabricated Graph calls, no fake join codes: the code exchange
      happens inside Remote Help, which independently re-verifies both
      identities via Entra (defense in depth on top of our consent gate).
    * ``get_session_status`` — Remote Help has no session-status API, so
      this returns a no-op update (``PENDING``) and our service keeps its
      own state machine authoritative (driven by agent/employee endpoints).
    * ``terminate_session`` — platform-level end; the Remote Help session
      itself is ended in-client. We record the intent and return True.

Required app-registration permissions (application):
    * ``DeviceManagementConfiguration.Read.All`` (remoteAssistanceSettings)
    * ``DeviceManagementManagedDevices.Read.All`` (device eligibility)
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import structlog

from app.services.remote_support.providers.base import (
    ProviderSessionStatus,
    ProviderStatusUpdate,
    RemoteSessionInfo,
    RemoteSupportProvider,
    SessionCapability,
)

logger = structlog.get_logger()

_GRAPH_BASE = "https://graph.microsoft.com"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_TOKEN_SAFETY_MARGIN_SECONDS = 120
_HTTP_TIMEOUT = 10.0

_EMPLOYEE_JOIN_INSTRUCTIONS = (
    "Open the Remote Help app on your device (pre-installed on managed "
    "devices — search 'Remote Help' in the Start menu), sign in with your "
    "work account, and share the 8-digit security code shown in the app "
    "with your IT specialist when asked. You will see exactly what the "
    "specialist can access and can end the session at any time."
)


class MicrosoftRemoteHelpProvider(RemoteSupportProvider):
    """Intune Remote Help adapter — attended-only, Entra-authenticated."""

    def __init__(
        self,
        *,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        admin_center_base_url: str = "https://intune.microsoft.com",
        api_base_url: str = _GRAPH_BASE,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._admin_center = admin_center_base_url.rstrip("/")
        self._api_base_url = api_base_url.rstrip("/")
        self._http = http_client
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ── Provider identity ────────────────────────────────────────────

    @property
    def provider_name(self) -> str:
        return "microsoft_remote_help"

    @property
    def display_name(self) -> str:
        return "Microsoft Remote Help"

    @property
    def supported_capabilities(self) -> list[SessionCapability]:
        return [
            SessionCapability.SCREEN_VIEW,
            SessionCapability.SCREEN_CONTROL,
            SessionCapability.CHAT,
            SessionCapability.ANNOTATION,
            SessionCapability.MULTI_MONITOR,
        ]

    @property
    def supports_unattended(self) -> bool:
        return False  # Remote Help is attended-only; see ADR safety rules.

    # ── Graph plumbing ───────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
        return self._http

    @property
    def is_configured(self) -> bool:
        return bool(self._tenant_id and self._client_id and self._client_secret)

    async def _get_token(self) -> str:
        """Client-credential token, cached until near expiry."""
        if self._token and time.time() < self._token_expires_at:
            return self._token
        resp = await self._client().post(
            _TOKEN_URL.format(tenant=self._tenant_id),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": f"{_GRAPH_BASE}/.default",
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = (
            time.time() + int(body.get("expires_in", 3600)) - _TOKEN_SAFETY_MARGIN_SECONDS
        )
        return self._token

    async def _graph_get(self, path: str) -> httpx.Response:
        token = await self._get_token()
        return await self._client().get(
            f"{self._api_base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _find_managed_device(self, user_principal_name: str) -> dict[str, Any] | None:
        """Look up the employee's primary managed device by UPN (best effort)."""
        try:
            resp = await self._graph_get(
                "/v1.0/deviceManagement/managedDevices"
                f"?$filter=userPrincipalName eq '{user_principal_name}'"
                "&$select=id,deviceName,complianceState,operatingSystem&$top=5"
            )
            if resp.status_code != 200:
                logger.warning(
                    "remote_help_device_lookup_failed",
                    status=resp.status_code,
                    upn=user_principal_name,
                )
                return None
            devices = resp.json().get("value", [])
            if not devices:
                return None
            # Prefer a compliant Windows device (Remote Help's primary target).
            for device in devices:
                if (
                    device.get("complianceState") == "compliant"
                    and device.get("operatingSystem", "").lower() == "windows"
                ):
                    return device
            return devices[0]
        except httpx.HTTPError as exc:
            logger.warning("remote_help_device_lookup_error", error=str(exc))
            return None

    # ── RemoteSupportProvider contract ───────────────────────────────

    async def create_session(
        self,
        *,
        agent_id: str,
        agent_name: str,
        employee_id: str,
        employee_name: str,
        session_type: str,
        capabilities: list[SessionCapability] | None = None,
        ticket_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RemoteSessionInfo:
        """Prepare a Remote Help session launch.

        ``provider_session_id`` is an internal correlation id (``msrh-…``)
        recorded in our audit trail and quotable when reconciling against the
        Microsoft 365 audit log — it is NOT a Graph resource id, because no
        session-creation API exists (see module docstring).
        """
        correlation_id = f"msrh-{uuid.uuid4().hex[:16]}"
        employee_upn = (metadata or {}).get("employee_upn", "")

        device = None
        if self.is_configured and employee_upn:
            device = await self._find_managed_device(employee_upn)

        if device:
            helper_url = (
                f"{self._admin_center}/#view/Microsoft_Intune_Devices/"
                f"DeviceSettingsMenuBlade/~/overview/mdmDeviceId/{device['id']}"
            )
        else:
            helper_url = (
                f"{self._admin_center}/#view/Microsoft_Intune_Devices/DevicesMenu/~/overview"
            )

        logger.info(
            "remote_help_session_prepared",
            correlation_id=correlation_id,
            session_type=session_type,
            ticket_id=ticket_id,
            device_resolved=bool(device),
        )

        requested = capabilities or [
            SessionCapability.SCREEN_VIEW
            if session_type == "screen_view"
            else SessionCapability.SCREEN_CONTROL
        ]
        return RemoteSessionInfo(
            provider_session_id=correlation_id,
            status=ProviderSessionStatus.WAITING_FOR_USER,
            join_url_agent=helper_url,
            join_url_employee=None,  # employee joins via the Remote Help app
            join_code=None,  # code exchange happens inside Remote Help
            capabilities_granted=requested,
            provider_metadata={
                "tenant_id": self._tenant_id,
                "session_type": session_type,
                "ticket_reference": ticket_id,
                "managed_device_id": device.get("id") if device else None,
                "managed_device_name": device.get("deviceName") if device else None,
                "employee_instructions": _EMPLOYEE_JOIN_INSTRUCTIONS,
            },
        )

    async def terminate_session(self, provider_session_id: str) -> bool:
        """Platform-level termination — the Remote Help session ends in-client.

        There is no Graph endpoint to force-end an attended session; the
        enforcement teeth are (a) the employee can disconnect in the Remote
        Help client at any time and (b) our session record + audit trail mark
        the session terminated, which the UI reflects immediately.
        """
        logger.info("remote_help_terminate_recorded", provider_session_id=provider_session_id)
        return True

    async def get_session_status(self, provider_session_id: str) -> ProviderStatusUpdate:
        """No session-status API exists; return a no-op update.

        ``PENDING`` intentionally maps to *no state change* in
        ``RemoteSupportService.poll_provider_status`` — our own state machine
        (driven by agent/employee endpoints) stays authoritative.
        """
        return ProviderStatusUpdate(
            provider_session_id=provider_session_id,
            status=ProviderSessionStatus.PENDING,
        )

    async def validate_prerequisites(
        self, employee_device_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Real Graph checks: config present, tenant reachable, Remote Help enabled."""
        if not self.is_configured:
            return False, (
                "Microsoft Remote Help is not configured "
                "(REMOTE_HELP_TENANT_ID/CLIENT_ID/CLIENT_SECRET)"
            )
        try:
            resp = await self._graph_get("/beta/deviceManagement/remoteAssistanceSettings")
            if resp.status_code == 200:
                state = resp.json().get("remoteAssistanceState", "")
                if str(state).lower() == "disabled":
                    return False, "Remote Help is disabled for this tenant (Intune settings)"
            elif resp.status_code in (401, 403):
                return False, (
                    "Graph app registration lacks permission to read Remote Help settings"
                )
            # 404/5xx: settings endpoint unavailable — don't block the workflow
            # on a beta endpoint; the Remote Help client is the final gate.
        except httpx.HTTPError as exc:
            return False, f"Cannot reach Microsoft Graph: {exc}"

        if employee_device_id:
            try:
                dev = await self._graph_get(
                    f"/v1.0/deviceManagement/managedDevices/{employee_device_id}"
                    "?$select=id,complianceState"
                )
                if dev.status_code == 404:
                    return False, "Employee device is not enrolled in Intune"
            except httpx.HTTPError:
                pass  # device pre-check is best-effort; enrollment re-checked in-client

        return True, None

    async def health_check(self) -> bool:
        """Provider reachable = we can mint a token and call Graph."""
        if not self.is_configured:
            return False
        try:
            resp = await self._graph_get("/v1.0/deviceManagement/managedDevices?$top=1")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
