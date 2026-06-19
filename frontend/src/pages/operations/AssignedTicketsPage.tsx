/**
 * "My Assigned" — tickets currently assigned to the signed-in IT specialist,
 * with each one's live-chat status if a session exists.
 *
 * Backed by ``GET /specialist-queue/mine``. The live-chat status pill
 * (active / idle / ended) is the most useful signal for triage: a specialist
 * picks the active idle-warning row first because that's the one most at
 * risk of auto-ending.
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { type MyAssignedItem, liveChatApi, queueApi } from '@/features/specialist-chat/api';

export function AssignedTicketsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<MyAssignedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await queueApi.myAssigned();
      setItems(resp.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load assigned tickets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, [load]);

  const openChat = async (item: MyAssignedItem) => {
    if (item.live_session_id) {
      navigate(`/operations/live-chat/${item.live_session_id}`, {
        state: { ticketNumber: item.ticket_number },
      });
      return;
    }
    // No active session yet — start one (idempotent on the unique partial index).
    try {
      const live = await liveChatApi.start(item.ticket_id);
      navigate(`/operations/live-chat/${live.id}`, {
        state: { ticketNumber: item.ticket_number },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open chat');
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-gray-900">My Assigned Tickets</h1>
        <button
          onClick={() => void load()}
          className="text-xs text-indigo-600 hover:text-indigo-800"
        >
          Refresh
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-6">Tickets currently assigned to you</p>

      {error && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          {error}
        </div>
      )}

      <div className="bg-white rounded-lg border overflow-hidden">
        {loading && items.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading…</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-gray-500 text-sm">
            Nothing assigned to you right now.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Ticket</th>
                <th className="px-4 py-2 text-left">Title</th>
                <th className="px-4 py-2 text-left">User</th>
                <th className="px-4 py-2 text-left">Live Status</th>
                <th className="px-4 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((it) => (
                <tr key={it.ticket_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-indigo-700">{it.ticket_number}</td>
                  <td className="px-4 py-3 text-gray-700">{it.title}</td>
                  <td className="px-4 py-3 text-gray-600">{it.user_name || '—'}</td>
                  <td className="px-4 py-3">
                    <LiveStatusBadge status={it.live_status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => void openChat(it)}
                      className="px-3 py-1 text-xs rounded-md bg-indigo-600 text-white hover:bg-indigo-700"
                    >
                      {it.live_session_id ? 'Open Chat' : 'Start Chat'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function LiveStatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-xs text-gray-400">No session</span>;
  const tone =
    status === 'active'
      ? 'bg-green-100 text-green-700'
      : status === 'idle_warning'
        ? 'bg-amber-100 text-amber-700'
        : status.startsWith('ended')
          ? 'bg-gray-100 text-gray-500'
          : 'bg-indigo-100 text-indigo-700';
  return <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${tone}`}>{status}</span>;
}
