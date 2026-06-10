# Frontend URL Configuration Fix — CORRECTED

## The Critical Issue

Browser was trying to connect to `http://aditi-backend:8000/api/v1`

**Problem**: `aditi-backend` hostname **does NOT exist on the host machine**. It only exists inside Docker network!

```
❌ WRONG: Browser → http://aditi-backend:8000/api/v1
   Browser is on HOST MACHINE, can't resolve Docker service names

✅ CORRECT: Browser → http://localhost:8000/api/v1
   localhost on host machine → proxies to backend container port 8000
```

## Root Causes

1. **docker-compose.yml**: Had `VITE_API_URL=http://aditi-backend:8000/api/v1`
   - This gets used by React app IN BROWSER
   - Browser runs on HOST, not in Docker network
   - `aditi-backend` is only resolvable INSIDE Docker network

2. **Misunderstanding network topology**:
   - ✓ Vite proxy (INSIDE container) CAN use service name `aditi-backend`
   - ✗ Browser (ON HOST) CANNOT use service name `aditi-backend`

## Solutions Implemented (CORRECTED)

### 1. FIXED: docker-compose.yml
```yaml
environment:
  # Browser runs on HOST MACHINE, not in Docker network!
  - VITE_API_URL=http://localhost:8000/api/v1
  - VITE_API_TARGET=http://aditi-backend:8000
```

### 2. How It Works

**When accessing http://localhost:5173 from browser:**
```
Browser (Host) → http://localhost:5173
  ↓ (Click Login)
React App fetch()
  ↓
POST http://localhost:8000/api/v1/auth/login
  ↓
Host port 8000 → Docker backend:8000
  ↓
Backend responds ✓
```

## Configuration Reference

| Variable | Value | Used By | Why |
|----------|-------|---------|-----|
| `VITE_API_URL` | `http://localhost:8000/api/v1` | React (browser) | Must be host-resolvable |
| `VITE_API_TARGET` | `http://aditi-backend:8000` | Vite proxy (container) | Can use Docker service name |

## Testing

1. Open: `http://localhost:5173`
2. Login: `alice.johnson@aditi.com` / `employee123`
3. Should work ✓

## Key Takeaway

**Browser cannot use Docker service names!**

Use `localhost` for VITE_API_URL (browser access)
Use `aditi-backend` for VITE_API_TARGET (container proxy only)
