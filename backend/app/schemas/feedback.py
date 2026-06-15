"""Pydantic v2 schemas for the post-chat feedback feature.

Covers:
- Progressive-disclosure submission (full payload; UI drives step logic)
- Conversation-level and message-level responses
- Analytics aggregations: summary, article health, agent summaries
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────
# Enums (string literals for schema compatibility)
# ─────────────────────────────────────────────────────────────────────

SupportModeStr = Literal["ai_only", "ai_plus_live_agent", "live_agent_only"]
FeedbackSourceStr = Literal["inline_chat", "ticket_page", "followup"]
QualityBucketStr = Literal["positive", "neutral", "negative"]


# ─────────────────────────────────────────────────────────────────────
# Conversation-level feedback
# ─────────────────────────────────────────────────────────────────────


class ConversationFeedbackCreate(BaseModel):
    """Payload for submitting (or updating) post-chat survey answers.

    All survey fields are optional — the client may submit progressively
    through the 5-step wizard.  The service merges partial submissions
    into the existing row (idempotent upsert).
    """

    # Step 1 — Was this helpful?
    helpful: bool | None = Field(default=None, description="True = helpful, False = not helpful")

    # Step 2 — Was your issue resolved?
    resolved: bool | None = Field(default=None)

    # Step 3 — Star rating (optional)
    rating: int | None = Field(default=None, ge=1, le=5, description="1–5 star rating")

    # Step 4 — Free-text comment (optional)
    comment: str | None = Field(default=None, max_length=2000)

    # Submission context
    feedback_source: FeedbackSourceStr = "inline_chat"
    ticket_id: uuid.UUID | None = Field(default=None, description="Linked ticket, if any")

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class ConversationFeedbackResponse(BaseModel):
    """Full feedback record returned to the client."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    ticket_id: uuid.UUID | None
    submitted_by_user_id: uuid.UUID

    # Survey answers
    helpful: bool | None
    resolved: bool | None
    rating: int | None
    comment: str | None

    # Metadata
    submitted_at: datetime
    channel: str
    feedback_source: str
    support_mode: str

    # Session context
    escalation_occurred: bool
    category: str | None
    subcategory: str | None
    knowledge_article_ids: list[str] | None

    # Timing
    session_duration_seconds: int | None
    first_response_time_seconds: int | None

    # Derived
    quality_bucket: str | None
    review_flag: bool
    review_flag_reason: str | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# Message-level feedback
# ─────────────────────────────────────────────────────────────────────


class MessageFeedbackCreate(BaseModel):
    """Inline thumbs-up / thumbs-down reaction on an AI message."""

    helpful: bool = Field(description="True = thumbs up, False = thumbs down")
    comment: str | None = Field(default=None, max_length=500)
    knowledge_article_ids: list[str] | None = Field(default=None)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class MessageFeedbackResponse(BaseModel):
    """Message feedback record returned to the client."""

    id: uuid.UUID
    message_id: uuid.UUID
    session_id: uuid.UUID
    submitted_by_user_id: uuid.UUID
    helpful: bool
    comment: str | None
    knowledge_article_ids: list[str] | None
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# Analytics aggregations
# ─────────────────────────────────────────────────────────────────────


class FeedbackAnalyticsSummary(BaseModel):
    """Aggregate feedback metrics for a time period, optionally filtered."""

    period_start: datetime
    period_end: datetime

    total_submissions: int = 0

    # Rates (0.0–1.0)
    helpful_rate: float | None = None
    resolved_rate: float | None = None
    response_rate: float | None = None  # # sessions with feedback / total sessions

    # CSAT (1–5 avg)
    csat_avg: float | None = None

    # Mode split
    ai_only_count: int = 0
    ai_plus_live_agent_count: int = 0
    live_agent_only_count: int = 0

    # AI-only sub-metrics
    ai_only_helpful_rate: float | None = None
    ai_only_resolved_rate: float | None = None
    ai_only_csat_avg: float | None = None

    # Live-agent sub-metrics
    live_agent_helpful_rate: float | None = None
    live_agent_resolved_rate: float | None = None
    live_agent_csat_avg: float | None = None

    # Quality buckets
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0

    # Escalation
    escalation_rate: float | None = None
    escalated_resolved_rate: float | None = None

    # Category breakdown (top 10)
    category_breakdown: dict[str, int] = Field(default_factory=dict)

    # Review queue
    flagged_count: int = 0


class ArticleFeedbackSummary(BaseModel):
    """Feedback signals for a single knowledge article."""

    article_id: str
    total_sessions_used: int = 0
    positive_sessions: int = 0
    negative_sessions: int = 0
    avg_rating: float | None = None
    helpful_rate: float | None = None
    resolved_rate: float | None = None
    flag_count: int = 0          # sessions where review_flag=True and article was cited
    flag_threshold_breached: bool = False


class AgentFeedbackSummary(BaseModel):
    """Aggregate feedback for a specific live IT agent."""

    agent_user_id: uuid.UUID
    total_sessions: int = 0
    sessions_with_feedback: int = 0
    helpful_rate: float | None = None
    resolved_rate: float | None = None
    csat_avg: float | None = None
    positive_count: int = 0
    negative_count: int = 0
    period_start: datetime
    period_end: datetime
