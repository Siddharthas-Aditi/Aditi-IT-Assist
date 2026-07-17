"""Rate limiting — sliding-window limiter with Redis backend + local fallback.

Replaces the long-standing "config-only" stub: ``RATE_LIMIT_ENABLED`` now
actually gates an ASGI middleware.

Design
------
* **Sliding window** per ``(client, bucket)``: at most ``limit + burst``
  requests in any 60-second window.
* **Buckets**: credential endpoints (``/auth/login``, ``/auth/refresh``,
  ``/auth/register``) get the tighter ``RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE``
  budget; everything else shares the per-client default budget.
* **Client identity**: the first hop of ``X-Forwarded-For`` when present
  (nginx terminates in front of us in production), else the socket peer.
* **Backends**: Redis (INCR + EXPIRE fixed-window approximation, shared
  across replicas) with automatic fallback to an in-process window when
  Redis is unreachable — a Redis outage must degrade limiting, not requests.
* **Exemptions**: health/readiness/metrics probes are never limited.

The window logic is a pure class (``SlidingWindowCounter``) so limits are
unit-testable without ASGI or Redis.
"""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

from app.core.config import settings

logger = structlog.get_logger()

_WINDOW_SECONDS = 60
_EXEMPT_SUFFIXES = ("/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json")
_AUTH_SUFFIXES = ("/auth/login", "/auth/refresh", "/auth/register")


class SlidingWindowCounter:
    """In-memory sliding window: timestamps per key, pruned on each hit."""

    def __init__(self, window_seconds: int = _WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, now: float | None = None) -> bool:
        """Record a request. Returns True if allowed, False if over limit."""
        ts = now if now is not None else time.monotonic()
        q = self._hits.setdefault(key, deque())
        cutoff = ts - self._window
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(ts)
        return True

    def prune(self, now: float | None = None) -> None:
        """Drop empty/stale keys (bounded memory under IP churn)."""
        ts = now if now is not None else time.monotonic()
        cutoff = ts - self._window
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[key]


class RateLimiter:
    """Redis-first limiter with in-memory fallback."""

    def __init__(self, redis_client: object | None = None) -> None:
        self._redis = redis_client
        self._redis_broken_until: float = 0.0
        self._local = SlidingWindowCounter()
        self._requests_since_prune = 0

    def _get_redis(self) -> object | None:
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
            except Exception:  # noqa: BLE001
                return None
        return self._redis

    async def allow(self, key: str, limit: int) -> bool:
        """True when the request fits the budget for ``key``."""
        now = time.monotonic()
        if now >= self._redis_broken_until:
            client = self._get_redis()
            if client is not None:
                try:
                    window_key = f"ratelimit:{key}:{int(time.time() // _WINDOW_SECONDS)}"
                    count = await client.incr(window_key)  # type: ignore[attr-defined]
                    if count == 1:
                        await client.expire(window_key, _WINDOW_SECONDS + 5)  # type: ignore[attr-defined]
                    return int(count) <= limit
                except Exception as exc:  # noqa: BLE001
                    # Back off Redis for 30s and degrade to the local window.
                    self._redis_broken_until = now + 30
                    logger.warning("rate_limit_redis_unavailable", error=str(exc))

        allowed = self._local.hit(key, limit, now=now)
        self._requests_since_prune += 1
        if self._requests_since_prune >= 1000:
            self._local.prune(now=now)
            self._requests_since_prune = 0
        return allowed


def classify_bucket(path: str) -> tuple[str, int]:
    """Map a request path to (bucket name, per-minute budget)."""
    if path.endswith(_AUTH_SUFFIXES):
        return "auth", settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE
    return "api", settings.RATE_LIMIT_REQUESTS_PER_MINUTE + settings.RATE_LIMIT_BURST


def client_identity(request: Request) -> str:
    """Spoof-resistant client key.

    ``X-Forwarded-For`` is a comma-separated chain where each proxy appends the
    peer it saw. Our nginx uses ``$proxy_add_x_forwarded_for``, so the real
    client is the ``RATE_LIMIT_TRUSTED_PROXY_HOPS``-th entry from the RIGHT;
    everything a client spoofs lands to the LEFT of that and is ignored.

    A previous version trusted the LEFTMOST entry, which is entirely
    caller-controlled — an attacker could rotate it per request to get a fresh
    bucket every time and defeat the brute-force guard. If the header is missing
    or shorter than the configured proxy chain (i.e. it didn't come through the
    expected proxies), we fall back to the socket peer rather than trust it.
    """
    peer = request.client.host if request.client else "unknown"
    hops = settings.RATE_LIMIT_TRUSTED_PROXY_HOPS
    if hops <= 0:
        return peer
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return peer


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429s clients that exceed their sliding-window budget."""

    def __init__(self, app: object, limiter: RateLimiter | None = None) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path
        if path.endswith(_EXEMPT_SUFFIXES):
            return await call_next(request)

        bucket, limit = classify_bucket(path)
        key = f"{client_identity(request)}:{bucket}"
        if not await self._limiter.allow(key, limit):
            logger.warning("rate_limit_exceeded", bucket=bucket, path=path)
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "rate_limited",
                    "message": "Too many requests. Please slow down and retry shortly.",
                },
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )
        return await call_next(request)
