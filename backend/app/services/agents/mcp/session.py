"""MCP session abstraction.

The tool layer depends only on the small :class:`McpSession` protocol — *not*
on the MCP SDK — so the dispatch/guardrail logic is fully unit-testable with a
fake session and the platform takes no hard dependency on a wire library.

A concrete adapter over the official ``mcp`` Python SDK is provided
(:class:`SdkMcpSession`) and imported lazily, so environments without the SDK
(or without any MCP servers configured) still import and run the rest of the
system. ``default_session_provider`` is the production factory; tests inject
their own provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.agents.mcp.profiles import McpServerProfile

logger = get_logger(__name__)


@runtime_checkable
class McpSession(Protocol):
    """Minimal MCP client surface the tool layer needs.

    A real implementation wraps an MCP client connection; ``call_tool`` invokes
    a tool on the server and returns its (already JSON-decoded) structured
    result. ``close`` releases the connection.
    """

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tool descriptors advertised by the server."""
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool and return its structured result."""
        ...

    async def close(self) -> None:
        ...


# A provider resolves a profile to a connected session. Async so real
# implementations can open a connection on demand.
SessionProvider = Callable[["McpServerProfile"], Awaitable[McpSession]]


class SdkMcpSession:
    """Adapter over the official ``mcp`` Python SDK.

    Intentionally thin and lazily-importing. Not exercised in the unit suite
    (no live servers / SDK in CI); covered by integration tests where an MCP
    server is reachable. Kept here so the production path is real code, not a
    TODO.
    """

    def __init__(self, profile: McpServerProfile, auth_token: str | None) -> None:
        self._profile = profile
        self._auth_token = auth_token
        self._client: Any = None

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import mcp  # noqa: F401  (lazy: only needed when actually connecting)
            from mcp.client.session import ClientSession  # type: ignore
            from mcp.client.streamable_http import streamablehttp_client  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "MCP SDK not available — install 'mcp' to use MCP-backed tools, "
                "or run with FEATURE_MCP_TOOLS off."
            ) from exc
        # Connection wiring (headers/auth) is established here in production.
        # Left minimal on purpose; integration tests cover the live path.
        headers = {"Authorization": f"Bearer {self._auth_token}"} if self._auth_token else {}
        self._ctx = streamablehttp_client(self._profile.endpoint, headers=headers)
        read, write, _ = await self._ctx.__aenter__()
        self._client = ClientSession(read, write)
        await self._client.__aenter__()
        await self._client.initialize()
        return self._client

    async def list_tools(self) -> list[dict[str, Any]]:
        client = await self._ensure_client()
        result = await client.list_tools()
        return [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        client = await self._ensure_client()
        result = await client.call_tool(name, arguments)
        # Prefer structured content when the server provides it.
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return dict(structured)
        content = getattr(result, "content", None) or []
        if content and hasattr(content[0], "text"):
            import json

            try:
                return json.loads(content[0].text)
            except (json.JSONDecodeError, TypeError):
                return {"text": content[0].text}
        return {}

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
                await self._ctx.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp_session_close_failed", error=str(exc))
            finally:
                self._client = None


async def default_session_provider(profile: McpServerProfile) -> McpSession:
    """Session factory: a mock session in dev (``MCP_USE_MOCK``), else a real
    SDK session with auth resolved from config."""
    from app.core.config import settings

    if getattr(settings, "MCP_USE_MOCK", False):
        from app.services.agents.mcp.mock_session import MockMcpSession

        return MockMcpSession(profile)

    token = getattr(settings, profile.auth_secret_ref, None) if profile.auth_secret_ref else None
    return SdkMcpSession(profile, token)


__all__ = ["McpSession", "SdkMcpSession", "SessionProvider", "default_session_provider"]
