/**
 * Agent Operations — admin/lead view of the agentic platform.
 *
 * Two sections:
 *   (a) Platform status — feature-flag chips, retrieval mode, contract versions,
 *       MCP server inventory, and the local + active MCP tool lists, sourced
 *       from `/agent-ops/status`.
 *   (b) Background tasks — the `/agent-ops/tasks` list with status badges plus an
 *       "Enqueue task" control that POSTs a new task and refetches.
 *
 * React Query owns refetching (15s poll on tasks + invalidate on enqueue).
 * Styling mirrors the Admin Console (PageHeader + Card design tokens).
 */

import { useMemo, useState } from 'react';
import { Bot, RefreshCw } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import {
  ENQUEUEABLE_TASKS,
  useAgentOpsStatus,
  useAgentTasks,
  useEnqueueTask,
} from '@/features/agent-ops/api';
import type {
  AgentOpsStatus,
  AgentTaskRecord,
  AgentTaskStatus,
  EnqueueableTask,
} from '@/features/agent-ops/types';
import { ApiError } from '@/lib/api';

export function AgentOperationsPage() {
  const status = useAgentOpsStatus();
  const tasks = useAgentTasks();

  return (
    <>
      <PageHeader
        title="Agent Operations"
        description="Agentic platform status, integrations, and background jobs"
        breadcrumbs={[{ label: 'Agent Operations' }]}
        actions={
          <button
            type="button"
            onClick={() => {
              void status.refetch();
              void tasks.refetch();
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            <RefreshCw
              size={14}
              className={status.isFetching || tasks.isFetching ? 'animate-spin' : ''}
            />{' '}
            Refresh
          </button>
        }
      />

      <div className="space-y-6 p-6">
        <PlatformStatusSection
          data={status.data}
          isLoading={status.isLoading}
          isError={status.isError}
        />
        <BackgroundTasksSection />
      </div>
    </>
  );
}

// ── (a) Platform status ───────────────────────────────────────────────

function PlatformStatusSection({
  data,
  isLoading,
  isError,
}: {
  data: AgentOpsStatus | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return (
      <Card>
        <p className="py-6 text-center text-sm text-muted-foreground">Loading platform status…</p>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <p className="py-6 text-center text-sm text-destructive">
          Failed to load platform status. Please refresh.
        </p>
      </Card>
    );
  }

  const flags: { label: string; on: boolean }[] = [
    { label: 'Agent tools', on: data.agent_tools_enabled },
    { label: 'Vector retrieval', on: data.vector_retrieval_enabled },
    { label: 'MCP tools', on: data.mcp_tools_enabled },
    { label: 'Write actions', on: data.write_actions_enabled },
    { label: 'Background agents', on: data.background_agents_enabled },
    { label: 'MCP mock mode', on: data.mcp_use_mock },
  ];

  const versions: { label: string; value: string }[] = [
    { label: 'Retrieval mode', value: data.retrieval_mode },
    { label: 'Ranking', value: data.ranking_version },
    { label: 'Registry', value: data.registry_version },
    { label: 'Tool registry', value: data.tool_registry_version },
    { label: 'MCP profile', value: data.mcp_profile_version },
  ];

  return (
    <>
      <Card>
        <h2 className="mb-4 text-sm font-semibold text-foreground">Feature flags</h2>
        <div className="flex flex-wrap gap-2">
          {flags.map((f) => (
            <FlagChip key={f.label} label={f.label} on={f.on} />
          ))}
        </div>

        <h3 className="mb-3 mt-6 text-sm font-semibold text-foreground">Versions</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {versions.map((v) => (
            <div key={v.label} className="rounded-lg border border-border bg-card px-3 py-2">
              <p className="text-xs text-muted-foreground">{v.label}</p>
              <p className="mt-0.5 font-mono text-sm font-medium text-foreground">{v.value}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold text-foreground">MCP servers</h2>
        {data.servers.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No MCP servers configured.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left">Server</th>
                  <th className="px-3 py-2 text-left">Trust tier</th>
                  <th className="px-3 py-2 text-left">Transport</th>
                  <th className="px-3 py-2 text-left">Enabled</th>
                  <th className="px-3 py-2 text-left">Tools</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.servers.map((server) => (
                  <tr key={server.server_id}>
                    <td className="px-3 py-2 font-medium text-foreground">
                      {server.display_name}
                    </td>
                    <td className="px-3 py-2 capitalize text-muted-foreground">
                      {server.trust_tier}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{server.transport}</td>
                    <td className="px-3 py-2">
                      <FlagChip label={server.enabled ? 'On' : 'Off'} on={server.enabled} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {server.tools.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          server.tools.map((t) => <ToolChip key={t} name={t} />)
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Local tools</h2>
          <ToolList tools={data.local_tools} />
        </Card>
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Active MCP tools</h2>
          <ToolList tools={data.active_mcp_tools} />
        </Card>
      </div>
    </>
  );
}

function ToolList({ tools }: { tools: string[] }) {
  if (tools.length === 0) {
    return <p className="py-2 text-sm text-muted-foreground">None active</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {tools.map((t) => (
        <ToolChip key={t} name={t} />
      ))}
    </div>
  );
}

// ── (b) Background tasks ──────────────────────────────────────────────

function BackgroundTasksSection() {
  const { data, isLoading, isError, refetch, isFetching } = useAgentTasks();
  const items = data?.items ?? [];

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Background tasks</h2>
        <button
          type="button"
          onClick={() => void refetch()}
          className="text-xs text-primary hover:underline"
        >
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <EnqueueTaskForm />

      {isLoading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Loading tasks…</p>
      ) : isError ? (
        <p className="py-6 text-center text-sm text-destructive">
          Failed to load tasks. Please refresh.
        </p>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No background tasks yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Attempts</th>
                <th className="px-3 py-2 text-left">Result / Error</th>
                <th className="px-3 py-2 text-left">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function TaskRow({ task }: { task: AgentTaskRecord }) {
  return (
    <tr className="align-top">
      <td className="px-3 py-2 font-medium text-foreground">{task.task_type}</td>
      <td className="px-3 py-2">
        <TaskStatusBadge status={task.status} />
      </td>
      <td className="px-3 py-2 text-muted-foreground">
        {task.attempts}/{task.max_attempts}
      </td>
      <td className="px-3 py-2">
        {task.error ? (
          <span className="text-xs text-destructive">{task.error}</span>
        ) : task.result ? (
          <pre className="max-w-xs overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-muted-foreground">
            {JSON.stringify(task.result)}
          </pre>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {new Date(task.updated_at).toLocaleString()}
      </td>
    </tr>
  );
}

function EnqueueTaskForm() {
  const enqueue = useEnqueueTask();
  const [taskType, setTaskType] = useState<string>(ENQUEUEABLE_TASKS[0].task_type);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const task: EnqueueableTask = useMemo(
    () => ENQUEUEABLE_TASKS.find((t) => t.task_type === taskType) ?? ENQUEUEABLE_TASKS[0],
    [taskType],
  );

  const onSelect = (type: string) => {
    setTaskType(type);
    setValues({});
    setError(null);
    setSuccess(null);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const missing = task.fields.filter((f) => f.required && !values[f.name]?.trim());
    if (missing.length > 0) {
      setError(`Missing required fields: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }

    // Coerce numeric-looking required fields (e.g. top_n) to numbers.
    const payload: Record<string, unknown> = {};
    for (const field of task.fields) {
      const raw = values[field.name]?.trim();
      if (!raw) continue;
      const num = Number(raw);
      payload[field.name] = field.name === 'top_n' && !Number.isNaN(num) ? num : raw;
    }

    try {
      const record = await enqueue.mutateAsync({
        task_type: task.task_type,
        payload,
        idempotency_key: `${task.task_type}-${Date.now()}`,
      });
      setSuccess(`Enqueued task ${record.id} (${record.status}).`);
      setValues({});
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('You do not have permission to enqueue tasks.');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to enqueue task');
      }
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="mb-5 space-y-3 rounded-lg border border-border bg-muted/30 p-4"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem] flex-1">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Task type
          </label>
          <select
            value={taskType}
            onChange={(e) => onSelect(e.target.value)}
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
          >
            {ENQUEUEABLE_TASKS.map((t) => (
              <option key={t.task_type} value={t.task_type}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {task.fields.map((field) => (
          <div key={field.name} className="min-w-[12rem] flex-1">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              {field.label}
              {field.required && <span className="text-destructive"> *</span>}
            </label>
            <input
              type="text"
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              placeholder={field.placeholder}
              className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
            />
          </div>
        ))}
        <button
          type="submit"
          disabled={enqueue.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {enqueue.isPending ? 'Enqueuing…' : 'Enqueue task'}
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{task.description}</p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-600">{success}</p>}
    </form>
  );
}

// ── Presentational helpers ────────────────────────────────────────────

function FlagChip({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
        on
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-border bg-muted text-muted-foreground'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${on ? 'bg-emerald-500' : 'bg-gray-400'}`} />
      {label}: {on ? 'on' : 'off'}
    </span>
  );
}

function ToolChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary">
      <Bot size={11} /> {name}
    </span>
  );
}

function TaskStatusBadge({ status }: { status: AgentTaskStatus }) {
  const tone: Record<AgentTaskStatus, string> = {
    pending: 'bg-yellow-100 text-yellow-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-emerald-100 text-emerald-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-gray-100 text-gray-600',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone[status]}`}>
      {status}
    </span>
  );
}
