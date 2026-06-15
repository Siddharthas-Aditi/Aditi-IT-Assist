import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Save, XCircle } from 'lucide-react';

import {
  useCandidate,
  useIngestionDuplicates,
  useRejectCandidate,
  useSaveCandidate,
  useUpdateCandidate,
} from '@/features/ingestion';
import { ConfidenceBadge } from '@/features/ingestion/components/ConfidenceBadge';
import { DuplicateSuggestionPanel } from '@/features/ingestion/components/DuplicateSuggestionPanel';
import { ExtractionMetaBanner } from '@/features/ingestion/components/ExtractionMetaBanner';
import { RawTextPreview } from '@/features/ingestion/components/RawTextPreview';
import type { CandidateUpdatePayload, IngestionWarning } from '@/types/ingestion';

function WarnBadge({ w }: { w: IngestionWarning }) {
  const colors =
    w.severity === 'error'
      ? 'bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400'
      : w.severity === 'warning'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'
        : 'bg-blue-50 text-blue-600 dark:bg-blue-950/20 dark:text-blue-400';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs ${colors}`}>
      {w.message}
    </span>
  );
}

export function CandidateEditorPage() {
  const { jobId, candidateId } = useParams<{ jobId: string; candidateId: string }>();
  const navigate = useNavigate();
  const { data: candidate, isLoading } = useCandidate(jobId, candidateId);

  const update = useUpdateCandidate(jobId ?? '', candidateId ?? '');
  const save = useSaveCandidate(jobId ?? '', candidateId ?? '');
  const reject = useRejectCandidate(jobId ?? '', candidateId ?? '');

  // Local form state mirroring editable extracted fields
  const [form, setForm] = useState<CandidateUpdatePayload>({});
  const [dirty, setDirty] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectPrompt, setShowRejectPrompt] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!candidate) return;
    setForm({
      extracted_title: candidate.extracted_title ?? '',
      extracted_summary: candidate.extracted_summary ?? '',
      extracted_category: candidate.extracted_category ?? '',
      extracted_subcategory: candidate.extracted_subcategory ?? '',
      extracted_product_or_system: candidate.extracted_product_or_system ?? '',
      extracted_platform: candidate.extracted_platform ?? '',
      extracted_escalation_criteria: candidate.extracted_escalation_criteria ?? '',
      extracted_tags: candidate.extracted_tags ?? [],
      extracted_symptoms: candidate.extracted_symptoms ?? [],
    });
    setDirty(false);
  }, [candidate]);

  const { data: duplicates } = useIngestionDuplicates(
    form.extracted_title,
    form.extracted_tags,
    form.extracted_product_or_system,
    form.extracted_category,
  );

  const set = (key: keyof CandidateUpdatePayload, value: unknown) => {
    setForm((p) => ({ ...p, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaveError(null);
    try {
      if (dirty) await update.mutateAsync(form);
      const result = await save.mutateAsync({});
      // Navigate directly to the new article so the user can continue the lifecycle
      navigate(`/dashboard/knowledge/${result.article_id}`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed. Please try again.');
    }
  };

  const handleReject = async () => {
    await reject.mutateAsync({ reason: rejectReason || undefined });
    navigate(`/dashboard/knowledge/ingest/${jobId}`);
  };

  if (isLoading) return <div className="p-6 text-sm text-gray-500">Loading candidate…</div>;
  if (!candidate) return <div className="p-6 text-sm text-red-500">Candidate not found.</div>;

  const isSaved = candidate.review_status === 'saved';
  const isRejected = candidate.review_status === 'rejected';

  // Re-evaluate error-severity warnings against the *current* form state.
  // If the user has already filled in a previously-missing field, that warning
  // is no longer blocking — don't keep the Save button disabled indefinitely.
  const blockingErrors = (candidate.validation_warnings ?? []).filter(
    (w: IngestionWarning) => {
      if (w.severity !== 'error') return false;
      if (w.code === 'MISSING_TITLE' && (form.extracted_title ?? '').trim()) return false;
      if (w.code === 'MISSING_CATEGORY' && (form.extracted_category ?? '').trim()) return false;
      return true;
    },
  );

  return (
    <div className="mx-auto max-w-7xl space-y-0 p-6">
      {/* Topbar */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigate(`/dashboard/knowledge/ingest/${jobId}`)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to job
        </button>
        <div className="flex items-center gap-2">
          <ConfidenceBadge
            score={candidate.extracted_confidence ?? undefined}
            level={candidate.confidence_level}
            size="md"
          />
          {!isSaved && !isRejected && (
            <>
              <button
                type="button"
                onClick={() => setShowRejectPrompt(true)}
                className="flex items-center gap-1.5 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400"
              >
                <XCircle className="h-3.5 w-3.5" />
                Reject
              </button>
              {dirty && (
                <button
                  type="button"
                  onClick={() => update.mutateAsync(form)}
                  disabled={update.isPending}
                  className="flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300"
                >
                  <Save className="h-3.5 w-3.5" />
                  Save Edits
                </button>
              )}
              <button
                type="button"
                onClick={handleSave}
                disabled={save.isPending || blockingErrors.length > 0}
                title={blockingErrors.length > 0 ? 'Fill in required fields (marked with *) to enable' : undefined}
                className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Save as Draft Article
              </button>
            </>
          )}
          {isSaved && (
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
              ✓ Saved as article
            </span>
          )}
          {isRejected && (
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-700 dark:bg-red-900/40 dark:text-red-400">
              Rejected
            </span>
          )}
        </div>
      </div>

      {/* Reject prompt */}
      {showRejectPrompt && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950/20">
          <p className="mb-2 text-sm font-medium text-red-700 dark:text-red-400">
            Rejection reason (optional)
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Why are you rejecting this candidate?"
              className="flex-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-400 dark:border-red-800 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={handleReject}
              disabled={reject.isPending}
              className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              Confirm Reject
            </button>
            <button
              type="button"
              onClick={() => setShowRejectPrompt(false)}
              className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* v2 pipeline metadata banner */}
      <ExtractionMetaBanner candidate={candidate} />

      {/* Save error banner */}
      {saveError && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/20 dark:text-red-400">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{saveError}</span>
        </div>
      )}

      {/* Warnings */}
      {(candidate.validation_warnings ?? []).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {candidate.validation_warnings!.map((w: IngestionWarning, i: number) => (
            <WarnBadge key={i} w={w} />
          ))}
        </div>
      )}

      {/* 2-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: raw text */}
        <div className="relative">
          <RawTextPreview text={candidate.raw_segment_text} />
        </div>

        {/* Right: structured form */}
        <div className="space-y-4">
          {/* Title */}
          <Field label="Title" required>
            <input
              type="text"
              value={form.extracted_title ?? ''}
              onChange={(e) => set('extracted_title', e.target.value)}
              disabled={isSaved || isRejected}
              className={input()}
            />
          </Field>

          {/* Summary */}
          <Field label="Short summary">
            <textarea
              rows={3}
              value={form.extracted_summary ?? ''}
              onChange={(e) => set('extracted_summary', e.target.value)}
              disabled={isSaved || isRejected}
              className={input()}
            />
          </Field>

          {/* Category / Subcategory */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category" required>
              <input
                type="text"
                value={form.extracted_category ?? ''}
                onChange={(e) => set('extracted_category', e.target.value)}
                disabled={isSaved || isRejected}
                className={input()}
              />
            </Field>
            <Field label="Subcategory">
              <input
                type="text"
                value={form.extracted_subcategory ?? ''}
                onChange={(e) => set('extracted_subcategory', e.target.value)}
                disabled={isSaved || isRejected}
                className={input()}
              />
            </Field>
          </div>

          {/* Product / Platform */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Product / System">
              <input
                type="text"
                value={form.extracted_product_or_system ?? ''}
                onChange={(e) => set('extracted_product_or_system', e.target.value)}
                disabled={isSaved || isRejected}
                className={input()}
              />
            </Field>
            <Field label="Platform">
              <input
                type="text"
                value={form.extracted_platform ?? ''}
                onChange={(e) => set('extracted_platform', e.target.value)}
                disabled={isSaved || isRejected}
                className={input()}
              />
            </Field>
          </div>

          {/* Tags */}
          <Field label="Tags (comma-separated)">
            <input
              type="text"
              value={(form.extracted_tags ?? []).join(', ')}
              onChange={(e) =>
                set(
                  'extracted_tags',
                  e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                )
              }
              disabled={isSaved || isRejected}
              className={input()}
            />
          </Field>

          {/* Escalation */}
          <Field label="Escalation criteria">
            <textarea
              rows={2}
              value={form.extracted_escalation_criteria ?? ''}
              onChange={(e) => set('extracted_escalation_criteria', e.target.value)}
              disabled={isSaved || isRejected}
              className={input()}
            />
          </Field>

          {/* Symptoms (read-only list) */}
          {(candidate.extracted_symptoms ?? []).length > 0 && (
            <Field label="Extracted symptoms">
              <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                {candidate.extracted_symptoms!.map((s: string, i: number) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />
                    {s}
                  </li>
                ))}
              </ul>
            </Field>
          )}

          {/* Duplicate panel */}
          {duplicates && duplicates.length > 0 && (
            <DuplicateSuggestionPanel matches={duplicates} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}

function input() {
  return [
    'block w-full rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm',
    'text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400',
    'dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100',
    'disabled:opacity-50 disabled:cursor-not-allowed',
  ].join(' ');
}
