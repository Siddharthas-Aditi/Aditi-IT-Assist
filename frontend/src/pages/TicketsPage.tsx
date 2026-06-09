import { Ticket, Clock, CheckCircle, AlertTriangle } from 'lucide-react';

const mockTickets = [
  {
    id: 'TKT-001',
    title: 'Outlook not receiving emails',
    status: 'open',
    priority: 'high',
    category: 'email/outlook',
    createdAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 'TKT-002',
    title: 'Intune compliance issue after travel',
    status: 'in_progress',
    priority: 'medium',
    category: 'device-management/intune',
    createdAt: '2024-01-14T14:00:00Z',
  },
  {
    id: 'TKT-003',
    title: 'Zoom audio not working in meetings',
    status: 'resolved',
    priority: 'low',
    category: 'video-conferencing/zoom',
    createdAt: '2024-01-13T09:15:00Z',
  },
];

const statusIcons = {
  open: AlertTriangle,
  in_progress: Clock,
  resolved: CheckCircle,
};

const statusColors = {
  open: 'text-orange-500 bg-orange-50',
  in_progress: 'text-blue-500 bg-blue-50',
  resolved: 'text-green-500 bg-green-50',
};

const priorityColors = {
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-yellow-100 text-yellow-700',
  high: 'bg-red-100 text-red-700',
  critical: 'bg-red-200 text-red-900',
};

export function TicketsPage() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Support Tickets</h1>
          <p className="text-sm text-muted-foreground">
            Track your escalated issues and their resolution status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Ticket className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{mockTickets.length} tickets</span>
        </div>
      </div>

      <div className="space-y-3">
        {mockTickets.map((ticket) => {
          const StatusIcon = statusIcons[ticket.status as keyof typeof statusIcons] || Clock;
          const statusColor = statusColors[ticket.status as keyof typeof statusColors] || '';
          const priorityColor = priorityColors[ticket.priority as keyof typeof priorityColors] || '';

          return (
            <div
              key={ticket.id}
              className="rounded-lg border border-border bg-card p-4 transition-colors hover:bg-accent/50"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`rounded-full p-1.5 ${statusColor}`}>
                    <StatusIcon className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">{ticket.title}</h3>
                    <p className="text-xs text-muted-foreground">
                      {ticket.id} • {ticket.category}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${priorityColor}`}>
                    {ticket.priority}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(ticket.createdAt).toLocaleDateString()}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {mockTickets.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Ticket className="h-12 w-12 text-muted-foreground/50" />
          <h3 className="mt-4 text-lg font-medium text-foreground">No tickets yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            When issues are escalated, they'll appear here as tickets.
          </p>
        </div>
      )}
    </div>
  );
}
