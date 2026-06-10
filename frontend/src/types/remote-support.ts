/** Types for remote support sessions, consent, and audit. */

export type RemoteSessionStatus =
  | 'requested'
  | 'consent_pending'
  | 'consent_granted'
  | 'consent_denied'
  | 'connecting'
  | 'active'
  | 'paused'
  | 'completed'
  | 'terminated'
  | 'expired';

export type RemoteSessionType = 'screen_view' | 'screen_control';

export interface RemoteSessionSummary {
  id: string;
  employee_id: string;
  agent_id: string;
  ticket_id: string | null;
  session_type: RemoteSessionType;
  status: RemoteSessionStatus;
  provider: string;
  requested_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  termination_reason: string | null;
}

export interface ConsentRecord {
  id: string;
  session_id: string;
  consent_type: string;
  granted: boolean;
  consented_at: string;
  revoked_at: string | null;
  denial_reason: string | null;
}

export interface SessionEvent {
  id: string;
  event_type: string;
  actor_id: string | null;
  occurred_at: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
}

export interface RemoteSessionDetail extends RemoteSessionSummary {
  join_url_agent: string | null;
  join_url_employee: string | null;
  join_code: string | null;
  consent_sent_at: string | null;
  consent_deadline: string | null;
  max_duration_minutes: number;
  justification: string | null;
  policy_check_passed: boolean;
  resolution_notes: string | null;
  actions_taken: string[] | null;
  consents: ConsentRecord[];
  events: SessionEvent[];
}

export interface ConsentNotification {
  session_id: string;
  agent_name: string;
  agent_email: string;
  session_type: RemoteSessionType;
  session_type_label: string;
  justification: string | null;
  consent_deadline: string;
  consent_text: string;
  ticket_reference: string | null;
}

export interface SessionLaunchInfo {
  session_id: string;
  provider: string;
  provider_display_name: string;
  join_url: string;
  join_code: string | null;
  instructions: string;
  expires_at: string | null;
}

export interface RequestSessionForm {
  employee_id: string;
  session_type: RemoteSessionType;
  ticket_id?: string;
  justification?: string;
  max_duration_minutes: number;
}

export interface SessionEndForm {
  resolution_notes?: string;
  actions_taken?: string[];
}
