# Docker Deployment Guide

**Status**: ✅ **READY FOR DEVELOPMENT**

## Quick Start

```bash
# Start all services
docker compose up -d

# Verify containers are healthy
docker compose ps

# View logs
docker compose logs backend    # Backend logs
docker compose logs frontend   # Frontend logs

# Stop all services
docker compose down
```

## Container Architecture

| Service | Image | Port | Status |
|---------|-------|------|--------|
| **PostgreSQL 16** | `pgvector/pgvector:pg16` | 5432 | ✅ Healthy |
| **Redis 7** | `redis:7-alpine` | 6379 | ✅ Healthy |
| **FastAPI Backend** | `aditi-assist-backend:latest` | 8000 | ✅ Healthy |
| **React Frontend** | `aditi-assist-frontend:latest` | 5173 | ✅ Healthy |

## Database Configuration

**Connection String (in Docker):**
```
postgresql+asyncpg://aditi:aditi_dev_password@postgres:5432/aditi_assist
```

**Features:**
- ✅ pgvector enabled for knowledge base similarity search
- ✅ 23 enterprise tables auto-created on startup via `Base.metadata.create_all()`
- ✅ Schema migration scripts ready for production (alembic)

**Seeded Data:**
- 56 permissions across 8 resource types
- 5 roles: `employee`, `it_agent`, `it_lead`, `it_admin`, `security_auditor`
- 7 sample users with role assignments
- 5 sample tickets for testing
- 4 knowledge base articles (Outlook, Zoom, Network, Access)

## Sample Credentials

```
┌─────────────────────────────────────────┬──────────────┬────────────┐
│ Email                                   │ Password     │ Role       │
├─────────────────────────────────────────┼──────────────┼────────────┤
│ alice.johnson@aditi.com                 │ employee123  │ employee   │
│ bob.williams@aditi.com                  │ employee123  │ employee   │
│ charlie.agent@aditi.com                 │ agent123     │ it_agent   │
│ diana.agent@aditi.com                   │ agent123     │ it_agent   │
│ edward.lead@aditi.com                   │ lead123      │ it_lead    │
│ admin@aditi.com                         │ admin123     │ it_admin   │
│ auditor@aditi.com                       │ auditor123   │ security   │
└─────────────────────────────────────────┴──────────────┴────────────┘
```

## API Endpoints — Quick Test

**⚠️ Important: All endpoints require the `/api/v1` prefix. See LOGIN_FIX.md if you get 404 errors.**

### 1. Health Check
```bash
curl http://localhost:8000/api/v1/health
# Returns: {"status": "healthy", "service": "aditi-it-assist", "version": "0.1.0"}
```

### 2. Authentication
```bash
# Login — MUST use /api/v1/ prefix
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.johnson@aditi.com","password":"employee123"}' \
  | jq -r '.access_token')

# Get authenticated user
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/auth/me
```

### 3. Tickets (Employee)
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/tickets/my
```

### 4. Knowledge Search
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/knowledge/search?query=outlook"
```

### 5. Chat with OpenAI
```bash
curl -X POST http://localhost:8000/api/v1/chat/message \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"My Outlook is not receiving emails"}'
```

### 6. Analytics Dashboard (IT Lead)
```bash
LEAD_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"edward.lead@aditi.com","password":"lead123"}' \
  | jq -r '.access_token')

curl -H "Authorization: Bearer $LEAD_TOKEN" \
  http://localhost:8000/api/v1/analytics/dashboard
```

### 7. Admin Endpoints
```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aditi.com","password":"admin123"}' \
  | jq -r '.access_token')

# Admin stats
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/v1/admin/stats

# Audit log
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/v1/admin/audit-log
```

## LLM Configuration

**OpenAI Integration:**
- Model: `gpt-4o-mini`
- Provider: OpenAI (via LiteLLM abstraction)
- Configuration: `.env` file

**Setup:**
1. Set `LLM_API_KEY` in `.env`:
   ```
   LLM_API_KEY=sk-proj-your-actual-key-here
   ```

2. Restart backend:
   ```bash
   docker compose restart backend
   ```

3. Test chat endpoint:
   ```bash
   curl -X POST http://localhost:8000/api/v1/chat/message \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"message":"My Outlook is not receiving emails"}'
   ```

**Response Format:**
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "issue_category": "email/outlook",
  "confidence_score": 0.85,
  "resolution_steps": [
    {
      "step_number": 1,
      "instruction": "Check if Work Offline mode is enabled",
      "details": "Go to Send/Receive tab..."
    }
  ],
  "ai_message": "Here are the steps..."
}
```

## Test Suite

**Run all tests in Docker:**
```bash
docker compose exec backend uv run pytest tests/ -q
# Result: 140 passed ✅
```

**Run specific test file:**
```bash
docker compose exec backend uv run pytest tests/unit/test_services/test_auth.py -v
```

**Run with coverage:**
```bash
docker compose exec backend uv run pytest tests/ --cov=app --cov-report=html
```

## Frontend

**Access at**: http://localhost:5173

**Development:**
- Hot-reload enabled
- Source maps included
- Tailwind CSS auto-compilation

**Build:**
```bash
# Build production image
docker compose build frontend

# Output: dist/ folder (ready for deployment)
```

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker compose logs backend

# Common issues:
# 1. Port 8000 in use: lsof -i :8000 | grep -v PID | awk '{print $2}' | xargs kill -9
# 2. Database not ready: Wait 5 seconds and restart
# 3. Missing env vars: Check .env file
```

### Database issues
```bash
# Check database health
docker compose exec postgres pg_isready

# Connect to database
docker compose exec postgres psql -U aditi -d aditi_assist

# View tables
\dt+

# Check specific table
SELECT COUNT(*) FROM users;
```

### Redis issues
```bash
# Check Redis
docker compose exec redis redis-cli ping
# Should return: PONG
```

### LLM API failures
```bash
# Check backend logs for OpenAI errors
docker compose logs backend | grep -i "openai\|llm\|api"

# Verify API key
echo $LLM_API_KEY

# Test with curl (requires jq)
curl -s http://localhost:8000/api/v1/health | jq
```

## Database Migrations

**Auto-schema creation (dev only):**
```python
# backend/app/main.py — Runs on startup
Base.metadata.create_all(engine)
```

**Production migrations (alembic):**
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Performance Notes

- **Backend hot-reload:** Changes to Python files auto-reload (uvicorn --reload)
- **Frontend hot-reload:** Changes to React files auto-reload (Vite HMR)
- **Database volume:** Data persists in `postgres_data/` volume
- **Response times:** ~200ms for typical endpoints (after first request)

## Security Notes

⚠️ **Development Only:**
- Hardcoded DB credentials in `.env`
- No HTTPS (use localhost:8000)
- Email-validator not production-ready
- CORS wide-open for local development

For production deployment, see `/docs/security/` directory.

## Next Steps

1. ✅ Test all endpoints with provided credentials
2. ✅ Verify OpenAI integration with real API key
3. ✅ Run full test suite (`docker compose exec backend uv run pytest tests/`)
4. 📝 Integration with CI/CD pipeline
5. 📝 Kubernetes deployment configuration
6. 📝 Production security hardening

## Related Documentation

- Backend API: `/docs/architecture/system-architecture.md`
- Multi-agent workflows: `/AGENTS.md`
- Database schema: `/docs/architecture/data-model.md`
- Authentication & RBAC: `/docs/architecture/access-control.md`
- Remote support: `/docs/architecture/remote-support.md`

---

**Status**: ✅ All 140 tests passing | All services healthy | LLM integrated
**Commit**: `66a5c59` — Docker deployment fixes
**Last Updated**: 2026-06-10
