/** Ticket workspace — IT staff detailed ticket view with actions. */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AlertCircle, Clock, MessageSquarePlus, RefreshCw, UserCheck } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import { apiRequest } from '@/lib/api';
import { useAuthStore } from '@/stores/auth-store';

interface TicketDetail {
  id: string;
  ticket_number: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  category: string | null;
  requester_id: string;
  assigned_to: string | null;
  created_at: string;
  sla_resolution_target: string | null;
  ai_summary: string | null;
  resolution_notes: string | null;
}

interface Comment {
  id: string;
  content: string;
  is_internal: boolean;
  author_id: string;
  created_at: string;
}

interface TicketEvent {
  type: string;
  description: string;
  created_at: string;
}

interface TicketDetailResponse {
  ticket: TicketDetail;
  comments: Comment[];
  events: TicketEvent[];
}

const STATUS_OPTIONS = [
  'new',
  'triaged',
  'in_progress',
  'waiting_for_user',
  'escalated',
  'resolved',
  'closed',
];

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800',
  triaged: 'bg-purple-100 text-purple-800',
  in_progress: 'bg-amber-100 text-amber-800',
  waiting_for_user: 'bg-orange-100 text-orange-800',
  escalated: 'bg-red-100 text-red-800',
  resolved: 'bg-emerald-100 text-emerald-800',
  closed: 'bg-gray-100 text-gray-700',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'text-red-700 bg-red-50 border-red-200',
  high: 'text-orange-700 bg-orange-50 border-orange-200',
  medium: 'text-amber-700 bg-amber-50 border-amber-200',
  low: 'text-emerald-700 bg-emerald-50 border-emerald-200',
};

function fmt(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export function TicketWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const currentUser = useAuthStore((s) => s.user);

  const [data, setData] = useState<TicketDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState('');
  const [internal, setInternal] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setData(await apiRequest<TicketDetailResponse>(`/tickets/${id}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load ticket');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const runAction = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  const ticket = data?.ticket;
  const isMine = Boolean(
    ticket?.assigned_to && currentUser && ticket.assigned_to === currentUser.id,
  );

  const timeline = useMemo(() => {
    if (!data) return [];
    const items: { ts: string; kind: 'comment' | 'event'; text: string; internal?: boolean }[] = [
      ...data.comments.map((c) => ({
        ts: c.created_at,
        kind: 'comment' as const,
        text: c.content,
        internal: c.is_internal,
      })),
      ...data.events.map((e) => ({
        ts: e.created_at,
        kind: 'event' as const,
        text: e.description || e.type,
      })),
    ];
    return items.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }, [data]);

  const breadcrumbs = [
    { label: 'Live Queue', to: '/operations' },
    { label: ticket?.ticket_number ?? 'Ticket' },
  ];

  if (loading) {
    return (
      <>
        <PageHeader title="Ticket" breadcrumbs={breadcrumbs} breadcrumbHome="/operations" />
        <div className="p-6 text-muted-foreground">Loading ticket…</div>
      </>
    );
  }

  if (error && !ticket) {
    return (
      <>
        <PageHeader title="Ticket" breadcrumbs={breadcrumbs} breadcrumbHome="/operations" />
        <div className="p-6">
          <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <AlertCircle size={16} /> {error}
          </div>
        </div>
      </>
    );
  }

  if (!ticket) return null;

  return (
    <>
      <PageHeader
        title={ticket.title}
        description={ticket.ticket_number}
        breadcrumbs={breadcrumbs}
        breadcrumbHome="/operations"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => load()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> Refresh
            </button>
            {!isMine && (
              <button
                type="button"
                disabled={busy || !currentUser}
                onClick={() =>
                  runAction(() =>
                    apiRequest(`/tickets/${id}/assign`, {
                      method: 'POST',
                      body: { agent_id: currentUser!.id },
                    }),
                  )
                }
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                <UserCheck size={14} /> Assign to me
              </button>
            )}
          </div>
        }
      />

      <div className="grid gap-6 p-6 lg:grid-cols-3">
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive lg:col-span-3">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {/* Main */}
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  STATUS_COLORS[ticket.status] || 'bg-gray-100 text-gray-700'
                }`}
              >
                {ticket.status.replace(/_/g, ' ')}
              </span>
              <span
                className={`rounded border px-2 py-0.5 text-xs font-medium ${
                  PRIORITY_COLORS[ticket.priority] || ''
                }`}
              >
                {ticket.priority}
              </span>
              {ticket.category && (
                <span className="text-xs text-muted-foreground">{ticket.category}</span>
              )}
            </div>
            <h2 className="mb-1 text-sm font-semibold text-foreground">Description</h2>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{ticket.description}</p>
            {ticket.ai_summary && (
              <div className="mt-4 rounded-lg bg-primary/5 p-3">
                <p className="text-xs font-medium text-primary">AI summary</p>
                <p className="mt-1 text-sm text-muted-foreground">{ticket.ai_summary}</p>
              </div>
            )}
          </Card>

          {/* Timeline */}
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-foreground">Activity</h2>
            {timeline.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">No activity yet.</p>
            ) : (
              <ol className="space-y-3">
                {timeline.map((item, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <Clock size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <p className="whitespace-pre-wrap text-foreground">
                        {item.text}
                        {item.kind === 'comment' && item.internal && (
                          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                            internal
                          </span>
                        )}
                        {item.kind === 'event' && (
                          <span className="ml-2 text-[11px] uppercase tracking-wide text-muted-foreground">
                            event
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">{fmt(item.ts)}</p>
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {/* Add comment */}
            <div className="mt-4 border-t border-border pt-4">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                placeholder="Add a comment or internal note…"
                className="w-full rounded-lg border border-border bg-card p-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              />
              <div className="mt-2 flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={internal}
                    onChange={(e) => setInternal(e.target.checked)}
                  />
                  Internal note (hidden from employee)
                </label>
                <button
                  type="button"
                  disabled={busy || !comment.trim()}
                  onClick={() =>
                    runAction(async () => {
                      await apiRequest(`/tickets/${id}/comments`, {
                        method: 'POST',
                        body: { content: comment.trim(), is_internal: internal },
                      });
                      setComment('');
                    })
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  <MessageSquarePlus size={14} /> Add comment
                </button>
              </div>
            </div>
          </Card>
        </div>

        {/* Side panel */}
        <div className="space-y-6">
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-foreground">Details</h2>
            <dl className="space-y-2.5 text-sm">
              <Row label="Status" value={ticket.status.replace(/_/g, ' ')} />
              <Row label="Priority" value={ticket.priority} />
              <Row
                label="Assignee"
                value={isMine ? 'You' : ticket.assigned_to ? 'Assigned' : 'Unassigned'}
              />
              <Row label="Created" value={fmt(ticket.created_at)} />
              <Row label="SLA target" value={fmt(ticket.sla_resolution_target)} />
            </dl>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-foreground">Update status</h2>
            <div className="flex flex-wrap gap-1.5">
              {STATUS_OPTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={busy || s === ticket.status}
                  onClick={() =>
                    runAction(() =>
                      apiRequest(`/tickets/${id}/status`, {
                        method: 'POST',
                        body: { status: s },
                      }),
                    )
                  }
                  className={`rounded-lg border px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                    s === ticket.status
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {s.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium capitalize text-foreground">{value}</dd>
    </div>
  );
}
