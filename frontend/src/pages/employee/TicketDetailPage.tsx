/** Ticket detail page — employee view with timeline. */

import { useParams, useNavigate } from 'react-router-dom';
import { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { ArrowLeft } from 'lucide-react';

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

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  triaged: 'bg-purple-100 text-purple-700',
  in_progress: 'bg-yellow-100 text-yellow-700',
  waiting_for_user: 'bg-orange-100 text-orange-700',
  resolved: 'bg-green-100 text-green-700',
  closed: 'bg-gray-100 text-gray-600',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-green-100 text-green-700',
};

export function TicketDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { token } = useAuthStore();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [comments, setComments] = useState<TicketComment[]>([]);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/tickets/my/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setError(res.status === 404 ? 'Ticket not found' : 'Failed to load ticket');
        return;
      }
      const data = await res.json();
      setTicket(data.ticket);
      setComments(data.comments ?? []);
      setEvents(data.events ?? []);
    } catch {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  }, [API_BASE, id, token]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  if (loading) {
    return <div className="p-6 text-center text-gray-400">Loading ticket…</div>;
  }
  if (error || !ticket) {
    return (
      <div className="p-6 text-center">
        <p className="text-red-500 mb-4">{error ?? 'Ticket not found'}</p>
        <button onClick={() => navigate(-1)} className="text-sm text-indigo-600 hover:underline">← Back</button>
      </div>
    );
  }

  const timeline = [
    ...events.map((e) => ({ kind: 'event' as const, text: e.description, type: e.type, ts: e.created_at })),
    ...comments.map((c) => ({ kind: 'comment' as const, text: c.content, type: 'comment', ts: c.created_at })),
  ].sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4">
        <ArrowLeft size={14} /> Back
      </button>

      {/* Header */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-xs text-gray-400 font-mono">{ticket.ticket_number}</p>
            <h1 className="text-xl font-bold text-gray-900 mt-1">{ticket.title}</h1>
          </div>
          <div className="flex gap-2">
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[ticket.status] ?? 'bg-gray-100 text-gray-600'}`}>{ticket.status.replace(/_/g, ' ')}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${PRIORITY_COLORS[ticket.priority] ?? 'bg-gray-100 text-gray-600'}`}>{ticket.priority}</span>
          </div>
        </div>
        <p className="text-sm text-gray-700 whitespace-pre-wrap">{ticket.description}</p>
        <div className="mt-4 flex gap-6 text-xs text-gray-400">
          {ticket.category && <span>Category: {ticket.category}</span>}
          <span>Created: {new Date(ticket.created_at).toLocaleString()}</span>
          {ticket.assigned_to && <span>Assigned: {ticket.assigned_to}</span>}
        </div>
      </div>

      {/* AI Summary */}
      {ticket.ai_summary && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 mb-6">
          <p className="text-xs font-semibold text-indigo-600 mb-1">AI Summary</p>
          <p className="text-sm text-indigo-800">{ticket.ai_summary}</p>
        </div>
      )}

      {/* Resolution Notes */}
      {ticket.resolution_notes && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
          <p className="text-xs font-semibold text-green-600 mb-1">Resolution</p>
          <p className="text-sm text-green-800">{ticket.resolution_notes}</p>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Activity Timeline</h3>
        {timeline.length > 0 ? (
          <div className="space-y-4 relative before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-0.5 before:bg-gray-200">
            {timeline.map((item, i) => (
              <div key={i} className="flex gap-3 pl-5 relative">
                <span className={`absolute left-0 top-1.5 w-4 h-4 rounded-full border-2 ${item.kind === 'comment' ? 'bg-indigo-100 border-indigo-400' : 'bg-gray-100 border-gray-400'}`} />
                <div>
                  <p className="text-sm text-gray-800">{item.text}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{new Date(item.ts).toLocaleString()} · {item.type}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400 text-center py-4">No activity yet</p>
        )}
      </div>
    </div>
  );
}
