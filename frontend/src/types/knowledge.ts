/** Knowledge management types — mirror of backend `schemas/knowledge.py`. */

export type ArticleStatus = 'draft' | 'in_review' | 'approved' | 'published' | 'archived';
export type ArticleType =
  | 'troubleshooting'
  | 'how_to'
  | 'faq'
  | 'known_error'
  | 'policy'
  | 'reference';
export type Audience = 'employee' | 'it_staff' | 'admin';
export type VisibilityScope = 'public_internal' | 'it_only' | 'admin_only';

export type LifecycleAction =
  | 'submit_for_review'
  | 'approve'
  | 'request_changes'
  | 'reject'
  | 'publish'
  | 'archive'
  | 'restore'
  | 'create_revision';

export interface Step {
  step_number: number;
  instruction: string;
  details?: string | null;
}

export interface ArticleSummary {
  id: string;
  slug?: string | null;
  title: string;
  short_summary?: string | null;
  status: ArticleStatus;
  article_type: ArticleType;
  category: string;
  subcategory?: string | null;
  product_or_system?: string | null;
  platform?: string | null;
  audience: Audience;
  version: number;
  tags: string[];
  ownership_group_id?: string | null;
  embedding_status: string;
  quality_score?: number | null;
  view_count: number;
  usage_count: number;
  feedback_score?: number | null;
  next_review_due_at?: string | null;
  is_stale: boolean;
  updated_at?: string | null;
}

export interface ArticleDetail extends ArticleSummary {
  content?: string | null;
  keywords: string[];
  issue_type?: string | null;
  severity_hint?: string | null;
  visibility_scope: VisibilityScope;
  symptoms: string[];
  probable_causes: string[];
  prerequisites: string[];
  troubleshooting_steps: Step[];
  resolution_steps: Step[];
  validation_steps: Step[];
  escalation_criteria?: string | null;
  escalation_target_team?: string | null;
  references: Array<Record<string, unknown>>;
  related_articles: string[];
  citation_label?: string | null;
  source_type?: string | null;
  source_reference?: string | null;
  author_id?: string | null;
  reviewer_id?: string | null;
  approver_id?: string | null;
  confidence_level?: number | null;
  last_reviewed_at?: string | null;
  published_at?: string | null;
  archived_at?: string | null;
  indexed_at?: string | null;
  index_version: number;
  successful_resolution_count: number;
  negative_feedback_count: number;
  available_actions: LifecycleAction[];
  created_at?: string | null;
}

export interface ArticleListResponse {
  articles: ArticleSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArticleWritePayload {
  title: string;
  short_summary?: string | null;
  article_type?: ArticleType;
  audience?: Audience;
  visibility_scope?: VisibilityScope;
  category: string;
  subcategory?: string | null;
  product_or_system?: string | null;
  platform?: string | null;
  issue_type?: string | null;
  severity_hint?: string | null;
  tags?: string[];
  keywords?: string[];
  ownership_group_id?: string | null;
  content?: string | null;
  symptoms?: string[];
  probable_causes?: string[];
  prerequisites?: string[];
  troubleshooting_steps?: Step[];
  resolution_steps?: Step[];
  validation_steps?: Step[];
  escalation_criteria?: string | null;
  escalation_target_team?: string | null;
  references?: Array<Record<string, unknown>>;
  related_articles?: string[];
  citation_label?: string | null;
  review_interval_days?: number;
}

export interface VersionSummary {
  id: string;
  version: number;
  title: string;
  status: string;
  change_summary?: string | null;
  author_id?: string | null;
  created_at: string;
}

export interface VersionDetail extends VersionSummary {
  snapshot: Record<string, unknown>;
}

export interface ReviewNote {
  id: string;
  reviewer_id?: string | null;
  decision: string;
  note?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  created_at: string;
}

export interface FeedbackItem {
  id: string;
  article_id: string;
  rating?: number | null;
  was_helpful?: boolean | null;
  comment?: string | null;
  source: string;
  created_at: string;
}

export interface TaxonomyTerm {
  id: string;
  term_type: string;
  key: string;
  label: string;
  description?: string | null;
  parent_id?: string | null;
  ticket_category_mapping?: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface OwnershipGroup {
  id: string;
  name: string;
  display_name: string;
  description?: string | null;
  owner_id?: string | null;
  default_reviewer_id?: string | null;
  member_ids: string[];
  is_active: boolean;
}

export interface RetrievalChunk {
  chunk_index: number;
  section: string;
  header: string;
  content: string;
  token_estimate: number;
  embedding_status: string;
}

export interface RetrievalPreview {
  article_id: string;
  citation_label: string;
  chunking_strategy: string;
  retrieval_text: string;
  chunks: RetrievalChunk[];
  total_tokens: number;
  warnings: string[];
}

export interface IndexingStatus {
  total_articles: number;
  published_articles: number;
  indexed_articles: number;
  pending_articles: number;
  stale_articles: number;
  failed_articles: number;
  total_chunks: number;
  index_version: number;
  last_indexed_at?: string | null;
  vector_store: string;
}

export interface ReindexResult {
  requested: number;
  reindexed: number;
  chunks_written: number;
  skipped: number;
  errors: string[];
}

export interface ArticleAnalytics {
  article_id: string;
  title: string;
  status: string;
  view_count: number;
  usage_count: number;
  successful_resolution_count: number;
  feedback_score?: number | null;
  negative_feedback_count: number;
  resolution_rate?: number | null;
  quality_score?: number | null;
  is_stale: boolean;
}

export interface KnowledgeAnalyticsSummary {
  total_articles: number;
  by_status: Record<string, number>;
  published_articles: number;
  stale_articles: number;
  avg_quality_score?: number | null;
  total_views: number;
  total_usage: number;
  avg_resolution_rate?: number | null;
  top_articles: ArticleAnalytics[];
  low_performers: ArticleAnalytics[];
}

export interface ArticleFilters {
  status?: ArticleStatus | '';
  category?: string;
  product_or_system?: string;
  platform?: string;
  audience?: Audience | '';
  ownership_group_id?: string;
  search?: string;
  review_due?: boolean;
  limit?: number;
  offset?: number;
}

// ─────────────────────────────────────────────────────────────────────
// Quality, completeness, stale analysis, templates
// ─────────────────────────────────────────────────────────────────────

export interface DimensionScore {
  name: string;
  label: string;
  score: number;            // 0.0 – 1.0
  earned: string[];
  missing: string[];
}

export interface CompletenessReport {
  score: number;            // 0 – 100
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  dimensions: DimensionScore[];
  ready_for_review: boolean;
  ready_for_publish: boolean;
  blocking_issues: string[];
  suggestions: string[];
}

export type WarningSeverity = 'error' | 'warning' | 'info';

export interface AuthorWarning {
  severity: WarningSeverity;
  field?: string | null;
  message: string;
  guidance?: string | null;
}

export interface StaleAnalysis {
  is_stale: boolean;
  staleness_score: number;         // 0.0 (fresh) – 1.0 (very stale)
  days_since_update?: number | null;
  days_overdue?: number | null;
  reasons: string[];
  recommendations: string[];
}

export interface ArticleTemplate {
  key: string;
  label: string;
  category: string;
  subcategory: string;
  product_or_system: string;
  description: string;
  icon: string;
}

export interface DuplicateHint {
  id: string;
  title: string;
  status: string;
}

