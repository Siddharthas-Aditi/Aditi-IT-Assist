# Frontend URL Configuration Fix

## Problem
Frontend was not correctly configured to connect to the backend API in Docker environment.

## Root Causes
1. **docker-compose.yml**: Set `VITE_API_URL=http://localhost:8000` (wrong)
   - Should be `http://aditi-backend:8000/api/v1` (service name in Docker network)
   - Was missing `/api/v1` prefix

2. **.env.example**: Showed localhost only, no guidance for Docker

3. **vite.config.ts**: Hardcoded proxy target to `http://localhost:8000`
   - Needed to use environment variable

## Solutions Implemented

### 1. Updated docker-compose.yml
```yaml
environment:
  # In Docker container network: use service name 'aditi-backend' 
  # NOT localhost, which would refer to the frontend container itself
  - VITE_API_URL=http://aditi-backend:8000/api/v1
  - VITE_API_TARGET=http://aditi-backend:8000
```

### 2. Updated vite.config.ts
```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: process.env.VITE_API_TARGET || 'http://localhost:8000',
      changeOrigin: true,
    },
  },
},
```

### 3. Updated .env.example
```bash
# Local dev (npm run dev):  http://localhost:8000/api/v1
# Docker dev:               http://aditi-backend:8000/api/v1
VITE_API_URL=http://localhost:8000/api/v1

# Backend target for Vite proxy (dev server only)
# Local dev:  http://localhost:8000
# Docker dev: http://aditi-backend:8000
VITE_API_TARGET=http://localhost:8000
```

### 4. Updated auth-store.ts and api.ts
Added documentation comments explaining the URL configuration.

## How It Works

### In Docker (Docker Compose)
1. Frontend container receives environment variables:
   - `VITE_API_URL=http://aditi-backend:8000/api/v1`
   - `VITE_API_TARGET=http://aditi-backend:8000`

2. Frontend (React) app makes API calls to `http://aditi-backend:8000/api/v1/auth/login`
   - Uses Docker internal network to reach backend service

3. Vite proxy (dev server) redirects `/api/*` to `http://aditi-backend:8000`
   - Enables hot-reload and development workflow

### In Local Dev (npm run dev)
1. Frontend receives environment variables from .env:
   - `VITE_API_URL=http://localhost:8000/api/v1`
   - `VITE_API_TARGET=http://localhost:8000`

2. Frontend makes API calls to `http://localhost:8000/api/v1/auth/login`
   - Uses localhost since backend is running on host

3. Vite proxy redirects `/api/*` to `http://localhost:8000`

## Testing

### Test Frontend Login (from host)
```bash
# Access frontend
http://localhost:5173

# Login with:
# Email: alice.johnson@aditi.com
# Password: employee123
```

### Test Backend API (direct)
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.johnson@aditi.com","password":"employee123"}'
```

## Environment Variables Summary

| Variable | Docker Value | Dev Value | Purpose |
|----------|--------------|-----------|---------|
| `VITE_API_URL` | `http://aditi-backend:8000/api/v1` | `http://localhost:8000/api/v1` | API base URL (with /api/v1 prefix) for fetch calls |
| `VITE_API_TARGET` | `http://aditi-backend:8000` | `http://localhost:8000` | Vite proxy target (dev server only, no prefix) |

## Files Modified
- `docker-compose.yml` — Frontend environment variables
- `frontend/vite.config.ts` — Use environment variable for proxy target
- `frontend/.env.example` — Document both Docker and dev configurations
- `frontend/src/stores/auth-store.ts` — Add documentation comments
- `frontend/src/lib/api.ts` — Add documentation comments (already correct)

## Next Steps
1. Frontend now correctly routes to backend in Docker
2. Tests confirm connectivity from Docker network
3. Login endpoint accessible at http://localhost:5173 (frontend)
4. All API calls properly proxied to backend
