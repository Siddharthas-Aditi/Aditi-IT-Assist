# Security & Governance — Aditi IT Assist

## Authentication & Authorization

### Current Phase (Development)
- JWT-based token authentication
- Role-based access control (RBAC)
- Roles: `employee`, `it_agent`, `admin`

### Future Phase (Production)
- Azure AD / Entra ID SSO integration
- OAuth 2.0 / OIDC flow
- MFA enforcement
- Session management with token rotation

## Data Protection

### Data Classification
- **Confidential**: User credentials, API keys, LLM responses with PII
- **Internal**: Support conversations, ticket details, knowledge base
- **Public**: System health status, anonymized metrics

### Encryption
- TLS 1.3 for all network communication
- AES-256 encryption at rest for database
- Secrets managed via environment variables (future: Azure Key Vault)

### PII Handling
- Conversation data may contain employee PII
- PII is not sent to external LLM providers without redaction (future)
- Data retention policy: 90 days for conversations, 1 year for tickets

## API Security

- Rate limiting: 60 requests/minute per user
- Input validation on all endpoints (Pydantic)
- SQL injection prevention (parameterized queries via SQLAlchemy)
- XSS prevention (React default escaping + CSP headers)
- CORS restricted to known origins

## AI Safety

- LLM outputs are not trusted — they pass through validation layer
- Confidence scoring prevents over-reliance on AI
- Escalation path ensures human oversight
- No autonomous actions (ticket creation requires user approval)
- Prompt injection mitigation via input sanitization

## Audit & Compliance

- All agent decisions logged to audit_events table
- Immutable audit trail (append-only)
- Session recordings preserved for quality review
- Admin dashboard for audit log review

## Incident Response

- See `docs/runbooks/incident-response.md` for procedures
- Error alerting via structured logging
- Circuit breaker pattern for external service failures
