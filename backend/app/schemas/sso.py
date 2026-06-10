"""Pydantic schemas for SAML/SSO configuration management.

Used by admin endpoints to configure Identity Providers,
manage group-role mappings, and handle certificate operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ─── IdP Configuration ─────────────────────────────────────────────────────────


class IdPConfigBase(BaseModel):
    """Base fields for Identity Provider configuration."""

    idp_id: str = Field(
        ..., min_length=2, max_length=100,
        description="Short unique identifier (e.g., 'entra-prod')",
        pattern=r"^[a-z0-9][a-z0-9\-]+$",
    )
    display_name: str = Field(..., max_length=255)
    description: str | None = None
    provider_type: Literal["saml", "oidc"] = "saml"


class IdPConfigCreate(IdPConfigBase):
    """Create a new IdP configuration."""

    # Endpoints
    entity_id: str = Field(
        ..., description="IdP Entity ID / Issuer URL",
    )
    sso_url: str = Field(
        ..., description="IdP Single Sign-On URL",
    )
    sso_post_url: str | None = None
    slo_url: str | None = None
    metadata_url: str | None = Field(
        None, description="Federation metadata URL for auto-refresh",
    )

    # Certificate
    x509_cert: str = Field(
        ..., description="IdP signing certificate (PEM format)",
    )
    x509_cert_secondary: str | None = None

    # SP identity
    sp_entity_id: str = "aditi-it-assist"

    # Attribute mapping
    attribute_mapping: AttributeMapping | None = None

    # Security
    want_assertions_signed: bool = True
    want_response_signed: bool = True
    allow_unencrypted_assertions: bool = False
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"

    # Behavior
    jit_provisioning_enabled: bool = True
    group_sync_enabled: bool = True
    default_role: str = "employee"


class IdPConfigUpdate(BaseModel):
    """Update an existing IdP configuration (partial update)."""

    display_name: str | None = None
    description: str | None = None
    status: Literal["active", "inactive", "testing"] | None = None
    is_default: bool | None = None

    # Endpoints
    sso_url: str | None = None
    sso_post_url: str | None = None
    slo_url: str | None = None
    metadata_url: str | None = None

    # Certificate
    x509_cert: str | None = None
    x509_cert_secondary: str | None = None

    # Attribute mapping
    attribute_mapping: AttributeMapping | None = None

    # Security
    want_assertions_signed: bool | None = None
    want_response_signed: bool | None = None
    allow_unencrypted_assertions: bool | None = None

    # Behavior
    jit_provisioning_enabled: bool | None = None
    group_sync_enabled: bool | None = None
    default_role: str | None = None


class IdPConfigResponse(IdPConfigBase):
    """IdP configuration response (excludes sensitive cert content)."""

    id: str
    status: str
    is_default: bool

    entity_id: str
    sso_url: str
    sso_post_url: str | None
    slo_url: str | None
    metadata_url: str | None

    sp_entity_id: str
    attribute_mapping: AttributeMapping | None

    want_assertions_signed: bool
    want_response_signed: bool
    name_id_format: str

    jit_provisioning_enabled: bool
    group_sync_enabled: bool
    default_role: str

    # Certificate status (not full cert content)
    cert_configured: bool
    cert_expires_at: datetime | None
    metadata_last_refreshed: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Attribute Mapping ─────────────────────────────────────────────────────────


class AttributeMapping(BaseModel):
    """Configures how IdP SAML attributes map to internal user fields.

    Each field is the URI/name of the SAML attribute as configured in the IdP.
    """

    email: str = Field(
        default="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        description="Attribute containing user email",
    )
    first_name: str = Field(
        default="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        description="Attribute containing first name",
    )
    last_name: str = Field(
        default="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        description="Attribute containing last name",
    )
    display_name: str = Field(
        default="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        description="Attribute containing display name",
    )
    groups: str = Field(
        default="http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        description="Attribute containing group memberships",
    )
    employee_id: str | None = Field(
        default=None,
        description="Attribute containing employee ID",
    )
    department: str | None = Field(
        default=None,
        description="Attribute containing department",
    )
    job_title: str | None = Field(
        default=None,
        description="Attribute containing job title",
    )
    phone: str | None = Field(
        default=None,
        description="Attribute containing phone number",
    )


# ─── Preset Templates ─────────────────────────────────────────────────────────


class IdPPresetRequest(BaseModel):
    """Request to generate IdP config from a preset template."""

    preset: Literal["entra_id", "okta", "onelogin", "google_workspace"]
    tenant_id: str | None = Field(
        None, description="Azure AD Tenant ID (for Entra ID)",
    )
    okta_domain: str | None = Field(
        None, description="Okta domain (e.g., company.okta.com)",
    )
    app_id: str | None = Field(
        None, description="Application/Client ID at the IdP",
    )


# ─── Group → Role Mapping ─────────────────────────────────────────────────────


class GroupRoleMappingBase(BaseModel):
    """Base fields for group-to-role mapping."""

    idp_group_name: str = Field(
        ..., description="Group name/ID as it appears in IdP claims",
    )
    internal_role_name: str = Field(
        ..., description="Internal RBAC role (e.g., 'it_agent')",
        pattern=r"^(employee|it_agent|it_lead|it_admin|security_auditor)$",
    )
    match_type: Literal["exact", "prefix", "regex"] = "exact"
    priority: int = Field(default=0, ge=0, le=100)


class GroupRoleMappingCreate(GroupRoleMappingBase):
    """Create a new group-role mapping."""

    pass


class GroupRoleMappingUpdate(BaseModel):
    """Update an existing group-role mapping."""

    idp_group_name: str | None = None
    internal_role_name: str | None = None
    match_type: Literal["exact", "prefix", "regex"] | None = None
    priority: int | None = None
    is_active: bool | None = None


class GroupRoleMappingResponse(GroupRoleMappingBase):
    """Group-role mapping response."""

    id: str
    idp_config_id: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Certificate Management ───────────────────────────────────────────────────


class CertificateUpload(BaseModel):
    """Upload an IdP signing certificate."""

    certificate_pem: str = Field(
        ..., description="X.509 certificate in PEM format",
    )
    is_primary: bool = Field(
        default=True, description="Set as primary signing certificate",
    )


class CertificateInfo(BaseModel):
    """Certificate metadata (does not include full PEM content)."""

    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    is_expired: bool
    days_until_expiry: int


class SPCertificateGenerate(BaseModel):
    """Request to generate a new SP certificate pair."""

    label: str = Field(..., description="Friendly label for the cert")
    purpose: Literal["signing", "encryption"] = "signing"
    validity_years: int = Field(default=2, ge=1, le=5)
    common_name: str = Field(default="Aditi IT Assist SP")


# ─── SAML Test & Validation ───────────────────────────────────────────────────


class SAMLTestResult(BaseModel):
    """Result of testing SAML configuration."""

    success: bool
    errors: list[str] = []
    warnings: list[str] = []
    metadata_valid: bool = False
    certificate_valid: bool = False
    endpoints_reachable: bool = False
    test_login_url: str | None = None


# ─── Onboarding/Offboarding ───────────────────────────────────────────────────


class JITProvisioningConfig(BaseModel):
    """Configuration for Just-In-Time user provisioning."""

    enabled: bool = True
    auto_activate: bool = True
    default_role: str = "employee"
    require_email_domain: str | None = Field(
        None, description="Only provision users from this email domain",
    )
    create_auth_identity: bool = True
    sync_attributes_on_login: bool = True
    sync_groups_on_login: bool = True


class OffboardingConfig(BaseModel):
    """Configuration for user offboarding/deprovisioning."""

    deactivate_on_group_removal: bool = Field(
        default=False,
        description="Deactivate user if removed from all mapped groups",
    )
    revoke_sessions_on_deactivate: bool = True
    retain_data_days: int = Field(
        default=90, description="Days to retain user data after deactivation",
    )
    notify_admin_on_deactivation: bool = True
