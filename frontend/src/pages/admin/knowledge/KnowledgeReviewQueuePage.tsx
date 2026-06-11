/** Review queue — articles awaiting reviewer action (in_review). */

import { ListChecks } from 'lucide-react';
import { Link } from 'react-router-dom';

import { EmptyState } from '@/components/ui';
import { ArticleStatusBadge, useReviewQueue } from '@/features/knowledge';

export function KnowledgeReviewQueuePage() {
  const { data, isLoading, isError } = useReviewQueue();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
      <p className="mb-5 mt-1 text-sm text-gray-500">
        Articles submitted for review, awaiting approval or change requests
      </p>

      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">Loading queue…</div>
      ) : isError ? (
        <div className="py-16 text-center text-red-600">Failed to load review queue.</div>
      ) : !data || data.length === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-7 w-7 text-primary" />}
          title="Queue is empty"
          description="No articles are currently awaiting review."
        />
      ) : (
        <div className="space-y-2">
          {data.map((a) => (
            <Link
              key={a.id}
              to={`/dashboard/knowledge/${a.id}`}
              className="flex items-center justify-between rounded-lg border border-border bg-white px-4 py-3 hover:border-primary/30"
            >
              <div>
                <p className="font-medium text-foreground">{a.title}</p>
                <p className="text-xs text-muted-foreground">
                  {a.category} · v{a.version} · updated{' '}
                  {a.updated_at ? new Date(a.updated_at).toLocaleDateString() : '—'}
                </p>
              </div>
              <ArticleStatusBadge status={a.status} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
