# Login Not Working — Solution

## ❌ The Problem

You're trying to login at:
```
POST http://localhost:8000/auth/login
```

This returns **404 Not Found** because the endpoint path is incomplete.

## ✅ The Solution

All API endpoints require the `/api/v1` prefix. Use this instead:

```
POST http://localhost:8000/api/v1/auth/login
```

## 📋 Complete Endpoint Reference

### Authentication
- **Login**: `POST /api/v1/auth/login`
- **Get User Info**: `GET /api/v1/auth/me`
- **Refresh Token**: `POST /api/v1/auth/refresh`
- **Logout**: `POST /api/v1/auth/logout`

### Tickets
- **My Tickets**: `GET /api/v1/tickets/my`
- **Create Ticket**: `POST /api/v1/tickets`
- **Get Ticket**: `GET /api/v1/tickets/{ticket_id}`
- **Update Ticket**: `PUT /api/v1/tickets/{ticket_id}`

### Knowledge
- **Search**: `GET /api/v1/knowledge/search?query={query}`
- **Get Article**: `GET /api/v1/knowledge/articles/{article_id}`

### Chat
- **Send Message**: `POST /api/v1/chat/message`
- **Get Session**: `GET /api/v1/chat/sessions/{session_id}`

### Analytics (IT Lead+)
- **Dashboard**: `GET /api/v1/analytics/dashboard`
- **Metrics**: `GET /api/v1/analytics/metrics`

### Admin (Admin only)
- **Stats**: `GET /api/v1/admin/stats`
- **Audit Log**: `GET /api/v1/admin/audit-log`

### Health
- **Health Check**: `GET /api/v1/health`

---

## 🧪 Working Example

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.johnson@aditi.com","password":"employee123"}' \
  | jq -r '.access_token')

# Use token to get user info
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/auth/me
```

## 📍 API Prefix Configuration

The `/api/v1` prefix is defined in `backend/app/core/config.py`:

```python
API_V1_PREFIX: str = "/api/v1"
```

And applied in `backend/app/main.py`:

```python
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
```

---

**All endpoints must start with `/api/v1/`**
