/** React Query hooks + API calls for knowledge management. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  ArticleDetail,
  ArticleFilters,
  ArticleListResponse,
  ArticleSummary,
  ArticleWritePayload,
  FeedbackItem,
  IndexingStatus,
  KnowledgeAnalyticsSummary,
  LifecycleAction,
  OwnershipGroup,
  ReindexResult,
  RetrievalPreview,
  ReviewNote,
  TaxonomyTerm,
  VersionSummary,
} from '@/types/knowledge';

const ADMIN = '/knowledge/admin';

export const knowledgeKeys = {
  all: ['knowledge'] as const,
  list: (filters: ArticleFilters) => ['knowledge', 'list', filters] as const,
  detail: (id: string) => ['knowledge', 'detail', id] as const,
  versions: (id: string) => ['knowledge', 'versions', id] as const,
  preview: (id: string) => ['knowledge', 'preview', id] as const,
  feedback: (id: string) => ['knowledge', 'feedback', id] as const,
  reviewNotes: (id: string) => ['knowledge', 'review-notes', id] as const,
  reviewQueue: ['knowledge', 'review-queue'] as const,
  stale: ['knowledge', 'stale'] as const,
  taxonomy: ['knowledge', 'taxonomy'] as const,
  ownership: ['knowledge', 'ownership'] as const,
  indexing: ['knowledge', 'indexing'] as const,
  analytics: ['knowledge', 'analytics'] as const,
};

// ── Queries ────────────────────────────────────────────────────────

export function useArticles(filters: ArticleFilters) {
  return useQuery({
    queryKey: knowledgeKeys.list(filters),
    queryFn: () =>
      apiRequest<ArticleListResponse>(`${ADMIN}/articles`, {
        query: {
          status: filters.status || undefined,
          category: filters.category,
          product_or_system: filters.product_or_system,
          platform: filters.platform,
          audience: filters.audience || undefined,
          ownership_group_id: filters.ownership_group_id,
          search: filters.search,
          review_due: filters.review_due,
          limit: filters.limit ?? 25,
          offset: filters.offset ?? 0,
        },
      }),
  });
}

export function useArticle(id: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.detail(id ?? ''),
    queryFn: () => apiRequest<ArticleDetail>(`${ADMIN}/articles/${id}`),
    enabled: Boolean(id),
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: knowledgeKeys.reviewQueue,
    queryFn: () => apiRequest<ArticleSummary[]>(`${ADMIN}/review-queue`),
  });
}

export function useStaleArticles() {
  return useQuery({
    queryKey: knowledgeKeys.stale,
    queryFn: () => apiRequest<ArticleSummary[]>(`${ADMIN}/stale`),
  });
}

export function useVersions(id: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.versions(id ?? ''),
    queryFn: () => apiRequest<VersionSummary[]>(`${ADMIN}/articles/${id}/versions`),
    enabled: Boolean(id),
  });
}

export function useRetrievalPreview(id: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.preview(id ?? ''),
    queryFn: () => apiRequest<RetrievalPreview>(`${ADMIN}/articles/${id}/preview`),
    enabled: Boolean(id),
  });
}

export function useFeedback(id: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.feedback(id ?? ''),
    queryFn: () => apiRequest<FeedbackItem[]>(`${ADMIN}/articles/${id}/feedback`),
    enabled: Boolean(id),
  });
}

export function useReviewNotes(id: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.reviewNotes(id ?? ''),
    queryFn: () => apiRequest<ReviewNote[]>(`${ADMIN}/articles/${id}/review-notes`),
    enabled: Boolean(id),
  });
}

export function useTaxonomy() {
  return useQuery({
    queryKey: knowledgeKeys.taxonomy,
    queryFn: () => apiRequest<TaxonomyTerm[]>(`${ADMIN}/taxonomy`),
  });
}

export function useOwnershipGroups() {
  return useQuery({
    queryKey: knowledgeKeys.ownership,
    queryFn: () => apiRequest<OwnershipGroup[]>(`${ADMIN}/ownership-groups`),
  });
}

export function useIndexingStatus() {
  return useQuery({
    queryKey: knowledgeKeys.indexing,
    queryFn: () => apiRequest<IndexingStatus>(`${ADMIN}/indexing/status`),
  });
}

export function useKnowledgeAnalytics() {
  return useQuery({
    queryKey: knowledgeKeys.analytics,
    queryFn: () => apiRequest<KnowledgeAnalyticsSummary>(`${ADMIN}/analytics/summary`),
  });
}

// ── Mutations ──────────────────────────────────────────────────────

export function useCreateArticle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ArticleWritePayload) =>
      apiRequest<ArticleDetail>(`${ADMIN}/articles`, { method: 'POST', body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.all }),
  });
}

export function useUpdateArticle(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<ArticleWritePayload>) =>
      apiRequest<ArticleDetail>(`${ADMIN}/articles/${id}`, { method: 'PATCH', body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.all }),
  });
}

export function useTransitionArticle(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { action: LifecycleAction; note?: string; change_summary?: string }) =>
      apiRequest<ArticleDetail>(`${ADMIN}/articles/${id}/transition`, {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.all }),
  });
}

export function useAddReviewNote(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { decision: string; note: string }) =>
      apiRequest<ReviewNote>(`${ADMIN}/articles/${id}/review-notes`, {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.reviewNotes(id) }),
  });
}

export function useReindex() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { article_ids?: string[]; only_stale?: boolean }) =>
      apiRequest<ReindexResult>(`${ADMIN}/indexing/reindex`, { method: 'POST', body: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.indexing }),
  });
}

export function useCreateTaxonomyTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      term_type: string;
      key: string;
      label: string;
      ticket_category_mapping?: string;
    }) => apiRequest<TaxonomyTerm>(`${ADMIN}/taxonomy`, { method: 'POST', body: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: knowledgeKeys.taxonomy }),
  });
}
