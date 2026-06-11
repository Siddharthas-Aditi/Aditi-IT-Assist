/** Indexing status panel + reindex controls. */

import { Database, RefreshCw } from 'lucide-react';
import { useState } from 'react';

import { StatCard } from '@/components/ui';
import { useIndexingStatus, useReindex } from '@/features/knowledge';
import { hasPermission, P } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';

export function KnowledgeIndexingPage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useIndexingStatus();
  const reindex = useReindex();
  const canReindex = hasPermission(user, P.KNOWLEDGE_REINDEX);
  const [result, setResult] = useState<string | null>(null);

  const run = async (onlyStale: boolean) => {
    setResult(null);
    try {
      const r = await reindex.mutateAsync({ only_stale: onlyStale });
      setResult(`Reindexed ${r.reindexed} article(s), ${r.chunks_written} chunks written.`);
    } catch (e) {
      setResult(e instanceof Error ? e.message : 'Reindex failed');
    }
  };

  return (
    <div className="p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Indexing</h1>
          <p className="mt-1 text-sm text-gray-500">
            Monitor the retrieval index and trigger rebuilds
          </p>
        </div>
        {canReindex && (
          <div className="flex gap-2">
            <button
              onClick={() => run(true)}
              disabled={reindex.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              <RefreshCw size={15} /> Reindex stale
            </button>
            <button
              onClick={() => run(false)}
              disabled={reindex.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              <RefreshCw size={15} /> Reindex all published
            </button>
          </div>
        )}
      </div>

      {result && (
        <div className="mb-4 rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
          {result}
        </div>
      )}

      {isLoading || !data ? (
        <div className="py-16 text-center text-muted-foreground">Loading indexing status…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard icon={<Database size={18} />} label="Published" value={String(data.published_articles)} />
            <StatCard icon={<Database size={18} />} label="Indexed" value={String(data.indexed_articles)} />
            <StatCard icon={<Database size={18} />} label="Stale" value={String(data.stale_articles)} />
            <StatCard icon={<Database size={18} />} label="Total chunks" value={String(data.total_chunks)} />
          </div>
          <div className="mt-4 rounded-xl border border-border bg-white p-4 text-sm">
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Vector store</span>
              <span className="font-medium">{data.vector_store}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Index version</span>
              <span className="font-medium">{data.index_version}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Pending</span>
              <span className="font-medium">{data.pending_articles}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Failed</span>
              <span className="font-medium">{data.failed_articles}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Last indexed</span>
              <span className="font-medium">
                {data.last_indexed_at ? new Date(data.last_indexed_at).toLocaleString() : '—'}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
