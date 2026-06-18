/** Team queue dashboard — IT lead view of all team tickets. */

import { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { AlertCircle, Clock, User, Tag, RefreshCw } from 'lucide-react';

interface Ticket {
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
  in_progress: 'bg-yellow-100 text-yellow-800',
  waiting_for_user: 'bg-orange-100 text-orange-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-800',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'text-red-700 bg-red-50 border-red-200',
  high: 'text-orange-700 bg-orange-50 border-orange-200',
  medium: 'text-yellow-700 bg-yellow-50 border-yellow-200',
  low: 'text-green-700 bg-green-50 border-green-200',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function TeamQueuePage() {
  const { token } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');

  const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (priorityFilter) params.set('priority', priorityFilter);
      const qs = params.toString() ? `?${params.toString()}` : '';

      const res = await fetch(`${API_BASE}/tickets/queue${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load tickets (${res.status})`);
      const data = await res.json();
      setTickets(data.tickets ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }, [API_BASE, token, statusFilter, priorityFilter]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Team Queue</h1>
          <p className="text-sm text-gray-500">All tickets across the IT support team</p>
        </div>
        <button
          onClick={fetchTickets}
          className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border px-3 py-2 text-sm text-gray-700"
        >
          <option value="">All Statuses</option>
          <option value="new">New</option>
          <option value="triaged">Triaged</option>
          <option value="in_progress">In Progress</option>
          <option value="waiting_for_user">Waiting for User</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="rounded-lg border px-3 py-2 text-sm text-gray-700"
        >
          <option value="">All Priorities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Content */}
      {loading ? (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          Loading tickets…
        </div>
      ) : error ? (
        <div className="bg-red-50 rounded-lg border border-red-200 p-6 text-center text-red-600">
          <AlertCircle className="mx-auto mb-2" size={24} />
          <p>{error}</p>
        </div>
      ) : tickets.length === 0 ? (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          No tickets in the queue matching your filters.
        </div>
      ) : (
        <div className="space-y-3">
          {tickets.map((ticket) => (
            <div key={ticket.id} className="bg-white rounded-lg border p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-gray-400">{ticket.ticket_number}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[ticket.status] || 'bg-gray-100 text-gray-700'}`}>
                      {ticket.status.replace(/_/g, ' ')}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${PRIORITY_COLORS[ticket.priority] || ''}`}>
                      {ticket.priority}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 truncate">{ticket.title}</h3>
                  {ticket.ai_summary && (
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{ticket.ai_summary}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 ml-4 shrink-0">
                  <div className="flex items-center gap-1 text-xs text-gray-400">
                    <Clock size={12} />
                    {formatDate(ticket.created_at)}
                  </div>
                  {ticket.category && (
                    <div className="flex items-center gap-1 text-xs text-gray-400">
                      <Tag size={12} />
                      {ticket.category}
                    </div>
                  )}
                  {ticket.assigned_to ? (
                    <div className="flex items-center gap-1 text-xs text-indigo-500">
                      <User size={12} /> Assigned
                    </div>
                  ) : (
                    <span className="text-xs text-amber-500 font-medium">Unassigned</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
