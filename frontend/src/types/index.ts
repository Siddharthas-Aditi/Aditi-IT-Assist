/** Shared types for the Aditi IT Assist frontend. */

export interface ResolutionStep {
  step_number: number;
  instruction: string;
  details?: string;
}

export interface QuickReplyOption {
  label: string;
  value: string;
}

/** Developer trace attached to assistant messages for IT/admin roles only. */
export interface ChatDebugInfo {
  normalized_system?: string | null;
  issue_subtype?: string | null;
  subtype_confidence?: number;
  conversation_phase?: string | null;
  loop_counter?: number;
  suggested_steps?: string[];
  failed_steps?: string[];
  confidence_breakdown?: Record<string, number> | null;
  retrieval_trace?: Record<string, unknown> | null;
  escalation_reason?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  confidence?: number;
  category?: string;
  subtype?: string;
  steps?: ResolutionStep[];
  requiresEscalation?: boolean;
  followUpQuestion?: string;
  quickReplies?: QuickReplyOption[];
  conversationPhase?: string;
  resolved?: boolean;
  debug?: ChatDebugInfo;
  timestamp: Date;
}

export interface ChatResponse {
  session_id: string;
  message_id: string;
  content: string;
  confidence_score: number;
  issue_category: string | null;
  issue_subtype: string | null;
  resolution_steps: ResolutionStep[];
  requires_escalation: boolean;
  follow_up_question: string | null;
  quick_replies: QuickReplyOption[] | null;
  conversation_phase: string | null;
  resolved: boolean;
  debug: ChatDebugInfo | null;
}

export interface Ticket {
  ticket_id: string;
  title: string;
  description: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  category: string | null;
  assigned_to: string | null;
  created_at: string;
}

export interface TicketListResponse {
  tickets: Ticket[];
  total: number;
  limit: number;
  offset: number;
}

export interface KnowledgeArticle {
  id: string;
  title: string;
  category: string;
  content: string;
  steps: Record<string, unknown>[];
  tags: string[];
}

export interface KnowledgeSearchResponse {
  results: KnowledgeArticle[];
  total: number;
  query: string;
}
