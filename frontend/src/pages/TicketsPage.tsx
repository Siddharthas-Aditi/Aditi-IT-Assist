import { Clock, CheckCircle, AlertTriangle, ArrowUpRight, Inbox } from 'lucide-react';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';

const mockTickets = [
  {
    id: 'TKT-001',
    title: 'Outlook not receiving emails',
    status: 'open',
    priority: 'high',
    category: 'email/outlook',
    createdAt: '2024-01-15T10:30:00Z',
    description: 'Email sync stopped working after password change',
  },
  {
    id: 'TKT-002',
    title: 'Intune compliance issue after travel',
    status: 'in_progress',
    priority: 'medium',
    category: 'device-management/intune',
    createdAt: '2024-01-14T14:00:00Z',
    description: 'Laptop shows non-compliant after returning from overseas',
  },
  {
    id: 'TKT-003',
    title: 'Zoom audio not working in meetings',
    status: 'resolved',
    priority: 'low',
    category: 'video-conferencing/zoom',
    createdAt: '2024-01-13T09:15:00Z',
    description: 'Others cannot hear me during Zoom meetings',
  },
];

const statusConfig = {
  open: { icon: AlertTriangle, color: 'warning' as const, label: 'Open' },
  in_progress: { icon: Clock, color: 'primary' as const, label: 'In Progress' },
  resolved: { icon: CheckCircle, color: 'success' as const, label: 'Resolved' },
};

const priorityConfig = {
  low: 'default' as const,
  medium: 'warning' as const,
  high: 'destructive' as const,
  critical: 'destructive' as const,
};

export function TicketsPage() {
  const hasTickets = mockTickets.length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Support Tickets</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Track escalated issues and their resolution status
          </p>
        </div>
        {hasTickets && (
          <div className="flex items-center gap-3">
            {/* Status pipeline */}
            <div className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5">
              <div className="flex items-center gap-1 text-xs">
                <span className="h-2 w-2 rounded-full bg-amber-400" />
                <span className="text-muted-foreground">1 open</span>
              </div>
              <span className="text-border">·</span>
              <div className="flex items-center gap-1 text-xs">
                <span className="h-2 w-2 rounded-full bg-blue-400" />
                <span className="text-muted-foreground">1 in progress</span>
              </div>
              <span className="text-border">·</span>
              <div className="flex items-center gap-1 text-xs">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="text-muted-foreground">1 resolved</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Tickets list */}
      {hasTickets ? (
        <div className="space-y-3">
          {mockTickets.map((ticket, idx) => {
            const status = statusConfig[ticket.status as keyof typeof statusConfig];
            const StatusIcon = status?.icon || Clock;
            const priorityVariant = priorityConfig[ticket.priority as keyof typeof priorityConfig];

            return (
              <div
                key={ticket.id}
                className="group rounded-xl border border-border bg-card p-4 transition-all duration-200 hover:shadow-md hover:border-primary/20 hover:-translate-y-0.5 animate-slide-up cursor-pointer"
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/5">
                      <StatusIcon className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                          {ticket.title}
                        </h3>
                        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                        {ticket.description}
                      </p>
                      <div className="mt-2 flex items-center gap-2">
                        <Badge variant={status?.color}>{status?.label}</Badge>
                        <Badge variant={priorityVariant}>{ticket.priority}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {ticket.id} · {ticket.category}
                        </span>
                      </div>
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {new Date(ticket.createdAt).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={<Inbox className="h-7 w-7 text-primary" />}
          title="No tickets yet"
          description="When issues are escalated by the AI support agent, they'll appear here as trackable tickets."
        />
      )}
    </div>
  );
}
