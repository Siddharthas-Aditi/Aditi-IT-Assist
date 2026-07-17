"""Tests for production security hardening.

Covers:
- Token denylist (revoke / is_revoked / fail-open / fail-closed)
- Access vs refresh token separation (type check, distinct jti, expiry)
- Refresh rotation + logout revocation (API level)
- Rate limiter sliding-window logic + bucket classification
- Production config validation
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.core.config import Settings, settings
from app.core.rate_limit import RateLimiter, SlidingWindowCounter, classify_bucket
from app.core.security import create_access_token, create_refresh_token
from app.core.token_store import TokenDenylist, set_token_denylist
from app.main import app


class FakeRedis:
    """Minimal async-redis fake for the denylist."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.broken = False

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        if self.broken:
            raise ConnectionError("redis down")
        self.store[name] = value
        return True

    async def exists(self, *names: str) -> int:
        if self.broken:
            raise ConnectionError("redis down")
        return sum(1 for n in names if n in self.store)


# ─────────────────────────────────────────────────────────────────────
# Token factories
# ─────────────────────────────────────────────────────────────────────


class TestTokenFactories:
    def _decode(self, token: str) -> dict:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    def test_access_token_has_unique_jti_and_iat(self):
        t1 = self._decode(create_access_token({"sub": "u1"}))
        t2 = self._decode(create_access_token({"sub": "u1"}))
        assert t1["jti"] != t2["jti"]
        assert "iat" in t1

    def test_refresh_token_is_typed_with_own_jti(self):
        access = self._decode(create_access_token({"sub": "u1"}))
        refresh = self._decode(create_refresh_token({"sub": "u1"}))
        assert refresh["type"] == "refresh"
        assert refresh["jti"] != access["jti"]

    def test_refresh_token_outlives_access_token(self):
        access = self._decode(create_access_token({"sub": "u1"}))
        refresh = self._decode(create_refresh_token({"sub": "u1"}))
        assert refresh["exp"] > access["exp"]


# ─────────────────────────────────────────────────────────────────────
# Denylist
# ─────────────────────────────────────────────────────────────────────


class TestTokenDenylist:
    @pytest.mark.asyncio
    async def test_revoke_then_is_revoked(self):
        dl = TokenDenylist(redis_client=FakeRedis())
        jti = str(uuid.uuid4())
        assert await dl.is_revoked(jti) is False
        assert await dl.revoke(jti, time.time() + 3600) is True
        assert await dl.is_revoked(jti) is True

    @pytest.mark.asyncio
    async def test_missing_jti_never_revoked(self):
        dl = TokenDenylist(redis_client=FakeRedis())
        assert await dl.is_revoked(None) is False
        assert await dl.is_revoked("") is False

    @pytest.mark.asyncio
    async def test_fail_open_when_redis_down(self):
        broken = FakeRedis()
        broken.broken = True
        dl = TokenDenylist(redis_client=broken)
        # default policy: fail-open
        assert await dl.is_revoked("some-jti") is False
        assert await dl.revoke("some-jti", time.time() + 60) is False

    @pytest.mark.asyncio
    async def test_fail_closed_when_configured(self):
        broken = FakeRedis()
        broken.broken = True
        dl = TokenDenylist(redis_client=broken)
        with (
            patch.object(settings, "TOKEN_DENYLIST_FAIL_CLOSED", True),
            pytest.raises(RuntimeError),
        ):
            await dl.is_revoked("some-jti")


# ─────────────────────────────────────────────────────────────────────
# Auth API — rotation, revocation, type separation
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_denylist():
    dl = TokenDenylist(redis_client=FakeRedis())
    set_token_denylist(dl)
    yield dl
    set_token_denylist(None)


@pytest.fixture
async def anon_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRefreshRotation:
    def _user(self):
        user = AsyncMock()
        user.id = uuid.uuid4()
        user.email = "e@test.aditi.com"
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_refresh_rotates_and_revokes_old_token(self, anon_client, fake_denylist):
        refresh = create_refresh_token({"sub": "u1", "email": "e@test.aditi.com"})
        with patch(
            "app.services.auth.service.AuthService.get_user_by_id",
            new=AsyncMock(return_value=self._user()),
        ):
            r1 = await anon_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
            assert r1.status_code == 200
            body = r1.json()
            assert body["access_token"]
            assert body["refresh_token"]  # rotated token returned

            # Replaying the old refresh token must now fail.
            r2 = await anon_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
            assert r2.status_code == 401
            assert r2.json()["detail"]["error_code"] == "session_expired"

    @pytest.mark.asyncio
    async def test_access_token_rejected_by_refresh(self, anon_client, fake_denylist):
        access = create_access_token({"sub": "u1"})
        r = await anon_client.post("/api/v1/auth/refresh", json={"refresh_token": access})
        assert r.status_code == 401


class TestAccessRefreshSeparation:
    @pytest.mark.asyncio
    async def test_refresh_token_cannot_authenticate_api_calls(self, fake_denylist):
        """A refresh token in the Authorization header must never grant access."""
        from app.services.auth.providers.local import LocalAuthProvider

        provider = LocalAuthProvider()
        refresh = create_refresh_token({"sub": str(uuid.uuid4())})
        result = await provider.validate_session(refresh)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_revoked_access_token_rejected(self, fake_denylist):
        from app.services.auth.providers.local import LocalAuthProvider

        provider = LocalAuthProvider()
        token = create_access_token({"sub": str(uuid.uuid4())})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        assert (await provider.validate_session(token)).success is True
        await fake_denylist.revoke(payload["jti"], payload["exp"])
        assert (await provider.validate_session(token)).success is False

    @pytest.mark.asyncio
    async def test_saml_provider_rejects_refresh_token(self, fake_denylist):
        """SAML session validation must enforce the SAME rules as local:
        no refresh-as-access, and honour the revocation denylist."""
        from app.services.auth.providers.saml import SAMLAuthProvider

        provider = SAMLAuthProvider()
        refresh = create_refresh_token({"sub": str(uuid.uuid4())})
        assert (await provider.validate_session(refresh)).success is False

    @pytest.mark.asyncio
    async def test_saml_provider_rejects_revoked_token(self, fake_denylist):
        from app.services.auth.providers.saml import SAMLAuthProvider

        provider = SAMLAuthProvider()
        token = create_access_token({"sub": str(uuid.uuid4())})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        assert (await provider.validate_session(token)).success is True
        await fake_denylist.revoke(payload["jti"], payload["exp"])
        assert (await provider.validate_session(token)).success is False


class TestLogoutRevocation:
    @pytest.mark.asyncio
    async def test_logout_denylists_presented_tokens(self, fake_denylist, mock_employee):
        from app.services.auth.dependencies import get_current_active_user

        access = create_access_token({"sub": str(mock_employee.id)})
        refresh = create_refresh_token({"sub": str(mock_employee.id)})
        access_jti = jwt.decode(access, settings.SECRET_KEY, algorithms=["HS256"])["jti"]
        refresh_jti = jwt.decode(refresh, settings.SECRET_KEY, algorithms=["HS256"])["jti"]

        app.dependency_overrides[get_current_active_user] = lambda: mock_employee
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.post(
                    "/api/v1/auth/logout",
                    json={"refresh_token": refresh},
                    headers={"Authorization": f"Bearer {access}"},
                )
            assert r.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_active_user, None)

        assert await fake_denylist.is_revoked(access_jti) is True
        assert await fake_denylist.is_revoked(refresh_jti) is True


# ─────────────────────────────────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────────────────────────────────


class TestSlidingWindowCounter:
    def test_allows_up_to_limit_then_blocks(self):
        counter = SlidingWindowCounter(window_seconds=60)
        allowed = [counter.hit("k", 3, now=100.0 + i) for i in range(5)]
        assert allowed == [True, True, True, False, False]

    def test_window_slides(self):
        counter = SlidingWindowCounter(window_seconds=60)
        for i in range(3):
            assert counter.hit("k", 3, now=100.0 + i)
        assert counter.hit("k", 3, now=130.0) is False
        # first hit (t=100) leaves the window at t>160
        assert counter.hit("k", 3, now=161.0) is True

    def test_keys_are_isolated(self):
        counter = SlidingWindowCounter(window_seconds=60)
        assert counter.hit("a", 1, now=100.0) is True
        assert counter.hit("a", 1, now=101.0) is False
        assert counter.hit("b", 1, now=101.0) is True

    def test_prune_drops_stale_keys(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.hit("old", 5, now=100.0)
        counter.prune(now=200.0)
        assert "old" not in counter._hits


class TestRateLimiterFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_local_window_when_redis_broken(self):
        class BrokenRedis:
            async def incr(self, key):
                raise ConnectionError("down")

            async def expire(self, key, ttl):
                raise ConnectionError("down")

        limiter = RateLimiter(redis_client=BrokenRedis())
        results = [await limiter.allow("client:api", 3) for _ in range(5)]
        assert results == [True, True, True, False, False]


class TestBucketClassification:
    def test_auth_endpoints_get_tight_budget(self):
        bucket, limit = classify_bucket("/api/v1/auth/login")
        assert bucket == "auth"
        assert limit == settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE

    def test_api_endpoints_get_default_budget(self):
        bucket, limit = classify_bucket("/api/v1/chat/message")
        assert bucket == "api"
        assert limit == settings.RATE_LIMIT_REQUESTS_PER_MINUTE + settings.RATE_LIMIT_BURST


# ─────────────────────────────────────────────────────────────────────
# Production config validation
# ─────────────────────────────────────────────────────────────────────


class TestProductionValidation:
    def _prod_settings(self, **overrides) -> Settings:
        base = dict(
            APP_ENV="production",
            DEBUG=False,
            SECRET_KEY="a" * 48,
            POSTGRES_PASSWORD="real-password-123",
            REDIS_PASSWORD="real-redis-pw",
            CORS_ORIGINS=["https://it-assist.aditiconsulting.com"],
            # Explicitly pin feature flags so that process-level env vars (from
            # the dev .env loaded by Docker Compose) don't leak into the test's
            # Settings instance via pydantic-settings' env-var priority chain.
            FEATURE_MCP_TOOLS=False,
            MCP_USE_MOCK=False,
            REMOTE_SUPPORT_USE_MOCK=True,
            _env_file=None,
        )
        base.update(overrides)
        return Settings(**base)

    def test_clean_production_config_passes(self):
        assert self._prod_settings().validate_production() == []

    def test_development_is_never_validated(self):
        s = Settings(APP_ENV="development", _env_file=None)
        assert s.validate_production() == []

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"SECRET_KEY": "change-me-in-production"}, "SECRET_KEY"),
            ({"SECRET_KEY": "short"}, "SECRET_KEY"),
            ({"DEBUG": True}, "DEBUG"),
            ({"POSTGRES_PASSWORD": "aditi_dev_password"}, "POSTGRES_PASSWORD"),
            ({"REDIS_PASSWORD": ""}, "REDIS_PASSWORD"),
            ({"CORS_ORIGINS": ["http://localhost:5173"]}, "CORS_ORIGINS"),
            ({"CORS_ORIGINS": ["*"]}, "CORS_ORIGINS"),
            ({"CORS_ORIGINS": ["http://prod.example.com"]}, "https"),
            ({"AUTH_PROVIDER": "saml", "LOCAL_AUTH_ENABLED": True}, "LOCAL_AUTH_ENABLED"),
            ({"FEATURE_MCP_TOOLS": True, "MCP_USE_MOCK": True}, "MCP_USE_MOCK"),
            ({"REMOTE_SUPPORT_USE_MOCK": False}, "REMOTE_SUPPORT_USE_MOCK"),
        ],
    )
    def test_each_violation_is_reported(self, override, fragment):
        violations = self._prod_settings(**override).validate_production()
        assert any(fragment in v for v in violations), violations

    def test_https_origin_and_disabled_local_auth_pass_under_sso(self):
        s = self._prod_settings(AUTH_PROVIDER="saml", LOCAL_AUTH_ENABLED=False)
        assert s.validate_production() == []

    def test_scheduled_reports_on_without_smtp_or_recipients_fires_violation(self):
        s = self._prod_settings(
            FEATURE_SCHEDULED_REPORTS=True,
            SMTP_USER="",
            SMTP_PASSWORD="",
            REPORT_RECIPIENTS="",
        )
        violations = s.validate_production()
        assert any("FEATURE_SCHEDULED_REPORTS" in v for v in violations), violations

    def test_scheduled_reports_off_does_not_require_smtp(self):
        s = self._prod_settings(
            FEATURE_SCHEDULED_REPORTS=False,
            SMTP_USER="",
            SMTP_PASSWORD="",
            REPORT_RECIPIENTS="",
        )
        assert s.validate_production() == []

    def test_scheduled_reports_on_with_smtp_and_recipients_passes(self):
        s = self._prod_settings(
            FEATURE_SCHEDULED_REPORTS=True,
            SMTP_USER="reports@aditiconsulting.com",
            SMTP_PASSWORD="real-smtp-password",
            REPORT_RECIPIENTS="lead@aditiconsulting.com",
        )
        assert s.validate_production() == []


# ─────────────────────────────────────────────────────────────────────
# Rate-limit client identity (spoof resistance)
# ─────────────────────────────────────────────────────────────────────


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """Minimal stand-in for a Starlette Request for client_identity()."""

    def __init__(self, xff: str | None, peer: str = "10.0.0.9") -> None:
        self.headers = {} if xff is None else {"x-forwarded-for": xff}
        self.client = _FakeClient(peer)


class TestClientIdentity:
    def test_uses_rightmost_trusted_hop_not_spoofable_left(self, monkeypatch):
        # nginx appends the real client on the RIGHT; a spoofed value sits left
        # and must be ignored with the default single trusted hop.
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
        req = _FakeRequest(xff="1.2.3.4, 9.9.9.9")  # 9.9.9.9 = real client
        assert rate_limit.client_identity(req) == "9.9.9.9"

    def test_attacker_cannot_rotate_bucket_via_left_xff(self, monkeypatch):
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
        a = rate_limit.client_identity(_FakeRequest(xff="rot-1, 9.9.9.9"))
        b = rate_limit.client_identity(_FakeRequest(xff="rot-2, 9.9.9.9"))
        assert a == b == "9.9.9.9"  # spoofed left value doesn't change the key

    def test_two_trusted_hops_selects_correct_entry(self, monkeypatch):
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 2)
        # chain: client, cdn, nginx-appended-peer -> real client is [-2]
        req = _FakeRequest(xff="spoof, 5.5.5.5, 6.6.6.6")
        assert rate_limit.client_identity(req) == "5.5.5.5"

    def test_zero_hops_ignores_xff_and_uses_peer(self, monkeypatch):
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 0)
        req = _FakeRequest(xff="1.2.3.4", peer="10.0.0.9")
        assert rate_limit.client_identity(req) == "10.0.0.9"

    def test_missing_xff_falls_back_to_peer(self, monkeypatch):
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
        req = _FakeRequest(xff=None, peer="10.0.0.9")
        assert rate_limit.client_identity(req) == "10.0.0.9"

    def test_short_chain_falls_back_to_peer(self, monkeypatch):
        # header present but shorter than the expected proxy chain -> untrusted.
        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 2)
        req = _FakeRequest(xff="1.2.3.4", peer="10.0.0.9")
        assert rate_limit.client_identity(req) == "10.0.0.9"
