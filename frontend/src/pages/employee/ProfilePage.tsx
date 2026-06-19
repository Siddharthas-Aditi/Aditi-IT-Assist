/** Profile page — employee can view their profile basics. */

import { useAuthStore } from '@/stores/auth-store';

function titleCase(role: string): string {
  return role
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ProfilePage() {
  const { user } = useAuthStore();
  const roles = user?.roles?.length ? user.roles : user?.role ? [user.role] : [];

  return (
    <div className="max-w-2xl p-6">
      <h1 className="mb-6 text-2xl font-bold text-foreground">My Profile</h1>

      <div className="space-y-4 rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-4 border-b border-border pb-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
            {user?.full_name?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">{user?.full_name}</h2>
            <p className="text-sm text-muted-foreground">{user?.email}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Employee ID" value={user?.employee_id || 'N/A'} />
          <Field label="Department" value={user?.department || 'N/A'} />
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {roles.length > 1 ? 'Roles' : 'Role'}
            </label>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {roles.length ? (
                roles.map((r) => (
                  <span
                    key={r}
                    className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                  >
                    {titleCase(r)}
                  </span>
                ))
              ) : (
                <span className="text-sm text-foreground">—</span>
              )}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Status
            </label>
            <p className="mt-1 text-sm font-medium text-[hsl(var(--success))]">Active</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      <p className="mt-1 text-sm text-foreground">{value}</p>
    </div>
  );
}
