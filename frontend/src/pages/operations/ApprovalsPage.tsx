/**
 * Approval queue — IT-staff view of proposed gated write actions.
 *
 * Lists `ApprovalRecord`s from `/agent-ops/approvals` (default: pending) with a
 * status filter. Pending rows can be approved/rejected by it_lead/it_admin only;
 * the controls are hidden for lower roles (mirroring the route gating) and a 403
 * from the lead-only endpoints is surfaced inline rather than crashing.
 *
 * A collapsible "Propose action" card lets any IT staffer draft a write action
 * for review. The form renders the right fields per selected tool (declarative
 * spec in `features/agent-ops/api.ts`) and auto-generates an `idempotency_key`.
 *
 * Self-contained — React Query owns refetching (15s poll + invalidate on
 * mutation). Styling mirrors `LiveQueuePage`.
 */

import { useMemo, useState } from 'react';
import { ShieldCheck } from 'lucide-react';

import {
  PROPOSABLE_TOOLS,
  useApprovals,
  useApproveAction,
  useProposeAction,
  useRejectAction,
} from '@/features/agent-ops/api';
import type {
  ApprovalRecord,
  ApprovalStatus,
  ApprovalStatusFilter,
  ProposableTool,
} from '@/features/agent-ops/types';
import { ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth-store';

const FILTERS: ApprovalStatusFilter[] = ['pending', 'all', 'approved', 'rejected'];

const FILTER_LABELS: Record<ApprovalStatusFilter, string> = {
  pending: 'Pending',
  all: 'All',
  approved: 'Approved',
  rejected: 'Rejected',
};

export function ApprovalsPage() {
  const isAdmin = useAuthStore((s) => s.isAdmin);
  const canDecide = isAdmin();

  const [filter, setFilter] = useState<ApprovalStatusFilter>('pending');
  const [showPropose, setShowPropose] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch, isFetching } = useApprovals(filter);
  const approve = useApproveAction();
  const reject = useRejectAction();

  const items = data?.items ?? [];
  const pendingCount = items.filter((i) => i.status === 'pending').length;

  const onDecide = async (id: string, decision: 'approve' | 'reject') => {
    setDecidingId(id);
    setActionError(null);
    try {
      if (decision === 'approve') {
        await approve.mutateAsync(id);
      } else {
        await reject.mutateAsync(id);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setActionError('You do not have permission to decide on approvals (it_lead or it_admin required).');
      } else {
        setActionError(e instanceof Error ? e.message : `Failed to ${decision} action`);
      }
    } finally {
      setDecidingId(null);
    }
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <ShieldCheck size={22} className="text-indigo-600" /> Approval Queue
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Gated write actions awaiting human review.
          </p>
        </div>
        <div className="flex gap-2">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                filter === f
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <Stat label="Pending" value={pendingCount} tone="yellow" />
        <Stat label="Shown" value={items.length} tone="indigo" />
        <Stat
          label="Decided"
          value={items.filter((i) => i.decided_at).length}
          tone="green"
        />
      </div>

      {actionError && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {actionError}
        </div>
      )}

      <ProposeCard open={showPropose} onToggle={() => setShowPropose((o) => !o)} />

      <div className="overflow-hidden rounded-lg border bg-white">
        <div className="flex items-center justify-between border-b bg-gray-50 p-4">
          <h2 className="text-sm font-medium text-gray-700">
            Approvals ({items.length})
          </h2>
          <button
            onClick={() => void refetch()}
            className="text-xs text-indigo-600 hover:text-indigo-800"
          >
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading approvals…</div>
        ) : isError ? (
          <div className="p-8 text-center text-sm text-red-600">
            Failed to load approvals. Please refresh.
          </div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No approvals match this filter.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left">Tool</th>
                <th className="px-4 py-2 text-left">Args</th>
                <th className="px-4 py-2 text-left">Proposer</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Age</th>
                <th className="px-4 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item) => (
                <ApprovalRow
                  key={item.id}
                  item={item}
                  canDecide={canDecide}
                  deciding={decidingId === item.id}
                  onDecide={onDecide}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ApprovalRow({
  item,
  canDecide,
  deciding,
  onDecide,
}: {
  item: ApprovalRecord;
  canDecide: boolean;
  deciding: boolean;
  onDecide: (id: string, decision: 'approve' | 'reject') => void;
}) {
  return (
    <tr className="align-top hover:bg-gray-50">
      <td className="px-4 py-3">
        <div className="font-medium text-indigo-700">{item.tool_name}</div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <SideEffectBadge sideEffect={item.side_effect} />
          {item.mcp_server && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">
              {item.mcp_server}
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-gray-700">
        <pre className="max-w-xs overflow-x-auto whitespace-pre-wrap break-words rounded bg-gray-50 px-2 py-1 text-[11px] text-gray-600">
          {compactArgs(item.args)}
        </pre>
        {item.reason && (
          <div className="mt-1 max-w-xs text-[11px] italic text-gray-400">
            “{item.reason}”
          </div>
        )}
        {item.status !== 'pending' && (item.result || item.error) && (
          <div
            className={`mt-1 max-w-xs rounded px-2 py-1 text-[11px] ${
              item.error
                ? 'bg-red-50 text-red-700'
                : 'bg-emerald-50 text-emerald-700'
            }`}
          >
            {item.error ? item.error : compactArgs(item.result ?? {})}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">{item.proposer_id}</td>
      <td className="px-4 py-3">
        <StatusBadge status={item.status} />
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">{relativeAge(item.created_at)}</td>
      <td className="px-4 py-3 text-right">
        {item.status === 'pending' ? (
          canDecide ? (
            <div className="flex justify-end gap-2">
              <button
                onClick={() => onDecide(item.id, 'approve')}
                disabled={deciding}
                className="rounded-md bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {deciding ? '…' : 'Approve'}
              </button>
              <button
                onClick={() => onDecide(item.id, 'reject')}
                disabled={deciding}
                className="rounded-md border border-red-200 bg-white px-3 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          ) : (
            <span className="text-xs text-gray-400">Lead approval required</span>
          )
        ) : (
          <span className="text-xs text-gray-400">
            {item.decided_by ? `By ${item.decided_by}` : '—'}
          </span>
        )}
      </td>
    </tr>
  );
}

// ── Propose action form ───────────────────────────────────────────────

function ProposeCard({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const propose = useProposeAction();
  const [toolName, setToolName] = useState<string>(PROPOSABLE_TOOLS[0].tool_name);
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const tool: ProposableTool = useMemo(
    () => PROPOSABLE_TOOLS.find((t) => t.tool_name === toolName) ?? PROPOSABLE_TOOLS[0],
    [toolName],
  );

  const onSelectTool = (name: string) => {
    setToolName(name);
    setValues({});
    setError(null);
    setSuccess(null);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const missing = tool.fields.filter((f) => f.required && !values[f.name]?.trim());
    if (missing.length > 0) {
      setError(`Missing required fields: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }
    if (!reason.trim()) {
      setError('A reason is required.');
      return;
    }

    const key = idempotencyKey.trim() || `${tool.tool_name}-${Date.now()}`;
    const args: Record<string, unknown> = { idempotency_key: key };
    for (const field of tool.fields) {
      const value = values[field.name]?.trim();
      if (value) args[field.name] = value;
    }

    try {
      const record = await propose.mutateAsync({
        tool_name: tool.tool_name,
        args,
        reason: reason.trim(),
      });
      setSuccess(`Proposed — approval ${record.id} is now ${record.status}.`);
      setValues({});
      setReason('');
      setIdempotencyKey('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('You do not have permission to propose actions.');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to propose action');
      }
    }
  };

  return (
    <div className="mb-6 overflow-hidden rounded-lg border bg-white">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        Propose action
        <span className="text-xs text-indigo-600">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <form onSubmit={onSubmit} className="space-y-4 border-t p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Write tool
            </label>
            <select
              value={toolName}
              onChange={(e) => onSelectTool(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            >
              {PROPOSABLE_TOOLS.map((t) => (
                <option key={t.tool_name} value={t.tool_name}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-400">{tool.description}</p>
          </div>

          {tool.fields.map((field) => (
            <div key={field.name}>
              <label className="mb-1 block text-xs font-medium text-gray-600">
                {field.label}
                {field.required && <span className="text-red-500"> *</span>}
              </label>
              {field.kind === 'select' ? (
                <select
                  value={values[field.name] ?? ''}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [field.name]: e.target.value }))
                  }
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select…</option>
                  {(field.options ?? []).map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : field.kind === 'textarea' ? (
                <textarea
                  value={values[field.name] ?? ''}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [field.name]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  rows={3}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
              ) : (
                <input
                  type="text"
                  value={values[field.name] ?? ''}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [field.name]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
              )}
            </div>
          ))}

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Reason <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this action is needed"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Idempotency key{' '}
              <span className="font-normal text-gray-400">(optional — auto-generated)</span>
            </label>
            <input
              type="text"
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              placeholder={`${tool.tool_name}-<timestamp>`}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          {error && <div className="text-sm text-red-600">{error}</div>}
          {success && <div className="text-sm text-emerald-600">{success}</div>}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={propose.isPending}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {propose.isPending ? 'Proposing…' : 'Propose for approval'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

// ── Presentational helpers ────────────────────────────────────────────

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'yellow' | 'indigo' | 'green';
}) {
  const colors = {
    yellow: 'text-yellow-600',
    indigo: 'text-indigo-600',
    green: 'text-emerald-600',
  }[tone];
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className={`text-2xl font-bold ${colors}`}>{value}</p>
      <p className="mt-1 text-xs text-gray-500">{label}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: ApprovalStatus }) {
  const tone: Record<ApprovalStatus, string> = {
    pending: 'bg-yellow-100 text-yellow-700',
    approved: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-gray-100 text-gray-700',
    failed: 'bg-red-100 text-red-700',
    invalid: 'bg-red-100 text-red-700',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone[status]}`}>
      {status}
    </span>
  );
}

function SideEffectBadge({ sideEffect }: { sideEffect: string }) {
  const tone =
    sideEffect === 'write'
      ? 'bg-orange-100 text-orange-700'
      : sideEffect === 'destructive'
        ? 'bg-red-100 text-red-700'
        : 'bg-gray-100 text-gray-600';
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tone}`}>
      {sideEffect}
    </span>
  );
}

function compactArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return '{}';
  return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join('\n');
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function relativeAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}
