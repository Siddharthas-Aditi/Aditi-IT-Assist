/** Ticket detail page — employee view with timeline. */

import { useParams, useNavigate } from 'react-router-dom';
import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft } from 'lucide-react';

import { apiRequest } from '@/lib/api';

interface TicketDetail {
  id: string;
  ticket_number: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  category: string | null;
  created_at: string;
  assigned_to: string | null;
  ai_summary: string | null;
  resolution_notes: string | null;
}

interface TicketComment {
  id: string;
  content: string;
  created_at: string;
}

interface TicketEvent {
  type: string;
  description: string;
  created_at: string;
}

interface DetailResponse {
  ticket: TicketDetail;
  comments: TicketComment[];
  events: TicketEvent[];
}

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  triaged: 'bg-purple-100 text-purple-700',
  in_progress: 'bg-amber-100 text-amber-700',
  waiting_for_user: 'bg-orange-100 text-orange-700',
  escalated: 'bg-red-100 text-red-700',
  resolved: 'bg-emerald-100 text-emerald-700',
  closed: 'bg-gray-100 text-gray-600',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-emerald-100 text-emerald-700',
};

function fmt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export function TicketDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [comments, setComments] = useState<TicketComment[]>([]);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<DetailResponse>(`/tickets/my/${id}`);
      setTicket(data.ticket);
      setComments(data.comments ?? []);
      setEvents(data.events ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load ticket');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  if (loading) {
    return <div className="p-6 text-center text-muted-foreground">Loading ticket…</div>;
  }
  if (error || !ticket) {
    return (
      <div className="p-6 text-center">
        <p className="mb-4 text-destructive">{error ?? 'Ticket not found'}</p>
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          <ArrowLeft size={14} /> Back
        </button>
      </div>
    );
  }

  const timeline = [
    ...events.map((e) => ({
      kind: 'event' as const,
      text: e.description,
      type: e.type,
      ts: e.created_at,
    })),
    ...comments.map((c) => ({
      kind: 'comment' as const,
      text: c.content,
      type: 'comment',
      ts: c.created_at,
    })),
  ].sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());

  return (
    <div className="mx-auto max-w-3xl p-6">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft size={14} /> Back
      </button>

      {/* Header */}
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{ticket.ticket_number}</p>
            <h1 className="mt-1 text-xl font-bold text-foreground">{ticket.title}</h1>
          </div>
          <div className="flex shrink-0 gap-2">
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                STATUS_COLORS[ticket.status] ?? 'bg-gray-100 text-gray-600'
              }`}
            >
              {ticket.status.replace(/_/g, ' ')}
            </span>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                PRIORITY_COLORS[ticket.priority] ?? 'bg-gray-100 text-gray-600'
              }`}
            >
              {ticket.priority}
            </span>
          </div>
        </div>
        <p className="whitespace-pre-wrap text-sm text-muted-foreground">{ticket.description}</p>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          {ticket.category && <span>Category: {ticket.category}</span>}
          <span>Created: {fmt(ticket.created_at)}</span>
          {ticket.assigned_to && <span>Assigned to a specialist</span>}
        </div>
      </div>

      {/* AI Summary */}
      {ticket.ai_summary && (
        <div className="mb-6 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <p className="mb-1 text-xs font-semibold text-primary">AI Summary</p>
          <p className="text-sm text-muted-foreground">{ticket.ai_summary}</p>
        </div>
      )}

      {/* Resolution Notes */}
      {ticket.resolution_notes && (
        <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="mb-1 text-xs font-semibold text-emerald-700">Resolution</p>
          <p className="text-sm text-emerald-800">{ticket.resolution_notes}</p>
        </div>
      )}

      {/* Timeline */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="mb-4 text-sm font-semibold text-foreground">Activity Timeline</h3>
        {timeline.length > 0 ? (
          <div className="relative space-y-4 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-0.5 before:bg-border">
            {timeline.map((item, i) => (
              <div key={i} className="relative flex gap-3 pl-5">
                <span
                  className={`absolute left-0 top-1.5 h-4 w-4 rounded-full border-2 ${
                    item.kind === 'comment'
                      ? 'border-primary/50 bg-primary/15'
                      : 'border-border bg-muted'
                  }`}
                />
                <div>
                  <p className="text-sm text-foreground">{item.text}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {fmt(item.ts)} · {item.type}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">No activity yet</p>
        )}
      </div>
    </div>
  );
}
