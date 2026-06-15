/** Ingestion pipeline types — mirror of backend `schemas/ingestion.py`. */

// ── Enums ──────────────────────────────────────────────────────────────────
export type ParseStatus = 'pending' | 'extracting' | 'parsing' | 'completed' | 'failed';
export type ExtractionStatus = 'pending' | 'completed' | 'failed';
export type CandidateReviewStatus = 'pending' | 'approved' | 'rejected' | 'saved';
export type WarningSeverity = 'error' | 'warning' | 'info';
export type AllowedExtension = 'docx' | 'pdf' | 'pptx' | 'txt' | 'md';

// ── Step ───────────────────────────────────────────────────────────────────
export interface ExtractionStep {
  step_number: number;
  instruction: string;
  details: string;
}

// ── Warning ────────────────────────────────────────────────────────────────
export interface IngestionWarning {
  code: string;
  message: string;
  severity: WarningSeverity;
}

// ── IngestionJob ───────────────────────────────────────────────────────────
export interface IngestionJobSummary {
  id: string;
  source_filename: string;
  source_type: string;
  source_size: number | null;
  parse_status: ParseStatus;
  extraction_status: ExtractionStatus;
  candidate_count: number;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestionJobDetail extends IngestionJobSummary {
  processing_summary: Record<string, number> | null;
  parser_version: string | null;
  error_details: string | null;
  raw_text_ref: string | null;
}

// ── Candidate ──────────────────────────────────────────────────────────────
export interface IngestionCandidateSummary {
  id: string;
  ingestion_job_id: string;
  candidate_index: number;
  extracted_title: string | null;
  extracted_category: string | null;
  extracted_subcategory: string | null;
  extracted_confidence: number | null;
  review_status: CandidateReviewStatus;
  mapped_article_id: string | null;
  warning_count: number;
  created_at: string;
}

export interface IngestionCandidateDetail {
  id: string;
  ingestion_job_id: string;
  candidate_index: number;
  extracted_title: string | null;
  extracted_summary: string | null;
  extracted_category: string | null;
  extracted_subcategory: string | null;
  extracted_product_or_system: string | null;
  extracted_platform: string | null;
  extracted_symptoms: string[] | null;
  extracted_troubleshooting_steps: ExtractionStep[] | null;
  extracted_resolution_steps: ExtractionStep[] | null;
  extracted_escalation_criteria: string | null;
  extracted_tags: string[] | null;
  extracted_keywords: string[] | null;
  extracted_owner_group: string | null;
  extracted_confidence: number | null;
  validation_warnings: IngestionWarning[] | null;
  review_status: CandidateReviewStatus;
  mapped_article_id: string | null;
  raw_segment_text: string | null;
  normalized_payload_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateUpdatePayload {
  extracted_title?: string;
  extracted_summary?: string;
  extracted_category?: string;
  extracted_subcategory?: string;
  extracted_product_or_system?: string;
  extracted_platform?: string;
  extracted_symptoms?: string[];
  extracted_troubleshooting_steps?: ExtractionStep[];
  extracted_resolution_steps?: ExtractionStep[];
  extracted_escalation_criteria?: string;
  extracted_tags?: string[];
  extracted_keywords?: string[];
  extracted_owner_group?: string;
}

// ── Save / reject ──────────────────────────────────────────────────────────
export interface SaveCandidateRequest {
  ownership_group_id?: string;
  author_override?: string;
}

export interface SaveCandidateResponse {
  candidate_id: string;
  article_id: string;
  article_slug: string | null;
  message: string;
}

export interface RejectCandidateRequest {
  reason?: string;
}

// ── Bulk save ──────────────────────────────────────────────────────────────
export interface BulkSaveRequest {
  candidate_ids: string[];
  ownership_group_id?: string;
}

export interface BulkSaveResult {
  candidate_id: string;
  success: boolean;
  article_id: string | null;
  error: string | null;
}

export interface BulkSaveResponse {
  saved: number;
  failed: number;
  results: BulkSaveResult[];
}

// ── Upload / pipeline ──────────────────────────────────────────────────────
export interface UploadResponse {
  job_id: string;
  source_filename: string;
  source_type: string;
  parse_status: ParseStatus;
  message: string;
}

export interface PipelineStatusResponse {
  job: IngestionJobDetail;
  candidates_pending: number;
  candidates_approved: number;
  candidates_rejected: number;
  candidates_saved: number;
}

// ── Duplicate match ────────────────────────────────────────────────────────
export interface DuplicateCandidateMatch {
  article_id: string;
  title: string;
  category: string | null;
  similarity_score: number;
  match_reason: string;
}
