/** Analytics dashboard — IT lead/admin metrics overview (real, NaN-safe). */

import { useState } from 'react';
import { RefreshCw, Ticket, FolderOpen, Bot, ShieldCheck, AlertTriangle, Users2 } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { Card, StatCard } from '@/components/ui';
import { useAgentWorkload, useDashboardMetrics } from '@/features/admin/api';

const RANGES = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
];

/** Render a 0-100 percentage that may be null/NaN as a safe string. */
function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'No data';
  return `${Math.round(value)}%`;
}

const OPEN_STATUSES = ['new', 'triaged', 'in_progress', 'waiting_for_user', 'escalated'];

export function DashboardPage() {
  const [rangeDays, setRangeDays] = useState(30);
  const { data: metrics, isLoading, isError, refetch, isFetching } = useDashboardMetrics(rangeDays);
  const { data: workload } = useAgentWorkload();

  const tm = metrics?.ticket_metrics;
  const ai = metrics?.ai_metrics;
  const sla = metrics?.sla_metrics;

  const openTickets = tm
    ? OPEN_STATUSES.reduce((sum, s) => sum + (tm.status_distribution[s] ?? 0), 0)
    : 0;

  return (
    <>
      <PageHeader
        title="Analytics"
        description="IT support performance across tickets, AI resolution, and SLAs"
        breadcrumbs={[{ label: 'Analytics' }]}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-border bg-card p-0.5">
              {RANGES.map((r) => (
                <button
                  key={r.days}
                  type="button"
                  onClick={() => setRangeDays(r.days)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    rangeDays === r.days
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        }
      />

      <div className="p-6">
        {isLoading ? (
          <div className="py-16 text-center text-muted-foreground">Loading dashboard…</div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center text-sm text-destructive">
            Failed to load analytics. Please refresh.
          </div>
        ) : (
          <>
            {/* KPI cards */}
            <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                icon={<Ticket size={18} />}
                label={`Total tickets (${rangeDays}d)`}
                value={String(tm?.total ?? 0)}
              />
              <StatCard
                icon={<FolderOpen size={18} />}
                label="Open tickets"
                value={String(openTickets)}
              />
              <StatCard
                icon={<Bot size={18} />}
                label="AI resolution rate"
                value={pct(ai?.resolution_rate)}
              />
              <StatCard
                icon={<ShieldCheck size={18} />}
                label="SLA compliance"
                value={pct(sla?.compliance_rate)}
              />
            </div>

            {/* Secondary metrics */}
            <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MiniStat label="AI sessions" value={String(ai?.total_sessions ?? 0)} />
              <MiniStat label="Escalation rate" value={pct(ai?.escalation_rate)} />
              <MiniStat
                label="SLA breached (open)"
                value={String(sla?.breached ?? 0)}
                warn={(sla?.breached ?? 0) > 0}
              />
              <MiniStat label="SLA at risk" value={String(sla?.at_risk ?? 0)} />
            </div>

            <div className="mb-6 grid gap-6 lg:grid-cols-2">
              {/* Priority distribution */}
              <Card>
                <h3 className="mb-4 text-sm font-semibold text-foreground">Priority distribution</h3>
                {tm && Object.keys(tm.priority_distribution).length > 0 ? (
                  <div className="space-y-2.5">
                    {Object.entries(tm.priority_distribution).map(([p, count]) => (
                      <div key={p} className="flex items-center gap-3">
                        <span className="w-16 text-xs font-medium capitalize text-muted-foreground">
                          {p}
                        </span>
                        <div className="h-2.5 flex-1 rounded-full bg-muted">
                          <div
                            className={`h-2.5 rounded-full ${
                              p === 'critical'
                                ? 'bg-red-500'
                                : p === 'high'
                                  ? 'bg-orange-500'
                                  : p === 'medium'
                                    ? 'bg-amber-400'
                                    : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(100, (count / (tm.total || 1)) * 100)}%` }}
                          />
                        </div>
                        <span className="w-8 text-right text-xs text-muted-foreground">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-6 text-center text-sm text-muted-foreground">No ticket data yet</p>
                )}
              </Card>

              {/* Category distribution */}
              <Card>
                <h3 className="mb-4 text-sm font-semibold text-foreground">Top categories</h3>
                {tm && Object.keys(tm.category_distribution).length > 0 ? (
                  <div className="space-y-2">
                    {Object.entries(tm.category_distribution).map(([cat, count]) => (
                      <div key={cat} className="flex items-center justify-between text-sm">
                        <span className="truncate text-muted-foreground">{cat}</span>
                        <span className="ml-2 font-semibold text-foreground">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-6 text-center text-sm text-muted-foreground">No category data yet</p>
                )}
              </Card>
            </div>

            {/* Agent workload */}
            <Card>
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
                <Users2 size={15} /> Agent workload
              </h3>
              {workload && workload.length > 0 ? (
                <div className="space-y-3">
                  {workload.map((agent) => (
                    <div key={agent.agent_id} className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                        {agent.agent_id.slice(0, 1).toUpperCase()}
                      </div>
                      <span className="flex-1 text-sm text-foreground">
                        Agent {agent.agent_id.slice(0, 8)}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {agent.active_tickets} active
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  No agent activity in this period
                </p>
              )}
            </Card>
          </>
        )}
      </div>
    </>
  );
}

function MiniStat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {warn && <AlertTriangle size={12} className="text-amber-500" />}
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-foreground">{value}</p>
    </div>
  );
}
