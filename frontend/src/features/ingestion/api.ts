/** React Query hooks for the document ingestion pipeline. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  BulkSaveRequest,
  BulkSaveResponse,
  CandidateUpdatePayload,
  DuplicateCandidateMatch,
  IngestionCandidateDetail,
  IngestionCandidateSummary,
  IngestionJobSummary,
  PipelineStatusResponse,
  RejectCandidateRequest,
  SaveCandidateRequest,
  SaveCandidateResponse,
  UploadResponse,
} from '@/types/ingestion';

const BASE = '/knowledge/ingest';

// ── Query keys ─────────────────────────────────────────────────────────────
export const ingestionKeys = {
  all: ['ingestion'] as const,
  jobs: () => ['ingestion', 'jobs'] as const,
  job: (id: string) => ['ingestion', 'job', id] as const,
  candidates: (jobId: string) => ['ingestion', 'candidates', jobId] as const,
  candidate: (jobId: string, cId: string) => ['ingestion', 'candidate', jobId, cId] as const,
  duplicates: (title: string) => ['ingestion', 'duplicates', title] as const,
};

// ── Jobs ───────────────────────────────────────────────────────────────────

export function useIngestionJobs(params?: { parse_status?: string; limit?: number }) {
  return useQuery({
    queryKey: [...ingestionKeys.jobs(), params],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (params?.parse_status) qs.set('parse_status', params.parse_status);
      if (params?.limit) qs.set('limit', String(params.limit));
      return apiRequest<IngestionJobSummary[]>(`${BASE}/jobs?${qs}`);
    },
  });
}

export function useIngestionJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ingestionKeys.job(jobId ?? ''),
    queryFn: () => apiRequest<PipelineStatusResponse>(`${BASE}/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.job.parse_status;
      // Poll while actively processing
      if (status === 'pending' || status === 'extracting' || status === 'parsing') {
        return 2500;
      }
      return false;
    },
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      apiRequest<IngestionJobSummary>(`${BASE}/jobs/${jobId}/retry`, { method: 'POST' }),
    onSuccess: (_data, jobId) => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.jobs() });
    },
  });
}

// ── Upload ─────────────────────────────────────────────────────────────────

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return apiRequest<UploadResponse>(`${BASE}/upload`, {
        method: 'POST',
        body: form,
        // Do NOT set Content-Type — browser sets it with boundary
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.jobs() });
    },
  });
}

// ── Candidates ─────────────────────────────────────────────────────────────

export function useCandidates(jobId: string | undefined, params?: { review_status?: string }) {
  return useQuery({
    queryKey: [...ingestionKeys.candidates(jobId ?? ''), params],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (params?.review_status) qs.set('review_status', params.review_status);
      return apiRequest<IngestionCandidateSummary[]>(
        `${BASE}/jobs/${jobId}/candidates?${qs}`
      );
    },
    enabled: Boolean(jobId),
  });
}

export function useCandidate(jobId: string | undefined, candidateId: string | undefined) {
  return useQuery({
    queryKey: ingestionKeys.candidate(jobId ?? '', candidateId ?? ''),
    queryFn: () =>
      apiRequest<IngestionCandidateDetail>(
        `${BASE}/jobs/${jobId}/candidates/${candidateId}`
      ),
    enabled: Boolean(jobId) && Boolean(candidateId),
  });
}

export function useUpdateCandidate(jobId: string, candidateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CandidateUpdatePayload) =>
      apiRequest<IngestionCandidateDetail>(
        `${BASE}/jobs/${jobId}/candidates/${candidateId}`,
        { method: 'PATCH', body: payload }
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidate(jobId, candidateId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidates(jobId) });
    },
  });
}

export function useSaveCandidate(jobId: string, candidateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SaveCandidateRequest) =>
      apiRequest<SaveCandidateResponse>(
        `${BASE}/jobs/${jobId}/candidates/${candidateId}/save`,
        { method: 'POST', body: payload }
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidate(jobId, candidateId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidates(jobId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) });
    },
  });
}

export function useRejectCandidate(jobId: string, candidateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RejectCandidateRequest) =>
      apiRequest<void>(
        `${BASE}/jobs/${jobId}/candidates/${candidateId}/reject`,
        { method: 'POST', body: payload }
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidates(jobId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidate(jobId, candidateId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) });
    },
  });
}

export function useBulkSave(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: BulkSaveRequest) =>
      apiRequest<BulkSaveResponse>(`${BASE}/jobs/${jobId}/bulk-save`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ingestionKeys.candidates(jobId) });
      void qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) });
    },
  });
}

// ── Duplicates ─────────────────────────────────────────────────────────────

export function useIngestionDuplicates(
  title: string | undefined,
  tags?: string[],
  product?: string,
  category?: string
) {
  return useQuery({
    queryKey: ingestionKeys.duplicates(title ?? ''),
    queryFn: () => {
      const qs = new URLSearchParams();
      if (title) qs.set('title', title);
      if (tags?.length) tags.forEach((t) => qs.append('tags', t));
      if (product) qs.set('product', product);
      if (category) qs.set('category', category);
      return apiRequest<DuplicateCandidateMatch[]>(`${BASE}/duplicates?${qs}`);
    },
    enabled: Boolean(title && title.length >= 3),
    staleTime: 30_000,
  });
}
