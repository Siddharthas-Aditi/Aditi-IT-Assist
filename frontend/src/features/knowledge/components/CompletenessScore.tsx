/** Article completeness score widget — shown in the editor sidebar. */

import { CheckCircle2, XCircle } from 'lucide-react';

import type { CompletenessReport, DimensionScore } from '@/types/knowledge';

interface Props {
  report: CompletenessReport;
}

const GRADE_RING: Record<string, string> = {
  A: 'text-emerald-600',
  B: 'text-teal-600',
  C: 'text-amber-500',
  D: 'text-orange-500',
  F: 'text-red-600',
};

const GRADE_BG: Record<string, string> = {
  A: 'bg-emerald-50 border-emerald-200',
  B: 'bg-teal-50 border-teal-200',
  C: 'bg-amber-50 border-amber-200',
  D: 'bg-orange-50 border-orange-200',
  F: 'bg-red-50 border-red-200',
};

function DimensionBar({ dim }: { dim: DimensionScore }) {
  const pct = Math.round(dim.score * 100);
  const barColor =
    pct >= 75
      ? 'bg-emerald-500'
      : pct >= 50
        ? 'bg-amber-400'
        : 'bg-red-400';

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-gray-700">{dim.label}</span>
        <span className="tabular-nums text-gray-500">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function CompletenessScore({ report }: Props) {
  const gradeColor = GRADE_RING[report.grade] ?? 'text-gray-500';
  const gradeBg = GRADE_BG[report.grade] ?? 'bg-gray-50 border-gray-200';

  return (
    <div className={`rounded-xl border p-4 ${gradeBg}`}>
      {/* Header */}
      <div className="mb-3 flex items-center gap-3">
        <div className={`text-3xl font-black leading-none ${gradeColor}`}>{report.grade}</div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-800">
            Completeness: {report.score.toFixed(0)}%
          </p>
          <p className="text-xs text-gray-500">
            {report.ready_for_publish
              ? '✅ Ready to publish'
              : report.ready_for_review
                ? '⚠️ Ready to submit for review'
                : '🔴 More content needed'}
          </p>
        </div>
      </div>

      {/* Dimension bars */}
      <div className="mb-3 space-y-2">
        {report.dimensions.map((d) => (
          <DimensionBar key={d.name} dim={d} />
        ))}
      </div>

      {/* Blocking issues */}
      {report.blocking_issues.length > 0 && (
        <div className="mb-2">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-700">
            Blockers
          </p>
          <ul className="space-y-0.5">
            {report.blocking_issues.map((issue, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-red-700">
                <XCircle size={12} className="mt-0.5 shrink-0" />
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Top suggestions (max 3 shown) */}
      {report.suggestions.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Suggestions
          </p>
          <ul className="space-y-0.5">
            {report.suggestions.slice(0, 3).map((s, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-gray-600">
                <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-gray-400" />
                {s}
              </li>
            ))}
            {report.suggestions.length > 3 && (
              <li className="text-xs text-gray-400">
                +{report.suggestions.length - 3} more suggestions
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
