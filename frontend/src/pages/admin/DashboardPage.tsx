/** Analytics dashboard page — IT lead/admin metrics overview. */

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/stores/auth-store';

export function DashboardPage() {
  const { token } = useAuthStore();
  const [_metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetchDashboard();
    // Run once on mount; fetchDashboard is stable for this page's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchDashboard = async () => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';
      const response = await fetch(`${API_BASE}/analytics/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        setMetrics(await response.json());
      }
    } catch {
      // Handle error
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">IT Analytics Dashboard</h1>
      <p className="text-sm text-gray-500 mb-6">Overview of IT support performance</p>

      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <MetricCard title="Open Tickets" value="15" trend="+3" color="blue" />
        <MetricCard title="Avg Resolution Time" value="4.2h" trend="-12%" color="green" />
        <MetricCard title="AI Resolution Rate" value="67%" trend="+5%" color="indigo" />
        <MetricCard title="SLA Compliance" value="94%" trend="+2%" color="emerald" />
      </div>

      {/* Charts placeholder */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-lg border p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Ticket Volume (30 days)</h3>
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            Chart visualization will render here
          </div>
        </div>
        <div className="bg-white rounded-lg border p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Category Distribution</h3>
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            Chart visualization will render here
          </div>
        </div>
      </div>

      {/* Agent workload */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Agent Workload</h3>
        <div className="space-y-3">
          <AgentRow name="Charlie Martinez" tickets={5} capacity={80} />
          <AgentRow name="Diana Chen" tickets={3} capacity={50} />
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, trend, color }: { title: string; value: string; trend: string; color: string }) {
  const isPositive = trend.startsWith('+') || trend.startsWith('-') && trend.includes('%');
  return (
    <div className="bg-white rounded-lg border p-4">
      <p className="text-xs text-gray-500 font-medium">{title}</p>
      <p className={`text-2xl font-bold text-${color}-600 mt-1`}>{value}</p>
      <p className={`text-xs mt-1 ${isPositive ? 'text-green-600' : 'text-gray-500'}`}>{trend} vs last period</p>
    </div>
  );
}

function AgentRow({ name, tickets, capacity }: { name: string; tickets: number; capacity: number }) {
  return (
    <div className="flex items-center gap-4">
      <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-medium text-indigo-700">
        {name.charAt(0)}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-gray-900">{name}</p>
        <div className="w-full bg-gray-100 rounded-full h-2 mt-1">
          <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${capacity}%` }} />
        </div>
      </div>
      <p className="text-sm text-gray-500">{tickets} active</p>
    </div>
  );
}
