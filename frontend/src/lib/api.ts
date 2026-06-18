/**
 * Thin typed fetch wrapper for the Aditi IT Assist API.
 *
 * Adds the bearer token from the auth store, JSON-encodes bodies, and surfaces
 * a typed `ApiError` with the backend's `detail` message. React Query hooks
 * build on top of this (see the per-feature api.ts modules).
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

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
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

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query } = options;
  const token = useAuthStore.getState().token;

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  // FormData must NOT have Content-Type set — the browser adds the
  // multipart boundary automatically. Only set JSON for plain objects.
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isFormData) headers['Content-Type'] = 'application/json';

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, extractErrorMessage(data, response.status));
  }
  return data as T;
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
