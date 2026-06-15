/**
 * Lifecycle action buttons for an article.
 *
 * Renders only the actions the backend reports as available for the current
 * status (`available_actions`) AND that the current user is permitted to perform
 * (client-side gate; the API re-checks). Governance-critical actions
 * (publish/archive) open a confirmation modal that captures an optional note.
 * For publish, an ownership group picker is shown when the article lacks one.
 */

import { useState } from 'react';

import { hasPermission } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';
import type { ArticleDetail, LifecycleAction } from '@/types/knowledge';
import { useOwnershipGroups, useTransitionArticle } from '../api';
import { ACTION_LABELS, CONFIRM_ACTIONS } from '../constants';
import { Modal } from './Modal';

/** Maps a lifecycle action to the permission that authorizes it. */
const ACTION_PERMISSION: Record<LifecycleAction, string> = {
  submit_for_review: 'knowledge:submit_review',
  approve: 'knowledge:approve',
  request_changes: 'knowledge:review',
  reject: 'knowledge:review',
  publish: 'knowledge:publish',
  archive: 'knowledge:archive',
  restore: 'knowledge:archive',
  create_revision: 'knowledge:update_all',
};

const PRIMARY: LifecycleAction[] = ['submit_for_review', 'approve', 'publish'];

interface Props {
  article: ArticleDetail;
  onDone?: () => void;
}

export function LifecycleActions({ article, onDone }: Props) {
  const user = useAuthStore((s) => s.user);
  const transition = useTransitionArticle(article.id);
  const { data: groups } = useOwnershipGroups();
  const [pending, setPending] = useState<LifecycleAction | null>(null);
  const [note, setNote] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const allowed = article.available_actions.filter((a) =>
    hasPermission(user, ACTION_PERMISSION[a]),
  );

  // For publish: article needs an ownership group — we collect it in the modal.
  const publishNeedsGroup = pending === 'publish' && !article.ownership_group_id;

  const run = async (action: LifecycleAction, withNote?: string) => {
    setError(null);
    try {
      await transition.mutateAsync({
        action,
        note: withNote,
        ownership_group_id: action === 'publish' && selectedGroupId ? selectedGroupId : undefined,
      });
      setPending(null);
      setNote('');
      setSelectedGroupId('');
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    }
  };

  const click = (action: LifecycleAction) => {
    if (CONFIRM_ACTIONS.includes(action) || action === 'reject' || action === 'request_changes') {
      setPending(action);
      setError(null);
    } else {
      run(action);
    }
  };

  if (allowed.length === 0) {
    return <p className="text-xs text-muted-foreground">No actions available for your role.</p>;
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {allowed.map((action) => {
          const isPrimary = PRIMARY.includes(action);
          return (
            <button
              key={action}
              onClick={() => click(action)}
              disabled={transition.isPending}
              className={
                isPrimary
                  ? 'rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50'
                  : 'rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50'
              }
            >
              {ACTION_LABELS[action]}
            </button>
          );
        })}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <Modal
        open={pending !== null}
        title={pending ? ACTION_LABELS[pending] : ''}
        onClose={() => {
          setPending(null);
          setError(null);
          setSelectedGroupId('');
        }}
        footer={
          <>
            <button
              onClick={() => { setPending(null); setError(null); setSelectedGroupId(''); }}
              className="rounded-lg border border-border px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={() => pending && run(pending, note || undefined)}
              disabled={transition.isPending || (publishNeedsGroup && !selectedGroupId)}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {transition.isPending ? 'Working…' : 'Confirm'}
            </button>
          </>
        }
      >
        {pending === 'publish' && (
          <p className="mb-3 text-sm text-muted-foreground">
            Publishing makes this article retrievable by the AI chat agent for employees.
            The article will be indexed for retrieval.
          </p>
        )}
        {pending === 'archive' && (
          <p className="mb-3 text-sm text-muted-foreground">
            Archiving removes this article from the retrieval index. The chat agent will
            stop using it immediately.
          </p>
        )}

        {/* Ownership group picker — shown for publish when not yet assigned */}
        {publishNeedsGroup && groups && groups.length > 0 && (
          <div className="mb-3">
            <label className="mb-1 block text-xs font-semibold text-amber-700">
              ⚠ Ownership group required to publish
            </label>
            <select
              value={selectedGroupId}
              onChange={(e) => setSelectedGroupId(e.target.value)}
              className="w-full rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-sm outline-none focus:border-primary"
            >
              <option value="">— Select a group —</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.display_name}</option>
              ))}
            </select>
          </div>
        )}
        {publishNeedsGroup && (!groups || groups.length === 0) && (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            No ownership groups exist. Create one first under Knowledge Base → Taxonomy.
          </div>
        )}

        <label className="mb-1 block text-xs font-medium text-foreground">
          Note {pending === 'reject' || pending === 'request_changes' ? '(required)' : '(optional)'}
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-border px-2 py-1.5 text-sm outline-none focus:border-primary"
          placeholder="Add a reviewer note…"
        />
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Modal>
    </>
  );
}


