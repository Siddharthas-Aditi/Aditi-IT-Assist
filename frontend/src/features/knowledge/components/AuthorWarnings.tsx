/** Inline author warnings panel — shown in the article editor. */

import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { useState } from 'react';

import type { AuthorWarning, WarningSeverity } from '@/types/knowledge';

interface Props {
  warnings: AuthorWarning[];
  /** If a field key is provided, only warnings matching that field are shown inline. */
  filterField?: string;
}

const SEV_CONFIG: Record<
  WarningSeverity,
  { icon: typeof AlertCircle; border: string; bg: string; text: string; badge: string }
> = {
  error: {
    icon: AlertCircle,
    border: 'border-red-200',
    bg: 'bg-red-50',
    text: 'text-red-800',
    badge: 'bg-red-100 text-red-700',
  },
  warning: {
    icon: AlertTriangle,
    border: 'border-amber-200',
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    badge: 'bg-amber-100 text-amber-700',
  },
  info: {
    icon: Info,
    border: 'border-blue-200',
    bg: 'bg-blue-50',
    text: 'text-blue-800',
    badge: 'bg-blue-100 text-blue-700',
  },
};

function WarningRow({ w }: { w: AuthorWarning }) {
  const cfg = SEV_CONFIG[w.severity as WarningSeverity] ?? SEV_CONFIG.info;
  const Icon = cfg.icon;
  return (
    <div className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${cfg.bg} ${cfg.border}`}>
      <Icon size={14} className={`mt-0.5 shrink-0 ${cfg.text}`} />
      <div className="min-w-0">
        <p className={`text-sm font-medium ${cfg.text}`}>{w.message}</p>
        {w.guidance && (
          <p className={`mt-0.5 text-xs ${cfg.text} opacity-80`}>{w.guidance}</p>
        )}
      </div>
    </div>
  );
}

/** Full panel shown in the editor sidebar — groups by severity. */
export function AuthorWarnings({ warnings, filterField }: Props) {
  const [expanded, setExpanded] = useState(true);

  const shown = filterField
    ? warnings.filter((w) => w.field === filterField)
    : warnings;

  if (shown.length === 0) return null;

  const errors = shown.filter((w) => w.severity === 'error');
  const warningItems = shown.filter((w) => w.severity === 'warning');
  const infoItems = shown.filter((w) => w.severity === 'info');

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-800">
          Author Guidance
          {errors.length > 0 && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
              {errors.length} error{errors.length !== 1 ? 's' : ''}
            </span>
          )}
          {warningItems.length > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
              {warningItems.length} warning{warningItems.length !== 1 ? 's' : ''}
            </span>
          )}
        </span>
        <span className="text-xs text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="space-y-1.5 border-t border-gray-100 p-3">
          {errors.map((w, i) => (
            <WarningRow key={`e-${i}`} w={w} />
          ))}
          {warningItems.map((w, i) => (
            <WarningRow key={`w-${i}`} w={w} />
          ))}
          {infoItems.map((w, i) => (
            <WarningRow key={`i-${i}`} w={w} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Compact single-field inline hint shown directly below a form field. */
export function FieldWarning({ warnings, field }: { warnings: AuthorWarning[]; field: string }) {
  const match = warnings.find((w) => w.field === field);
  if (!match) return null;
  const cfg = SEV_CONFIG[match.severity as WarningSeverity] ?? SEV_CONFIG.info;
  const Icon = cfg.icon;
  return (
    <p className={`mt-1 flex items-center gap-1 text-xs ${cfg.text}`}>
      <Icon size={11} className="shrink-0" />
      {match.message}
    </p>
  );
}
