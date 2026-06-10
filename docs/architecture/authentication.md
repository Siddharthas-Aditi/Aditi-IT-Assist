# Authentication Architecture

> Complete authentication system design for Aditi IT Assist.
> Covers local auth, SAML SSO, session management, and extensibility.

---

## 1. Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Pluggable providers** | Abstract `AuthProvider` base class; runtime selection via config |
| **Local auth always available** | SAML is additive; local never removed (fallback for outages) |
| **Single session format** | All providers issue the same internal JWT after auth |
| **Database-driven config** | IdP settings stored in DB (no redeploy for new IdP) |
| **Separation of concerns** | Provider handles auth; service handles session/user lifecycle |
| **Audit everything** | Every auth event logged to immutable audit trail |

---

## 2. Provider Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       AuthProvider (ABC)                              │
│                                                                      │
│  provider_name        ─ str                                          │
│  supports_sso         ─ bool                                         │
│  supports_jit         ─ bool                                         │
│  supports_group_sync  ─ bool                                         │
│                                                                      │
│  authenticate(**kw)        → AuthResult                              │
│  validate_session(token)   → AuthResult                              │
│  logout(user_id, sid)      → bool                                    │
│                                                                      │
│  # SSO extension points:                                             │
│  initiate_login(relay_state, idp_id) → SSOLoginResult                │
│  process_callback(**kw)              → AuthResult                    │
│  initiate_logout(user_id, ...)       → SSOLogoutResult               │
│  get_metadata()                      → str | None                    │
└──────────────┬──────────────────────────────────┬────────────────────┘
               │                                  │
    ┌──────────▼──────────┐           ┌──────────▼──────────┐
    │  LocalAuthProvider   │           │  SAMLAuthProvider    │
    │                      │           │                      │
    │  email/password      │           │  SAML 2.0 SSO       │
    │  bcrypt hashing      │           │  JIT provisioning    │
    │  JWT session create  │           │  Group→Role mapping  │
    │                      │           │  Multi-IdP support   │
    └──────────────────────┘           └──────────────────────┘
                                                │
                                       ┌────────▼────────┐
                                       │ Future: OIDC    │
                                       │ Provider        │
                                       └─────────────────┘
```

### Provider Registry

| Provider | Class | Status | Config Key |
|----------|-------|--------|------------|
| `local` | `LocalAuthProvider` | ✅ Production | `AUTH_PROVIDER=local` |
| `saml` | `SAMLAuthProvider` | ✅ Architecture complete | `SAML_ENABLED=true` |
| `oidc` | `OIDCAuthProvider` | 📋 Planned | — |

### Result Types

```python
@dataclass
class AuthResult:
    success: bool
    user: User | None
    error: str | None
    provider: str
    provider_user_id: str | None
    claims: dict | None
    session_index: str | None    # SAML SessionIndex
    name_id: str | None          # SAML NameID
    groups: list[str]            # IdP groups
    is_new_user: bool            # JIT provisioned

@dataclass
class SSOLoginResult:
    redirect_url: str | None
    error: str | None
    request_id: str | None       # AuthnRequest ID

@dataclass
class SSOLogoutResult:
    redirect_url: str | None
    success: bool
    error: str | None
```

---

## 3. Authentication Flows

### 3.1 Local Login (Email + Password)

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Client  │         │  Backend │         │    DB    │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │  POST /auth/login   │                    │
     │  {email, password}  │                    │
     │────────────────────►│                    │
     │                     │  SELECT user       │
     │                     │───────────────────►│
     │                     │  user record       │
     │                     │◄───────────────────│
     │                     │                    │
     │                     │  bcrypt verify     │
     │                     │  create JWT        │
     │                     │  record session    │
     │                     │───────────────────►│
     │                     │                    │
     │  {access_token,     │                    │
     │   refresh_token,    │                    │
     │   user}             │                    │
     │◄────────────────────│                    │
```

**JWT payload**:
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "email": "charlie.agent@aditi.com",
  "role": "it_agent",
  "roles": ["it_agent"],
  "jti": "unique-session-uuid",
  "provider": "local",
  "iat": 1718035200,
  "exp": 1718121600
}
```

### 3.2 SAML SSO Login (SP-Initiated)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Browser │    │  Backend │    │   IdP    │    │    DB    │
└────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
     │ GET /auth/saml/login        │               │
     │ ?relay_state=/support       │               │
     │────────────────────────────►│               │
     │                             │               │
     │  302 Redirect               │               │
     │  Location: IdP SSO URL      │               │
     │  + SAMLRequest (AuthnReq)   │               │
     │◄────────────────────────────│               │
     │                             │               │
     │  Redirect to IdP            │               │
     │────────────────────────────────────────────►│
     │                             │               │
     │  User authenticates at IdP  │               │
     │◄───────────────────────────────────────────►│
     │                             │               │
     │  POST /auth/saml/acs        │               │
     │  SAMLResponse (assertion)   │               │
     │  RelayState                 │               │
     │────────────────────────────►│               │
     │                             │               │
     │                             │  Validate signature
     │                             │  Extract claims
     │                             │  Map groups→roles
     │                             │               │
     │                             │  Lookup/JIT user      │
     │                             │──────────────────────►│
     │                             │  user record          │
     │                             │◄──────────────────────│
     │                             │               │
     │                             │  Issue JWT     │
     │                             │  Record session│
     │                             │──────────────────────►│
     │                             │               │
     │  302 Redirect               │               │
     │  /support?token=jwt         │               │
     │◄────────────────────────────│               │
```

### 3.3 SAML Single Logout (SP-Initiated)

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  Browser │    │  Backend │    │   IdP    │
└────┬─────┘    └────┬─────┘    └────┬─────┘
     │ POST /auth/saml/logout      │
     │────────────────────────────►│
     │                             │
     │                             │  Build LogoutRequest
     │                             │  (SessionIndex + NameID)
     │                             │
     │  302 Redirect               │
     │  Location: IdP SLO URL      │
     │  + SAMLRequest              │
     │◄────────────────────────────│
     │                             │
     │  Redirect to IdP SLO        │
     │─────────────────────────────────────────►│
     │                             │            │
     │  IdP terminates session     │            │
     │                             │            │
     │  302 Redirect to SLS        │            │
     │  + SAMLResponse             │            │
     │◄────────────────────────────────────────│
     │                             │
     │  GET /auth/saml/sls         │
     │  ?SAMLResponse=...          │
     │────────────────────────────►│
     │                             │
     │                             │  Validate LogoutResponse
     │                             │  Revoke local session
     │                             │
     │  302 → /login?slo=success   │
     │◄────────────────────────────│
```

---

## 4. Session Management

### Session Storage

All providers converge to the same internal session mechanism:

| Field | Source |
|-------|--------|
| `token_jti` | UUID generated at login |
| `user_id` | Internal user ID |
| `provider` | `"local"` or `"saml"` |
| `ip_address` | Request IP |
| `user_agent` | Browser UA |
| `expires_at` | Token expiry time |
| `saml_session_index` | SAML SessionIndex (for SLO) |
| `saml_name_id` | SAML NameID (for SLO) |

### Token Lifecycle

| Event | Action |
|-------|--------|
| Login | Create `LoginSession` + issue JWT |
| API request | Validate JWT signature + expiry |
| Refresh | Issue new JWT (same `jti`) |
| Logout | Revoke `LoginSession` |
| SAML SLO | Revoke all sessions for user with matching `session_index` |
| Password change | Revoke all user sessions |
| Admin deactivation | Revoke all user sessions |

### Token Revocation

Currently: session table with `is_active` flag.
Future: Redis-backed token blacklist for immediate revocation.

---

## 5. Data Model

### Core Auth Tables

```
┌─────────────────────┐       ┌──────────────────────┐
│       users          │       │   auth_identities    │
├─────────────────────┤       ├──────────────────────┤
│ id (UUID, PK)       │       │ id (UUID, PK)        │
│ email               │◄──────│ user_id (FK)         │
│ full_name           │       │ provider (enum)      │
│ hashed_password     │       │ provider_user_id     │
│ is_active           │       │ provider_email       │
│ is_verified         │       │ provider_metadata    │
│ last_login_at       │       │ last_login_at        │
└─────────────────────┘       └──────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────┐       ┌──────────────────────────────┐
│   login_sessions     │       │  identity_provider_configs   │
├─────────────────────┤       ├──────────────────────────────┤
│ id (UUID, PK)       │       │ id (UUID, PK)                │
│ user_id (FK)        │       │ idp_id (unique)              │
│ token_jti           │       │ entity_id                    │
│ provider            │       │ sso_url, slo_url             │
│ ip_address          │       │ x509_cert                    │
│ user_agent          │       │ attribute_mapping (JSONB)    │
│ expires_at          │       │ jit_provisioning_enabled     │
│ is_active           │       │ group_sync_enabled           │
│ saml_session_index  │       │ status (active/inactive)     │
│ saml_name_id        │       └──────────────────────────────┘
└─────────────────────┘                │ 1:N
                                       ▼
                              ┌──────────────────────────────┐
                              │  idp_group_role_mappings      │
                              ├──────────────────────────────┤
                              │ idp_config_id (FK)            │
                              │ idp_group_name                │
                              │ internal_role_name            │
                              │ match_type, priority          │
                              └──────────────────────────────┘
```

---

## 6. Provider Selection Logic

```python
# Startup: resolve auth providers
providers: dict[str, AuthProvider] = {}

# Local is ALWAYS available
providers["local"] = LocalAuthProvider()

# SAML is available if enabled
if settings.SAML_ENABLED:
    # Load IdP configs from DB
    idp_configs = await load_idp_configs_from_db()
    group_mappings = await load_group_mappings_from_db()
    providers["saml"] = SAMLAuthProvider(
        sp_config=build_sp_config(settings),
        idp_configs=idp_configs,
        group_mappings=group_mappings,
    )

# Route resolution:
# /auth/login         → providers["local"]
# /auth/saml/login    → providers["saml"]
# /auth/saml/acs      → providers["saml"]
# Token validation    → providers[session.provider]
```

**Key**: Both providers can coexist. The frontend shows both login options.

---

## 7. Frontend Integration

### Login Page Behavior

```typescript
// Check if SSO is available
const { data: samlStatus } = useQuery('/auth/saml/status');

// Render:
// [Login with Email]  ← always shown
// [Login with SSO]    ← shown if samlStatus.enabled && samlStatus.configured
```

### SSO Login Button Action

```typescript
function handleSSOLogin() {
  // Redirect to backend SAML login endpoint
  // which will redirect to IdP
  window.location.href = `/api/v1/auth/saml/login?relay_state=${window.location.pathname}`;
}
```

### Token Reception (after ACS redirect)

```typescript
// Frontend route handler for /?token=xxx (redirect from ACS)
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  if (token) {
    authStore.setToken(token);
    // Remove token from URL
    window.history.replaceState({}, '', window.location.pathname);
  }
}, []);
```

---

## 8. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Password storage | bcrypt with cost factor 12 |
| JWT algorithm | HS256 (upgrade to RS256 for multi-service) |
| SAML assertion replay | Nonce tracking in Redis (5-min TTL) |
| XSW attacks | python3-saml's built-in protection |
| Token theft | Short expiry (24h) + refresh rotation |
| Session fixation | New JTI on every login |
| CSRF on ACS | RelayState includes CSRF token |
| Brute force | Rate limiting (5 attempts/min per email) |
| IdP certificate expiry | Monitoring + auto-refresh from metadata URL |

---

## 9. Observability

### Auth Events Logged

| Event | Level | Fields |
|-------|-------|--------|
| `auth_login_success` | INFO | user_id, provider, ip |
| `auth_login_failure` | WARN | email, provider, reason, ip |
| `auth_saml_initiate` | INFO | idp_id, relay_state |
| `auth_saml_acs_success` | INFO | user_id, is_new_user, groups |
| `auth_saml_acs_failure` | ERROR | error, idp_id |
| `auth_saml_slo` | INFO | user_id, session_index |
| `auth_jit_provision` | INFO | email, roles, idp_id |
| `auth_session_revoked` | INFO | user_id, reason |
| `auth_token_expired` | DEBUG | user_id, jti |

### Metrics

| Metric | Type | Alert |
|--------|------|-------|
| `auth.login.total` | Counter (by provider, status) | — |
| `auth.login.latency` | Histogram (by provider) | p99 > 5s |
| `auth.saml.assertion_validation` | Counter (success/failure) | failure rate > 5% |
| `auth.jit_provision.total` | Counter | — |
| `auth.active_sessions` | Gauge | > 10,000 |

---

## 10. File Reference

| Purpose | Path |
|---------|------|
| Provider interface | `backend/app/services/auth/providers/base.py` |
| Local provider | `backend/app/services/auth/providers/local.py` |
| SAML provider | `backend/app/services/auth/providers/saml.py` |
| Auth service | `backend/app/services/auth/service.py` |
| Auth dependencies | `backend/app/services/auth/dependencies.py` |
| API routes | `backend/app/api/v1/auth.py` |
| User/Role models | `backend/app/models/auth.py` |
| SSO/IdP models | `backend/app/models/sso.py` |
| SSO schemas | `backend/app/schemas/sso.py` |
| RBAC permissions | `backend/app/core/permissions.py` |
| Config | `backend/app/core/config.py` |
| SAML roadmap | `docs/security/saml-roadmap.md` |
| RBAC matrix | `docs/security/rbac-matrix.md` |
