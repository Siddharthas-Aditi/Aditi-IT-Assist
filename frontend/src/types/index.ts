/** Shared types for the Aditi IT Assist frontend. */

export interface ResolutionStep {
  step_number: number;
  instruction: string;
  details?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  confidence?: number;
  category?: string;
  steps?: ResolutionStep[];
  requiresEscalation?: boolean;
  followUpQuestion?: string;
  timestamp: Date;
}

export interface ChatResponse {
  session_id: string;
  message_id: string;
  content: string;
  confidence_score: number;
  issue_category: string | null;
  resolution_steps: ResolutionStep[];
  requires_escalation: boolean;
  follow_up_question: string | null;
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
