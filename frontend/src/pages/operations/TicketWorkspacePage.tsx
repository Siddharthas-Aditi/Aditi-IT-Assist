/** Ticket workspace — IT staff detailed ticket view with actions. */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertCircle,
  Clock,
  MessageSquarePlus,
  RefreshCw,
  RotateCcw,
  UserCheck,
  XCircle,
} from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import { HandoffContextPanel } from '@/features/specialist-chat/HandoffContextPanel';
import { CloseTicketModal } from '@/features/tickets/CloseTicketModal';
import { TicketPropertiesPanel } from '@/features/tickets/TicketPropertiesPanel';
import { apiRequest, ticketsApi } from '@/lib/api';
import { isITStaff } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';

/** Terminal statuses from which a ticket can be reopened (mirrors the backend
 *  `TicketService.reopen_ticket` guard). */
const REOPENABLE_STATUSES = new Set(['resolved', 'closed']);

interface TicketDetail {
  id: string;
  ticket_number: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  category: string | null;
  subcategory: string | null;
  item: string | null;
  ticket_type: string | null;
  urgency: string | null;
  impact: string | null;
  source: string | null;
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
  const [closeModalOpen, setCloseModalOpen] = useState(false);

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
  const canReopen = Boolean(
    ticket && isITStaff(currentUser) && REOPENABLE_STATUSES.has(ticket.status),
  );
  const canClose = Boolean(
    ticket && isITStaff(currentUser) && ticket.status !== 'closed',
  );
  const agentLabel = isMine ? 'You' : ticket?.assigned_to ? 'Assigned' : 'Unassigned';

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

  if (!ticket || !id) return null;

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
            {canClose && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setCloseModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 transition-colors hover:bg-emerald-100 disabled:opacity-50"
              >
                <XCircle size={14} /> Close
              </button>
            )}
            {canReopen && (
              <button
                type="button"
                disabled={busy}
                onClick={() => runAction(() => ticketsApi.reopen(id))}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
              >
                <RotateCcw size={14} /> Reopen ticket
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

        <div className="space-y-6 lg:col-span-2">
          <HandoffContextPanel ticketId={id} />

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

        <div className="space-y-6">
          <TicketPropertiesPanel
            ticketId={id}
            ticket={ticket}
            agentLabel={agentLabel}
            disabled={ticket.status === 'closed'}
            onUpdated={() => void load()}
            onError={setError}
          />
        </div>
      </div>

      <CloseTicketModal
        ticketId={id}
        open={closeModalOpen}
        onClose={() => setCloseModalOpen(false)}
        onClosed={() => {
          setCloseModalOpen(false);
          void load();
        }}
        initialCategory={ticket.category ?? ''}
        initialSubcategory={ticket.subcategory ?? ''}
        initialItem={ticket.item ?? ''}
      />
    </>
  );
}
