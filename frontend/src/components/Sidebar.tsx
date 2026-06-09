import { NavLink } from 'react-router-dom';
import {
  MessageSquare,
  Ticket,
  LayoutDashboard,
  Sparkles,
} from 'lucide-react';

const navItems = [
  { to: '/chat', icon: MessageSquare, label: 'Support Chat' },
  { to: '/tickets', icon: Ticket, label: 'Tickets' },
  { to: '/admin', icon: LayoutDashboard, label: 'Dashboard' },
];

export function Sidebar() {
  return (
    <aside className="hidden w-60 flex-col border-r border-border bg-card lg:flex">
      {/* Brand */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-brand shadow-sm">
          <Sparkles className="h-4 w-4 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-foreground tracking-tight">Aditi IT Assist</h1>
          <p className="text-[11px] text-muted-foreground">AI Support Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'gradient-brand-subtle text-primary shadow-sm'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
            SA
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-xs font-medium text-foreground">Siddhartha A.</p>
            <p className="truncate text-[11px] text-muted-foreground">IT Department</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
