interface Props {
  score: number | null | undefined;
  size?: 'sm' | 'md';
  showLabel?: boolean;
}

function getColor(score: number): string {
  if (score >= 0.8) return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  if (score >= 0.6) return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300';
  if (score >= 0.4) return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300';
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400';
}

function getLabel(score: number): string {
  if (score >= 0.8) return 'High';
  if (score >= 0.6) return 'Medium';
  if (score >= 0.4) return 'Low';
  return 'Very Low';
}

export function ConfidenceBadge({ score, size = 'sm', showLabel = true }: Props) {
  if (score === null || score === undefined) {
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">–</span>
    );
  }

  const pct = Math.round(score * 100);
  const color = getColor(score);
  const label = getLabel(score);
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium',
        textSize,
        color,
      ].join(' ')}
      title={`Extraction confidence: ${pct}%`}
    >
      {pct}%{showLabel && <span className="opacity-70">· {label}</span>}
    </span>
  );
}
