import { AlertCircle, AlertTriangle, ArrowUpRight, CheckCircle2, Tag, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { IngestionCandidateSummary } from '@/types/ingestion';
import { ConfidenceBadge } from './ConfidenceBadge';

interface Props {
  candidate: IngestionCandidateSummary;
  jobId: string;
  selected?: boolean;
  onSelect?: (id: string, checked: boolean) => void;
}

const REVIEW_ICON = {
  pending: <AlertCircle className="h-4 w-4 text-yellow-500" />,
  approved: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  rejected: <XCircle className="h-4 w-4 text-red-500" />,
  saved: <CheckCircle2 className="h-4 w-4 text-indigo-500" />,
} as const;

export function CandidateCard({ candidate, jobId, selected = false, onSelect }: Props) {
  return (
    <div
      className={[
        'rounded-lg border p-4 transition-colors',
        selected
          ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-600 dark:bg-indigo-950/30'
          : 'border-gray-200 bg-white hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900',
      ].join(' ')}
    >
      <div className="flex items-start gap-3">
        {onSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => onSelect(candidate.id, e.target.checked)}
            className="mt-1 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            disabled={candidate.review_status === 'saved' || candidate.review_status === 'rejected'}
          />
        )}

        <div className="min-w-0 flex-1">
          {/* Header */}
          <div className="flex items-center gap-2">
            {REVIEW_ICON[candidate.review_status]}
            <Link
              to={
                candidate.mapped_article_id
                  ? `/dashboard/knowledge/${candidate.mapped_article_id}`
                  : `/dashboard/knowledge/ingest/${jobId}/${candidate.id}`
              }
              className="truncate text-sm font-semibold text-gray-900 hover:text-indigo-600 dark:text-gray-100 dark:hover:text-indigo-400"
            >
              {candidate.extracted_title ?? `Candidate #${candidate.candidate_index + 1}`}
            </Link>
          </div>

          {/* Meta row */}
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            {candidate.extracted_category && (
              <span className="flex items-center gap-1">
                <Tag className="h-3 w-3" />
                {candidate.extracted_category}
              </span>
            )}
            <ConfidenceBadge
              score={candidate.extracted_confidence ?? undefined}
              level={candidate.confidence_level}
            />
            {candidate.review_required && candidate.review_status === 'pending' && (
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                Review required
              </span>
            )}
            {candidate.warning_count > 0 && (
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <AlertCircle className="h-3 w-3" />
                {candidate.warning_count} warning{candidate.warning_count !== 1 ? 's' : ''}
              </span>
            )}
            {candidate.mapped_article_id && (
              <Link
                to={`/dashboard/knowledge/${candidate.mapped_article_id}`}
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-0.5 rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900/40 dark:text-indigo-300"
              >
                Saved as article
                <ArrowUpRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
