import { NavLink } from 'react-router-dom';
import {
  MessageSquare,
  Ticket,
  Settings,
  BookOpen,
  LayoutDashboard,
} from 'lucide-react';

const navItems = [
  { to: '/chat', icon: MessageSquare, label: 'Support Chat' },
  { to: '/tickets', icon: Ticket, label: 'Tickets' },
  { to: '/admin', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/admin', icon: BookOpen, label: 'Knowledge Base' },
  { to: '/admin', icon: Settings, label: 'Settings' },
];

export function Sidebar() {
  return (
    <aside className="hidden w-64 border-r border-border bg-card lg:block">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <span className="text-sm font-bold text-primary-foreground">A</span>
        </div>
        <div>
          <h1 className="text-sm font-semibold text-foreground">Aditi IT Assist</h1>
          <p className="text-xs text-muted-foreground">AI Support Platform</p>
        </div>
      </div>
      <nav className="space-y-1 p-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to + item.label}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
