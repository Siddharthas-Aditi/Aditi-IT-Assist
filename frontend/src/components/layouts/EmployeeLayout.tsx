/** Employee workspace layout — brand-consistent sidebar navigation. */

import { Outlet, NavLink } from 'react-router-dom';
import { MessageSquare, Ticket, User, LogOut, LifeBuoy, ArrowRight } from 'lucide-react';

import { useAuthStore } from '@/stores/auth-store';

const NAV = [
  { to: '/support/chat', label: 'Support Chat', icon: MessageSquare },
  { to: '/support/tickets', label: 'My Tickets', icon: Ticket },
  { to: '/support/profile', label: 'Profile', icon: User },
];

export function EmployeeLayout() {
  const { user, logout, isITStaff } = useAuthStore();

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
            <p className="text-[11px] text-white/55">Employee Support</p>
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

        {/* Cross-workspace link for IT staff (legitimate multi-role navigation) */}
        {isITStaff() && (
          <div className="px-3 pb-2">
            <NavLink
              to="/operations"
              className="flex items-center justify-between rounded-lg px-3 py-2 text-xs text-white/60 transition-colors hover:bg-white/5 hover:text-white"
            >
              Switch to Operations
              <ArrowRight size={14} />
            </NavLink>
          </div>
        )}

        {/* Account footer */}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2.5 px-2">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--accent))]/20 text-xs font-semibold text-[hsl(var(--accent))]">
              {user?.full_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
              <p className="truncate text-[11px] text-white/55">{user?.email}</p>
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
        <Outlet />
      </main>
    </div>
  );
}
