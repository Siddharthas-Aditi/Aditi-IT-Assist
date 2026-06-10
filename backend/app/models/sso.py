"""Identity Provider configuration models for SAML/OIDC SSO.

Stores IdP settings, certificates, claim mappings, and group-role mappings
in the database for admin-configurable SSO without redeployment.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─────────────────────────────────────────────────────────────────────
# Identity Provider Configuration
# ─────────────────────────────────────────────────────────────────────

IDP_PROVIDER_TYPES = ("saml", "oidc")
IDP_STATUS_VALUES = ("active", "inactive", "testing")


class IdentityProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistent IdP configuration for SAML/OIDC providers.

    Each row represents one configured Identity Provider (e.g., Entra ID tenant).
    Supports multiple IdPs for multi-tenant or multi-org setups.
    """

    __tablename__ = "identity_provider_configs"

    # ── Identity ──
    idp_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True,
        comment="Short identifier (e.g., 'entra-prod', 'okta-dev')",
    )
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_type: Mapped[str] = mapped_column(
        Enum(*IDP_PROVIDER_TYPES, name="idp_provider_type"),
        default="saml",
    )
    status: Mapped[str] = mapped_column(
        Enum(*IDP_STATUS_VALUES, name="idp_status"),
        default="inactive",
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── SAML IdP Endpoints ──
    entity_id: Mapped[str] = mapped_column(
        String(500), comment="IdP Entity ID / Issuer URL",
    )
    sso_url: Mapped[str] = mapped_column(
        String(500), comment="IdP Single Sign-On URL (HTTP-Redirect binding)",
    )
    sso_post_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="IdP SSO URL for HTTP-POST binding",
    )
    slo_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="IdP Single Logout URL",
    )
    metadata_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="IdP Federation Metadata URL (for auto-refresh)",
    )

    # ── Certificates ──
    # Stored as PEM text; in production consider encrypting at rest
    x509_cert: Mapped[str] = mapped_column(
        Text, default="",
        comment="Primary IdP signing certificate (PEM)",
    )
    x509_cert_secondary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Secondary cert for rotation (PEM)",
    )
    cert_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Expiry of primary certificate",
    )

    # ── SP Configuration (per-IdP if multi-tenant) ──
    sp_entity_id: Mapped[str] = mapped_column(
        String(500), default="aditi-it-assist",
        comment="SP Entity ID presented to this IdP",
    )

    # ── Claim/Attribute Mapping ──
    attribute_mapping: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Maps IdP attributes to internal fields: {email, name, groups, ...}",
    )

    # ── Security Settings ──
    want_assertions_signed: Mapped[bool] = mapped_column(Boolean, default=True)
    want_response_signed: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_unencrypted_assertions: Mapped[bool] = mapped_column(Boolean, default=False)
    name_id_format: Mapped[str] = mapped_column(
        String(200),
        default="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )

    # ── Behavior ──
    jit_provisioning_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="Auto-create users on first SAML login",
    )
    group_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="Sync group memberships from IdP claims",
    )
    default_role: Mapped[str] = mapped_column(
        String(50), default="employee",
        comment="Role assigned when no group mapping matches",
    )

    # ── Metadata ──
    metadata_last_refreshed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    configured_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    # ── Relationships ──
    group_mappings: Mapped[list["IdPGroupRoleMapping"]] = relationship(
        back_populates="identity_provider",
        cascade="all, delete-orphan",
    )


# ─────────────────────────────────────────────────────────────────────
# IdP Group → Internal Role Mapping
# ─────────────────────────────────────────────────────────────────────


class IdPGroupRoleMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Maps an IdP group claim value to an internal RBAC role.

    Used during SAML assertion processing to determine which roles
    to assign to a user based on their IdP group memberships.
    """

    __tablename__ = "idp_group_role_mappings"

    idp_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_provider_configs.id", ondelete="CASCADE"),
        index=True,
    )
    idp_group_name: Mapped[str] = mapped_column(
        String(255),
        comment="Group name/ID as it appears in IdP claims",
    )
    internal_role_name: Mapped[str] = mapped_column(
        String(50),
        comment="Internal role name (e.g., 'it_agent', 'it_admin')",
    )
    match_type: Mapped[str] = mapped_column(
        String(20), default="exact",
        comment="How to match: 'exact', 'prefix', 'regex'",
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="Higher priority wins on conflicts",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Relationship ──
    identity_provider: Mapped["IdentityProviderConfig"] = relationship(
        back_populates="group_mappings",
    )


# ─────────────────────────────────────────────────────────────────────
# SP Certificate Store
# ─────────────────────────────────────────────────────────────────────


class SPCertificate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Service Provider certificates for SAML signing/encryption.

    Supports certificate rotation: multiple certs can exist,
    but only one is "active" for signing at a time.
    """

    __tablename__ = "sp_certificates"

    label: Mapped[str] = mapped_column(
        String(100), comment="Friendly label (e.g., 'signing-2025')",
    )
    certificate: Mapped[str] = mapped_column(
        Text, comment="PEM-encoded X.509 certificate",
    )
    private_key_encrypted: Mapped[str] = mapped_column(
        Text, comment="PEM private key (encrypted at rest)",
    )
    purpose: Mapped[str] = mapped_column(
        String(20), default="signing",
        comment="'signing' or 'encryption'",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
