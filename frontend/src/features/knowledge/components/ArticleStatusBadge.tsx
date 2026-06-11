/** Reusable article status badge with consistent per-status styling. */

import { clsx } from 'clsx';

import type { ArticleStatus } from '@/types/knowledge';
import { STATUS_LABELS, STATUS_STYLES } from '../constants';

interface Props {
  status: ArticleStatus;
  className?: string;
}

export function ArticleStatusBadge({ status, className }: Props) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        STATUS_STYLES[status],
        className,
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
