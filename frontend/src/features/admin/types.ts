/** Admin Console API types — mirror of `backend/app/schemas/admin.py`. */

export type UserStatusFilter = 'active' | 'inactive';

export interface RoleSummary {
  name: string;
  display_name: string;
  description?: string | null;
  priority: number;
}

export interface RoleAssignmentInfo {
  role: string;
  display_name: string;
  assigned_at?: string | null;
  expires_at?: string | null;
}

export interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  department?: string | null;
  job_title?: string | null;
  is_active: boolean;
  is_verified: boolean;
  primary_role: string;
  roles: string[];
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface UserDetail extends UserSummary {
  employee_id?: string | null;
  phone?: string | null;
  role_assignments: RoleAssignmentInfo[];
}

export interface UserListResponse {
  users: UserSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserFilters {
  search?: string;
  role?: string;
  status?: UserStatusFilter | '';
  limit?: number;
  offset?: number;
}

export interface UserUpdatePayload {
  full_name?: string;
  department?: string;
  job_title?: string;
  phone?: string;
  is_active?: boolean;
}

export type AuditSeverity = 'info' | 'warning' | 'error' | 'critical';

export interface AuditEvent {
  id: string;
  actor_email?: string | null;
  actor_role?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  description?: string | null;
  severity: string;
  ip_address?: string | null;
  created_at: string;
}

export interface AuditEventDetail extends AuditEvent {
  user_agent?: string | null;
  old_value?: Record<string, unknown> | null;
  new_value?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface AuditListResponse {
  events: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFacets {
  actions: string[];
  resource_types: string[];
  severities: string[];
}

export interface AuditFilters {
  severity?: string;
  action?: string;
  resource_type?: string;
  actor_email?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface DashboardMetrics {
  ticket_metrics: {
    total: number;
    status_distribution: Record<string, number>;
    priority_distribution: Record<string, number>;
    category_distribution: Record<string, number>;
  };
  ai_metrics: {
    ai_resolved: number;
    total_sessions: number;
    resolution_rate: number; // already a percentage (0-100)
    escalation_rate: number; // already a percentage (0-100)
    avg_confidence: number | null; // 0-1 or null when no data
  };
  sla_metrics: {
    at_risk: number;
    breached: number;
    resolved_with_target: number;
    resolved_on_time: number;
    compliance_rate: number | null; // already a percentage (0-100) or null
  };
  remote_support_metrics?: {
    total_sessions: number;
    completed_sessions: number;
  };
  period: { start: string; end: string };
}

export interface AgentWorkload {
  agent_id: string;
  active_tickets: number;
}

export interface SystemStats {
  total_users: number;
  active_users: number;
  total_tickets: number;
  open_tickets: number;
  published_articles: number;
  draft_articles: number;
  audit_events_24h: number;
  total_sessions: number;
  resolution_rate: number;
}
