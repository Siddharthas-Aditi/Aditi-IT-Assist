/** Agent Operations API types — mirror of `backend/app/api/v1/agent_ops.py`. */

export type RetrievalMode = 'hybrid' | 'keyword';

export interface McpServerStatus {
  server_id: string;
  display_name: string;
  trust_tier: string;
  transport: string;
  enabled: boolean;
  tools: string[];
}

export interface AgentOpsStatus {
  agent_tools_enabled: boolean;
  vector_retrieval_enabled: boolean;
  mcp_tools_enabled: boolean;
  write_actions_enabled: boolean;
  background_agents_enabled: boolean;
  mcp_use_mock: boolean;
  retrieval_mode: RetrievalMode;
  ranking_version: string;
  registry_version: string;
  tool_registry_version: string;
  mcp_profile_version: string;
  local_tools: string[];
  active_mcp_tools: string[];
  servers: McpServerStatus[];
}

export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'failed'
  | 'invalid';

export interface ApprovalRecord {
  id: string;
  tool_name: string;
  args: Record<string, unknown>;
  reason: string;
  status: ApprovalStatus;
  side_effect: string;
  mcp_server: string | null;
  args_hash: string;
  proposer_id: string;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ApprovalListResponse {
  items: ApprovalRecord[];
}

export interface ProposeActionPayload {
  tool_name: string;
  args: Record<string, unknown>;
  reason: string;
}

export type AgentTaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface AgentTaskRecord {
  id: string;
  task_type: string;
  status: AgentTaskStatus;
  attempts: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentTaskListResponse {
  items: AgentTaskRecord[];
}

export interface EnqueueTaskPayload {
  task_type: string;
  payload: Record<string, unknown>;
  idempotency_key?: string;
}

/** Approval filter values exposed in the UI. */
export type ApprovalStatusFilter = 'all' | 'pending' | 'approved' | 'rejected';

/** Declarative spec for the write tools a user can propose. */
export interface ToolArgField {
  name: string;
  label: string;
  /** Render hint — `textarea` for long free text, `select` for picklists. */
  kind: 'text' | 'textarea' | 'select';
  required: boolean;
  placeholder?: string;
  options?: string[];
}

export interface ProposableTool {
  tool_name: string;
  label: string;
  description: string;
  /** Fields the user fills in (excludes the auto-generated idempotency_key). */
  fields: ToolArgField[];
}

/** Declarative spec for the background task types a user can enqueue. */
export interface EnqueueableTask {
  task_type: string;
  label: string;
  description: string;
  fields: ToolArgField[];
}
