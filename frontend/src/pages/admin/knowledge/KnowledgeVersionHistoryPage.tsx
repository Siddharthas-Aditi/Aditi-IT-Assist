/** Article version history. */

import { ArrowLeft } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { useVersions } from '@/features/knowledge';

export function KnowledgeVersionHistoryPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError } = useVersions(id);

  return (
    <div className="p-6">
      <Link
        to={`/dashboard/knowledge/${id}`}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={15} /> Back to article
      </Link>
      <h1 className="text-2xl font-bold text-gray-900">Version History</h1>
      <p className="mb-5 mt-1 text-sm text-gray-500">
        Immutable snapshots captured at each governance transition
      </p>

      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">Loading versions…</div>
      ) : isError ? (
        <div className="py-16 text-center text-red-600">Failed to load versions.</div>
      ) : !data || data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No version snapshots yet. Versions are created on publish, archive, and revision.
        </p>
      ) : (
        <ol className="relative space-y-4 border-l border-border pl-5">
          {data.map((v) => (
            <li key={v.id} className="relative">
              <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full bg-primary" />
              <div className="rounded-lg border border-border bg-white p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground">
                    v{v.version} · {v.title}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(v.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Status: {v.status}
                  {v.change_summary ? ` — ${v.change_summary}` : ''}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
