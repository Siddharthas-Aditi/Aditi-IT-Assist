/** Side panel showing governance, ownership, and retrieval metadata. */

import type { ArticleDetail } from '@/types/knowledge';
import { ARTICLE_TYPE_LABELS, AUDIENCE_LABELS } from '../constants';
import { StaleArticleWarning } from './StaleArticleWarning';

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value || '—'}</span>
    </div>
  );
}

function fmt(d?: string | null): string {
  return d ? new Date(d).toLocaleDateString() : '—';
}

export function ArticleMetadataPanel({ article }: { article: ArticleDetail }) {
  return (
    <div className="space-y-4">
      {article.is_stale && <StaleArticleWarning dueAt={article.next_review_due_at} />}

      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Classification
        </h3>
        <Row label="Type" value={ARTICLE_TYPE_LABELS[article.article_type]} />
        <Row label="Category" value={article.category} />
        <Row label="Subcategory" value={article.subcategory} />
        <Row label="Product / System" value={article.product_or_system} />
        <Row label="Platform" value={article.platform} />
        <Row label="Audience" value={AUDIENCE_LABELS[article.audience]} />
        <Row label="Visibility" value={article.visibility_scope} />
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Governance
        </h3>
        <Row label="Version" value={`v${article.version}`} />
        <Row label="Quality score" value={article.quality_score?.toFixed(2)} />
        <Row label="Last reviewed" value={fmt(article.last_reviewed_at)} />
        <Row label="Next review due" value={fmt(article.next_review_due_at)} />
        <Row label="Published" value={fmt(article.published_at)} />
        <Row label="Source" value={article.source_type} />
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Retrieval
        </h3>
        <Row label="Citation label" value={article.citation_label} />
        <Row label="Embedding status" value={article.embedding_status} />
        <Row label="Index version" value={article.index_version} />
        <Row label="Indexed at" value={fmt(article.indexed_at)} />
        <Row label="Views" value={article.view_count} />
        <Row label="Used by agent" value={article.usage_count} />
      </div>
    </div>
  );
}
