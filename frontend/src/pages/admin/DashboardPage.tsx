/** Analytics dashboard page — IT lead/admin metrics overview. */

import { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { RefreshCw } from 'lucide-react';

interface DashboardMetrics {
  ticket_metrics: {
    total: number;
    status_distribution: Record<string, number>;
    priority_distribution: Record<string, number>;
    category_distribution: Record<string, number>;
  };
  ai_metrics: {
    ai_resolved: number;
    total_sessions: number;
    resolution_rate: number;
    avg_confidence: number;
  };
  sla_metrics: {
    sla_met: number;
    sla_breached: number;
    compliance_rate: number;
  };
  period: { start: string; end: string };
}

interface AgentWorkload {
  agent_id: string;
  active_tickets: number;
}

export function DashboardPage() {
  const { token } = useAuthStore();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [workload, setWorkload] = useState<AgentWorkload[]>([]);
  const [loading, setLoading] = useState(true);

  const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [dashRes, workRes] = await Promise.allSettled([
        fetch(`${API_BASE}/analytics/dashboard`, { headers }),
        fetch(`${API_BASE}/analytics/workload`, { headers }),
      ]);
      if (dashRes.status === 'fulfilled' && dashRes.value.ok) {
        setMetrics(await dashRes.value.json());
      }
      if (workRes.status === 'fulfilled' && workRes.value.ok) {
        setWorkload(await workRes.value.json());
      }
    } catch { /* handled */ }
    setLoading(false);
  }, [token, API_BASE]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const tm = metrics?.ticket_metrics;
  const ai = metrics?.ai_metrics;
  const sla = metrics?.sla_metrics;

  const openTickets = tm
    ? (tm.status_distribution['new'] ?? 0)
      + (tm.status_distribution['triaged'] ?? 0)
      + (tm.status_distribution['in_progress'] ?? 0)
      + (tm.status_distribution['waiting_for_user'] ?? 0)
    : 0;
  const aiRate = ai ? `${Math.round(ai.resolution_rate * 100)}%` : '—';
  const slaRate = sla ? `${Math.round(sla.compliance_rate * 100)}%` : '—';

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">IT Analytics Dashboard</h1>
          <p className="text-sm text-gray-500">Overview of IT support performance</p>
        </div>
        <button onClick={fetchAll} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-12">Loading dashboard…</div>
      ) : (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-4 gap-4 mb-8">
            <MetricCard title="Total Tickets (30d)" value={String(tm?.total ?? 0)} color="blue" />
            <MetricCard title="Open Tickets" value={String(openTickets)} color="orange" />
            <MetricCard title="AI Resolution Rate" value={aiRate} color="indigo" />
            <MetricCard title="SLA Compliance" value={slaRate} color="emerald" />
          </div>

          {/* Distributions */}
          <div className="grid grid-cols-2 gap-6 mb-6">
            <div className="bg-white rounded-lg border p-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Priority Distribution</h3>
              {tm && Object.keys(tm.priority_distribution).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(tm.priority_distribution).map(([p, count]) => (
                    <div key={p} className="flex items-center gap-3">
                      <span className="text-xs font-medium text-gray-600 w-16 capitalize">{p}</span>
                      <div className="flex-1 bg-gray-100 rounded-full h-3">
                        <div
                          className={`h-3 rounded-full ${p === 'critical' ? 'bg-red-500' : p === 'high' ? 'bg-orange-500' : p === 'medium' ? 'bg-yellow-500' : 'bg-green-500'}`}
                          style={{ width: `${Math.min(100, (count / (tm.total || 1)) * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 w-8 text-right">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-6">No ticket data yet</p>
              )}
            </div>
            <div className="bg-white rounded-lg border p-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Category Distribution</h3>
              {tm && Object.keys(tm.category_distribution).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(tm.category_distribution).map(([cat, count]) => (
                    <div key={cat} className="flex items-center justify-between">
                      <span className="text-xs text-gray-600 truncate">{cat}</span>
                      <span className="text-xs font-semibold text-gray-800 ml-2">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-6">No category data yet</p>
              )}
            </div>
          </div>

          {/* Agent workload */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Agent Workload</h3>
            {workload.length > 0 ? (
              <div className="space-y-3">
                {workload.map((agent) => (
                  <AgentRow key={agent.agent_id} agentId={agent.agent_id} tickets={agent.active_tickets} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">No agent activity data available</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ title, value, color }: { title: string; value: string; color: string }) {
  return (
    <div className="bg-white rounded-lg border p-4">
      <p className="text-xs text-gray-500 font-medium">{title}</p>
      <p className={`text-2xl font-bold text-${color}-600 mt-1`}>{value}</p>
    </div>
  );
}

function AgentRow({ agentId, tickets }: { agentId: string; tickets: number }) {
  const shortId = agentId.slice(0, 8);
  return (
    <div className="flex items-center gap-4">
      <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-medium text-indigo-700">
        {shortId.charAt(0).toUpperCase()}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-gray-900">Agent {shortId}</p>
      </div>
      <p className="text-sm text-gray-500">{tickets} active</p>
    </div>
  );
}
