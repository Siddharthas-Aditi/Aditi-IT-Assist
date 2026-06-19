/** My Tickets page — employee view of own support tickets. */

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, Plus, Ticket as TicketIcon } from 'lucide-react';

import { EmptyState } from '@/components/ui';
import { apiRequest } from '@/lib/api';

interface TicketSummary {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
  priority: string;
  created_at: string;
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

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

export function MyTicketsPage() {
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTickets = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiRequest<{ tickets: TicketSummary[] }>('/tickets/my');
      setTickets(data.tickets || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tickets');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">My Tickets</h1>
          <p className="mt-1 text-sm text-muted-foreground">Track your IT support requests</p>
        </div>
        <Link
          to="/support/chat"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus size={16} /> New Request
        </Link>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-muted-foreground">Loading tickets…</div>
      ) : error ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-sm text-destructive">
          <AlertCircle size={16} /> {error}
        </div>
      ) : tickets.length === 0 ? (
        <EmptyState
          icon={<TicketIcon className="h-7 w-7 text-primary" />}
          title="No tickets yet"
          description="Start a support chat and we'll create a ticket if your issue needs a specialist."
          action={
            <Link
              to="/support/chat"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              Start a chat
            </Link>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Ticket</th>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Priority</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tickets.map((ticket) => (
                <tr key={ticket.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Link
                      to={`/support/tickets/${ticket.id}`}
                      className="font-mono text-sm text-primary hover:underline"
                    >
                      {ticket.ticket_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-foreground">{ticket.title}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        STATUS_COLORS[ticket.status] || 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {ticket.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 capitalize text-muted-foreground">{ticket.priority}</td>
                  <td className="px-4 py-3 text-muted-foreground">{fmtDate(ticket.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
