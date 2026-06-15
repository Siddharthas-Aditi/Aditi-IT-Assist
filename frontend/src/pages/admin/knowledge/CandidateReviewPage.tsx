import { useState } from 'react';
import { Briefcase, CheckSquare, RefreshCw, XSquare } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import {
  useBulkSave,
  useCandidates,
  useIngestionJob,
  useRetryJob,
} from '@/features/ingestion';
import { CandidateCard } from '@/features/ingestion/components/CandidateCard';
import { ParseStatusBadge } from '@/features/ingestion/components/ParseStatusBadge';
import type { CandidateReviewStatus } from '@/types/ingestion';

function timeAgo(dateStr: string): string {
  const secs = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

const STATUS_TABS: { label: string; value: CandidateReviewStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Saved', value: 'saved' },
  { label: 'Rejected', value: 'rejected' },
];

export function CandidateReviewPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [activeTab, setActiveTab] = useState<CandidateReviewStatus | 'all'>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkSavedCount, setBulkSavedCount] = useState<number | null>(null);

  const { data: jobData, isLoading: jobLoading } = useIngestionJob(jobId);
  const { data: candidates, isLoading: candidatesLoading } = useCandidates(
    jobId,
    activeTab === 'all' ? undefined : { review_status: activeTab },
  );
  const retry = useRetryJob();
  const bulkSave = useBulkSave(jobId ?? '');

  const toggleSelect = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleBulkSave = async () => {
    if (!jobId || !selectedIds.size) return;
    const count = selectedIds.size;
    await bulkSave.mutateAsync({ candidate_ids: [...selectedIds] });
    setSelectedIds(new Set());
    setBulkSavedCount(count);
  };

  if (jobLoading) return <div className="p-6 text-sm text-gray-500">Loading job…</div>;
  if (!jobData) return <div className="p-6 text-sm text-red-500">Job not found.</div>;

  const { job } = jobData;
  const isPending = job.parse_status === 'pending' || job.parse_status === 'extracting' || job.parse_status === 'parsing';

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      {/* Job header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Briefcase className="h-5 w-5 text-indigo-500" />
            <h1 className="text-xl font-bold text-gray-900 dark:text-white truncate max-w-lg">
              {job.source_filename}
            </h1>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-gray-500">
            <ParseStatusBadge status={job.parse_status} />
            <span>
              Uploaded {timeAgo(job.created_at)}
            </span>
            {job.source_size && (
              <span>{(job.source_size / 1024).toFixed(1)} KB</span>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          {job.parse_status === 'failed' && (
            <button
              type="button"
              onClick={() => retry.mutate(jobId!)}
              disabled={retry.isPending}
              className="flex items-center gap-1.5 rounded-md bg-orange-100 px-3 py-1.5 text-xs font-medium text-orange-700 hover:bg-orange-200 disabled:opacity-50 dark:bg-orange-900/30 dark:text-orange-300"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry Pipeline
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Pending', count: jobData.candidates_pending, color: 'text-yellow-600' },
          { label: 'Approved', count: jobData.candidates_approved, color: 'text-green-600' },
          { label: 'Saved', count: jobData.candidates_saved, color: 'text-indigo-600' },
          { label: 'Rejected', count: jobData.candidates_rejected, color: 'text-red-600' },
        ].map(({ label, count, color }) => (
          <div
            key={label}
            className="rounded-lg border border-gray-200 bg-white p-3 text-center dark:border-gray-700 dark:bg-gray-900"
          >
            <p className={`text-2xl font-bold ${color}`}>{count}</p>
            <p className="text-xs text-gray-500">{label}</p>
          </div>
        ))}
      </div>

      {/* Post-bulk-save guidance */}
      {bulkSavedCount !== null && (
        <div className="flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800 dark:border-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300">
          <span>
            ✅ <strong>{bulkSavedCount} article{bulkSavedCount !== 1 ? 's' : ''}</strong> saved as draft.
            {' '}Submit each one for review to begin the approval workflow.
          </span>
          <div className="flex items-center gap-2 ml-4">
            <Link
              to="/dashboard/knowledge?status=draft"
              className="whitespace-nowrap rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
            >
              View Draft Articles →
            </Link>
            <button
              type="button"
              onClick={() => setBulkSavedCount(null)}
              className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Processing indicator */}
      {isPending && (
        <div className="rounded-lg bg-blue-50 px-4 py-3 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">
          Pipeline is running… candidates will appear shortly.
        </div>
      )}

      {/* Status tabs + bulk actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              onClick={() => { setActiveTab(tab.value); setSelectedIds(new Set()); }}
              className={[
                'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                activeTab === tab.value
                  ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">{selectedIds.size} selected</span>
            <button
              type="button"
              onClick={handleBulkSave}
              disabled={bulkSave.isPending}
              className="flex items-center gap-1.5 rounded-md bg-green-100 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-200 disabled:opacity-50 dark:bg-green-900/30 dark:text-green-300"
            >
              <CheckSquare className="h-3.5 w-3.5" />
              Save {selectedIds.size} as Draft
            </button>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="flex items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
            >
              <XSquare className="h-3.5 w-3.5" />
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Candidates list */}
      {candidatesLoading ? (
        <p className="text-sm text-gray-400">Loading candidates…</p>
      ) : !candidates?.length ? (
        <div className="rounded-lg border border-dashed border-gray-200 p-8 text-center text-sm text-gray-400 dark:border-gray-700">
          {isPending ? 'Waiting for extraction to complete…' : 'No candidates match this filter.'}
        </div>
      ) : (
        <div className="space-y-2">
          {candidates.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              jobId={jobId!}
              selected={selectedIds.has(c.id)}
              onSelect={toggleSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
