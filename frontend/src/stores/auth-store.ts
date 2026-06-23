/**
 * Authentication store — manages login state and tokens.
 *
 * Session-expiry behavior is centralized here. The store:
 *
 * 1. Persists both the access token and the refresh token so the API
 *    wrapper can attempt one /auth/refresh on a 401-session-expired before
 *    giving up.
 * 2. Listens for the `aditi:session-expired` window event that
 *    `lib/api.ts` emits when refresh fails or auth is missing — and
 *    redirects to `/login?reason=expired&next=<original-path>`.
 * 3. On login + refresh, decodes the JWT `exp` claim and schedules a
 *    single setTimeout to proactively expire the session client-side when
 *    the token lapses. This avoids "ghost session" UX where the user clicks
 *    something only to realize their token died ten minutes ago.
 *
 * The redirect uses `window.location.replace` — not React Router — so the
 * store can fire it without depending on the router instance.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuthUser, LoginRequest, LoginResponse, UserRole } from '@/types/auth';
import {
  SESSION_EXPIRED_EVENT,
  type SessionExpiredDetail,
} from '@/lib/api';
import { clearAllChatSessions } from '@/lib/chat-session-sync';

// API_BASE is the base URL for API calls, should include /api/v1 prefix
// In dev (npm run dev):    http://localhost:8000/api/v1
// In Docker (dev server):  http://aditi-backend:8000/api/v1
// Fallback to relative path for SPA deployments
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface AuthStore {
  user: AuthUser | null;
  token: string | null;
  refreshToken: string | null;
  /** Absolute epoch ms when the access token expires (decoded from JWT exp).
   *  null when the token can't be decoded — the timer is simply skipped. */
  tokenExpiresAt: number | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (credentials: LoginRequest) => Promise<void>;
  logout: (opts?: { redirect?: boolean; reason?: string; next?: string }) => void;
  setUser: (user: AuthUser) => void;
  setTokens: (tokens: { accessToken: string; refreshToken: string | null }) => void;
  checkAuth: () => Promise<void>;

  // Role helpers
  hasRole: (role: UserRole) => boolean;
  hasAnyRole: (...roles: UserRole[]) => boolean;
  isITStaff: () => boolean;
  isAdmin: () => boolean;
}

// ── Idle-tab proactive logout ──────────────────────────────────────────
// A single setTimeout that fires when the access token's `exp` lapses.
// Cleared and rescheduled on every token change.

let idleLogoutTimer: ReturnType<typeof setTimeout> | null = null;

function clearIdleTimer(): void {
  if (idleLogoutTimer) {
    clearTimeout(idleLogoutTimer);
    idleLogoutTimer = null;
  }
}

/** Decode the `exp` (epoch seconds) claim from a JWT without verifying it.
 *  Returns null on any decode failure — the timer just won't be set. */
function decodeJwtExp(token: string): number | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    // Browser base64url decode
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(json) as { exp?: number };
    return typeof claims.exp === 'number' ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

function scheduleIdleLogout(
  expiresAtMs: number | null,
  onExpire: () => void,
): void {
  clearIdleTimer();
  if (!expiresAtMs) return;
  // Fire 1 second before exp so the user doesn't see a 401 race.
  const ms = expiresAtMs - Date.now() - 1000;
  if (ms <= 0) {
    // Token is already expired.
    onExpire();
    return;
  }
  // setTimeout's max is ~24.8 days; clamp.
  const safe = Math.min(ms, 2_000_000_000);
  idleLogoutTimer = setTimeout(onExpire, safe);
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      tokenExpiresAt: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (credentials: LoginRequest) => {
        set({ isLoading: true });
        try {
          const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
          }

          const data: LoginResponse = await response.json();
          const tokenExpiresAt = decodeJwtExp(data.access_token);
          set({
            user: data.user,
            token: data.access_token,
            refreshToken: data.refresh_token ?? null,
            tokenExpiresAt,
            isAuthenticated: true,
            isLoading: false,
          });
          // Proactive expiry — fire session-expired event when the token
          // actually lapses, instead of waiting for the next API call.
          scheduleIdleLogout(tokenExpiresAt, () =>
            get().logout({ redirect: true, reason: 'expired' }),
          );
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: ({ redirect = false, reason, next } = {}) => {
        clearIdleTimer();
        clearAllChatSessions();
        set({
          user: null,
          token: null,
          refreshToken: null,
          tokenExpiresAt: null,
          isAuthenticated: false,
        });
        if (redirect && typeof window !== 'undefined') {
          const params = new URLSearchParams();
          if (reason) params.set('reason', reason);
          if (next) params.set('next', next);
          const qs = params.toString();
          window.location.replace(`/login${qs ? `?${qs}` : ''}`);
        }
      },

      setUser: (user: AuthUser) => {
        set({ user, isAuthenticated: true });
      },

      setTokens: ({ accessToken, refreshToken }) => {
        const tokenExpiresAt = decodeJwtExp(accessToken);
        set({
          token: accessToken,
          refreshToken: refreshToken ?? get().refreshToken,
          tokenExpiresAt,
          isAuthenticated: true,
        });
        scheduleIdleLogout(tokenExpiresAt, () =>
          get().logout({ redirect: true, reason: 'expired' }),
        );
      },

      checkAuth: async () => {
        const { token } = get();
        if (!token) return;

        try {
          const response = await fetch(`${API_BASE}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (response.ok) {
            const user = await response.json();
            set({ user, isAuthenticated: true });
          } else {
            get().logout();
          }
        } catch {
          get().logout();
        }
      },

      hasRole: (role: UserRole) => {
        const { user } = get();
        return user?.roles?.includes(role) ?? false;
      },

      hasAnyRole: (...roles: UserRole[]) => {
        const { user } = get();
        return roles.some((r) => user?.roles?.includes(r));
      },

      isITStaff: () => {
        return get().hasAnyRole('it_agent', 'it_lead', 'it_admin');
      },

      isAdmin: () => {
        return get().hasAnyRole('it_lead', 'it_admin');
      },
    }),
    {
      name: 'aditi-auth',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        tokenExpiresAt: state.tokenExpiresAt,
        user: state.user,
      }),
      // `isAuthenticated` is intentionally not persisted, so recompute it from
      // the restored token after rehydration. Without this, a full page reload
      // (refresh or deep link) resets it to `false` and RouteGuard bounces an
      // already-authenticated user back to /login.
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isAuthenticated = Boolean(state.token);
          // Re-schedule the idle-tab timer using the persisted exp claim, so
          // a refreshed tab with a near-expired token still fires the
          // proactive logout instead of relying on the next API call to
          // 401-bounce.
          scheduleIdleLogout(state.tokenExpiresAt, () => {
            useAuthStore.getState().logout({ redirect: true, reason: 'expired' });
          });
        }
      },
    }
  )
);

// ── Session-expired event listener ─────────────────────────────────────
// The single global subscriber. `lib/api.ts` emits this event when a 401
// can't be recovered via refresh; we centralize the redirect here so every
// page behaves identically. Registered exactly once at module load.
if (typeof window !== 'undefined') {
  window.addEventListener(SESSION_EXPIRED_EVENT, (ev: Event) => {
    const detail = (ev as CustomEvent<SessionExpiredDetail>).detail;
    useAuthStore.getState().logout({
      redirect: true,
      reason: detail?.reason ?? 'expired',
      next: detail?.next,
    });
  });

  // ── Cross-tab session synchronization ──────────────────────────────
  // When the user logs out (or in) in one tab, the localStorage change fires
  // a `storage` event in every *other* tab in the same browser. We listen
  // for changes to the `aditi-auth` key and rehydrate the Zustand store so
  // all tabs stay in sync — logout in one tab logs out everywhere, and login
  // in one tab picks up the session in every other open tab.
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key !== 'aditi-auth') return;

    const store = useAuthStore.getState();

    if (event.newValue === null) {
      // Key was removed (logout cleared it) — force logout in this tab too.
      if (store.isAuthenticated) {
        clearIdleTimer();
        useAuthStore.setState({
          user: null,
          token: null,
          refreshToken: null,
          tokenExpiresAt: null,
          isAuthenticated: false,
        });
        window.location.replace('/login?reason=logged_out_other_tab');
      }
      return;
    }

    // Parse the new value and sync state
    try {
      const persisted = JSON.parse(event.newValue) as {
        state?: {
          token?: string | null;
          refreshToken?: string | null;
          tokenExpiresAt?: number | null;
          user?: AuthUser | null;
        };
      };
      const newState = persisted?.state;
      if (!newState) return;

      const wasAuthenticated = store.isAuthenticated;
      const newToken = newState.token ?? null;
      const isNowAuthenticated = Boolean(newToken);

      if (!wasAuthenticated && isNowAuthenticated && newState.user) {
        // Another tab logged in — pick up the session here too.
        useAuthStore.setState({
          user: newState.user,
          token: newToken,
          refreshToken: newState.refreshToken ?? null,
          tokenExpiresAt: newState.tokenExpiresAt ?? null,
          isAuthenticated: true,
        });
        scheduleIdleLogout(newState.tokenExpiresAt ?? null, () =>
          useAuthStore.getState().logout({ redirect: true, reason: 'expired' }),
        );
      } else if (wasAuthenticated && !isNowAuthenticated) {
        // Another tab logged out — clear this tab too.
        clearIdleTimer();
        useAuthStore.setState({
          user: null,
          token: null,
          refreshToken: null,
          tokenExpiresAt: null,
          isAuthenticated: false,
        });
        window.location.replace('/login?reason=logged_out_other_tab');
      } else if (wasAuthenticated && isNowAuthenticated && newState.user) {
        // Token refresh from another tab — pick up the new token silently.
        useAuthStore.setState({
          user: newState.user,
          token: newToken,
          refreshToken: newState.refreshToken ?? null,
          tokenExpiresAt: newState.tokenExpiresAt ?? null,
        });
        scheduleIdleLogout(newState.tokenExpiresAt ?? null, () =>
          useAuthStore.getState().logout({ redirect: true, reason: 'expired' }),
        );
      }
    } catch {
      // Malformed JSON — ignore.
    }
  });
}
