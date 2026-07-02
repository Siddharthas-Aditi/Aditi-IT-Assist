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

/**
 * Typed freshness of a live-chat request (single source of truth:
 * backend `waiting_info`, driven by LIVE_WAIT_TIMEOUT_SECONDS):
 * - "waiting"     — employee presumed still at their keyboard → claim opens live chat
 * - "likely_left" — past the wait window; employee was shown the async-ticket
 *                   fallback → claim routes to the ticket workspace, NOT a live chat
 * - "claimed"     — already owned by a specialist
 */
export type WaitingState = 'waiting' | 'likely_left' | 'claimed';

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
  waiting_state: WaitingState;
  waited_seconds: number;
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
  /** Freshness at claim time — "waiting" opens live chat, "likely_left" routes to the ticket. */
  waiting_state: 'waiting' | 'likely_left';
  waited_seconds: number;
  handoff_package: HandoffPackage;
}

// ── Escalation artifacts (summary-first handoff view) ──────────────────
// Mirrors backend `app/schemas/escalation.py`.

export type TranscriptRole = 'employee' | 'assistant' | 'system' | 'specialist';

export interface TranscriptMessage {
  seq: number;
  role: TranscriptRole;
  content: string;
  message_type?: string | null;
  timestamp?: string | null;
}

export interface TranscriptSnapshot {
  id: string;
  chat_session_id: string;
  captured_at: string;
  message_count: number;
  context_version: string;
  messages: TranscriptMessage[];
}

export interface KBArticleRef {
  article_id: string;
  title: string;
  relevance?: number | null;
}

export interface SpecialistHandoffView {
  ticket_id: string;
  ticket_number: string;
  // Overview
  issue_summary: string;
  category?: string | null;
  subcategory?: string | null;
  affected_system?: string | null;
  urgency?: string | null;
  ai_confidence?: number | null;
  ai_resolution_status: string;
  escalation_reason?: string | null;
  escalation_created_at?: string | null;
  // AI handoff detail
  user_problem_statement?: string | null;
  detected_intent?: string | null;
  steps_attempted: StepAttempted[];
  // KB signals
  kb_articles_referenced: KBArticleRef[];
  kb_gap_tags: string[];
  // Full transcript (collapsible / secondary)
  transcript?: TranscriptSnapshot | null;
  has_structured_context: boolean;
}

export interface ResolutionComparisonInput {
  specialist_resolution_summary: string;
  specialist_resolution_steps?: string[];
  final_resolution_category?: string | null;
  ai_vs_specialist_resolution_gap?: string | null;
  kb_candidate_flag?: boolean;
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
  /** Roles currently typing, excluding the caller (drives the typing banner). */
  typing?: SpecialistMessageRole[];
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

  /** Summary-first, transcript-second view the specialist reads on pickup. */
  getHandoffView: (ticketId: string) =>
    apiRequest<SpecialistHandoffView>(`/specialist-queue/${ticketId}/handoff-view`),

  /** Capture what the specialist actually did, for AI/KB improvement. */
  recordResolutionComparison: (ticketId: string, body: ResolutionComparisonInput) =>
    apiRequest<unknown>(`/specialist-queue/${ticketId}/resolution-comparison`, {
      method: 'POST',
      body,
    }),

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
      // Omit idle thresholds unless overridden — the backend default (7-minute
      // warning + 2-minute grace) is the source of truth.
      body: {
        ticket_id: ticketId,
        ...(opts?.idleWarningSeconds != null
          ? { idle_warning_seconds: opts.idleWarningSeconds }
          : {}),
        ...(opts?.idleEndSeconds != null ? { idle_end_seconds: opts.idleEndSeconds } : {}),
      },
    }),

  get: (sessionId: string) =>
    apiRequest<SpecialistChatSessionOut>(`/specialist-chat/${sessionId}`),

  /** Heartbeat the caller's typing state (ephemeral; does not reset idle). */
  typing: (sessionId: string, isTyping: boolean) =>
    apiRequest<{ role: SpecialistMessageRole; is_typing: boolean }>(
      `/specialist-chat/${sessionId}/typing`,
      { method: 'POST', body: { is_typing: isTyping } },
    ),

  send: (sessionId: string, content: string) =>
    apiRequest<SpecialistChatMessageOut>(`/specialist-chat/${sessionId}/message`, {
      method: 'POST',
      body: { content },
    }),

  /**
   * Specialist requests a remote support session from inside this chat.
   * Employee/ticket linkage is derived server-side from the chat session;
   * the employee gets the consent prompt in the same chat window.
   */
  requestRemote: (
    sessionId: string,
    body: {
      session_type: 'screen_view' | 'screen_control';
      justification?: string;
      max_duration_minutes?: number;
    },
  ) =>
    apiRequest<{
      remote_session_id: string;
      status: string;
      session_type: string;
      consent_deadline: string | null;
    }>(`/specialist-chat/${sessionId}/remote-session`, {
      method: 'POST',
      body,
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
