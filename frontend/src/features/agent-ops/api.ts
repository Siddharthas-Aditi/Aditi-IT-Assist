/** React Query hooks + API calls for the Agent Operations console. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  AgentOpsStatus,
  AgentTaskListResponse,
  AgentTaskRecord,
  ApprovalListResponse,
  ApprovalRecord,
  ApprovalStatusFilter,
  EnqueueTaskPayload,
  EnqueueableTask,
  ProposableTool,
  ProposeActionPayload,
} from './types';

const AGENT_OPS = '/agent-ops';

export const agentOpsKeys = {
  all: ['agent-ops'] as const,
  status: ['agent-ops', 'status'] as const,
  approvals: (status: ApprovalStatusFilter) =>
    ['agent-ops', 'approvals', status] as const,
  tasks: ['agent-ops', 'tasks'] as const,
};

// ── Platform status ───────────────────────────────────────────────────

export function useAgentOpsStatus() {
  return useQuery({
    queryKey: agentOpsKeys.status,
    queryFn: () => apiRequest<AgentOpsStatus>(`${AGENT_OPS}/status`),
  });
}

// ── Approvals ─────────────────────────────────────────────────────────

export function useApprovals(status: ApprovalStatusFilter = 'pending') {
  return useQuery({
    queryKey: agentOpsKeys.approvals(status),
    queryFn: () =>
      apiRequest<ApprovalListResponse>(`${AGENT_OPS}/approvals`, {
        // The backend default returns pending; `all` omits the filter.
        query: { status: status === 'all' ? undefined : status },
      }),
    refetchInterval: 15000,
  });
}

export function useProposeAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProposeActionPayload) =>
      apiRequest<ApprovalRecord>(`${AGENT_OPS}/approvals`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}

export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<ApprovalRecord>(`${AGENT_OPS}/approvals/${id}/approve`, {
        method: 'POST',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}

export function useRejectAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<ApprovalRecord>(`${AGENT_OPS}/approvals/${id}/reject`, {
        method: 'POST',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}

// ── Background tasks ──────────────────────────────────────────────────

export function useAgentTasks() {
  return useQuery({
    queryKey: agentOpsKeys.tasks,
    queryFn: () => apiRequest<AgentTaskListResponse>(`${AGENT_OPS}/tasks`),
    refetchInterval: 15000,
  });
}

export function useEnqueueTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EnqueueTaskPayload) =>
      apiRequest<AgentTaskRecord>(`${AGENT_OPS}/tasks`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentOpsKeys.tasks });
    },
  });
}

// ── Declarative catalogs (drive the propose / enqueue forms) ──────────
//
// These mirror the backend write-tool and task-type contracts. Keeping them
// declarative means the forms render the right fields per selection without
// per-tool branching in the page component. The `idempotency_key` arg is
// auto-generated on submit, so it is intentionally not a user field.

export const PROPOSABLE_TOOLS: ProposableTool[] = [
  {
    tool_name: 'entra_unlock_account',
    label: 'Unlock Entra account',
    description: 'Unlock a locked-out directory account.',
    fields: [
      {
        name: 'user_principal_name',
        label: 'User principal name',
        kind: 'text',
        required: true,
        placeholder: 'user@aditi.com',
      },
    ],
  },
  {
    tool_name: 'reset_mfa',
    label: 'Reset MFA',
    description: "Reset a user's multi-factor authentication methods.",
    fields: [
      {
        name: 'user_principal_name',
        label: 'User principal name',
        kind: 'text',
        required: true,
        placeholder: 'user@aditi.com',
      },
    ],
  },
  {
    tool_name: 'servicenow_create_incident',
    label: 'Create ServiceNow incident',
    description: 'Open a new incident in ServiceNow.',
    fields: [
      {
        name: 'short_description',
        label: 'Short description',
        kind: 'text',
        required: true,
        placeholder: 'Brief summary of the issue',
      },
      {
        name: 'description',
        label: 'Description',
        kind: 'textarea',
        required: true,
        placeholder: 'Full details of the incident',
      },
      {
        name: 'urgency',
        label: 'Urgency',
        kind: 'select',
        required: true,
        options: ['low', 'medium', 'high'],
      },
    ],
  },
];

export const ENQUEUEABLE_TASKS: EnqueueableTask[] = [
  {
    task_type: 'knowledge_improvement_sweep',
    label: 'Knowledge improvement sweep',
    description: 'Review the top-N articles for improvement candidates.',
    fields: [
      {
        name: 'top_n',
        label: 'Top N articles',
        kind: 'text',
        required: true,
        placeholder: '10',
      },
    ],
  },
  {
    task_type: 'proactive_diagnostics',
    label: 'Proactive diagnostics',
    description: 'Run proactive diagnostics for a user.',
    fields: [
      {
        name: 'upn',
        label: 'User principal name',
        kind: 'text',
        required: true,
        placeholder: 'user@aditi.com',
      },
    ],
  },
];
