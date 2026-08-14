/** IT Operations layout for agents, leads, admins — brand-consistent shell. */

import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import {
  Inbox,
  ClipboardList,
  Monitor,
  LayoutDashboard,
  LogOut,
  Headset,
  ArrowLeft,
  ShieldCheck,
  Cpu,
  Boxes,
} from 'lucide-react';

import { useAuthStore } from '@/stores/auth-store';

const NAV = [
  { to: '/operations/queue', label: 'Live Queue', icon: Inbox },
  { to: '/operations/assigned', label: 'My Assigned', icon: ClipboardList },
  { to: '/operations/remote-assist', label: 'Remote Assist', icon: Monitor },
  { to: '/operations/device-actions', label: 'Device Actions', icon: Cpu },
  { to: '/operations/approvals', label: 'Approvals', icon: ShieldCheck },
];

export function OperationsLayout() {
  const location = useLocation();
  const { user, logout, isAdmin } = useAuthStore();

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))]">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--accent))]/15 text-[hsl(var(--accent))]">
            <Headset size={20} />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-tight">Aditi IT Assist</h1>
            <p className="text-[11px] text-white/55">IT Operations</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-white/10 font-medium text-white ring-1 ring-white/10'
                    : 'text-white/70 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Cross-workspace links (legitimate multi-role navigation) */}
        <div className="space-y-0.5 px-3 pb-2">
          {/* Both targets sit behind AdminRoute (it_lead + it_admin), which is
              exactly what isAdmin() reports — so neither link can bounce an
              agent to /unauthorized. */}
          {isAdmin() && (
            <>
              <NavLink
                to="/itsm/changes"
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-white/60 transition-colors hover:bg-white/5 hover:text-white"
              >
                <Boxes size={14} /> Changes &amp; Assets
              </NavLink>
              <NavLink
                to="/dashboard"
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-white/60 transition-colors hover:bg-white/5 hover:text-white"
              >
                <LayoutDashboard size={14} /> Admin Console
              </NavLink>
            </>
          )}
          <NavLink
            to="/support"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-white/60 transition-colors hover:bg-white/5 hover:text-white"
          >
            <ArrowLeft size={14} /> Employee View
          </NavLink>
        </div>

        {/* Account footer */}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2.5 px-2">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--accent))]/20 text-xs font-semibold text-[hsl(var(--accent))]">
              {user?.full_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
              <p className="truncate text-[11px] capitalize text-white/55">
                {user?.role?.replace(/_/g, ' ')}
              </p>
            </div>
            <button
              onClick={() => logout()}
              className="rounded p-1 text-white/50 transition-colors hover:text-red-300"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-auto">
        <ErrorBoundary key={location.pathname} boundaryName="operations">
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
