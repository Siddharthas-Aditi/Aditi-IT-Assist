/**
 * FeedbackReviewPage
 *
 * Admin / IT-lead review queue for flagged post-chat feedback.
 * Shows feedback records where review_flag=true (rating ≤ 2, unresolved,
 * or explicitly marked as not helpful).
 *
 * Route: /dashboard/feedback/review
 * Access: it_lead, it_admin
 */

import { useState } from 'react';

import { useFeedbackReviewQueue } from '@/features/chat/feedbackApi';
import type { ConversationFeedback } from '@/types/feedback';

const PAGE_SIZE = 20;

function QualityBadge({ bucket }: { bucket: string | null }) {
  if (!bucket) return null;
  const map: Record<string, { label: string; cls: string }> = {
    positive: { label: 'Positive', cls: 'bg-green-100 text-green-700' },
    neutral: { label: 'Neutral', cls: 'bg-yellow-100 text-yellow-700' },
    negative: { label: 'Negative', cls: 'bg-red-100 text-red-700' },
  };
  const entry = map[bucket] ?? { label: bucket, cls: 'bg-slate-100 text-slate-600' };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${entry.cls}`}>
      {entry.label}
    </span>
  );
}

function StarRating({ rating }: { rating: number | null }) {
  if (!rating) return <span className="text-xs text-slate-400">No rating</span>;
  return (
    <span className="text-sm" aria-label={`${rating} out of 5 stars`}>
      {'⭐'.repeat(rating)}{'☆'.repeat(5 - rating)}
    </span>
  );
}

function FeedbackRow({ item }: { item: ConversationFeedback }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          {/* Header row */}
          <div className="flex flex-wrap items-center gap-2">
            <QualityBadge bucket={item.quality_bucket} />
            {item.review_flag && (
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">
                🚩 Flagged
              </span>
            )}
            <span className="text-xs text-slate-400">
              {new Date(item.submitted_at).toLocaleString()}
            </span>
          </div>

          {/* Category + mode */}
          <div className="flex flex-wrap gap-3 text-xs text-slate-500">
            {item.category && <span>📂 {item.category}{item.subcategory ? ` / ${item.subcategory}` : ''}</span>}
            <span>🤖 {item.support_mode.replace(/_/g, ' ')}</span>
            {item.escalation_occurred && <span>⬆️ Escalated</span>}
          </div>

          {/* Survey signals */}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <span className={item.helpful === true ? 'text-green-600' : item.helpful === false ? 'text-red-500' : 'text-slate-400'}>
              {item.helpful === true ? '👍 Helpful' : item.helpful === false ? '👎 Not helpful' : 'Helpfulness: —'}
            </span>
            <span className={item.resolved === true ? 'text-green-600' : item.resolved === false ? 'text-orange-500' : 'text-slate-400'}>
              {item.resolved === true ? '✅ Resolved' : item.resolved === false ? '⚠️ Unresolved' : 'Resolution: —'}
            </span>
            <StarRating rating={item.rating} />
          </div>

          {/* Flag reason */}
          {item.review_flag_reason && (
            <p className="text-xs text-red-500">Reason: {item.review_flag_reason}</p>
          )}
        </div>

        {/* Expand toggle */}
        {item.comment && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 text-xs text-blue-500 hover:text-blue-700"
          >
            {expanded ? 'Hide comment' : 'View comment'}
          </button>
        )}
      </div>

      {expanded && item.comment && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-700">
          "{item.comment}"
        </div>
      )}

      {/* Links */}
      <div className="mt-3 flex gap-3 text-xs">
        <a
          href={`/operations/tickets?session=${item.conversation_id}`}
          className="text-blue-500 hover:underline"
        >
          View session →
        </a>
        {item.ticket_id && (
          <a
            href={`/operations/tickets/${item.ticket_id}`}
            className="text-blue-500 hover:underline"
          >
            View ticket →
          </a>
        )}
      </div>
    </div>
  );
}

export function FeedbackReviewPage() {
  const [page, setPage] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState('');

  const { data, isLoading, isError } = useFeedbackReviewQueue({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    category: categoryFilter || undefined,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Feedback Review Queue</h1>
        <p className="mt-1 text-sm text-slate-500">
          Flagged feedback records requiring review (low ratings, unresolved issues).
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-slate-600">Category:</label>
        <input
          type="text"
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(0); }}
          placeholder="Filter by category…"
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:outline-none
                     focus:ring-2 focus:ring-blue-400"
        />
        {categoryFilter && (
          <button
            onClick={() => setCategoryFilter('')}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* Stats bar */}
      {data && (
        <p className="text-sm text-slate-500">
          {data.total} flagged record{data.total !== 1 ? 's' : ''} total
          {categoryFilter ? ` in "${categoryFilter}"` : ''}
        </p>
      )}

      {/* Content */}
      {isLoading && (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg bg-slate-100" />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-600">
          Failed to load feedback. Please refresh.
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-8 text-center">
          <p className="text-slate-500">🎉 No flagged feedback to review.</p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="space-y-3">
          {data.items.map((item) => (
            <FeedbackRow key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-sm text-slate-500">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
