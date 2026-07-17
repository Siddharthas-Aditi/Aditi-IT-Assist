"""SAML 2.0 authentication provider — enterprise SSO integration.

Architecture:
    This provider implements SAML 2.0 SP (Service Provider) functionality.
    It is designed to work with any SAML 2.0 compliant Identity Provider:
    - Microsoft Entra ID (Azure AD)
    - Okta
    - OneLogin
    - PingFederate
    - Google Workspace

Flow:
    1. User hits /auth/saml/login → SP generates AuthnRequest → redirect to IdP
    2. User authenticates at IdP → IdP POSTs SAML Response to /auth/saml/acs
    3. SP validates response, extracts claims, maps groups → issues JWT
    4. User hits /auth/saml/logout → SP generates LogoutRequest → redirect to IdP
    5. IdP terminates session → IdP redirects to /auth/saml/sls

Dependencies (install when ready to implement):
    - python3-saml (OneLogin) or pysaml2 (IdentityPython)
    - xmlsec1 system library for signature validation
    - cryptography for certificate handling

See: docs/security/saml-roadmap.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.services.auth.providers.base import (
    AuthProvider,
    AuthResult,
    SSOLoginResult,
    SSOLogoutResult,
)

logger = structlog.get_logger()


# ─── Configuration Dataclasses ─────────────────────────────────────────────────


@dataclass
class SAMLIdPConfig:
    """Identity Provider configuration loaded from DB or settings.

    Supports both metadata URL (auto-refresh) and manual configuration.
    """

    # Identity
    idp_id: str  # Internal identifier
    entity_id: str  # IdP Entity ID
    display_name: str

    # Endpoints
    sso_url: str  # HTTP-Redirect binding
    sso_post_url: str | None = None  # HTTP-POST binding (optional)
    slo_url: str | None = None  # Single Logout URL

    # Certificates
    x509_cert: str = ""  # PEM-encoded signing certificate
    x509_cert_multi: list[str] = field(default_factory=list)  # For cert rotation

    # Metadata (alternative to manual config)
    metadata_url: str | None = None  # Auto-refresh metadata URL

    # Claims mapping (IdP-specific attribute URIs)
    attr_email: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    attr_first_name: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
    attr_last_name: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
    attr_display_name: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
    attr_groups: str = "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
    attr_employee_id: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/employeeid"
    attr_department: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/department"

    # Behavior
    want_assertions_signed: bool = True
    want_response_signed: bool = True
    allow_unencrypted: bool = False
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"


@dataclass
class SAMLSPConfig:
    """Service Provider (our application) configuration."""

    entity_id: str = "aditi-it-assist"
    acs_url: str = ""  # Assertion Consumer Service URL
    sls_url: str = ""  # Single Logout Service URL
    metadata_url: str = ""  # Our metadata endpoint

    # SP certificates (for signing AuthnRequest / decrypting assertions)
    sp_cert: str = ""  # PEM-encoded SP certificate
    sp_private_key: str = ""  # PEM-encoded SP private key

    # Organization info (included in metadata)
    org_name: str = "Aditi Consulting"
    org_display_name: str = "Aditi IT Assist"
    org_url: str = "https://aditiconsulting.com"

    # Contact
    tech_contact_name: str = ""
    tech_contact_email: str = ""


@dataclass
class GroupRoleMapping:
    """Maps an external IdP group to an internal role.

    Supports exact match and prefix match patterns.
    """

    idp_group: str  # IdP group name or ID
    internal_role: str  # Role name (employee, it_agent, etc.)
    match_type: str = "exact"  # "exact" | "prefix" | "regex"
    priority: int = 0  # Higher priority wins on conflict


@dataclass
class SAMLClaimsResult:
    """Parsed and validated claims from a SAML assertion."""

    email: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    groups: list[str] = field(default_factory=list)
    employee_id: str | None = None
    department: str | None = None
    name_id: str | None = None
    session_index: str | None = None
    raw_attributes: dict[str, Any] = field(default_factory=dict)


# ─── SAML Provider ─────────────────────────────────────────────────────────────


class SAMLAuthProvider(AuthProvider):
    """SAML 2.0 SSO provider — extensible enterprise authentication.

    This provider orchestrates the full SAML flow:
    - AuthnRequest generation and IdP redirect
    - Assertion validation and claims extraction
    - Group-to-role mapping
    - JIT (Just-In-Time) user provisioning
    - Single Logout (SLO)

    The actual SAML XML processing is delegated to a SAMLBackend
    abstraction to allow swapping python3-saml ↔ pysaml2.
    """

    def __init__(
        self,
        sp_config: SAMLSPConfig | None = None,
        idp_configs: list[SAMLIdPConfig] | None = None,
        group_mappings: list[GroupRoleMapping] | None = None,
    ) -> None:
        self._sp_config = sp_config or SAMLSPConfig()
        self._idp_configs: dict[str, SAMLIdPConfig] = {c.idp_id: c for c in (idp_configs or [])}
        self._group_mappings = group_mappings or self._default_group_mappings()

    @property
    def provider_name(self) -> str:
        return "saml"

    @property
    def supports_sso(self) -> bool:
        return True

    @property
    def supports_jit_provisioning(self) -> bool:
        return True

    @property
    def supports_group_sync(self) -> bool:
        return True

    # ── Core Interface ──────────────────────────────────────────────

    async def authenticate(self, **kwargs: Any) -> AuthResult:
        """Process a validated SAML assertion into an AuthResult.

        Expected kwargs:
            claims: SAMLClaimsResult - parsed assertion claims
            db: AsyncSession - database session for user lookup/creation

        This method is called AFTER assertion validation by process_callback().
        """
        claims: SAMLClaimsResult | None = kwargs.get("claims")
        if not claims:
            return AuthResult(
                success=False,
                error="No SAML claims provided",
                provider="saml",
            )

        # Map groups to internal roles
        mapped_roles = self.map_groups_to_roles(claims.groups)

        logger.info(
            "saml_authenticate",
            email=claims.email,
            groups=claims.groups,
            mapped_roles=mapped_roles,
        )

        # In production: lookup or JIT-provision user here
        # For now, return the structured result for the auth service to handle
        return AuthResult(
            success=True,
            provider="saml",
            provider_user_id=claims.name_id or claims.email,
            claims={
                "email": claims.email,
                "display_name": claims.display_name,
                "first_name": claims.first_name,
                "last_name": claims.last_name,
                "employee_id": claims.employee_id,
                "department": claims.department,
                "groups": claims.groups,
                "mapped_roles": mapped_roles,
            },
            groups=claims.groups,
            session_index=claims.session_index,
            name_id=claims.name_id,
        )

    async def validate_session(self, token: str, **kwargs: Any) -> AuthResult:
        """Validate SAML session — delegates to JWT after initial SAML auth.

        After SAML login, we issue our own JWT. Subsequent requests validate
        that JWT, so this method uses the same JWT validation as local auth.
        """
        from app.core.security import verify_token

        payload = verify_token(token)
        if not payload:
            return AuthResult(success=False, error="Invalid or expired session")

        # Parity with LocalAuthProvider: a refresh token must never authenticate
        # an API call, and revoked tokens (logout / refresh rotation) must be
        # rejected. Without these, SAML mode silently ignored the denylist and
        # let long-lived refresh tokens act as access tokens.
        if payload.get("type") == "refresh":
            return AuthResult(success=False, error="Refresh token cannot be used for access")

        from app.core.token_store import get_token_denylist

        try:
            revoked = await get_token_denylist().is_revoked(payload.get("jti"))
        except RuntimeError:
            return AuthResult(success=False, error="Token revocation check unavailable")
        if revoked:
            return AuthResult(success=False, error="Token has been revoked")

        return AuthResult(
            success=True,
            provider="saml",
            provider_user_id=payload.get("sub"),
            claims=payload,
        )

    # ── SSO Flow Methods ────────────────────────────────────────────

    async def initiate_login(
        self, *, relay_state: str | None = None, idp_id: str | None = None
    ) -> SSOLoginResult:
        """Generate SAML AuthnRequest and return redirect URL to IdP.

        Args:
            relay_state: URL to redirect user to after authentication
            idp_id: Which IdP to use (for multi-IdP setups)

        Returns:
            SSOLoginResult with redirect URL or error
        """
        idp_config = self._resolve_idp(idp_id)
        if not idp_config:
            return SSOLoginResult(
                error="No Identity Provider configured. Contact your administrator."
            )

        logger.info(
            "saml_initiate_login",
            idp_id=idp_config.idp_id,
            relay_state=relay_state,
        )

        # TODO: Implementation with python3-saml or pysaml2:
        # 1. Build AuthnRequest XML
        # 2. Sign with SP private key (if configured)
        # 3. Encode + deflate for redirect binding
        # 4. Construct IdP SSO URL with SAMLRequest param
        #
        # auth = OneLogin_Saml2_Auth(request_data, self._build_settings(idp_config))
        # redirect_url = auth.login(relay_state)

        return SSOLoginResult(
            error="SAML login not yet implemented. Install python3-saml to enable.",
        )

    async def process_callback(self, **kwargs: Any) -> AuthResult:
        """Process SAML ACS (Assertion Consumer Service) callback.

        Args:
            saml_response: Base64-encoded SAML Response from IdP
            relay_state: Relay state from the request
            request_data: HTTP request data for validation (URL, method, etc.)
            idp_id: Optional IdP identifier

        Returns:
            AuthResult with parsed claims and user info
        """
        saml_response: str | None = kwargs.get("saml_response")
        relay_state: str | None = kwargs.get("relay_state")
        idp_id: str | None = kwargs.get("idp_id")

        if not saml_response:
            return AuthResult(
                success=False,
                error="No SAML response received",
                provider="saml",
            )

        idp_config = self._resolve_idp(idp_id)
        if not idp_config:
            return AuthResult(
                success=False,
                error="Identity Provider not configured",
                provider="saml",
            )

        logger.info(
            "saml_process_acs",
            idp_id=idp_config.idp_id,
            relay_state=relay_state,
        )

        # TODO: Implementation with python3-saml or pysaml2:
        # 1. Parse and validate SAML Response
        # 2. Verify signature against IdP certificate
        # 3. Check assertion conditions (NotBefore, NotOnOrAfter, Audience)
        # 4. Extract attributes using configured mapping
        # 5. Return parsed claims
        #
        # auth = OneLogin_Saml2_Auth(request_data, self._build_settings(idp_config))
        # auth.process_response()
        # errors = auth.get_errors()
        # if errors: return AuthResult(success=False, error=str(errors))
        # claims = self._extract_claims(auth, idp_config)
        # return await self.authenticate(claims=claims, **kwargs)

        return AuthResult(
            success=False,
            error="SAML response processing not yet implemented",
            provider="saml",
        )

    async def initiate_logout(
        self,
        *,
        user_id: str,
        session_index: str | None = None,
        name_id: str | None = None,
    ) -> SSOLogoutResult:
        """Initiate SAML Single Logout (SLO).

        Generates a LogoutRequest to the IdP to terminate the SSO session.

        Args:
            user_id: Internal user ID
            session_index: SAML SessionIndex from original login
            name_id: SAML NameID from original login
        """
        logger.info(
            "saml_initiate_logout",
            user_id=user_id,
            session_index=session_index,
        )

        # TODO: Implementation:
        # 1. Build LogoutRequest XML with SessionIndex + NameID
        # 2. Sign with SP private key
        # 3. Redirect to IdP SLO URL
        #
        # auth = OneLogin_Saml2_Auth(request_data, settings)
        # redirect_url = auth.logout(name_id=name_id, session_index=session_index)

        return SSOLogoutResult(
            success=True,  # Local session will be invalidated regardless
        )

    async def process_slo_response(self, **kwargs: Any) -> SSOLogoutResult:
        """Process IdP's LogoutResponse after SLO.

        Called when IdP redirects back to our SLS endpoint.
        """
        logger.info("saml_process_slo")

        # TODO: Validate LogoutResponse signature
        return SSOLogoutResult(success=True)

    async def get_metadata(self) -> str | None:
        """Generate SAML SP metadata XML.

        Returns XML metadata document suitable for importing into any
        SAML-compliant IdP.
        """
        sp = self._sp_config
        default_name_id_format = SAMLIdPConfig(
            idp_id="", entity_id="", display_name="", sso_url=""
        ).name_id_format

        # Minimal metadata template — production uses python3-saml generation
        return f"""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="{sp.entity_id}"
    validUntil="2030-01-01T00:00:00Z">
  <md:SPSSODescriptor
      AuthnRequestsSigned="true"
      WantAssertionsSigned="true"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:NameIDFormat>{default_name_id_format}</md:NameIDFormat>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="{sp.acs_url}"
        index="1"
        isDefault="true"/>

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="{sp.sls_url}"/>
  </md:SPSSODescriptor>

  <md:Organization>
    <md:OrganizationName xml:lang="en">{sp.org_name}</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="en">{sp.org_display_name}</md:OrganizationDisplayName>
    <md:OrganizationURL xml:lang="en">{sp.org_url}</md:OrganizationURL>
  </md:Organization>
</md:EntityDescriptor>"""

    # ── Group → Role Mapping ────────────────────────────────────────

    def map_groups_to_roles(self, idp_groups: list[str]) -> list[str]:
        """Map IdP group claims to internal RBAC role names.

        Uses the configured group mappings with priority resolution.
        Higher priority mappings take precedence on conflicts.

        Args:
            idp_groups: List of group names/IDs from IdP assertion

        Returns:
            List of internal role names (e.g., ["it_agent", "employee"])
        """
        roles: set[str] = set()
        matched: list[tuple[int, str]] = []

        for mapping in self._group_mappings:
            for group in idp_groups:
                if self._group_matches(group, mapping):
                    matched.append((mapping.priority, mapping.internal_role))

        if matched:
            # Sort by priority (highest first) and collect roles
            matched.sort(key=lambda x: x[0], reverse=True)
            roles = {role for _, role in matched}
        else:
            # No group matched → default to employee
            roles.add("employee")

        logger.debug(
            "saml_group_mapping",
            input_groups=idp_groups,
            mapped_roles=sorted(roles),
        )
        return sorted(roles)

    # ── JIT Provisioning ────────────────────────────────────────────

    async def jit_provision_user(
        self, claims: SAMLClaimsResult, mapped_roles: list[str], db: Any
    ) -> AuthResult:
        """Just-In-Time provision a user from SAML claims.

        Called when a user authenticates via SAML for the first time
        and doesn't exist in our database.

        Steps:
            1. Create User record from claims
            2. Create AuthIdentity linking to IdP
            3. Assign roles based on group mapping
            4. Create group memberships
            5. Log provisioning event to audit trail

        Args:
            claims: Parsed SAML assertion claims
            mapped_roles: Roles determined by group mapping
            db: Database session

        Returns:
            AuthResult with newly created user
        """
        logger.info(
            "saml_jit_provision",
            email=claims.email,
            roles=mapped_roles,
        )

        # TODO: Full implementation:
        # from app.models.auth import User, AuthIdentity, UserRoleAssignment
        # user = User(
        #     email=claims.email,
        #     full_name=claims.display_name,
        #     employee_id=claims.employee_id,
        #     department=claims.department,
        #     hashed_password="",  # No local password for SSO users
        #     is_active=True,
        #     is_verified=True,
        # )
        # db.add(user)
        # await db.flush()
        # ... create AuthIdentity, assign roles ...

        return AuthResult(
            success=False,
            error="JIT provisioning not yet implemented",
            provider="saml",
            is_new_user=True,
        )

    async def sync_user_attributes(self, user: Any, claims: SAMLClaimsResult, db: Any) -> None:
        """Sync user attributes from SAML claims on each login.

        Updates department, job title, group memberships etc.
        Called for existing users on subsequent SAML logins.
        """
        logger.debug(
            "saml_sync_attributes",
            user_id=str(getattr(user, "id", "unknown")),
            email=claims.email,
        )
        # TODO: Update user fields that changed
        # TODO: Sync group memberships
        # TODO: Log attribute changes to audit trail

    # ── Offboarding / Deprovisioning ───────────────────────────────

    async def handle_user_removal(self, user_id: str, db: Any) -> None:
        """Handle user deprovisioning when removed from IdP.

        Triggered by:
        - SCIM DELETE event (if SCIM is configured)
        - Absence of user in group sync (configurable behavior)
        - Manual admin action

        Behavior:
        - Deactivate user account (soft delete)
        - Revoke all active sessions
        - Log deprovisioning event
        """
        logger.warning("saml_user_deprovisioned", user_id=user_id)
        # TODO: Implement deactivation logic

    # ── Internals ──────────────────────────────────────────────────

    def _resolve_idp(self, idp_id: str | None = None) -> SAMLIdPConfig | None:
        """Resolve which IdP configuration to use.

        For single-IdP setups, returns the only config.
        For multi-IdP, uses idp_id to select.
        """
        if not self._idp_configs:
            return None
        if idp_id and idp_id in self._idp_configs:
            return self._idp_configs[idp_id]
        # Return first (default) IdP
        return next(iter(self._idp_configs.values()))

    @staticmethod
    def _group_matches(group: str, mapping: GroupRoleMapping) -> bool:
        """Check if a group matches a mapping rule."""
        if mapping.match_type == "exact":
            return group == mapping.idp_group
        elif mapping.match_type == "prefix":
            return group.startswith(mapping.idp_group)
        elif mapping.match_type == "regex":
            import re

            return bool(re.match(mapping.idp_group, group))
        return False

    @staticmethod
    def _default_group_mappings() -> list[GroupRoleMapping]:
        """Default group-to-role mappings for common IdP group names."""
        return [
            # Microsoft Entra ID common group names
            GroupRoleMapping("IT-Admins", "it_admin", priority=40),
            GroupRoleMapping("IT-Team-Leads", "it_lead", priority=30),
            GroupRoleMapping("IT-Support-Team", "it_agent", priority=20),
            GroupRoleMapping("Security-Auditors", "security_auditor", priority=15),
            GroupRoleMapping("All-Employees", "employee", priority=10),
            # Okta-style group names
            GroupRoleMapping("aditi-it-admin", "it_admin", priority=40),
            GroupRoleMapping("aditi-it-leads", "it_lead", priority=30),
            GroupRoleMapping("aditi-it-agents", "it_agent", priority=20),
            GroupRoleMapping("aditi-security", "security_auditor", priority=15),
            GroupRoleMapping("aditi-employees", "employee", priority=10),
        ]


# ─── IdP-Specific Helpers ──────────────────────────────────────────────────────
#
# These functions provide pre-configured SAMLIdPConfig for common IdPs.
# They DO NOT implement vendor-specific APIs — only claim mapping defaults.
#


def entra_id_config(
    *,
    tenant_id: str,
    entity_id: str | None = None,
    display_name: str = "Microsoft Entra ID",
) -> SAMLIdPConfig:
    """Create SAMLIdPConfig pre-configured for Microsoft Entra ID.

    The caller still needs to provide the IdP certificate.

    Args:
        tenant_id: Azure AD tenant ID (GUID)
        entity_id: Override entity ID (defaults to Entra standard)
        display_name: Friendly name
    """
    return SAMLIdPConfig(
        idp_id="entra",
        entity_id=entity_id or f"https://sts.windows.net/{tenant_id}/",
        display_name=display_name,
        sso_url=f"https://login.microsoftonline.com/{tenant_id}/saml2",
        slo_url=f"https://login.microsoftonline.com/{tenant_id}/saml2",
        # Microsoft Entra standard claim URIs
        attr_email="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        attr_first_name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        attr_last_name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        attr_display_name="http://schemas.microsoft.com/identity/claims/displayname",
        attr_groups="http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        attr_employee_id="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/employeeid",
        attr_department="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/department",
        name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )


def okta_config(
    *,
    okta_domain: str,
    app_id: str,
    display_name: str = "Okta",
) -> SAMLIdPConfig:
    """Create SAMLIdPConfig pre-configured for Okta.

    Args:
        okta_domain: e.g., "aditiconsulting.okta.com"
        app_id: Okta application ID
        display_name: Friendly name
    """
    return SAMLIdPConfig(
        idp_id="okta",
        entity_id=f"http://www.okta.com/{app_id}",
        display_name=display_name,
        sso_url=f"https://{okta_domain}/app/{app_id}/sso/saml",
        slo_url=f"https://{okta_domain}/app/{app_id}/slo/saml",
        metadata_url=f"https://{okta_domain}/app/{app_id}/sso/saml/metadata",
        # Okta default attribute mappings
        attr_email="email",
        attr_first_name="firstName",
        attr_last_name="lastName",
        attr_display_name="displayName",
        attr_groups="groups",
        attr_employee_id="employeeNumber",
        attr_department="department",
        name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )
