"""Schemas for RBAC-scoped analytics reports (Workstream 4).

All values that cannot be computed (no data in window) are ``None``, not
fabricated numbers — the frontend renders that as "No data".

Data-gap notes
--------------
- ``KBEffectivenessReport`` uses ``successful_resolution_count`` on
  ``KnowledgeArticle`` (incremented by the knowledge improvement loop) as the
  proxy for citation-led resolution. Per-session citation-to-outcome linking
  would require a dedicated citation-session join table, which does not yet
  exist.
- ``WorkloadReport.agentic_dispatches`` uses the ``agent_action_ledger``
  introduced in Workstream 1.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResolutionTrendPoint(BaseModel):
    """One data point in the resolution-time trend series."""

    date: str  # ISO YYYY-MM-DD
    avg_resolution_hours: float | None = None
    ticket_count: int = 0


class ResolutionTrendReport(BaseModel):
    points: list[ResolutionTrendPoint] = []
    overall_avg_hours: float | None = None
    window_start: datetime
    window_end: datetime


class EscalationRateReport(BaseModel):
    total_sessions: int = 0
    escalated_sessions: int = 0
    escalation_rate: float | None = None  # 0..1; None when no sessions
    avg_confidence_at_escalation: float | None = None
    window_start: datetime
    window_end: datetime


class KBArticleEffectivenessRow(BaseModel):
    article_id: str
    title: str
    category: str | None = None
    successful_resolutions: int = 0
    quality_score: float | None = None


class KBEffectivenessReport(BaseModel):
    """KB article effectiveness — proxy metric via successful_resolution_count.

    Data gap: per-session citation-to-outcome linking is not yet persisted.
    This report uses the denormalised ``successful_resolution_count`` counter
    on ``KnowledgeArticle`` as the best available proxy.
    """

    articles: list[KBArticleEffectivenessRow] = []
    total_published: int = 0
    articles_with_zero_resolutions: int = 0


class AgentWorkloadRow(BaseModel):
    agent_id: str
    agent_name: str
    open_tickets: int = 0
    resolved_this_window: int = 0
    agentic_dispatches: int = 0  # from agent_action_ledger


class WorkloadReport(BaseModel):
    agents: list[AgentWorkloadRow] = []
    window_start: datetime
    window_end: datetime


class SLAComplianceReport(BaseModel):
    total_tickets: int = 0
    within_sla: int = 0
    breached: int = 0
    at_risk: int = 0
    compliance_rate: float | None = None  # None when no tickets
    window_start: datetime
    window_end: datetime


class FeedbackSentimentReport(BaseModel):
    total_responses: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    avg_rating: float | None = None
    positive_rate: float | None = None
    window_start: datetime
    window_end: datetime
