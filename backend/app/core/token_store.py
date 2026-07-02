"""Redis-backed JWT denylist — token revocation for logout + refresh rotation.

Design
------
We denylist by ``jti`` (unique per token since the auth provider mints a
fresh UUID for every access *and* refresh token). A revoked jti is stored in
Redis with a TTL equal to the token's remaining lifetime, so the denylist is
self-cleaning and never grows beyond the set of not-yet-expired revoked
tokens.

Failure policy
--------------
If Redis is unreachable, behavior is governed by
``settings.TOKEN_DENYLIST_FAIL_CLOSED``:

* ``False`` (default): fail-open — auth continues, a warning is logged and
  the ``token_denylist_unavailable`` audit signal fires. Revocation is a
  hardening layer on top of short-lived tokens; total auth outage on a Redis
  blip is a worse failure mode for an internal IT tool.
* ``True``: fail-closed — token validation errors out (401s). Choose this in
  high-security deployments where revocation must be absolute.

This module is deliberately dependency-light: a tiny protocol over the redis
client so unit tests can inject a fake without a running Redis.
"""

from __future__ import annotations

import time
from typing import Protocol

import structlog

from app.core.config import settings

logger = structlog.get_logger()

_PREFIX = "auth:denylist:"


class SupportsRedis(Protocol):
    """The minimal async-redis surface the denylist needs."""

    async def set(self, name: str, value: str, ex: int | None = None) -> object: ...

    async def exists(self, *names: str) -> int: ...


class TokenDenylist:
    """jti denylist with TTL-based self-expiry.

    Args:
        redis_client: Injected client (tests). When None, a lazy client is
            created from ``settings.REDIS_URL`` on first use.
    """

    def __init__(self, redis_client: SupportsRedis | None = None) -> None:
        self._client: SupportsRedis | None = redis_client
        self._client_failed_at: float = 0.0

    def _get_client(self) -> SupportsRedis:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        return self._client

    async def revoke(self, jti: str, expires_at_ts: float) -> bool:
        """Denylist ``jti`` until the token's own expiry. Returns success."""
        if not jti:
            return False
        ttl = max(1, int(expires_at_ts - time.time()))
        try:
            await self._get_client().set(f"{_PREFIX}{jti}", "1", ex=ttl)
            return True
        except Exception as exc:  # noqa: BLE001 — any client error is an availability event
            logger.warning("token_denylist_unavailable", op="revoke", error=str(exc))
            return False

    async def is_revoked(self, jti: str | None) -> bool:
        """True if the jti has been revoked.

        Raises:
            RuntimeError: when Redis is unavailable AND fail-closed is set.
        """
        if not jti:
            # Legacy tokens without a jti cannot be individually revoked;
            # they age out via their (short) exp. Treat as not revoked.
            return False
        try:
            return bool(await self._get_client().exists(f"{_PREFIX}{jti}"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("token_denylist_unavailable", op="is_revoked", error=str(exc))
            if settings.TOKEN_DENYLIST_FAIL_CLOSED:
                raise RuntimeError("token denylist unavailable") from exc
            return False


_denylist: TokenDenylist | None = None


def get_token_denylist() -> TokenDenylist:
    """Process-wide denylist singleton (lazy Redis connection)."""
    global _denylist
    if _denylist is None:
        _denylist = TokenDenylist()
    return _denylist


def set_token_denylist(denylist: TokenDenylist | None) -> None:
    """Test seam — replace (or reset with None) the singleton."""
    global _denylist
    _denylist = denylist
