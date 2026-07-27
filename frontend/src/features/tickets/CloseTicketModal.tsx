/** Mandatory close form with resolution notes and cascading category fields. */

import { useEffect, useState } from 'react';

import { Modal } from '@/features/knowledge/components/Modal';
import { ticketsApi } from '@/lib/api';

import {
  CategoryCascadeFields,
  type CategoryCascadeValues,
} from './CategoryCascadeFields';

const TEXTAREA_CLASS =
  'w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-50';

const LABEL_CLASS = 'mb-1 block text-xs font-medium text-gray-600';

interface Props {
  ticketId: string;
  open: boolean;
  onClose: () => void;
  onClosed: () => void;
  initialCategory?: string;
  initialSubcategory?: string;
  initialItem?: string;
}

export function CloseTicketModal({
  ticketId,
  open,
  onClose,
  onClosed,
  initialCategory = '',
  initialSubcategory = '',
  initialItem = '',
}: Props) {
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [closeNotes, setCloseNotes] = useState('');
  const [cascade, setCascade] = useState<CategoryCascadeValues>({
    category: '',
    subcategory: '',
    item: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setResolutionNotes('');
    setCloseNotes('');
    setCascade({
      category: initialCategory,
      subcategory: initialSubcategory,
      item: initialItem,
    });
    setError(null);
    setSubmitting(false);
  }, [open, initialCategory, initialSubcategory, initialItem]);

  const canSubmit =
    resolutionNotes.trim().length > 0 &&
    cascade.category.length > 0 &&
    cascade.subcategory.length > 0 &&
    cascade.item.length > 0 &&
    !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);
    try {
      await ticketsApi.close(ticketId, {
        resolution_notes: resolutionNotes.trim(),
        category: cascade.category,
        subcategory: cascade.subcategory,
        item: cascade.item,
        close_notes: closeNotes.trim() || undefined,
      });
      onClosed();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to close ticket');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Close ticket"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="close-ticket-form"
            disabled={!canSubmit}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Closing…' : 'Confirm close'}
          </button>
        </>
      }
    >
      <form id="close-ticket-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="resolution-notes" className={LABEL_CLASS}>
            Resolution notes <span className="text-red-500">*</span>
          </label>
          <textarea
            id="resolution-notes"
            value={resolutionNotes}
            onChange={(e) => setResolutionNotes(e.target.value)}
            rows={4}
            disabled={submitting}
            placeholder="Describe how the issue was resolved…"
            className={TEXTAREA_CLASS}
          />
        </div>

        <CategoryCascadeFields
          category={cascade.category}
          subcategory={cascade.subcategory}
          item={cascade.item}
          onChange={setCascade}
          disabled={submitting}
        />

        <div>
          <label htmlFor="close-notes" className={LABEL_CLASS}>
            Close notes
          </label>
          <textarea
            id="close-notes"
            value={closeNotes}
            onChange={(e) => setCloseNotes(e.target.value)}
            rows={2}
            disabled={submitting}
            placeholder="Optional internal note…"
            className={TEXTAREA_CLASS}
          />
        </div>

        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
