/** Audit log viewer — security auditor & admin. Real, filterable event trail. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Search, Shield } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { EmptyState } from '@/components/ui';
import { useAuditEvents, useAuditFacets } from '@/features/admin/api';
import { SeverityBadge } from '@/features/admin/components/badges';
import { fmtDateTime } from '@/features/admin/utils';
import type { AuditFilters } from '@/features/admin/types';

const PAGE_SIZE = 50;

export function AuditLogPage() {
  const [filters, setFilters] = useState<AuditFilters>({ limit: PAGE_SIZE, offset: 0 });
  const [searchInput, setSearchInput] = useState('');
  const { data, isLoading, isError, refetch, isFetching } = useAuditEvents(filters);
  const { data: facets } = useAuditFacets();

  const page = Math.floor((filters.offset ?? 0) / PAGE_SIZE) + 1;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters((f) => ({ ...f, search: searchInput.trim() || undefined, offset: 0 }));
  };

  const patch = (p: Partial<AuditFilters>) => setFilters((f) => ({ ...f, ...p, offset: 0 }));

  return (
    <>
      <PageHeader
        title="Audit Logs"
        description="Immutable trail of security- and governance-relevant events"
        breadcrumbs={[{ label: 'Audit Logs' }]}
        breadcrumbHome="/audit"
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />

      <div className="p-6">
        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <form onSubmit={submitSearch} className="relative min-w-[220px] flex-1">
            <Search size={15} className="absolute left-3 top-2.5 text-muted-foreground" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search action, description, resource…"
              className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </form>
          <select
            value={filters.severity ?? ''}
            onChange={(e) => patch({ severity: e.target.value || undefined })}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All severities</option>
            {(facets?.severities ?? ['info', 'warning', 'error', 'critical']).map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
          <select
            value={filters.action ?? ''}
            onChange={(e) => patch({ action: e.target.value || undefined })}
            className="max-w-[200px] rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All actions</option>
            {facets?.actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <input
            value={filters.actor_email ?? ''}
            onChange={(e) => patch({ actor_email: e.target.value || undefined })}
            placeholder="Actor email…"
            className="w-44 rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="py-16 text-center text-muted-foreground">Loading audit events…</div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center text-sm text-destructive">
            Failed to load audit events. Please refresh.
          </div>
        ) : !data || data.events.length === 0 ? (
          <EmptyState
            icon={<Shield className="h-7 w-7 text-primary" />}
            title="No audit events"
            description="No events match the current filters. Events are recorded automatically as users and admins act on the system."
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Time</th>
                  <th className="px-4 py-2.5 font-medium">Severity</th>
                  <th className="px-4 py-2.5 font-medium">Action</th>
                  <th className="px-4 py-2.5 font-medium">Actor</th>
                  <th className="px-4 py-2.5 font-medium">Resource</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.events.map((ev) => (
                  <tr key={ev.id} className="transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                      {fmtDateTime(ev.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={ev.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/audit/${ev.id}`}
                        className="font-medium text-foreground hover:text-primary"
                      >
                        {ev.action}
                      </Link>
                      {ev.description && (
                        <p className="truncate text-xs text-muted-foreground">{ev.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{ev.actor_email || 'system'}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {ev.resource_type}
                      {ev.resource_id ? <span className="text-border"> · {ev.resource_id.slice(0, 8)}</span> : ''}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/audit/${ev.id}`}
                        className="text-xs font-medium text-primary hover:underline"
                      >
                        Details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data && data.total > 0 && (
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} event{data.total !== 1 ? 's' : ''} · page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() =>
                  setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE_SIZE) }))
                }
                className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE_SIZE }))}
                className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
