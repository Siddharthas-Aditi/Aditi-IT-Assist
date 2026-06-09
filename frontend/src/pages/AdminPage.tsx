import { Users, Zap, BookOpen, Activity, Clock, TrendingUp } from 'lucide-react';
import { StatCard } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

const stats = [
  { label: 'Total Sessions', value: '142', icon: <Users className="h-5 w-5" />, trend: '12%', trendUp: true },
  { label: 'Resolution Rate', value: '67%', icon: <Zap className="h-5 w-5" />, trend: '5%', trendUp: true },
  { label: 'Avg. Confidence', value: '0.78', icon: <TrendingUp className="h-5 w-5" />, trend: '0.03', trendUp: true },
  { label: 'Knowledge Articles', value: '4', icon: <BookOpen className="h-5 w-5" />, trend: '1', trendUp: true },
];

const recentActivity = [
  { id: 1, action: 'Issue resolved', detail: 'Outlook sync — email/outlook', time: '2 min ago', type: 'success' as const },
  { id: 2, action: 'Ticket escalated', detail: 'Intune compliance — TKT-004', time: '15 min ago', type: 'warning' as const },
  { id: 3, action: 'New session', detail: 'Camera issue reported', time: '32 min ago', type: 'default' as const },
  { id: 4, action: 'Issue resolved', detail: 'Zoom audio fix applied', time: '1 hr ago', type: 'success' as const },
  { id: 5, action: 'Knowledge gap', detail: 'VPN connectivity — no articles found', time: '2 hr ago', type: 'destructive' as const },
];

const knowledgeCategories = [
  { title: 'Outlook Email Issues', category: 'email/outlook', articles: 1, resolutionRate: 82 },
  { title: 'Zoom Application', category: 'video-conferencing/zoom', articles: 2, resolutionRate: 71 },
  { title: 'Intune Compliance', category: 'device-management/intune', articles: 1, resolutionRate: 65 },
  { title: 'Camera Issues', category: 'hardware/camera', articles: 1, resolutionRate: 88 },
];

export function AdminPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            System overview and knowledge base performance
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
          <Activity className="h-3.5 w-3.5" />
          All systems operational
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard
            key={stat.label}
            icon={stat.icon}
            label={stat.label}
            value={stat.value}
            trend={stat.trend}
            trendUp={stat.trendUp}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Recent Activity */}
        <div className="lg:col-span-3 rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-foreground">Recent Activity</h2>
            <Badge variant="outline">Live</Badge>
          </div>
          <div className="space-y-3">
            {recentActivity.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-lg border border-border/50 p-3 transition-colors hover:bg-accent/30 animate-slide-right"
                style={{ animationDelay: `${item.id * 60}ms` }}
              >
                <div className="flex items-center gap-3">
                  <Badge variant={item.type}>{item.action}</Badge>
                  <span className="text-sm text-foreground">{item.detail}</span>
                </div>
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {item.time}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Knowledge Base */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-foreground">Knowledge Base</h2>
            <span className="text-xs text-muted-foreground">4 categories</span>
          </div>
          <div className="space-y-3">
            {knowledgeCategories.map((kb) => (
              <div
                key={kb.category}
                className="rounded-lg border border-border/50 p-3 transition-all hover:shadow-sm hover:border-primary/20"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">{kb.title}</p>
                    <p className="text-xs text-muted-foreground">{kb.category}</p>
                  </div>
                  <Badge variant="primary">
                    {kb.articles} {kb.articles === 1 ? 'article' : 'articles'}
                  </Badge>
                </div>
                {/* Resolution rate bar */}
                <div className="mt-2.5">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Resolution rate</span>
                    <span className="font-medium text-foreground">{kb.resolutionRate}%</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-secondary">
                    <div
                      className="h-1.5 rounded-full gradient-brand transition-all duration-500"
                      style={{ width: `${kb.resolutionRate}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
