/**
 * Typed client for the specialist queue + live-chat APIs.
 *
 * Wraps the seven endpoints under `/specialist-queue` and `/specialist-chat`.
 * All calls go through `apiRequest` so the global 401-interceptor +
 * session-expired contract from `lib/api.ts` is honored uniformly.
 *
 * Response types mirror the backend Pydantic schemas at
 * `app/schemas/specialist_queue.py` and `app/schemas/specialist_chat.py` —
 * keep these in sync if either side changes.
 */

import { apiRequest } from '@/lib/api';

// ── Shared ────────────────────────────────────────────────────────────

export type SpecialistChatStatus =
  | 'active'
  | 'idle_warning'
  | 'ended_by_user'
  | 'ended_by_specialist'
  | 'ended_by_timeout'
  | 'ended_by_system';

export type SpecialistChatEndReason =
  | 'resolved'
  | 'user_left'
  | 'specialist_ended'
  | 'idle_timeout'
  | 'session_error';

export type SpecialistMessageRole = 'user' | 'specialist' | 'system';

export type TicketPriority = 'low' | 'medium' | 'high' | 'critical';

// ── Queue ────────────────────────────────────────────────────────────

export interface HandoffSummary {
  issue_one_liner: string;
  affected_system?: string | null;
  issue_category?: string | null;
  issue_subtype?: string | null;
  urgency?: 'low' | 'medium' | 'high' | 'critical' | null;
  user_name?: string | null;
  user_email?: string | null;
  ai_confidence_at_handoff: number;
}

export interface QueueEntry {
  ticket_id: string;
  ticket_number: string;
  title: string;
  priority: TicketPriority;
  status: string;
  category?: string | null;
  issue_subtype?: string | null;
  requester_name?: string | null;
  queued_at: string;
  claimed_by_name?: string | null;
  claimed_at?: string | null;
  summary: HandoffSummary;
}

export interface QueueListResponse {
  total: number;
  entries: QueueEntry[];
}

export interface MyAssignedItem {
  ticket_id: string;
  ticket_number: string;
  title: string;
  priority: TicketPriority;
  issue_subtype?: string | null;
  user_name?: string | null;
  live_session_id?: string | null;
  live_status?: SpecialistChatStatus | null;
  last_activity_at?: string | null;
}

export interface MyAssignedResponse {
  total: number;
  items: MyAssignedItem[];
}

export interface ConversationTurn {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface StepAttempted {
  instruction: string;
  outcome: 'worked' | 'failed' | 'skipped' | 'unknown';
  source_kb_title?: string | null;
}

export interface HandoffPackage {
  schema_version: '1.0';
  session_id: string;
  ticket_id?: string | null;
  summary: HandoffSummary;
  diagnostic_slots: Record<string, string>;
  steps_attempted: StepAttempted[];
  kb_sources_consulted: { article_id: string; title: string; relevance?: number | null }[];
  web_sources_consulted: { url: string; title: string; trust_tier: string; snippet?: string | null }[];
  conversation: ConversationTurn[];
  handoff_reason: string;
  handoff_triggered_by: string;
  supervisor_decision_trace: unknown[];
}

export interface ClaimResponse {
  ticket_id: string;
  ticket_number: string;
  claimed_by_user_id: string;
  claimed_at: string;
  handoff_package: HandoffPackage;
}

// ── Live chat ────────────────────────────────────────────────────────

export interface SpecialistChatMessageOut {
  id: string;
  role: SpecialistMessageRole;
  content: string;
  system_event?: string | null;
  sender_id?: string | null;
  created_at: string;
}

export interface SpecialistChatSessionOut {
  id: string;
  ticket_id: string;
  ticket_number?: string | null;
  user_id: string;
  user_name?: string | null;
  user_email?: string | null;
  specialist_id: string;
  specialist_name?: string | null;
  specialist_email?: string | null;
  status: SpecialistChatStatus;
  started_at: string;
  last_activity_at: string;
  ended_at?: string | null;
  end_reason?: SpecialistChatEndReason | null;
  idle_warning_seconds: number;
  idle_end_seconds: number;
  messages: SpecialistChatMessageOut[];
}

// ── Calls ────────────────────────────────────────────────────────────

export const queueApi = {
  list: (opts?: { onlyUnclaimed?: boolean; includeMine?: boolean; limit?: number }) =>
    apiRequest<QueueListResponse>('/specialist-queue', {
      query: {
        only_unclaimed: opts?.onlyUnclaimed,
        include_mine: opts?.includeMine,
        limit: opts?.limit,
      },
    }),

  myAssigned: () => apiRequest<MyAssignedResponse>('/specialist-queue/mine'),

  getHandoffPackage: (ticketId: string) =>
    apiRequest<HandoffPackage>(`/specialist-queue/${ticketId}`),

  claim: (ticketId: string) =>
    apiRequest<ClaimResponse>('/specialist-queue/claim', {
      method: 'POST',
      body: { ticket_id: ticketId },
    }),

  release: (ticketId: string) =>
    apiRequest<{ ticket_id: string; status: string }>('/specialist-queue/release', {
      method: 'POST',
      body: { ticket_id: ticketId },
    }),

  resolve: (
    ticketId: string,
    body: {
      resolution_notes: string;
      propose_knowledge_candidate?: boolean;
    },
  ) =>
    apiRequest<{
      ticket_id: string;
      status: 'resolved';
      knowledge_candidate_id?: string | null;
    }>('/specialist-queue/resolve', {
      method: 'POST',
      body: { ticket_id: ticketId, ...body },
    }),
};

export interface ActiveSessionResponse {
  session_id: string | null;
  status?: SpecialistChatStatus;
  ticket_number?: string | null;
}

export const liveChatApi = {
  /** The caller's current live session, if any (powers the employee join banner). */
  active: () => apiRequest<ActiveSessionResponse>('/specialist-chat/active'),

  start: (ticketId: string, opts?: { idleWarningSeconds?: number; idleEndSeconds?: number }) =>
    apiRequest<SpecialistChatSessionOut>('/specialist-chat/start', {
      method: 'POST',
      body: {
        ticket_id: ticketId,
        idle_warning_seconds: opts?.idleWarningSeconds ?? 120,
        idle_end_seconds: opts?.idleEndSeconds ?? 180,
      },
    }),

  get: (sessionId: string) =>
    apiRequest<SpecialistChatSessionOut>(`/specialist-chat/${sessionId}`),

  send: (sessionId: string, content: string) =>
    apiRequest<SpecialistChatMessageOut>(`/specialist-chat/${sessionId}/message`, {
      method: 'POST',
      body: { content },
    }),

  end: (
    sessionId: string,
    body: {
      reason: SpecialistChatEndReason;
      resolution_notes?: string;
      propose_knowledge_candidate?: boolean;
    },
  ) =>
    apiRequest<{
      session_id: string;
      status: SpecialistChatStatus;
      end_reason: SpecialistChatEndReason;
      knowledge_candidate_id?: string | null;
    }>(`/specialist-chat/${sessionId}/end`, {
      method: 'POST',
      body,
    }),
};
