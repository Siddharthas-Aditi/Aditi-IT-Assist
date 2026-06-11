/** Knowledge analytics — corpus health and content effectiveness. */

import { BarChart3, BookOpen, ThumbsDown, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';

import { StatCard } from '@/components/ui';
import { useKnowledgeAnalytics } from '@/features/knowledge';
import type { ArticleAnalytics } from '@/types/knowledge';

function Table({ title, rows }: { title: string; rows: ArticleAnalytics[] }) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold text-foreground">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No data.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">Article</th>
              <th className="py-1 font-medium">Used</th>
              <th className="py-1 font-medium">Resolution</th>
              <th className="py-1 font-medium">Feedback</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => (
              <tr key={r.article_id}>
                <td className="py-1.5">
                  <Link
                    to={`/dashboard/knowledge/${r.article_id}`}
                    className="text-foreground hover:text-primary"
                  >
                    {r.title}
                  </Link>
                </td>
                <td className="py-1.5 text-muted-foreground">{r.usage_count}</td>
                <td className="py-1.5 text-muted-foreground">
                  {r.resolution_rate != null ? `${Math.round(r.resolution_rate * 100)}%` : '—'}
                </td>
                <td className="py-1.5 text-muted-foreground">
                  {r.feedback_score != null ? r.feedback_score.toFixed(2) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function KnowledgeAnalyticsPage() {
  const { data, isLoading, isError } = useKnowledgeAnalytics();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900">Knowledge Analytics</h1>
      <p className="mb-5 mt-1 text-sm text-gray-500">
        Corpus health and content effectiveness across the knowledge base
      </p>

      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">Loading analytics…</div>
      ) : isError || !data ? (
        <div className="py-16 text-center text-red-600">Failed to load analytics.</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard icon={<BookOpen size={18} />} label="Total articles" value={String(data.total_articles)} />
            <StatCard icon={<TrendingUp size={18} />} label="Published" value={String(data.published_articles)} />
            <StatCard icon={<BarChart3 size={18} />} label="Total agent uses" value={String(data.total_usage)} />
            <StatCard icon={<ThumbsDown size={18} />} label="Stale" value={String(data.stale_articles)} />
          </div>

          <div className="mt-4 rounded-xl border border-border bg-white p-4 text-sm">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Avg quality</p>
                <p className="text-lg font-semibold">
                  {data.avg_quality_score != null ? data.avg_quality_score.toFixed(2) : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Avg resolution rate</p>
                <p className="text-lg font-semibold">
                  {data.avg_resolution_rate != null
                    ? `${Math.round(data.avg_resolution_rate * 100)}%`
                    : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total views</p>
                <p className="text-lg font-semibold">{data.total_views}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">In review</p>
                <p className="text-lg font-semibold">{data.by_status.in_review ?? 0}</p>
              </div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Table title="Top performing" rows={data.top_articles} />
            <Table title="Needs attention" rows={data.low_performers} />
          </div>
        </>
      )}
    </div>
  );
}
