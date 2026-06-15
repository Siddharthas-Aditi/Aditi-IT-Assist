import { AlertTriangle, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { DuplicateCandidateMatch } from '@/types/ingestion';

interface Props {
  matches: DuplicateCandidateMatch[];
}

export function DuplicateSuggestionPanel({ matches }: Props) {
  if (!matches.length) return null;

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-700/50 dark:bg-amber-950/20">
      <div className="flex items-center gap-2 text-sm font-semibold text-amber-800 dark:text-amber-300">
        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
        {matches.length} potentially similar article{matches.length !== 1 ? 's' : ''} found
      </div>
      <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
        Review these before saving to avoid duplication.
      </p>
      <ul className="mt-3 space-y-2">
        {matches.map((m) => (
          <li
            key={m.article_id}
            className="flex items-start justify-between gap-2 rounded-md bg-white px-3 py-2 dark:bg-gray-900"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
                {m.title}
              </p>
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                {m.category ?? 'Unknown category'} ·{' '}
                <span className="font-medium">{Math.round(m.similarity_score * 100)}%</span> match
                ({m.match_reason})
              </p>
            </div>
            <Link
              to={`/dashboard/knowledge/${m.article_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 text-indigo-500 hover:text-indigo-700"
              title="Open existing article"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
