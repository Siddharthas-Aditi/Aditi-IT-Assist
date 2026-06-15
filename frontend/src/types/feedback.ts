/**
 * TypeScript types for the post-chat feedback feature.
 *
 * Mirrors backend/app/schemas/feedback.py exactly.
 */

export type SupportMode = 'ai_only' | 'ai_plus_live_agent' | 'live_agent_only';
export type FeedbackSource = 'inline_chat' | 'ticket_page' | 'followup';
export type QualityBucket = 'positive' | 'neutral' | 'negative';

// ── Conversation-level feedback ────────────────────────────────────────────────

export interface ConversationFeedbackCreate {
  helpful?: boolean | null;
  resolved?: boolean | null;
  rating?: number | null;   // 1–5
  comment?: string | null;
  feedback_source?: FeedbackSource;
  ticket_id?: string | null;
}

export interface ConversationFeedback {
  id: string;
  conversation_id: string;
  ticket_id: string | null;
  submitted_by_user_id: string;

  // Survey answers
  helpful: boolean | null;
  resolved: boolean | null;
  rating: number | null;
  comment: string | null;

  // Metadata
  submitted_at: string;
  channel: string;
  feedback_source: FeedbackSource;
  support_mode: SupportMode;

  // Session context
  escalation_occurred: boolean;
  category: string | null;
  subcategory: string | null;
  knowledge_article_ids: string[] | null;

  // Timing
  session_duration_seconds: number | null;
  first_response_time_seconds: number | null;

  // Derived
  quality_bucket: QualityBucket | null;
  review_flag: boolean;
  review_flag_reason: string | null;

  created_at: string;
  updated_at: string;
}

// ── Message-level feedback ─────────────────────────────────────────────────────

export interface MessageFeedbackCreate {
  helpful: boolean;
  comment?: string | null;
  knowledge_article_ids?: string[] | null;
}

export interface MessageFeedback {
  id: string;
  message_id: string;
  session_id: string;
  submitted_by_user_id: string;
  helpful: boolean;
  comment: string | null;
  knowledge_article_ids: string[] | null;
  submitted_at: string;
  created_at: string;
  updated_at: string;
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface FeedbackAnalyticsSummary {
  period_start: string;
  period_end: string;
  total_submissions: number;

  helpful_rate: number | null;
  resolved_rate: number | null;
  response_rate: number | null;
  csat_avg: number | null;

  ai_only_count: number;
  ai_plus_live_agent_count: number;
  live_agent_only_count: number;

  ai_only_helpful_rate: number | null;
  ai_only_resolved_rate: number | null;
  ai_only_csat_avg: number | null;

  live_agent_helpful_rate: number | null;
  live_agent_resolved_rate: number | null;
  live_agent_csat_avg: number | null;

  positive_count: number;
  neutral_count: number;
  negative_count: number;

  escalation_rate: number | null;
  escalated_resolved_rate: number | null;

  category_breakdown: Record<string, number>;
  flagged_count: number;
}

export interface ArticleFeedbackSummary {
  article_id: string;
  total_sessions_used: number;
  positive_sessions: number;
  negative_sessions: number;
  avg_rating: number | null;
  helpful_rate: number | null;
  resolved_rate: number | null;
  flag_count: number;
  flag_threshold_breached: boolean;
}

export interface AgentFeedbackSummary {
  agent_user_id: string;
  total_sessions: number;
  sessions_with_feedback: number;
  helpful_rate: number | null;
  resolved_rate: number | null;
  csat_avg: number | null;
  positive_count: number;
  negative_count: number;
  period_start: string;
  period_end: string;
}

// ── Review queue ───────────────────────────────────────────────────────────────

export interface FeedbackReviewQueueResponse {
  items: ConversationFeedback[];
  total: number;
  limit: number;
  offset: number;
}
