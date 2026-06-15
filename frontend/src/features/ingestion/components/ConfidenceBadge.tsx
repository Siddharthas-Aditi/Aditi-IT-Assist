import type { ConfidenceLevel } from '@/types/ingestion';

interface Props {
  score?: number | null;
  level?: ConfidenceLevel | null;
  size?: 'sm' | 'md';
  showLabel?: boolean;
}

const LEVEL_COLOR: Record<ConfidenceLevel, string> = {
  high:      'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  medium:    'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  low:       'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  very_low:  'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
};
const LEVEL_LABEL: Record<ConfidenceLevel, string> = {
  high: 'High', medium: 'Medium', low: 'Low', very_low: 'Very Low',
};

function scoreToLevel(score: number): ConfidenceLevel {
  if (score >= 0.75) return 'high';
  if (score >= 0.50) return 'medium';
  if (score >= 0.30) return 'low';
  return 'very_low';
}

export function ConfidenceBadge({ score, level, size = 'sm', showLabel = true }: Props) {
  const effectiveLevel: ConfidenceLevel | null =
    level ?? (score != null ? scoreToLevel(score) : null);

  if (effectiveLevel === null) {
    return <span className="text-xs text-gray-400 dark:text-gray-500">–</span>;
  }

  const pct = score != null ? `${Math.round(score * 100)}% · ` : '';
  const color = LEVEL_COLOR[effectiveLevel];
  const label = LEVEL_LABEL[effectiveLevel];
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <span
      className={['inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium', textSize, color].join(' ')}
      title={`Extraction confidence${score != null ? `: ${Math.round(score * 100)}%` : ''}`}
    >
      {showLabel ? `${pct}${label}` : (score != null ? `${Math.round(score * 100)}%` : label)}
    </span>
  );
}
