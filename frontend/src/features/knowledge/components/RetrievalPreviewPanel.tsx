/** Shows how an article will be chunked & presented to the AI retrieval layer. */

import { AlertTriangle, FileText } from 'lucide-react';

import { useRetrievalPreview } from '../api';

export function RetrievalPreviewPanel({ articleId }: { articleId: string }) {
  const { data, isLoading, isError } = useRetrievalPreview(articleId);

  if (isLoading) return <p className="text-sm text-muted-foreground">Building retrieval preview…</p>;
  if (isError || !data)
    return <p className="text-sm text-red-600">Could not load retrieval preview.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-2.5 py-1 font-medium text-primary">
          <FileText size={14} /> {data.chunks.length} chunks
        </span>
        <span className="text-muted-foreground">~{data.total_tokens} tokens</span>
        <span className="text-muted-foreground">strategy: {data.chunking_strategy}</span>
        <span className="text-muted-foreground">citation: {data.citation_label}</span>
      </div>

      {data.warnings.length > 0 && (
        <div className="space-y-1">
          {data.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
            >
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        {data.chunks.map((chunk) => (
          <div key={chunk.chunk_index} className="rounded-lg border border-border bg-white">
            <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {chunk.section}
              </span>
              <span className="text-[11px] text-muted-foreground">~{chunk.token_estimate} tok</span>
            </div>
            <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
              {chunk.content}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
