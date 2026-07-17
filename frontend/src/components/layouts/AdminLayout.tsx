/**
 * Admin / IT-Lead console layout.
 *
 * Admin-focused shell: a single, stable navigation rail (no cross-workspace
 * profile switching) and a clean enterprise account summary in the footer.
 * Branding uses the Aditi sidebar token (dark blue) for theme consistency.
 */

import { useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import {
  BarChart3,
  BookOpen,
  Shield,
  Users2,
  UserCog,
  LogOut,
  ChevronDown,
  LifeBuoy,
  Bot,
} from 'lucide-react';

import { useAuthStore } from '@/stores/auth-store';
import { hasPermission, isLeadOrAbove, P, type UserRole } from '@/lib/permissions';
import type { AuthUser } from '@/types/auth';

const ROLE_LABELS: Record<UserRole, string> = {
  employee: 'Employee',
  it_agent: 'IT Agent',
  it_lead: 'IT Lead',
  it_admin: 'IT Admin',
  security_auditor: 'Security Auditor',
};

interface NavItem {
  to: string;
  label: string;
  icon: typeof BarChart3;
  end?: boolean;
  /** Whether this user may see (and reach) the item — mirrors route guards. */
  can: (user: AuthUser | null) => boolean;
}

// Gating mirrors the route guards so a user never sees a link that would bounce
// to /unauthorized: /dashboard/* is it_lead+; /dashboard/users is it_admin only
// (admin:manage_users); /audit is it_admin + security_auditor (admin:view_audit_log).
const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Analytics', icon: BarChart3, end: true, can: isLeadOrAbove },
  { to: '/dashboard/team-queue', label: 'Team Queue', icon: Users2, can: isLeadOrAbove },
  { to: '/dashboard/knowledge', label: 'Knowledge Base', icon: BookOpen, can: isLeadOrAbove },
  {
    to: '/dashboard/users',
    label: 'User Management',
    icon: UserCog,
    can: (u) => hasPermission(u, P.ADMIN_MANAGE_USERS),
  },
  {
    to: '/audit',
    label: 'Audit Logs',
    icon: Shield,
    can: (u) => hasPermission(u, P.ADMIN_VIEW_AUDIT_LOG),
  },
  { to: '/dashboard/agent-ops', label: 'Agent Operations', icon: Bot, can: isLeadOrAbove },
];

export function AdminLayout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const initials = (user?.full_name || '?')
    .split(' ')
    .map((p) => p.charAt(0))
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const roleLabel = user?.role ? ROLE_LABELS[user.role] ?? user.role : '';

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))]">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--accent))]/15 text-[hsl(var(--accent))]">
            <LifeBuoy size={20} />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-tight">Aditi IT Assist</h1>
            <p className="text-[11px] text-white/55">Admin Console</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2">
          <p className="px-3 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-wider text-white/40">
            Operations
          </p>
          {NAV.filter((i) => i.can(user)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-white/10 font-medium text-white shadow-sm ring-1 ring-white/10'
                    : 'text-white/70 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Account summary */}
        <div className="relative border-t border-white/10 p-3">
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-white/5"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--accent))]/20 text-xs font-semibold text-[hsl(var(--accent))]">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
              <p className="truncate text-[11px] text-white/55">{user?.email}</p>
            </div>
            <ChevronDown
              size={16}
              className={`shrink-0 text-white/50 transition-transform ${menuOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {menuOpen && (
            <div className="absolute bottom-[4.25rem] left-3 right-3 overflow-hidden rounded-lg border border-white/10 bg-[hsl(var(--sidebar))] shadow-xl">
              <div className="border-b border-white/10 px-3 py-2.5">
                <p className="text-[11px] uppercase tracking-wide text-white/40">Signed in as</p>
                <p className="mt-0.5 truncate text-sm text-white">{user?.full_name}</p>
                {roleLabel && (
                  <span className="mt-1 inline-flex rounded-full bg-[hsl(var(--accent))]/15 px-2 py-0.5 text-[11px] font-medium text-[hsl(var(--accent))]">
                    {roleLabel}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  navigate('/support/profile');
                }}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-white/80 transition-colors hover:bg-white/5"
              >
                <UserCog size={15} /> Profile &amp; settings
              </button>
              <button
                type="button"
                onClick={() => logout()}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-red-300 transition-colors hover:bg-red-500/10"
              >
                <LogOut size={15} /> Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-auto">
        <ErrorBoundary key={location.pathname} boundaryName="admin">
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
