"""Schemas for the live specialist-chat API.

Kept separate from ``schemas/chat.py`` (the AI chat) and
``schemas/specialist_queue.py`` (the queue), because the *active live chat*
is its own concern with its own evolving fields.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SpecialistChatStatus = Literal[
    "active",
    "idle_warning",
    "ended_by_user",
    "ended_by_specialist",
    "ended_by_timeout",
    "ended_by_system",
]

SpecialistChatEndReason = Literal[
    "resolved",
    "user_left",
    "specialist_ended",
    "idle_timeout",
    "session_error",
]

SpecialistMessageRole = Literal["user", "specialist", "system"]


class StartLiveChatRequest(BaseModel):
    """Body for starting a live specialist chat after a ticket claim."""

    ticket_id: UUID
    idle_warning_seconds: int = Field(120, ge=30, le=600)
    idle_end_seconds: int = Field(180, ge=60, le=1200)


class SpecialistChatMessageOut(BaseModel):
    """One message in the transcript."""

    id: UUID
    role: SpecialistMessageRole
    content: str
    system_event: str | None = None
    sender_id: UUID | None = None
    created_at: datetime


class SpecialistChatSessionOut(BaseModel):
    """Full state of a live session for the client to render."""

    id: UUID
    ticket_id: UUID
    ticket_number: str | None = None
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    specialist_id: UUID
    specialist_name: str | None = None
    specialist_email: str | None = None
    status: SpecialistChatStatus
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None = None
    end_reason: SpecialistChatEndReason | None = None
    idle_warning_seconds: int
    idle_end_seconds: int
    messages: list[SpecialistChatMessageOut] = Field(default_factory=list)


class SendSpecialistMessageRequest(BaseModel):
    """Body for posting a message into a live session."""

    content: str = Field(..., min_length=1, max_length=8000)


class EndLiveChatRequest(BaseModel):
    """Body for ending a live session."""

    reason: SpecialistChatEndReason
    resolution_notes: str | None = None
    propose_knowledge_candidate: bool = Field(
        False,
        description=(
            "When True, the resolution notes are sent to the Knowledge "
            "Improvement review queue as a candidate (NEVER auto-published)."
        ),
    )


class EndLiveChatResponse(BaseModel):
    session_id: UUID
    status: SpecialistChatStatus
    end_reason: SpecialistChatEndReason
    knowledge_candidate_id: UUID | None = None


class MyAssignedItem(BaseModel):
    """One entry on the specialist's 'My Assigned' list."""

    ticket_id: UUID
    ticket_number: str
    title: str
    priority: Literal["low", "medium", "high", "critical"]
    issue_subtype: str | None = None
    user_name: str | None = None
    live_session_id: UUID | None = None
    live_status: SpecialistChatStatus | None = None
    last_activity_at: datetime | None = None


class MyAssignedResponse(BaseModel):
    total: int
    items: list[MyAssignedItem]
