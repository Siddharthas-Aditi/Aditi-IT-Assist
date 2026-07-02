"""Remote support providers package — single construction point.

``build_provider_registry()`` is the ONE place a provider gets configured,
used by both ``RemoteSupportService`` and the provider-health endpoint, so
mock/real selection can never drift between the two.

Selection contract (mirrors ``MCP_USE_MOCK``):
* ``REMOTE_SUPPORT_USE_MOCK=true`` (default) → only the mock provider is
  registered. Sessions honestly record ``provider="mock_remote_support"``.
* ``REMOTE_SUPPORT_USE_MOCK=false`` → the real Microsoft Remote Help
  adapter is registered, configured from ``REMOTE_HELP_*`` settings
  (production startup validation refuses to boot if they're missing).
"""

from __future__ import annotations

from app.core.config import settings
from app.services.remote_support.providers.base import RemoteSupportProvider
from app.services.remote_support.providers.microsoft_remote_help import (
    MicrosoftRemoteHelpProvider,
)
from app.services.remote_support.providers.mock import MockRemoteSupportProvider


def build_provider_registry() -> dict[str, RemoteSupportProvider]:
    """Provider name → configured instance (feature-flag aware)."""
    if settings.REMOTE_SUPPORT_USE_MOCK:
        mock = MockRemoteSupportProvider()
        return {mock.provider_name: mock}

    real = MicrosoftRemoteHelpProvider(
        tenant_id=settings.REMOTE_HELP_TENANT_ID,
        client_id=settings.REMOTE_HELP_CLIENT_ID,
        client_secret=settings.REMOTE_HELP_CLIENT_SECRET,
        admin_center_base_url=settings.INTUNE_ADMIN_CENTER_BASE_URL,
    )
    return {real.provider_name: real}


__all__ = [
    "MicrosoftRemoteHelpProvider",
    "MockRemoteSupportProvider",
    "RemoteSupportProvider",
    "build_provider_registry",
]
