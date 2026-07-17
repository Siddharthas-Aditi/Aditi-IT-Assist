"""Pydantic schemas for remote support session lifecycle."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic evaluates these annotations at runtime
from typing import Literal

from pydantic import BaseModel, Field

# ── Request Schemas ───────────────────────────────────────────────────


class RemoteSessionRequestCreate(BaseModel):
    """IT agent requests a new remote support session."""

    employee_id: str = Field(..., description="UUID of the employee to assist")
    session_type: Literal["screen_view", "screen_control"] = "screen_view"
    ticket_id: str | None = Field(None, description="Associated ticket UUID")
    support_session_id: str | None = Field(
        None,
        description=(
            "Live specialist-chat session UUID this remote session was launched "
            "from — completes the audit chain chat → ticket → remote session"
        ),
    )
    justification: str | None = Field(
        None,
        max_length=1000,
        description="Reason for requesting remote access (required for screen_control)",
    )
    max_duration_minutes: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Maximum session duration; hard-enforced",
    )


class ConsentDecision(BaseModel):
    """Employee grants or denies consent for a remote session."""

    granted: bool
    denial_reason: str | None = Field(
        None,
        max_length=500,
        description="Optional reason when denying (surfaced to agent)",
    )


class ConsentRevoke(BaseModel):
    """Employee revokes active consent mid-session."""

    reason: str | None = Field(None, max_length=500)


class SessionEndRequest(BaseModel):
    """End a remote session with resolution notes."""

    resolution_notes: str | None = Field(None, max_length=4000)
    actions_taken: list[str] | None = Field(
        None, description="Structured list of actions performed"
    )


class ResolutionNotesUpdate(BaseModel):
    """Update resolution notes after session ends."""

    resolution_notes: str = Field(..., max_length=4000)
    actions_taken: list[str] | None = None


# ── Response Schemas ──────────────────────────────────────────────────


class ConsentResponse(BaseModel):
    """Consent record returned in API responses."""

    id: str
    session_id: str
    consent_type: str
    granted: bool
    consented_at: datetime
    revoked_at: datetime | None
    denial_reason: str | None

    model_config = {"from_attributes": True}


class SessionEventResponse(BaseModel):
    """Single lifecycle event for a session."""

    id: str
    event_type: str
    actor_id: str | None
    occurred_at: datetime
    description: str | None
    context_data: dict | None = None

    model_config = {"from_attributes": True}


class RemoteSessionResponse(BaseModel):
    """Full remote session detail response."""

    id: str
    employee_id: str
    agent_id: str
    ticket_id: str | None
    session_type: str
    status: str
    provider: str

    # Join metadata (only returned to agent + employee in their respective roles)
    join_url_agent: str | None
    join_url_employee: str | None
    join_code: str | None

    # Timing
    requested_at: datetime
    consent_sent_at: datetime | None
    consent_deadline: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    max_duration_minutes: int
    duration_seconds: int | None

    # Policy
    justification: str | None
    policy_check_passed: bool
    termination_reason: str | None

    # Post-session
    resolution_notes: str | None
    actions_taken: list | None

    # Related records
    consents: list[ConsentResponse]
    events: list[SessionEventResponse]

    model_config = {"from_attributes": True}


class RemoteSessionSummary(BaseModel):
    """Lightweight session summary for list endpoints."""

    id: str
    employee_id: str
    agent_id: str
    ticket_id: str | None
    session_type: str
    status: str
    provider: str
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    termination_reason: str | None

    model_config = {"from_attributes": True}


class SessionLaunchInfo(BaseModel):
    """Launch metadata returned after session is ready to connect.

    Returned only once after consent_granted → connecting transition.
    Contains the deep-link URLs to hand off to the external tool.
    """

    session_id: str
    provider: str
    provider_display_name: str
    join_url: str = Field(..., description="Deep-link URL for this user's role")
    join_code: str | None = Field(None, description="Numeric code if provider uses codes")
    instructions: str
    expires_at: datetime | None


class ConsentNotification(BaseModel):
    """Payload sent to employee when a remote session is requested.

    Used to populate the consent modal in the frontend.
    """

    session_id: str
    agent_name: str
    agent_email: str
    session_type: str
    session_type_label: str  # "View Only" | "Full Control"
    justification: str | None
    consent_deadline: datetime
    consent_text: str  # Full legal-style consent notice
    ticket_reference: str | None


class ProviderHealthResponse(BaseModel):
    """Health status of configured remote support provider."""

    provider_name: str
    display_name: str
    healthy: bool
    capabilities: list[str]
    supports_unattended: bool
    error: str | None
