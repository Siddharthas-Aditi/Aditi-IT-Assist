"""Tests for remote-support providers, registry selection, and time-policy sweep.

Covers:
- Provider registry: mock by default, real Graph adapter when flag is off
- MicrosoftRemoteHelpProvider: honest Graph behavior with a fake httpx client
  (token caching, device-resolved launch URLs, prereq validation, no-op status)
- RemoteSupportService.sweep_sessions: consent expiry + max-duration enforcement
- Prerequisite gate in request_session
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services.remote_support.providers import build_provider_registry
from app.services.remote_support.providers.base import ProviderSessionStatus
from app.services.remote_support.providers.microsoft_remote_help import (
    MicrosoftRemoteHelpProvider,
)
from app.services.remote_support.providers.mock import MockRemoteSupportProvider
from app.services.remote_support.service import PolicyViolation, RemoteSupportService

# ─────────────────────────────────────────────────────────────────────
# Fake Graph transport
# ─────────────────────────────────────────────────────────────────────


class FakeGraph:
    """Programmable httpx.AsyncClient stand-in for Graph + token endpoints."""

    def __init__(self) -> None:
        self.token_calls = 0
        self.responses: dict[str, tuple[int, dict]] = {}

    def route(self, path_fragment: str, status_code: int, body: dict) -> None:
        self.responses[path_fragment] = (status_code, body)

    async def post(self, url: str, data: dict | None = None, **kw) -> httpx.Response:
        assert "oauth2/v2.0/token" in url
        self.token_calls += 1
        return httpx.Response(
            200,
            content=json.dumps({"access_token": "fake-token", "expires_in": 3600}),
            request=httpx.Request("POST", url),
        )

    async def get(self, url: str, headers: dict | None = None, **kw) -> httpx.Response:
        assert headers and headers["Authorization"] == "Bearer fake-token"
        for fragment, (status_code, body) in self.responses.items():
            if fragment in url:
                return httpx.Response(
                    status_code,
                    content=json.dumps(body),
                    request=httpx.Request("GET", url),
                )
        return httpx.Response(404, content="{}", request=httpx.Request("GET", url))


def _real_provider(fake: FakeGraph) -> MicrosoftRemoteHelpProvider:
    return MicrosoftRemoteHelpProvider(
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="secret-1",
        http_client=fake,  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────────────
# Registry selection
# ─────────────────────────────────────────────────────────────────────


class TestProviderRegistry:
    def test_mock_by_default(self):
        with patch.object(settings, "REMOTE_SUPPORT_USE_MOCK", True):
            registry = build_provider_registry()
        assert list(registry) == ["mock_remote_support"]
        assert isinstance(registry["mock_remote_support"], MockRemoteSupportProvider)

    def test_real_provider_when_mock_disabled(self):
        with (
            patch.object(settings, "REMOTE_SUPPORT_USE_MOCK", False),
            patch.object(settings, "REMOTE_HELP_TENANT_ID", "t"),
            patch.object(settings, "REMOTE_HELP_CLIENT_ID", "c"),
            patch.object(settings, "REMOTE_HELP_CLIENT_SECRET", "s"),
        ):
            registry = build_provider_registry()
        assert list(registry) == ["microsoft_remote_help"]
        assert isinstance(registry["microsoft_remote_help"], MicrosoftRemoteHelpProvider)

    def test_mock_sessions_audit_honestly(self):
        """Mock provider must never claim to be the real one in audit records."""
        assert MockRemoteSupportProvider().provider_name != "microsoft_remote_help"


# ─────────────────────────────────────────────────────────────────────
# Microsoft Remote Help provider
# ─────────────────────────────────────────────────────────────────────


class TestRemoteHelpProvider:
    @pytest.mark.asyncio
    async def test_unconfigured_prereqs_fail_clearly(self):
        provider = MicrosoftRemoteHelpProvider()
        ok, error = await provider.validate_prerequisites()
        assert ok is False
        assert "not configured" in (error or "")
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_token_is_cached_across_calls(self):
        fake = FakeGraph()
        fake.route("managedDevices", 200, {"value": []})
        provider = _real_provider(fake)
        await provider.health_check()
        await provider.health_check()
        assert fake.token_calls == 1

    @pytest.mark.asyncio
    async def test_create_session_resolves_device_blade_url(self):
        fake = FakeGraph()
        fake.route(
            "managedDevices",
            200,
            {
                "value": [
                    {
                        "id": "dev-123",
                        "deviceName": "LAPTOP-01",
                        "complianceState": "compliant",
                        "operatingSystem": "Windows",
                    }
                ]
            },
        )
        provider = _real_provider(fake)
        info = await provider.create_session(
            agent_id="a",
            agent_name="Agent",
            employee_id="e",
            employee_name="Employee",
            session_type="screen_view",
            metadata={"employee_upn": "employee@aditiconsulting.com"},
        )
        assert info.provider_session_id.startswith("msrh-")
        assert "mdmDeviceId/dev-123" in (info.join_url_agent or "")
        assert info.join_code is None  # code exchange happens inside Remote Help
        assert info.provider_metadata["managed_device_id"] == "dev-123"
        assert info.status == ProviderSessionStatus.WAITING_FOR_USER

    @pytest.mark.asyncio
    async def test_create_session_without_device_falls_back_to_dashboard(self):
        fake = FakeGraph()
        fake.route("managedDevices", 200, {"value": []})
        provider = _real_provider(fake)
        info = await provider.create_session(
            agent_id="a",
            agent_name="Agent",
            employee_id="e",
            employee_name="Employee",
            session_type="screen_control",
            metadata={"employee_upn": "employee@aditiconsulting.com"},
        )
        assert "DevicesMenu" in (info.join_url_agent or "")
        assert info.provider_metadata["managed_device_id"] is None

    @pytest.mark.asyncio
    async def test_prereqs_fail_when_tenant_disabled(self):
        fake = FakeGraph()
        fake.route("remoteAssistanceSettings", 200, {"remoteAssistanceState": "disabled"})
        provider = _real_provider(fake)
        ok, error = await provider.validate_prerequisites()
        assert ok is False
        assert "disabled" in (error or "")

    @pytest.mark.asyncio
    async def test_prereqs_fail_when_permissions_missing(self):
        fake = FakeGraph()
        fake.route("remoteAssistanceSettings", 403, {})
        provider = _real_provider(fake)
        ok, error = await provider.validate_prerequisites()
        assert ok is False
        assert "permission" in (error or "")

    @pytest.mark.asyncio
    async def test_prereqs_pass_when_enabled(self):
        fake = FakeGraph()
        fake.route("remoteAssistanceSettings", 200, {"remoteAssistanceState": "enabled"})
        provider = _real_provider(fake)
        ok, error = await provider.validate_prerequisites()
        assert ok is True
        assert error is None

    @pytest.mark.asyncio
    async def test_status_poll_is_a_noop_update(self):
        """No Remote Help status API exists — the update must not force a state."""
        provider = MicrosoftRemoteHelpProvider()
        update = await provider.get_session_status("msrh-abc")
        assert update.status == ProviderSessionStatus.PENDING


# ─────────────────────────────────────────────────────────────────────
# Service: prerequisite gate + sweep
# ─────────────────────────────────────────────────────────────────────


def _mock_db_for(sessions_by_query: list[list]) -> MagicMock:
    """DB mock whose successive ``execute`` calls return the given scalar lists."""
    db = MagicMock()
    results = []
    for sessions in sessions_by_query:
        result = MagicMock()
        result.scalars.return_value.all.return_value = sessions
        results.append(result)

    async def execute(_stmt):
        return results.pop(0)

    db.execute = execute
    db.add = MagicMock()
    return db


def _sweepable_session(**overrides) -> MagicMock:
    session = MagicMock()
    session.id = uuid.uuid4()
    session.provider = "mock_remote_support"
    session.provider_session_id = None
    session.max_duration_minutes = 30
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class TestPrerequisiteGate:
    @pytest.mark.asyncio
    async def test_request_session_blocked_when_prereqs_fail(self):
        agent = MagicMock()
        agent.id = uuid.uuid4()
        agent.role_names = ["it_agent"]
        agent.full_name = "Agent"
        agent.email = "agent@test.com"

        svc = RemoteSupportService(MagicMock())
        broken_provider = MagicMock()

        async def failing_prereqs(*a, **kw):
            return False, "tenant misconfigured"

        broken_provider.validate_prerequisites = failing_prereqs
        svc._providers = {"mock_remote_support": broken_provider}

        with pytest.raises(PolicyViolation, match="tenant misconfigured"):
            await svc.request_session(agent=agent, employee_id=uuid.uuid4())


class TestSessionSweep:
    # NOTE: sweep_sessions() runs THREE queries in order:
    #   1) consent_pending past deadline, 2) consent_granted/connecting never
    #   launched (stale), 3) live sessions over max duration.
    # _mock_db_for takes one result list per query, in that order.

    @pytest.mark.asyncio
    async def test_expires_consent_pending_past_deadline(self):
        stale = _sweepable_session(status="consent_pending")
        db = _mock_db_for([[stale], [], []])
        svc = RemoteSupportService(MagicMock())
        svc.db = db

        counts = await svc.sweep_sessions()
        assert counts["expired"] == 1
        assert stale.status == "expired"
        assert stale.termination_reason == "consent_expired"

    @pytest.mark.asyncio
    async def test_expires_stale_consent_granted_never_launched(self):
        abandoned = _sweepable_session(
            status="consent_granted",
            started_at=None,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db = _mock_db_for([[], [abandoned], []])
        svc = RemoteSupportService(MagicMock())
        svc.db = db

        counts = await svc.sweep_sessions()
        assert counts["stale_abandoned"] == 1
        assert abandoned.status == "expired"
        assert abandoned.termination_reason == "stale_no_launch"

    @pytest.mark.asyncio
    async def test_terminates_sessions_over_max_duration(self):
        overrun = _sweepable_session(
            status="active",
            started_at=datetime.now(UTC) - timedelta(minutes=90),
            max_duration_minutes=30,
        )
        db = _mock_db_for([[], [], [overrun]])
        svc = RemoteSupportService(MagicMock())
        svc.db = db

        counts = await svc.sweep_sessions()
        assert counts["max_duration_terminated"] == 1
        assert overrun.status == "terminated"
        assert overrun.termination_reason == "max_duration_exceeded"

    @pytest.mark.asyncio
    async def test_leaves_in_window_sessions_alone(self):
        healthy = _sweepable_session(
            status="active",
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            max_duration_minutes=30,
        )
        db = _mock_db_for([[], [], [healthy]])
        svc = RemoteSupportService(MagicMock())
        svc.db = db

        counts = await svc.sweep_sessions()
        assert counts == {"expired": 0, "max_duration_terminated": 0, "stale_abandoned": 0}
        assert healthy.status == "active"
