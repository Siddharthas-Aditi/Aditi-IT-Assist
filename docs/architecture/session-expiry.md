# Session expiry & token refresh

> One contract between backend, API client, auth store, and router so an
> expired JWT always lands the user on `/login` — *the same way, everywhere
> in the application*. No per-page handling; no silent dead clicks.

---

## Why this exists

The pre-fix application had three different behaviors when the JWT
expired:

1. The browser tab kept a stale token in `localStorage`. The user's next
   click hit a 401, and that page silently failed with a generic toast.
2. Some pages caught the 401 and redirected to `/login`; others didn't.
3. A user whose tab had been idle past `exp` had no idea until they
   clicked something — by then the 401 had already happened.

The fix unifies all three paths into a single, testable contract.

---

## The contract

### Backend — typed 401 body

`app/services/auth/dependencies.py:get_current_user` returns 401 with a
structured `detail`:

```json
{
  "detail": {
    "error_code": "session_expired" | "auth_required",
    "message": "Your session has expired. Please sign in again."
  }
}
```

The two codes have distinct semantics:

| `error_code` | Meaning | Frontend behavior |
|---|---|---|
| `auth_required` | No bearer token at all (user never logged in or token cleared) | Redirect to `/login` immediately. No refresh attempt. |
| `session_expired` | Token was present but failed validation (sig, exp, type, user disabled) | Try `/auth/refresh` ONCE. On success retry the request; on failure redirect to `/login`. |

### Backend — `POST /auth/refresh`

`app/api/v1/auth.py:refresh_session` accepts the long-lived refresh token in
the body (never the Authorization header — preventing accidental
access-token reuse). Returns a new access token. Refuses unless the JWT
`type` claim is `"refresh"` and the user is active.

Failure response mirrors the 401 contract above with
`error_code: "session_expired"`.

### Frontend — single interceptor in `lib/api.ts`

`apiRequest()` is the only fetch wrapper any feature imports. It owns:

1. The 401 detect (with the typed code).
2. The refresh-once mutex (`refreshInFlight`) so a burst of concurrent
   requests share ONE refresh call and don't race each other.
3. The retry-once policy on `session_expired`.
4. The terminal `session-expired` window event when refresh fails or the
   code is `auth_required`.

Importantly, `/auth/login`, `/auth/refresh`, `/auth/register` are excluded
from the interceptor (`isAuthRoute()`) — a failed login or refresh must
never recurse into "let me try to refresh".

### Frontend — `auth-store` owns state + redirect

The store:

- Persists `token`, `refreshToken`, `tokenExpiresAt`, `user` to localStorage.
- Decodes the JWT `exp` on every login + refresh and stores it as
  `tokenExpiresAt`.
- Schedules a single `setTimeout(scheduleIdleLogout, …)` that fires the
  same `session-expired` event one second before the token actually
  expires — so an idle tab logs out cleanly instead of bouncing on the
  next click.
- Registers exactly ONE `window.addEventListener` for `session-expired`.
  That handler calls `logout({ redirect: true, reason, next })`, which
  flips state and calls `window.location.replace('/login?reason=…&next=…')`.

### Frontend — `LoginPage` honors `reason` and `next`

The login page reads `?reason=…&next=…` from the URL. The reason renders an
amber banner ("Your session expired. Please sign in again."); the next
param drives the post-login redirect (with an open-redirect guard:
`next` must start with `/` and not `//`).

---

## End-to-end flows

### 1. Token expires while user is active

```
user clicks Save
  └─▶ apiRequest('/tickets/…/save')
        └─▶ 401 { error_code: 'session_expired' }
              └─▶ refreshAccessToken()  → new access token
                    └─▶ retry the original POST
                          └─▶ 200 OK
                                └─▶ feature continues; user never notices
```

### 2. Refresh also fails

```
user clicks Save
  └─▶ 401 session_expired
        └─▶ /auth/refresh → 401 session_expired
              └─▶ emit('session-expired', { reason: 'refresh_failed', next: '/tickets/123' })
                    └─▶ auth-store.logout({ redirect: true })
                          └─▶ window.location.replace('/login?reason=refresh_failed&next=/tickets/123')
```

### 3. Idle tab past `exp`

```
tab sits idle, exp lapses
  └─▶ scheduleIdleLogout's setTimeout fires
        └─▶ logout({ redirect: true, reason: 'expired' })
              └─▶ /login?reason=expired
```

### 4. Cold load of a deep link without a token

```
GET /tickets/123
  └─▶ RouteGuard: !isAuthenticated
        └─▶ <Navigate to="/login" state={{ from: location }} replace />
```

(Route-guard path is unchanged; the new interceptor is for in-session
expiry.)

---

## Invariants

1. **Single redirect entry point.** `window.location.replace('/login?…')`
   is called only inside `auth-store.logout({redirect:true})`. Nothing
   else in the codebase navigates to `/login` programmatically on expiry.
2. **No silent 401.** Every 401 either retries successfully or fires
   `session-expired`. There is no path where a component sees a raw 401.
3. **Refresh-once.** The mutex guarantees one `/auth/refresh` per burst.
4. **No refresh loop on auth routes.** `/auth/login`, `/auth/refresh`,
   `/auth/register` bypass the interceptor.
5. **Open-redirect guard.** `next` must be a same-origin relative path
   starting with `/` and not `//`.
6. **Proactive expiry.** Idle tabs log out at `exp − 1s`, not on the
   first click after expiry.
7. **No `react-router` in `api.ts`.** The wrapper emits an event; the
   store owns the redirect. This keeps `api.ts` testable in isolation.

---

## Configuration

| Setting | Default | Where |
|---|---|---|
| Access token expiry | 30 min | `ACCESS_TOKEN_EXPIRE_MINUTES` in `app.core.config` |
| Refresh token expiry | 7 days | hard-coded in `local.py` (move to config in Phase 2) |
| Idle-tab timer offset | 1 s before `exp` | `scheduleIdleLogout` in `auth-store.ts` |
| Refresh-call timeout | uses fetch defaults | `lib/api.ts` |

---

## Manual verification checklist

After deploy:

- [ ] Login. In DevTools, set the access token to a manually-expired one;
      click anywhere. The page should refresh seamlessly (200 from
      the retried request) and stay on the same view.
- [ ] Repeat, but also expire the refresh token. The page should
      redirect to `/login?reason=refresh_failed&next=<current path>`
      with the amber banner.
- [ ] Login, then leave the tab idle past `exp`. Confirm redirect fires
      automatically without any user action.
- [ ] Deep-link to `/admin` while logged out. Confirm `RouteGuard`
      bounces to `/login` (no `reason` banner — this is the cold path).
- [ ] Submit a wrong password. Confirm the login error shows and no
      redirect happens (the auth-route exclusion holds).
- [ ] Sign in via the `next` redirect link; confirm you land on the
      intended page, not the role default.

---

## Future improvements

- **Refresh token rotation.** The backend already issues a refresh token
  on login; a Phase-2 enhancement rotates it on every `/auth/refresh`
  call and persists a server-side allow-list for revocation. The
  frontend already calls `setTokens(...)` with the rotated value
  whenever the response includes one.
- **Redis-backed access-token denylist.** Drives "force-logout this
  user" from the admin UI by adding the JTI to a denylist that
  `validate_token` checks.
- **SSO single logout (SLO)** integration with the existing SAML stub —
  on `session-expired` from an SSO-originated session, send the SLO
  request to the IdP.
- **Tighten exp for cross-tab sync.** Use a `BroadcastChannel` so
  logout in one tab immediately logs out other tabs, instead of each
  tab running its own idle timer.
