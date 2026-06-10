# SAML SSO Integration Roadmap

> Phased implementation plan for enterprise SSO integration in Aditi IT Assist.
> Target IdPs: Microsoft Entra ID, Okta (extensible to any SAML 2.0 IdP).

---

## 1. Current Architecture Status

| Component | Status | Location |
|-----------|--------|----------|
| Pluggable auth provider interface | ✅ Complete | `services/auth/providers/base.py` |
| SAML provider (extensible stub) | ✅ Complete | `services/auth/providers/saml.py` |
| SAML API endpoints (full flow) | ✅ Complete | `api/v1/auth.py` |
| IdP configuration model | ✅ Complete | `models/sso.py` |
| SAML schemas (Pydantic) | ✅ Complete | `schemas/sso.py` |
| Group-to-role mapping logic | ✅ Complete | `providers/saml.py` (GroupRoleMapping) |
| IdP presets (Entra, Okta) | ✅ Complete | `providers/saml.py` helpers |
| SP metadata generation | ✅ Template | needs python3-saml |
| SAML assertion processing | 🔲 Stub | needs python3-saml |
| JIT user provisioning | 🔲 Designed | needs implementation |
| Certificate management | 🔲 Model only | needs crypto util |
| Admin UI for IdP config | 🔲 Not started | frontend |
| SCIM provisioning | 🔲 Future | phase 4 |

---

## 2. Implementation Phases

### Phase 1: Foundation (Week 1-2) — CURRENT

**Goal**: Extensible architecture with all interfaces defined.

- [x] `AuthProvider` ABC with SSO lifecycle methods
- [x] `SAMLAuthProvider` with full method signatures
- [x] `SAMLIdPConfig`, `SAMLSPConfig`, `GroupRoleMapping` dataclasses
- [x] `IdentityProviderConfig` SQLAlchemy model
- [x] `IdPGroupRoleMapping` SQLAlchemy model
- [x] Pydantic schemas for admin CRUD
- [x] FastAPI routes: `/saml/login`, `/saml/acs`, `/saml/metadata`, `/saml/sls`
- [x] Preset helpers: `entra_id_config()`, `okta_config()`
- [x] Configuration in `settings` (SAML_ENABLED, cert paths, etc.)

### Phase 2: Core SAML Processing (Week 3-4)

**Goal**: Functional SAML login with a single IdP.

**Dependencies**:
```toml
# pyproject.toml
[project.optional-dependencies]
saml = ["python3-saml>=1.16.0", "cryptography>=42.0"]
```

**System dependency**: `xmlsec1` (for XML signature validation)

**Tasks**:
- [ ] Install `python3-saml` + `xmlsec1`
- [ ] Implement `_build_saml_settings()` → `OneLogin_Saml2_Settings` from our config
- [ ] Implement `initiate_login()` → generate `AuthnRequest` + redirect URL
- [ ] Implement `process_callback()` → validate response + extract claims
- [ ] Implement `get_metadata()` → proper SP metadata via library
- [ ] Implement `initiate_logout()` → `LogoutRequest` generation
- [ ] Implement `process_slo_response()` → validate `LogoutResponse`
- [ ] Add assertion validation: signature, conditions, audience, replay
- [ ] Integration tests with samltool.io mock IdP

### Phase 3: User Lifecycle (Week 5-6)

**Goal**: JIT provisioning, attribute sync, group-based role assignment.

**Tasks**:
- [ ] Implement `jit_provision_user()` — create User + AuthIdentity + roles
- [ ] Implement `sync_user_attributes()` — update on each login
- [ ] Implement group-sync logic — add/remove role assignments
- [ ] Handle domain validation (only provision `@aditi*.com` emails)
- [ ] Store `session_index` + `name_id` in `LoginSession` for SLO
- [ ] Emit audit events: `user_provisioned`, `roles_synced`, `user_deactivated`
- [ ] Admin endpoint: GET `/admin/sso/idp` — list IdP configs
- [ ] Admin endpoint: POST `/admin/sso/idp` — create IdP config
- [ ] Admin endpoint: CRUD `/admin/sso/idp/{id}/mappings` — group mappings
- [ ] Migration: add `sso` models to Alembic

### Phase 4: Admin UI & Certificate Management (Week 7-8)

**Goal**: Self-service IdP configuration via admin dashboard.

**Tasks**:
- [ ] Frontend: SSO configuration page (`/dashboard/sso`)
- [ ] Frontend: IdP setup wizard (upload cert, paste metadata URL)
- [ ] Frontend: Group-mapping editor (table with add/edit/delete)
- [ ] Frontend: Test connection button → `POST /admin/sso/test`
- [ ] Backend: Certificate parsing utility (extract expiry, subject, etc.)
- [ ] Backend: SP cert generation endpoint (self-signed for dev)
- [ ] Backend: Metadata URL auto-refresh (periodic task)
- [ ] Backend: Certificate expiry alerting

### Phase 5: Production Hardening (Week 9-10)

**Goal**: Security, monitoring, multi-IdP support.

**Tasks**:
- [ ] XML Signature Wrapping attack protection
- [ ] Assertion replay detection (nonce store in Redis)
- [ ] Rate limiting on SAML endpoints
- [ ] Multi-IdP support (IdP discovery page)
- [ ] IdP-initiated SSO support
- [ ] Encrypted assertions support
- [ ] SAML event monitoring dashboard
- [ ] Certificate rotation without downtime
- [ ] Load testing SAML flow

### Phase 6: Advanced Features (Future)

- [ ] SCIM 2.0 provisioning endpoint (Entra/Okta push)
- [ ] Conditional Access / step-up authentication relay
- [ ] Session binding to SAML assertion validity
- [ ] Cross-tenant federation
- [ ] OIDC provider implementation (reuse same base interface)
- [ ] Social login providers (Google, Microsoft personal)

---

## 3. IdP Configuration Guides

### 3.1 Microsoft Entra ID (Azure AD)

**Azure Portal → Enterprise Applications → New Application → Create your own**

| Setting | Value |
|---------|-------|
| Identifier (Entity ID) | `aditi-it-assist` |
| Reply URL (ACS) | `https://{domain}/api/v1/auth/saml/acs` |
| Sign-on URL | `https://{domain}/login` |
| Logout URL | `https://{domain}/api/v1/auth/saml/sls` |
| Relay State | `https://{domain}/support` |

**Claims Configuration**:

| Claim | Source | Attribute |
|-------|--------|-----------|
| `emailaddress` | user.mail | Required |
| `givenname` | user.givenname | Required |
| `surname` | user.surname | Required |
| `name` | user.displayname | Required |
| `groups` | Group membership | Required — emit as group names |
| `employeeid` | user.employeeid | Optional |
| `department` | user.department | Optional |

**Group Claims**: Configure → "Groups assigned to the application" → Emit group names (not Object IDs).

**Our Config** (using helper):
```python
from app.services.auth.providers.saml import entra_id_config

idp = entra_id_config(tenant_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
# Then set idp.x509_cert from downloaded certificate
```

### 3.2 Okta

**Okta Admin → Applications → Create App Integration → SAML 2.0**

| Setting | Value |
|---------|-------|
| Single Sign-On URL | `https://{domain}/api/v1/auth/saml/acs` |
| Audience URI (SP Entity ID) | `aditi-it-assist` |
| Default RelayState | `https://{domain}/support` |
| Name ID Format | EmailAddress |
| Application username | Okta username (email) |

**Attribute Statements**:

| Name | Format | Value |
|------|--------|-------|
| `email` | Unspecified | user.email |
| `firstName` | Unspecified | user.firstName |
| `lastName` | Unspecified | user.lastName |
| `displayName` | Unspecified | `String.join(" ", user.firstName, user.lastName)` |
| `department` | Unspecified | user.department |
| `employeeNumber` | Unspecified | user.employeeNumber |

**Group Attribute**: Name = `groups`, Filter = Matches regex `aditi-.*`

**Our Config** (using helper):
```python
from app.services.auth.providers.saml import okta_config

idp = okta_config(okta_domain="aditiconsulting.okta.com", app_id="abc123def456")
```

---

## 4. Group → Role Mapping Strategy

### Default Mappings

| IdP Group Pattern | Internal Role | Priority |
|-------------------|---------------|----------|
| `IT-Admins` / `aditi-it-admin` | `it_admin` | 40 |
| `IT-Team-Leads` / `aditi-it-leads` | `it_lead` | 30 |
| `IT-Support-Team` / `aditi-it-agents` | `it_agent` | 20 |
| `Security-Auditors` / `aditi-security` | `security_auditor` | 15 |
| `All-Employees` / `aditi-employees` | `employee` | 10 |

### Conflict Resolution

When a user belongs to multiple groups that map to different roles:
1. **All mapped roles are assigned** (user can have multiple roles)
2. **Primary role** = highest priority mapping
3. **Effective permissions** = union of all role permissions (via inheritance)

### Admin-Configurable Mappings

Stored in `idp_group_role_mappings` table, manageable via admin UI.
Supports match types: `exact`, `prefix`, `regex`.

---

## 5. Onboarding / Offboarding Flow

### First-Time Login (JIT Provisioning)

```
User clicks "Login with SSO"
  → Redirect to IdP
  → User authenticates at IdP
  → IdP POSTs assertion to ACS
  → We validate assertion
  → Email lookup in users table
  → NOT FOUND:
      → Create User (email, name, department from claims)
      → Create AuthIdentity (provider=saml, provider_user_id=NameID)
      → Map groups → assign roles
      → Emit audit event: "user_provisioned"
      → Issue JWT, redirect to frontend
```

### Subsequent Logins (Attribute Sync)

```
User clicks "Login with SSO"
  → Same SAML flow...
  → Email lookup → FOUND:
      → Update last_login_at
      → Sync attributes if changed (department, name)
      → Sync group memberships → update roles
      → Emit audit event: "user_login_saml"
      → Issue JWT, redirect to frontend
```

### Offboarding

| Trigger | Detection | Action |
|---------|-----------|--------|
| User removed from all IdP groups | Next login attempt → no groups | Deactivate account |
| User disabled in IdP | SAML response indicates disabled | Deactivate + revoke sessions |
| SCIM DELETE (future) | Webhook from IdP | Immediate deactivation |
| Manual admin action | Admin UI | Immediate deactivation |
| Certificate expiry | IdP cert expired | Block all SAML logins (fallback to local) |

**Deactivation behavior**:
- `is_active = False` (soft delete, data preserved)
- All active `LoginSession` records revoked
- Audit event emitted
- Admin notified via configured channel
- Data retained for 90 days (configurable)

---

## 6. Certificate Handling

### IdP Certificate (their cert, we validate)

| Concern | Approach |
|---------|----------|
| Storage | `identity_provider_configs.x509_cert` (PEM in DB) |
| Rotation | Secondary cert field for overlap period |
| Auto-refresh | Periodic fetch from `metadata_url` |
| Expiry alert | Background job checks `cert_expires_at` |
| Format | PEM (X.509) |

### SP Certificate (our cert, they validate)

| Concern | Approach |
|---------|----------|
| Storage | `sp_certificates` table (encrypted private key) |
| Generation | Admin endpoint or CLI command |
| Signing | Used to sign `AuthnRequest` and `LogoutRequest` |
| Encryption | Used to decrypt encrypted assertions |
| Rotation | New cert generated → update metadata at IdP → deactivate old |
| Format | PEM (X.509) + PEM (RSA private key) |

### Rotation Procedure

```
1. Generate new SP certificate pair
2. Add to SP metadata (both old + new in KeyDescriptor)
3. Update metadata at IdP (re-import or auto-refresh)
4. Wait for IdP to recognize new cert (24-48h)
5. Switch signing to new cert
6. Remove old cert from metadata after grace period
```

---

## 7. Security Checklist

- [ ] Validate XML signature on every SAML response
- [ ] Validate assertion conditions (`NotBefore`, `NotOnOrAfter`)
- [ ] Validate `Audience` restriction matches our Entity ID
- [ ] Protect against XML Signature Wrapping (XSW) attacks
- [ ] Assertion replay protection (store used `InResponseTo` IDs in Redis, TTL=5min)
- [ ] Use HTTPS for all SAML endpoints (redirect binding + POST binding)
- [ ] Never log full SAML assertions (contain PII)
- [ ] SP private key stored encrypted at rest
- [ ] Rate limit ACS endpoint (max 10 req/s per IP)
- [ ] Monitor for assertion time skew (>5 min drift = alert)
- [ ] Audit log all SAML events (login, logout, JIT provision, errors)
- [ ] Disable SAML_ENABLED in dev to prevent accidental IdP registration

---

## 8. Configuration Reference

### Environment Variables

```env
# Enable SAML SSO
SAML_ENABLED=true
AUTH_PROVIDER=local  # Keep local as fallback; SAML is additive

# IdP Configuration (can also be stored in DB)
SAML_IDP_ENTITY_ID=https://sts.windows.net/{tenant-id}/
SAML_IDP_SSO_URL=https://login.microsoftonline.com/{tenant-id}/saml2
SAML_IDP_SLO_URL=https://login.microsoftonline.com/{tenant-id}/saml2
SAML_IDP_CERTIFICATE=<path-to-idp-cert.pem>

# SP Configuration
SAML_SP_ENTITY_ID=aditi-it-assist
SAML_SP_ACS_URL=https://your-domain.com/api/v1/auth/saml/acs
SAML_SP_SLS_URL=https://your-domain.com/api/v1/auth/saml/sls
SAML_SP_CERT=<path-to-sp-cert.pem>
SAML_SP_KEY=<path-to-sp-key.pem>

# Behavior
SAML_DEFAULT_ROLE=employee
SAML_JIT_PROVISIONING=true
SAML_GROUP_SYNC=true
SAML_ALLOWED_EMAIL_DOMAINS=aditiconsulting.com,aditi.com
```

### Key Code Paths

| Purpose | File |
|---------|------|
| Provider interface | `backend/app/services/auth/providers/base.py` |
| SAML implementation | `backend/app/services/auth/providers/saml.py` |
| API routes | `backend/app/api/v1/auth.py` |
| IdP DB model | `backend/app/models/sso.py` |
| Admin schemas | `backend/app/schemas/sso.py` |
| Config settings | `backend/app/core/config.py` |
| Architecture doc | `docs/architecture/authentication.md` |

---

## 9. Testing Strategy

| Level | What | How |
|-------|------|-----|
| Unit | Group mapping logic | pytest with mock claims |
| Unit | Claims extraction | pytest with fixture assertions |
| Integration | Full SAML flow | samltool.io mock IdP |
| Integration | JIT provisioning | Test DB with assertion fixtures |
| E2E | Browser SSO flow | Playwright + mock IdP |
| Security | XSW attacks | Dedicated attack payloads |
| Load | ACS endpoint throughput | locust / k6 |

---

## 10. Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Use `python3-saml` over `pysaml2` | Simpler API, better docs, OneLogin maintained | 2026-06 |
| 2 | Keep local auth alongside SAML | Fallback for IdP outages + dev environment | 2026-06 |
| 3 | Store IdP config in DB (not just env) | Enables admin UI config without redeploy | 2026-06 |
| 4 | JIT provisioning over pre-provisioning | Reduces sync complexity, immediate access | 2026-06 |
| 5 | Issue internal JWT after SAML auth | Consistent session handling across providers | 2026-06 |
| 6 | Multi-IdP support from day one | Architecture supports it, even if single-IdP initially | 2026-06 |
| 7 | Group-based role mapping (not claim-based) | Aligns with how Entra/Okta manage access | 2026-06 |
| 8 | Soft-delete on offboarding | Audit retention + potential re-onboarding | 2026-06 |
