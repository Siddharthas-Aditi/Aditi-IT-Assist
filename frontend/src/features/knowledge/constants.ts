/** Display labels, colors, and option lists for knowledge management UI. */

import type { ArticleStatus, ArticleType, Audience, LifecycleAction } from '@/types/knowledge';

export const STATUS_LABELS: Record<ArticleStatus, string> = {
  draft: 'Draft',
  in_review: 'In Review',
  approved: 'Approved',
  published: 'Published',
  archived: 'Archived',
};

/** Tailwind classes per status — distinct draft/review/published treatment. */
export const STATUS_STYLES: Record<ArticleStatus, string> = {
  draft: 'bg-gray-100 text-gray-700 border-gray-200',
  in_review: 'bg-amber-50 text-amber-700 border-amber-200',
  approved: 'bg-blue-50 text-blue-700 border-blue-200',
  published: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  archived: 'bg-zinc-100 text-zinc-500 border-zinc-200',
};

export const ARTICLE_TYPE_LABELS: Record<ArticleType, string> = {
  troubleshooting: 'Troubleshooting',
  how_to: 'How-To',
  faq: 'FAQ',
  known_error: 'Known Error',
  policy: 'Policy',
  reference: 'Reference',
};

export const AUDIENCE_LABELS: Record<Audience, string> = {
  employee: 'Employees',
  it_staff: 'IT Staff',
  admin: 'Admins',
};

export const ACTION_LABELS: Record<LifecycleAction, string> = {
  submit_for_review: 'Submit for Review',
  approve: 'Approve',
  request_changes: 'Request Changes',
  reject: 'Reject',
  publish: 'Publish',
  archive: 'Archive',
  restore: 'Restore to Draft',
  create_revision: 'New Revision',
};

/** Actions that need a confirmation modal (irreversible-ish or governance-critical). */
export const CONFIRM_ACTIONS: LifecycleAction[] = ['publish', 'archive'];

export const STATUS_OPTIONS: { value: ArticleStatus; label: string }[] = (
  Object.keys(STATUS_LABELS) as ArticleStatus[]
).map((s) => ({ value: s, label: STATUS_LABELS[s] }));

export const ARTICLE_TYPE_OPTIONS: { value: ArticleType; label: string }[] = (
  Object.keys(ARTICLE_TYPE_LABELS) as ArticleType[]
).map((t) => ({ value: t, label: ARTICLE_TYPE_LABELS[t] }));

export const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = (
  Object.keys(AUDIENCE_LABELS) as Audience[]
).map((a) => ({ value: a, label: AUDIENCE_LABELS[a] }));
