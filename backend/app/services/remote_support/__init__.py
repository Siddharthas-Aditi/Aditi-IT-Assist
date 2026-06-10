"""Remote support service package — provider-based remote assistance orchestration."""

from app.services.remote_support.providers.base import (
    RemoteSessionInfo,
    RemoteSupportProvider,
)
from app.services.remote_support.providers.microsoft_remote_help import (
    MicrosoftRemoteHelpProvider,
)
from app.services.remote_support.service import RemoteSupportService

__all__ = [
    "RemoteSessionInfo",
    "RemoteSupportProvider",
    "MicrosoftRemoteHelpProvider",
    "RemoteSupportService",
]
