/** My Tickets page — employee view of own support tickets. */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';

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
  in_progress: 'bg-yellow-100 text-yellow-800',
  waiting_for_user: 'bg-orange-100 text-orange-800',
  escalated: 'bg-red-100 text-red-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-800',
};

export function MyTicketsPage() {
  const { token } = useAuthStore();
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchTickets();
    // Run once on mount; fetchTickets is stable for this page's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchTickets = async () => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';
      const response = await fetch(`${API_BASE}/tickets/my`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setTickets(data.tickets || []);
      }
    } catch {
      // Handle error
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Tickets</h1>
          <p className="text-sm text-gray-500 mt-1">Track your IT support requests</p>
        </div>
        <Link
          to="/support/chat"
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
        >
          + New Request
        </Link>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading tickets...</div>
      ) : tickets.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500">No tickets yet.</p>
          <p className="text-sm text-gray-400 mt-1">Start a support chat to create a ticket.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ticket</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Priority</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {tickets.map((ticket) => (
                <tr key={ticket.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/support/tickets/${ticket.id}`} className="text-indigo-600 font-mono text-sm hover:underline">
                      {ticket.ticket_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">{ticket.title}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 text-xs rounded-full font-medium ${STATUS_COLORS[ticket.status] || 'bg-gray-100'}`}>
                      {ticket.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 capitalize">{ticket.priority}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(ticket.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
