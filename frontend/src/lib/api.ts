/**
 * Thin typed fetch wrapper for the Aditi IT Assist API.
 *
 * Adds the bearer token from the auth store, JSON-encodes bodies, and surfaces
 * a typed `ApiError` with the backend's `detail` message. React Query hooks
 * build on top of this (see the per-feature api.ts modules).
 *
 * Session-expiry contract
 * -----------------------
 * 401 responses from the backend carry a typed body of the form
 * `{ detail: { error_code, message } }`. This wrapper is the SINGLE
 * interceptor for that contract — no component should ever see a raw 401.
 *
 *   - error_code = "session_expired" → attempt /auth/refresh ONCE. On
 *     success, retry the original request once. On failure, emit a
 *     `session-expired` window event and throw.
 *   - error_code = "auth_required" → emit the event immediately. No retry.
 *
 * The event listener lives in auth-store (it owns the state + redirect).
 * Keeping the event boundary here means api.ts never imports react-router.
 */

import { useAuthStore } from '@/stores/auth-store';
import type {
  RemoteSessionDetail,
  RemoteSessionSummary,
  RequestSessionForm,
  SessionEndForm,
  SessionLaunchInfo,
} from '@/types/remote-support';

export const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

/** Custom event the auth store listens to. */
export const SESSION_EXPIRED_EVENT = 'aditi:session-expired';

export type SessionExpiredReason =
  | 'session_expired'
  | 'auth_required'
  | 'refresh_failed';

export interface SessionExpiredDetail {
  reason: SessionExpiredReason;
  /** Path the user was trying to load — surfaced as `next=` on /login. */
  next?: string;
}

function emitSessionExpired(detail: SessionExpiredDetail): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<SessionExpiredDetail>(SESSION_EXPIRED_EVENT, { detail }),
  );
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Typed error code parsed from the backend body, when present. */
    public errorCode?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

/**
 * Turn a backend error body into a human-readable message.
 *
 * FastAPI validation errors (422) return `detail` as an array of
 * `{ loc, msg, type }` objects, not a string — collapse those to a readable,
 * field-aware sentence instead of a generic "Request failed".
 */
export function extractErrorMessage(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown; message?: unknown } | null)?.detail;
  const message = (data as { message?: unknown } | null)?.message;

  if (typeof detail === 'string') return detail;
  if (typeof message === 'string') return message;

  // Structured 401 body: `{ detail: { error_code, message } }`.
  if (detail && typeof detail === 'object' && 'message' in (detail as object)) {
    const m = (detail as { message?: unknown }).message;
    if (typeof m === 'string') return m;
  }

  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === 'string') return d;
        const msg = (d as { msg?: string })?.msg;
        const loc = (d as { loc?: unknown[] })?.loc;
        const field = Array.isArray(loc) && loc.length ? loc[loc.length - 1] : undefined;
        if (!msg) return undefined;
        return field ? `${msg} (${field})` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }

  return `Request failed (${status})`;
}

/** Pulls the typed error_code from a structured 401 body, if present. */
function extractErrorCode(data: unknown): string | undefined {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object' && 'error_code' in (detail as object)) {
    const code = (detail as { error_code?: unknown }).error_code;
    if (typeof code === 'string') return code;
  }
  return undefined;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Query;
}

function buildUrl(path: string, query?: Query): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/**
 * Module-level mutex so concurrent 401s share ONE refresh call rather than
 * racing /auth/refresh in parallel (which can revoke each other's new tokens
 * if the backend rotates refresh tokens).
 */
let refreshInFlight: Promise<string | null> | null = null;

/** Calls /auth/refresh with the stored refresh token. Returns the new
 *  access token on success, null on failure. Never throws.
 */
async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refreshToken = useAuthStore.getState().refreshToken;
    if (!refreshToken) return null;
    try {
      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!resp.ok) return null;
      const data = (await resp.json()) as {
        access_token: string;
        refresh_token?: string;
      };
      useAuthStore.getState().setTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token ?? refreshToken,
      });
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Build headers for one attempt. Re-built on retry so the new token is sent. */
function buildHeaders(body: unknown): Record<string, string> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isFormData) headers['Content-Type'] = 'application/json';
  return headers;
}

/** Routes the wrapper should NEVER try to refresh against (avoid loops). */
function isAuthRoute(path: string): boolean {
  return (
    path.startsWith('/auth/login') ||
    path.startsWith('/auth/refresh') ||
    path.startsWith('/auth/register')
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, query } = options;
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;

  async function performFetch(): Promise<Response> {
    return fetch(buildUrl(path, query), {
      method,
      headers: buildHeaders(body),
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  let response = await performFetch();

  // ── 401 interceptor ────────────────────────────────────────────────
  // /auth/login and /auth/refresh themselves get their 401 passed through —
  // a failed login or refresh must not loop into "try to refresh".
  if (response.status === 401 && !isAuthRoute(path)) {
    const peekText = await response.clone().text();
    const peekData = peekText ? safeJson(peekText) : null;
    const code = extractErrorCode(peekData);

    if (code === 'session_expired') {
      const newToken = await refreshAccessToken();
      if (newToken) {
        // Single retry with the new token.
        response = await performFetch();
        if (response.status !== 401) {
          // continue to the success / non-401 path below
        } else {
          // Still 401 after refresh — the refresh succeeded but the call
          // still failed (server-side revocation, permissions change).
          // Treat as terminal.
          emitSessionExpired({ reason: 'refresh_failed', next: currentPath() });
          throw new ApiError(401, 'Session expired', code);
        }
      } else {
        emitSessionExpired({ reason: 'session_expired', next: currentPath() });
        throw new ApiError(401, extractErrorMessage(peekData, 401), code);
      }
    } else {
      // auth_required (or unknown 401) — no point refreshing without context.
      emitSessionExpired({
        reason: (code as SessionExpiredReason | undefined) ?? 'auth_required',
        next: currentPath(),
      });
      throw new ApiError(401, extractErrorMessage(peekData, 401), code);
    }
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractErrorMessage(data, response.status),
      extractErrorCode(data),
    );
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function currentPath(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const p = window.location.pathname + window.location.search;
  return p === '/login' ? undefined : p;
}

// ── Feature clients ─────────────────────────────────────────────────
//
// Thin namespaced clients built on `apiRequest`, consumed by the chat store
// and the remote-assist page. Knowledge management uses React Query hooks in
// `features/knowledge/api.ts` instead.

export interface ChatDebugInfo {
  normalized_system?: string | null;
  issue_subtype?: string | null;
  subtype_confidence?: number;
  conversation_phase?: string | null;
  loop_counter?: number;
  suggested_steps?: string[];
  failed_steps?: string[];
  confidence_breakdown?: Record<string, number> | null;
  retrieval_trace?: Record<string, unknown> | null;
  escalation_reason?: string | null;
  routed_specialist?: string | null;
  retrieval_source?: string | null;
  citations?: { title?: string; category?: string; citation_label?: string }[];
}

export interface ChatMessageResponse {
  session_id: string;
  message_id: string;
  content: string;
  role: string;
  confidence_score: number;
  issue_category: string | null;
  issue_subtype: string | null;
  resolution_steps: { step_number: number; instruction: string; details?: string }[];
  requires_escalation: boolean;
  follow_up_question: string | null;
  quick_replies: { label: string; value: string }[] | null;
  conversation_phase: string | null;
  resolved: boolean;
  debug: ChatDebugInfo | null;
}

export interface LiveAgentResponse {
  session_id: string;
  message: string;
  ticket: {
    ticket_id: string;
    ticket_number: string;
    status: string;
    priority: string;
    live_agent_requested: boolean;
  } | null;
}

export const chatApi = {
  sendMessage: (message: string, sessionId?: string) =>
    apiRequest<ChatMessageResponse>('/chat/message', {
      method: 'POST',
      body: { message, session_id: sessionId },
    }),

  requestLiveAgent: (sessionId: string) =>
    apiRequest<LiveAgentResponse>('/chat/request-live-agent', {
      method: 'POST',
      body: { session_id: sessionId },
    }),

  cancelWaiting: (sessionId: string) =>
    apiRequest<{ session_id: string; message: string; cancelled: boolean }>(
      '/chat/cancel-waiting',
      { method: 'POST', body: { session_id: sessionId } },
    ),

  getWaitingStatus: (sessionId: string) =>
    apiRequest<{
      session_id: string;
      waiting: boolean;
      ticket_number: string | null;
      waited_seconds: number;
      specialist_available: boolean;
      fallback_message: string | null;
    }>(`/chat/waiting-status/${sessionId}`),
};

const REMOTE = '/remote-support';

export const remoteApi = {
  requestSession: (form: RequestSessionForm) =>
    apiRequest<{ session_id: string } & Partial<RemoteSessionDetail>>(`${REMOTE}/sessions`, {
      method: 'POST',
      body: form,
    }),
  launchSession: (sessionId: string) =>
    apiRequest<SessionLaunchInfo>(`${REMOTE}/sessions/${sessionId}/launch`, { method: 'POST' }),
  markConnected: (sessionId: string) =>
    apiRequest<void>(`${REMOTE}/sessions/${sessionId}/connected`, { method: 'POST' }),
  endSession: (sessionId: string, body: SessionEndForm) =>
    apiRequest<void>(`${REMOTE}/sessions/${sessionId}/end`, { method: 'POST', body }),
  updateResolution: (sessionId: string, body: SessionEndForm) =>
    apiRequest<void>(`${REMOTE}/sessions/${sessionId}/resolution`, { method: 'PUT', body }),
  getSession: (sessionId: string) =>
    apiRequest<RemoteSessionDetail>(`${REMOTE}/sessions/${sessionId}`),
  listSessions: (params?: { limit?: number }) =>
    apiRequest<RemoteSessionSummary[]>(`${REMOTE}/sessions`, { query: { limit: params?.limit } }),
};
