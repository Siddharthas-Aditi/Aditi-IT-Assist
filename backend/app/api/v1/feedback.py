"""Feedback API — post-chat survey and message-level reactions.

Endpoints:
  POST   /feedback/conversation/{session_id}           — submit/update survey
  GET    /feedback/conversation/{session_id}           — own feedback
  GET    /feedback/conversation/{session_id}/all       — all feedback (agent+)
  GET    /feedback/ticket/{ticket_id}                  — feedback for ticket (agent+)
  POST   /feedback/message/{message_id}                — message reaction
  GET    /feedback/analytics/summary                   — aggregate stats (lead+)
  GET    /feedback/analytics/articles                  — article health (lead+)
  GET    /feedback/analytics/agents/{agent_id}         — agent summary (lead+)
  GET    /feedback/review-queue                        — flagged items (lead+)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.schemas.feedback import (
    AgentFeedbackSummary,
    ArticleFeedbackSummary,
    ConversationFeedbackCreate,
    ConversationFeedbackResponse,
    FeedbackAnalyticsSummary,
    MessageFeedbackCreate,
    MessageFeedbackResponse,
)
from app.services.auth.dependencies import CurrentUser, ITAgentUser, ITLeadUser, require_permissions
from app.services.feedback_analytics_service import FeedbackAnalyticsService
from app.services.feedback_service import FeedbackService

router = APIRouter()


# ─── Dependency factories ──────────────────────────────────────────────────────


def get_service(db: AsyncSession = Depends(get_db)) -> FeedbackService:  # noqa: B008
    return FeedbackService(db)


def get_analytics_service(
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FeedbackAnalyticsService:
    return FeedbackAnalyticsService(db)


# ─── Conversation-level feedback ──────────────────────────────────────────────


@router.post(
    "/conversation/{session_id}",
    response_model=ConversationFeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit or update post-chat survey",
)
async def submit_conversation_feedback(
    session_id: str,
    payload: ConversationFeedbackCreate,
    current_user: Annotated[object, Depends(require_permissions(P.FEEDBACK_SUBMIT))],
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> ConversationFeedbackResponse:
    """Submit (or update) the post-chat survey for a support session.

    Idempotent: subsequent POSTs merge new answers into the existing row.
    Employees may only submit feedback for their own sessions.
    """
    try:
        return await service.submit_feedback(
            session_id=session_id,
            user_id=str(current_user.id),  # type: ignore[union-attr]
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/conversation/{session_id}",
    response_model=ConversationFeedbackResponse | None,
    summary="Get own feedback for a session",
)
async def get_own_conversation_feedback(
    session_id: str,
    current_user: Annotated[object, Depends(require_permissions(P.FEEDBACK_VIEW_OWN))],
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> ConversationFeedbackResponse | None:
    """Return the current user's survey response for a session, or null if not yet submitted."""
    return await service.get_session_feedback(
        session_id=session_id,
        user_id=str(current_user.id),  # type: ignore[union-attr]
    )


@router.get(
    "/conversation/{session_id}/all",
    response_model=list[ConversationFeedbackResponse],
    summary="Get all feedback for a session (agent+)",
)
async def get_session_feedback_all(
    session_id: str,
    _current_user: ITAgentUser,
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> list[ConversationFeedbackResponse]:
    """Return all feedback entries for a session. Requires it_agent or higher."""
    return await service.get_session_feedback_all(session_id=session_id)


@router.get(
    "/ticket/{ticket_id}",
    response_model=list[ConversationFeedbackResponse],
    summary="Get feedback linked to a ticket (agent+)",
)
async def get_ticket_feedback(
    ticket_id: str,
    _current_user: ITAgentUser,
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> list[ConversationFeedbackResponse]:
    """Return feedback entries linked to a specific ticket."""
    return await service.get_ticket_feedback(ticket_id=ticket_id)


# ─── Message-level feedback ────────────────────────────────────────────────────


@router.post(
    "/message/{message_id}",
    response_model=MessageFeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit thumbs up/down on an AI message",
)
async def submit_message_feedback(
    message_id: str,
    session_id: str = Query(..., description="Parent session ID"),
    payload: MessageFeedbackCreate = ...,  # type: ignore[assignment]
    current_user: Annotated[object, Depends(require_permissions(P.FEEDBACK_SUBMIT))] = ...,
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> MessageFeedbackResponse:
    """Submit or update an inline reaction on a specific AI message."""
    return await service.submit_message_feedback(
        message_id=message_id,
        session_id=session_id,
        user_id=str(current_user.id),  # type: ignore[union-attr]
        payload=payload,
    )


# ─── Analytics ────────────────────────────────────────────────────────────────


@router.get(
    "/analytics/summary",
    response_model=FeedbackAnalyticsSummary,
    summary="Aggregate feedback metrics (lead+)",
)
async def get_analytics_summary(
    _current_user: Annotated[
        object, Depends(require_permissions(P.FEEDBACK_VIEW_ANALYTICS))
    ],
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    category: str | None = Query(default=None),
    support_mode: str | None = Query(default=None),
    analytics: FeedbackAnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> FeedbackAnalyticsSummary:
    """Return aggregate CSAT, helpful rate, resolved rate, and mode comparison."""
    return await analytics.get_summary(
        from_dt=from_dt,
        to_dt=to_dt,
        category=category,
        support_mode=support_mode,
    )


@router.get(
    "/analytics/articles",
    response_model=dict[str, ArticleFeedbackSummary],
    summary="Per-article feedback health (lead+)",
)
async def get_article_health(
    article_ids: list[str] = Query(..., description="Comma-separated article UUIDs"),
    _current_user: Annotated[
        object, Depends(require_permissions(P.FEEDBACK_VIEW_ANALYTICS))
    ] = ...,
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    analytics: FeedbackAnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> dict[str, ArticleFeedbackSummary]:
    """Return feedback signals for specified knowledge articles."""
    return await analytics.get_article_health(
        article_ids, from_dt=from_dt, to_dt=to_dt
    )


@router.get(
    "/analytics/agents/{agent_id}",
    response_model=AgentFeedbackSummary,
    summary="Agent feedback summary (lead+)",
)
async def get_agent_feedback_summary(
    agent_id: uuid.UUID,
    _current_user: Annotated[
        object, Depends(require_permissions(P.FEEDBACK_VIEW_ANALYTICS))
    ],
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    analytics: FeedbackAnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> AgentFeedbackSummary:
    """Return CSAT / helpful / resolved rate for a specific IT agent."""
    return await analytics.get_agent_summary(
        agent_user_id=agent_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )


# ─── Review queue ─────────────────────────────────────────────────────────────


@router.get(
    "/review-queue",
    response_model=dict,
    summary="Flagged feedback review queue (lead+)",
)
async def get_review_queue(
    _current_user: Annotated[
        object, Depends(require_permissions(P.FEEDBACK_REVIEW))
    ],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    service: FeedbackService = Depends(get_service),  # noqa: B008
) -> dict:
    """Return paginated list of review-flagged feedback entries."""
    items, total = await service.list_flagged(
        limit=limit, offset=offset, category=category
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
