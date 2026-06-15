import type { ParseStatus } from '@/types/ingestion';

interface Props {
  status: ParseStatus;
  className?: string;
}

const CONFIG: Record<ParseStatus, { label: string; colors: string }> = {
  pending: {
    label: 'Pending',
    colors: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  },
  extracting: {
    label: 'Extracting',
    colors: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  },
  parsing: {
    label: 'Parsing',
    colors: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
  },
  completed: {
    label: 'Completed',
    colors: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  },
  failed: {
    label: 'Failed',
    colors: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  },
};

const PULSE_STATUSES: ParseStatus[] = ['extracting', 'parsing'];

export function ParseStatusBadge({ status, className = '' }: Props) {
  const { label, colors } = CONFIG[status] ?? CONFIG.pending;
  const pulse = PULSE_STATUSES.includes(status);

  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        colors,
        className,
      ].join(' ')}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
        </span>
      )}
      {label}
    </span>
  );
}
