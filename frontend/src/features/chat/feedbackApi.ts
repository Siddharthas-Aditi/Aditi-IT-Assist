/**
 * React Query hooks for the feedback feature.
 * Consumed by PostChatFeedbackCard and MessageFeedbackControls.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  ConversationFeedback,
  ConversationFeedbackCreate,
  FeedbackAnalyticsSummary,
  FeedbackReviewQueueResponse,
  MessageFeedback,
  MessageFeedbackCreate,
} from '@/types/feedback';

// ── Conversation feedback ──────────────────────────────────────────────────────

export function useSessionFeedback(sessionId: string | null) {
  return useQuery<ConversationFeedback | null>({
    queryKey: ['feedback', 'conversation', sessionId],
    queryFn: () =>
      apiRequest<ConversationFeedback | null>(`/feedback/conversation/${sessionId}`),
    enabled: Boolean(sessionId),
  });
}

export function useSubmitFeedback(sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ConversationFeedback, Error, ConversationFeedbackCreate>({
    mutationFn: (payload) =>
      apiRequest<ConversationFeedback>(`/feedback/conversation/${sessionId}`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['feedback', 'conversation', sessionId] });
    },
  });
}

// ── Message feedback ───────────────────────────────────────────────────────────

export function useSubmitMessageFeedback(messageId: string, sessionId: string) {
  return useMutation<MessageFeedback, Error, MessageFeedbackCreate>({
    mutationFn: (payload) =>
      apiRequest<MessageFeedback>(
        `/feedback/message/${messageId}`,
        {
          method: 'POST',
          body: payload,
          query: { session_id: sessionId },
        },
      ),
  });
}

// ── Analytics (admin / lead) ───────────────────────────────────────────────────

export function useFeedbackAnalyticsSummary(params?: {
  from?: string;
  to?: string;
  category?: string;
}) {
  return useQuery<FeedbackAnalyticsSummary>({
    queryKey: ['feedback', 'analytics', 'summary', params],
    queryFn: () =>
      apiRequest<FeedbackAnalyticsSummary>('/feedback/analytics/summary', {
        query: params as Record<string, string>,
      }),
  });
}

// ── Review queue ───────────────────────────────────────────────────────────────

export function useFeedbackReviewQueue(params?: {
  limit?: number;
  offset?: number;
  category?: string;
}) {
  return useQuery<FeedbackReviewQueueResponse>({
    queryKey: ['feedback', 'review-queue', params],
    queryFn: () =>
      apiRequest<FeedbackReviewQueueResponse>('/feedback/review-queue', {
        query: params as Record<string, string | number>,
      }),
  });
}
