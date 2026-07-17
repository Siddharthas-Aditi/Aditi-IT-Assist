"""Auth provider interface — pluggable authentication backends.

This module defines the contract that all auth providers must implement.
Providers are selected via AUTH_PROVIDER config and resolved at startup.

Supported providers:
- local: Email/password with bcrypt + JWT sessions
- saml: SAML 2.0 SSO (Microsoft Entra, Okta, etc.)
- oidc: OpenID Connect (future)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthProviderType(StrEnum):
    """Supported authentication provider types."""

    LOCAL = "local"
    SAML = "saml"
    OIDC = "oidc"


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    success: bool
    user: Any | None = None  # User model (avoid circular import)
    error: str | None = None
    provider: str = "local"
    provider_user_id: str | None = None
    claims: dict[str, Any] | None = None
    # SSO-specific metadata
    session_index: str | None = None  # SAML SessionIndex
    name_id: str | None = None  # SAML NameID
    groups: list[str] = field(default_factory=list)
    is_new_user: bool = False  # True if JIT-provisioned


@dataclass
class SSOLoginResult:
    """Result of initiating an SSO login flow (redirect URL or error)."""

    redirect_url: str | None = None
    error: str | None = None
    request_id: str | None = None  # Track the AuthnRequest


@dataclass
class SSOLogoutResult:
    """Result of initiating/processing SSO logout."""

    redirect_url: str | None = None
    success: bool = False
    error: str | None = None


class AuthProvider(ABC):
    """Abstract base for authentication providers (local, SAML, OIDC).

    Lifecycle:
        1. Provider is instantiated at app startup
        2. `authenticate()` is called per login attempt
        3. `validate_session()` is called per authenticated request
        4. `logout()` handles session cleanup

    SSO providers additionally implement:
        - `initiate_login()` → redirect URL to IdP
        - `process_callback()` → handle IdP response
        - `initiate_logout()` → redirect URL for SLO
        - `get_metadata()` → SP metadata for IdP registration
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider (e.g., 'local', 'saml')."""
        ...

    @property
    def provider_type(self) -> AuthProviderType:
        """Type classification for this provider."""
        return AuthProviderType(self.provider_name)

    @property
    def supports_sso(self) -> bool:
        """Whether this provider supports SSO flows (login redirect + callback)."""
        return False

    @property
    def supports_jit_provisioning(self) -> bool:
        """Whether this provider can create users on first login."""
        return False

    @property
    def supports_group_sync(self) -> bool:
        """Whether this provider can sync group memberships from IdP."""
        return False

    @abstractmethod
    async def authenticate(self, **kwargs: Any) -> AuthResult:
        """Authenticate user with provider-specific credentials.

        For local: email + password
        For SAML: processed assertion data
        For OIDC: authorization code or token
        """
        ...

    @abstractmethod
    async def validate_session(self, token: str, **kwargs: Any) -> AuthResult:
        """Validate an existing session/token."""
        ...

    async def logout(self, user_id: str, session_id: str) -> bool:
        """Logout / revoke session. Default: no-op returns True."""
        return True

    # ── SSO-specific methods (override in SSO providers) ──────────

    async def initiate_login(
        self, *, relay_state: str | None = None, idp_id: str | None = None
    ) -> SSOLoginResult:
        """Generate redirect URL to IdP login page.

        Args:
            relay_state: URL to redirect back to after auth
            idp_id: Optional IdP identifier for multi-IdP setups

        Returns:
            SSOLoginResult with redirect URL or error
        """
        return SSOLoginResult(error=f"{self.provider_name} does not support SSO login")

    async def process_callback(self, **kwargs: Any) -> AuthResult:
        """Process IdP callback (SAML ACS, OIDC redirect).

        Args:
            For SAML: saml_response (str), relay_state (str|None)
            For OIDC: code (str), state (str)
        """
        return AuthResult(
            success=False,
            error=f"{self.provider_name} does not support SSO callbacks",
            provider=self.provider_name,
        )

    async def initiate_logout(
        self,
        *,
        user_id: str,
        session_index: str | None = None,
        name_id: str | None = None,
    ) -> SSOLogoutResult:
        """Initiate Single Logout with IdP.

        Args:
            user_id: Internal user ID
            session_index: SAML SessionIndex from login
            name_id: SAML NameID from login
        """
        return SSOLogoutResult(success=True)

    async def get_metadata(self) -> str | None:
        """Return SP metadata (XML for SAML, JSON for OIDC discovery).

        Returns None if the provider doesn't publish metadata.
        """
        return None
