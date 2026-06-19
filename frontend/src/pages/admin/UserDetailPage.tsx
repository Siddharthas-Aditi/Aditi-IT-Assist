/** User detail — profile, role assignments, and activation controls. */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Mail, Building2, BadgeCheck, Plus, X, Power } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import {
  useAssignRole,
  useRevokeRole,
  useRoles,
  useUpdateUser,
  useUser,
} from '@/features/admin/api';
import { RoleBadge, StatusBadge } from '@/features/admin/components/badges';
import { fmtDateTime, roleLabel } from '@/features/admin/utils';
import { hasPermission, P } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, isError } = useUser(id);
  const { data: roles } = useRoles();

  const canManage = hasPermission(user, P.ADMIN_MANAGE_USERS);
  const canAssignRoles = hasPermission(user, P.ADMIN_ASSIGN_ROLES);
  const isSelf = Boolean(user && data && user.id === data.id);

  const updateUser = useUpdateUser(id ?? '');
  const assignRole = useAssignRole(id ?? '');
  const revokeRole = useRevokeRole(id ?? '');

  const [roleToAdd, setRoleToAdd] = useState('');
  const [error, setError] = useState<string | null>(null);

  const breadcrumbs = [
    { label: 'User Management', to: '/dashboard/users' },
    { label: data?.full_name ?? 'User' },
  ];

  if (isLoading) {
    return (
      <>
        <PageHeader title="User" breadcrumbs={breadcrumbs} />
        <div className="p-6 text-muted-foreground">Loading user…</div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="User" breadcrumbs={breadcrumbs} />
        <div className="p-6 text-destructive">User not found.</div>
      </>
    );
  }

  const assignedRoleNames = new Set(data.role_assignments.map((a) => a.role));
  const availableRoles = (roles ?? []).filter((r) => !assignedRoleNames.has(r.name));

  const runAction = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    }
  };

  return (
    <>
      <PageHeader
        title={data.full_name}
        description={data.email}
        breadcrumbs={breadcrumbs}
        actions={
          canManage && !isSelf ? (
            <button
              type="button"
              disabled={updateUser.isPending}
              onClick={() => runAction(() => updateUser.mutateAsync({ is_active: !data.is_active }))}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                data.is_active
                  ? 'border border-destructive/40 text-destructive hover:bg-destructive/10'
                  : 'bg-[hsl(var(--success))] text-white hover:opacity-90'
              }`}
            >
              <Power size={14} /> {data.is_active ? 'Suspend account' : 'Reactivate account'}
            </button>
          ) : canManage && isSelf ? (
            <span className="text-xs text-muted-foreground">This is your account</span>
          ) : undefined
        }
      />

      <div className="grid gap-6 p-6 lg:grid-cols-3">
        {error && (
          <div className="lg:col-span-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Profile */}
        <Card className="lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Profile
          </h2>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Field icon={<Mail size={15} />} label="Email" value={data.email} />
            <Field
              icon={<BadgeCheck size={15} />}
              label="Status"
              value={<StatusBadge active={data.is_active} />}
            />
            <Field icon={<Building2 size={15} />} label="Department" value={data.department || '—'} />
            <Field label="Job title" value={data.job_title || '—'} />
            <Field label="Employee ID" value={data.employee_id || '—'} />
            <Field label="Verified" value={data.is_verified ? 'Yes' : 'No'} />
            <Field label="Last login" value={fmtDateTime(data.last_login_at)} />
            <Field label="Created" value={fmtDateTime(data.created_at)} />
          </dl>
        </Card>

        {/* Roles */}
        <Card>
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Roles &amp; access
          </h2>
          <div className="space-y-2">
            {data.role_assignments.length === 0 && (
              <p className="text-sm text-muted-foreground">No roles assigned.</p>
            )}
            {data.role_assignments.map((a) => (
              <div
                key={a.role}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
              >
                <div>
                  <RoleBadge role={a.role} />
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Since {fmtDateTime(a.assigned_at)}
                  </p>
                </div>
                {canAssignRoles && (
                  <button
                    type="button"
                    title={`Revoke ${roleLabel(a.role)}`}
                    disabled={revokeRole.isPending || data.role_assignments.length <= 1}
                    onClick={() => runAction(() => revokeRole.mutateAsync(a.role))}
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                  >
                    <X size={15} />
                  </button>
                )}
              </div>
            ))}
          </div>

          {canAssignRoles && availableRoles.length > 0 && (
            <div className="mt-4 flex gap-2 border-t border-border pt-4">
              <select
                value={roleToAdd}
                onChange={(e) => setRoleToAdd(e.target.value)}
                className="flex-1 rounded-lg border border-border bg-card px-2 py-1.5 text-sm outline-none focus:border-primary"
              >
                <option value="">Add role…</option>
                {availableRoles.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.display_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!roleToAdd || assignRole.isPending}
                onClick={() =>
                  runAction(async () => {
                    await assignRole.mutateAsync(roleToAdd);
                    setRoleToAdd('');
                  })
                }
                className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-40"
              >
                <Plus size={14} /> Add
              </button>
            </div>
          )}
          {!canAssignRoles && (
            <p className="mt-3 text-xs text-muted-foreground">
              You don&apos;t have permission to change role assignments.
            </p>
          )}
        </Card>
      </div>
    </>
  );
}

function Field({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-sm text-foreground">{value}</dd>
    </div>
  );
}
