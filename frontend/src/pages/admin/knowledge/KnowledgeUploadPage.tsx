import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Clock } from 'lucide-react';
function timeAgo(dateStr: string): string {
  const secs = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}
import { useIngestionJobs, useUploadDocument } from '@/features/ingestion';
import { DropZone } from '@/features/ingestion/components/DropZone';
import { ParseStatusBadge } from '@/features/ingestion/components/ParseStatusBadge';

export function KnowledgeUploadPage() {
  const navigate = useNavigate();
  const { data: jobs, isLoading: jobsLoading } = useIngestionJobs({ limit: 10 });
  const upload = useUploadDocument();
  const [lastError, setLastError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setLastError(null);
    try {
      const res = await upload.mutateAsync(file);
      navigate(`/dashboard/knowledge/ingest/${res.job_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed. Please try again.';
      setLastError(msg);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Upload Document</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Upload a DOCX, PDF, PPTX, TXT, or Markdown file. The system will extract and
          structure its content into knowledge article candidates for your review.
        </p>
      </div>

      {/* Drop zone */}
      <DropZone onFileSelected={handleFile} isUploading={upload.isPending} />

      {lastError && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
          {lastError}
        </div>
      )}

      {/* Recent jobs */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold text-gray-700 dark:text-gray-300">
          <Clock className="h-4 w-4" />
          Recent Jobs
        </h2>
        {jobsLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : !jobs?.length ? (
          <p className="rounded-lg border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400 dark:border-gray-700">
            No uploads yet.
          </p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  {['File', 'Type', 'Candidates', 'Status', 'Uploaded'].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    onClick={() => navigate(`/dashboard/knowledge/ingest/${job.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 flex-shrink-0 text-gray-400" />
                        <span className="max-w-[200px] truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                          {job.source_filename}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs uppercase text-gray-500">{job.source_type}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                      {job.candidate_count}
                    </td>
                    <td className="px-4 py-3">
                      <ParseStatusBadge status={job.parse_status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {timeAgo(job.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
