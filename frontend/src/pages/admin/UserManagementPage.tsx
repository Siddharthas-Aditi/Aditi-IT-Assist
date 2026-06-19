/** User management — list, search, filter, and navigate to user detail. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Search, UserCog, Users2 } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { EmptyState } from '@/components/ui';
import { useRoles, useUsers } from '@/features/admin/api';
import { RoleBadge, StatusBadge } from '@/features/admin/components/badges';
import { fmtDateTime } from '@/features/admin/utils';
import type { UserFilters } from '@/features/admin/types';

const PAGE_SIZE = 25;

export function UserManagementPage() {
  const [filters, setFilters] = useState<UserFilters>({ limit: PAGE_SIZE, offset: 0 });
  const [searchInput, setSearchInput] = useState('');
  const { data, isLoading, isError, refetch, isFetching } = useUsers(filters);
  const { data: roles } = useRoles();

  const page = Math.floor((filters.offset ?? 0) / PAGE_SIZE) + 1;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters((f) => ({ ...f, search: searchInput.trim() || undefined, offset: 0 }));
  };

  return (
    <>
      <PageHeader
        title="User Management"
        description="Administer users, role assignments, and account status"
        breadcrumbs={[{ label: 'User Management' }]}
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
          <form onSubmit={submitSearch} className="relative min-w-[240px] flex-1">
            <Search size={15} className="absolute left-3 top-2.5 text-muted-foreground" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by name or email…"
              className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </form>
          <select
            value={filters.role ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value || undefined, offset: 0 }))}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All roles</option>
            {roles?.map((r) => (
              <option key={r.name} value={r.name}>
                {r.display_name}
              </option>
            ))}
          </select>
          <select
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                status: (e.target.value as UserFilters['status']) || undefined,
                offset: 0,
              }))
            }
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Suspended</option>
          </select>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="py-16 text-center text-muted-foreground">Loading users…</div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center text-sm text-destructive">
            Failed to load users. Please refresh.
          </div>
        ) : !data || data.users.length === 0 ? (
          <EmptyState
            icon={<Users2 className="h-7 w-7 text-primary" />}
            title="No users found"
            description="No users match the current filters. Try clearing the search or filters."
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">User</th>
                  <th className="px-4 py-2.5 font-medium">Roles</th>
                  <th className="px-4 py-2.5 font-medium">Department</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Last login</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.users.map((u) => (
                  <tr key={u.id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <Link
                        to={`/dashboard/users/${u.id}`}
                        className="font-medium text-foreground hover:text-primary"
                      >
                        {u.full_name}
                      </Link>
                      <p className="text-xs text-muted-foreground">{u.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {u.roles.length ? (
                          u.roles.map((r) => <RoleBadge key={r} role={r} />)
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{u.department || '—'}</td>
                    <td className="px-4 py-3">
                      <StatusBadge active={u.is_active} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDateTime(u.last_login_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/dashboard/users/${u.id}`}
                        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        <UserCog size={13} /> Manage
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
              {data.total} user{data.total !== 1 ? 's' : ''} · page {page} of {totalPages}
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
