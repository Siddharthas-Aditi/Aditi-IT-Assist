import { BarChart3, Users, Zap, BookOpen } from 'lucide-react';

const stats = [
  { label: 'Total Sessions', value: '142', icon: Users, trend: '+12%' },
  { label: 'Resolution Rate', value: '67%', icon: Zap, trend: '+5%' },
  { label: 'Avg. Confidence', value: '0.78', icon: BarChart3, trend: '+0.03' },
  { label: 'Knowledge Articles', value: '4', icon: BookOpen, trend: '+1' },
];

export function AdminPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Admin Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          System overview and knowledge base management
        </p>
      </div>

      {/* Stats Grid */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-border bg-card p-4"
          >
            <div className="flex items-center justify-between">
              <stat.icon className="h-5 w-5 text-muted-foreground" />
              <span className="text-xs font-medium text-green-600">{stat.trend}</span>
            </div>
            <div className="mt-3">
              <p className="text-2xl font-bold text-foreground">{stat.value}</p>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Knowledge Base Section */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="mb-4 text-lg font-semibold text-foreground">Knowledge Base</h2>
        <div className="space-y-3">
          {[
            { title: 'Outlook Email Issues', category: 'email/outlook', articles: 1 },
            { title: 'Zoom Application', category: 'video-conferencing/zoom', articles: 2 },
            { title: 'Intune Compliance', category: 'device-management/intune', articles: 1 },
            { title: 'Camera Issues', category: 'hardware/camera', articles: 1 },
          ].map((kb) => (
            <div
              key={kb.category}
              className="flex items-center justify-between rounded-lg border border-border p-3"
            >
              <div>
                <p className="text-sm font-medium text-foreground">{kb.title}</p>
                <p className="text-xs text-muted-foreground">{kb.category}</p>
              </div>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                {kb.articles} {kb.articles === 1 ? 'article' : 'articles'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
