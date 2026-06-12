/** Inline duplicate article hints — shown below the title field in the editor. */

import { ExternalLink } from 'lucide-react';

import type { DuplicateHint } from '@/types/knowledge';
import { STATUS_LABELS } from '../constants';
import type { ArticleStatus } from '@/types/knowledge';

interface Props {
  hints: DuplicateHint[];
  /** If true, show a loading shimmer. */
  loading?: boolean;
}

export function DuplicateHints({ hints, loading }: Props) {
  if (loading) {
    return (
      <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-400">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-gray-300" />
        Checking for duplicates…
      </div>
    );
  }

  if (hints.length === 0) return null;

  return (
    <div className="mt-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
      <p className="mb-1.5 text-xs font-semibold text-amber-800">
        ⚠️ Similar article{hints.length !== 1 ? 's' : ''} already exist
      </p>
      <ul className="space-y-1">
        {hints.map((h) => (
          <li key={h.id} className="flex items-center gap-2 text-xs">
            <span className="rounded border border-amber-200 bg-white px-1.5 py-0.5 text-amber-700">
              {STATUS_LABELS[h.status as ArticleStatus] ?? h.status}
            </span>
            <a
              href={`/dashboard/knowledge/${h.id}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 font-medium text-amber-800 hover:underline"
            >
              {h.title}
              <ExternalLink size={11} className="shrink-0" />
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-amber-700 opacity-80">
        Consider editing an existing article instead of creating a new one.
      </p>
    </div>
  );
}
