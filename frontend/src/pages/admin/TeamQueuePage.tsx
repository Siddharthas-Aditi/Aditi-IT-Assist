/** Team queue — IT lead/admin view of all team tickets with filters + search. */

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock, Tag, User, RefreshCw, Search, Inbox } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { EmptyState } from '@/components/ui';
import { apiRequest } from '@/lib/api';

interface QueueTicket {
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
  ai_summary: string | null;
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

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

export function TeamQueuePage() {
  const [tickets, setTickets] = useState<QueueTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [search, setSearch] = useState('');

  const load = useMemo(
    () => async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiRequest<{ tickets: QueueTicket[] }>('/tickets/queue', {
          query: { status: statusFilter || undefined, priority: priorityFilter || undefined },
        });
        setTickets(data.tickets ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load tickets');
      } finally {
        setLoading(false);
      }
    },
    [statusFilter, priorityFilter],
  );

  useEffect(() => {
    load();
  }, [load]);

  const visible = tickets.filter((t) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      t.title.toLowerCase().includes(q) ||
      t.ticket_number.toLowerCase().includes(q) ||
      (t.category ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <>
      <PageHeader
        title="Team Queue"
        description="All tickets across the IT support team — filter, search, and open to act"
        breadcrumbs={[{ label: 'Team Queue' }]}
        actions={
          <button
            type="button"
            onClick={() => load()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />

      <div className="p-6">
        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="absolute left-3 top-2.5 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by id, title, or category…"
              className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All statuses</option>
            <option value="new">New</option>
            <option value="triaged">Triaged</option>
            <option value="in_progress">In Progress</option>
            <option value="waiting_for_user">Waiting for User</option>
            <option value="escalated">Escalated</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        {/* Content */}
        {loading ? (
          <div className="py-16 text-center text-muted-foreground">Loading tickets…</div>
        ) : error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center text-sm text-destructive">
            {error}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-7 w-7 text-primary" />}
            title="Queue is clear"
            description="No tickets match the current filters. New and unassigned tickets will appear here."
          />
        ) : (
          <div className="space-y-3">
            {visible.map((ticket) => (
              <Link
                key={ticket.id}
                to={`/operations/tickets/${ticket.id}`}
                className="block rounded-xl border border-border bg-card p-4 transition-all hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-md"
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">
                        {ticket.ticket_number}
                      </span>
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
                    </div>
                    <h3 className="truncate text-sm font-semibold text-foreground">{ticket.title}</h3>
                    {ticket.ai_summary && (
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {ticket.ai_summary}
                      </p>
                    )}
                  </div>
                  <div className="ml-4 flex shrink-0 flex-col items-end gap-1">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock size={12} />
                      {formatDate(ticket.created_at)}
                    </span>
                    {ticket.category && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Tag size={12} />
                        {ticket.category}
                      </span>
                    )}
                    {ticket.assigned_to ? (
                      <span className="flex items-center gap-1 text-xs text-primary">
                        <User size={12} /> Assigned
                      </span>
                    ) : (
                      <span className="text-xs font-medium text-amber-500">Unassigned</span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
