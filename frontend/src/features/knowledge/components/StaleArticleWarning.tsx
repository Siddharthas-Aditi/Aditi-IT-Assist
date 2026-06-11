/** Inline "needs review" indicator for aging/stale published content. */

import { AlertTriangle } from 'lucide-react';

interface Props {
  dueAt?: string | null;
  compact?: boolean;
}

export function StaleArticleWarning({ dueAt, compact = false }: Props) {
  const label = dueAt
    ? `Review overdue (due ${new Date(dueAt).toLocaleDateString()})`
    : 'Needs review';

  if (compact) {
    return (
      <span
        title={label}
        className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700"
      >
        <AlertTriangle size={11} /> Stale
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
      <AlertTriangle size={16} />
      <span>{label} — content may be out of date.</span>
    </div>
  );
}
