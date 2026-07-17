"""Remote support API — session orchestration, consent management, and audit.

Endpoint groups:
  IT Agent endpoints (require it_agent role or above):
    POST   /remote-support/sessions                  — request new session
    POST   /remote-support/sessions/{id}/send-consent — push consent to employee
    POST   /remote-support/sessions/{id}/launch       — create provider session
    POST   /remote-support/sessions/{id}/connected    — mark as actively connected
    POST   /remote-support/sessions/{id}/end          — end session with notes
    PUT    /remote-support/sessions/{id}/resolution   — update resolution notes
    GET    /remote-support/sessions                   — list sessions
    GET    /remote-support/sessions/{id}              — get session detail
    GET    /remote-support/sessions/{id}/status       — poll provider status

  Employee endpoints (require authentication):
    GET    /remote-support/sessions/{id}/consent-info — get consent modal payload
    POST   /remote-support/sessions/{id}/consent      — grant or deny consent
    POST   /remote-support/sessions/{id}/revoke       — revoke consent mid-session
    GET    /remote-support/my-sessions                — employee's own sessions

  System:
    GET    /remote-support/provider/health            — provider connectivity check
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.remote_support import (
    ConsentDecision,
    ConsentNotification,
    ConsentRevoke,
    ProviderHealthResponse,
    RemoteSessionRequestCreate,
    RemoteSessionResponse,
    RemoteSessionSummary,
    ResolutionNotesUpdate,
    SessionEndRequest,
    SessionLaunchInfo,
)
from app.services.auth.dependencies import CurrentUser, ITAgentUser
from app.services.remote_support.service import (
    ConsentRequired,
    InvalidTransition,
    PolicyViolation,
    RemoteSupportService,
    SessionNotFound,
)

router = APIRouter()


def _get_service(db: AsyncSession) -> RemoteSupportService:
    return RemoteSupportService(db)


def _handle_errors(exc: Exception) -> None:
    """Convert service errors to appropriate HTTP responses."""
    if isinstance(exc, SessionNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PolicyViolation):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ConsentRequired):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InvalidTransition):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


# ── IT Agent Endpoints ────────────────────────────────────────────────


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Request a remote support session",
)
async def request_remote_session(
    data: RemoteSessionRequestCreate,
    agent: ITAgentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """IT agent requests a remote session with an employee.

    - `screen_view` requires `it_agent` role or above
    - `screen_control` requires `it_lead` or `it_admin`, plus a justification
    - Consent notification is automatically queued to the employee
    """
    svc = _get_service(db)
    try:
        session = await svc.request_session(
            agent=agent,
            employee_id=uuid.UUID(data.employee_id),
            session_type=data.session_type,
            ticket_id=uuid.UUID(data.ticket_id) if data.ticket_id else None,
            support_session_id=(
                uuid.UUID(data.support_session_id) if data.support_session_id else None
            ),
            justification=data.justification,
            max_duration_minutes=data.max_duration_minutes,
            ip_address=request.client.host if request.client else None,
        )
        # Automatically mark consent as pending
        await svc.send_consent_request(session.id, agent)
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {
        "session_id": str(session.id),
        "status": session.status,
        "session_type": session.session_type,
        "consent_deadline": session.consent_deadline.isoformat()
        if session.consent_deadline
        else None,
        "message": "Consent request sent to employee",
    }


@router.post(
    "/sessions/{session_id}/launch",
    summary="Launch provider session after consent is granted",
)
async def launch_remote_session(
    session_id: str,
    agent: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionLaunchInfo:
    """Create a session at the external provider (e.g. Microsoft Remote Help).

    Returns the join URL the agent should open in the remote support client.
    The employee will separately receive a notification to open the join URL
    in their installed client.

    Requires: `consent_granted` status.
    """
    svc = _get_service(db)
    try:
        session = await svc.launch_session(uuid.UUID(session_id), agent)
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    provider = svc._resolve_provider(session.provider)

    return SessionLaunchInfo(
        session_id=str(session.id),
        provider=session.provider,
        provider_display_name=provider.display_name,
        join_url=session.join_url_agent or "",
        join_code=session.join_code,
        instructions=(
            f"Open {provider.display_name} and the session will connect automatically. "
            f"The employee has been notified to accept on their device."
        ),
        expires_at=None,
    )


@router.post(
    "/sessions/{session_id}/connected",
    summary="Mark session as actively connected",
)
async def mark_session_connected(
    session_id: str,
    agent: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Confirm that the agent has connected to the remote session.

    Called by the client after the remote tool confirms connection.
    """
    svc = _get_service(db)
    try:
        session = await svc.mark_connected(uuid.UUID(session_id), agent)
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {
        "session_id": str(session.id),
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }


@router.post(
    "/sessions/{session_id}/end",
    summary="End a remote session",
)
async def end_remote_session(
    session_id: str,
    data: SessionEndRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """End a remote session. Can be called by the agent, employee, or admin.

    Optionally include resolution notes and a list of actions taken.
    """
    svc = _get_service(db)
    try:
        session = await svc.end_session(
            session_id=uuid.UUID(session_id),
            actor=current_user,
            resolution_notes=data.resolution_notes,
            actions_taken=data.actions_taken,
        )
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {
        "session_id": str(session.id),
        "status": session.status,
        "duration_seconds": session.duration_seconds,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


@router.put(
    "/sessions/{session_id}/resolution",
    summary="Update resolution notes after session ends",
)
async def update_resolution_notes(
    session_id: str,
    data: ResolutionNotesUpdate,
    agent: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Update or add resolution notes to a completed session."""
    svc = _get_service(db)
    try:
        session = await svc.update_resolution_notes(
            session_id=uuid.UUID(session_id),
            agent=agent,
            resolution_notes=data.resolution_notes,
            actions_taken=data.actions_taken,
        )
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {"session_id": str(session.id), "message": "Resolution notes updated"}


@router.get(
    "/sessions",
    summary="List remote sessions",
    response_model=list[RemoteSessionSummary],
)
async def list_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RemoteSessionSummary]:
    """List remote sessions visible to the current user.

    - Employees see only their own sessions
    - Agents see sessions they initiated
    - IT Leads, Admins, Auditors see all sessions
    """
    svc = _get_service(db)
    sessions = await svc.list_sessions(
        current_user, status=status_filter, limit=limit, offset=offset
    )
    return [RemoteSessionSummary.model_validate(s) for s in sessions]


@router.get(
    "/sessions/{session_id}",
    summary="Get full session detail",
    response_model=RemoteSessionResponse,
)
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RemoteSessionResponse:
    """Get full detail for a remote session including events and consents."""
    svc = _get_service(db)
    try:
        session = await svc.get_session(uuid.UUID(session_id), current_user)
    except Exception as exc:
        _handle_errors(exc)

    # Redact join URLs for employees (they use their own URL)
    response = RemoteSessionResponse.model_validate(session)
    if current_user.id == session.employee_id and "it_agent" not in current_user.role_names:
        response.join_url_agent = None  # employees don't need agent URL

    return response


@router.get(
    "/sessions/{session_id}/status",
    summary="Poll provider for latest session status",
)
async def poll_session_status(
    session_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Sync session status from the external provider.

    Intended for use by the frontend to detect session state changes
    (e.g., employee accepted → session went active).
    """
    svc = _get_service(db)
    try:
        # Authorization: enforce the SAME participant/role visibility check as
        # GET /sessions/{id} before touching the provider. Without this, any
        # authenticated user could enumerate session UUIDs, read another user's
        # session, and drive a provider-side state transition on it (IDOR).
        session_uuid = uuid.UUID(session_id)
        await svc.get_session(session_uuid, current_user)
        session = await svc.poll_provider_status(session_uuid)
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {
        "session_id": str(session.id),
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration_seconds": session.duration_seconds,
    }


# ── Employee Endpoints ────────────────────────────────────────────────


@router.get(
    "/consent/pending",
    summary="Employee: poll for a pending consent request",
)
async def pending_consent(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The employee UI polls this to surface the consent modal.

    Returns the consent-notification payload for the most recent
    ``consent_pending`` session targeting the current user (within its
    consent window), or ``{"pending": false}``. Cheap by design — it is
    polled alongside the chat state.
    """
    svc = _get_service(db)
    payload = await svc.get_pending_consent_for_employee(current_user)
    if payload is None:
        return {"pending": False}
    return {"pending": True, "notification": ConsentNotification(**payload).model_dump()}


@router.get(
    "/sessions/{session_id}/consent-info",
    response_model=ConsentNotification,
    summary="Get consent modal payload for employee",
)
async def get_consent_info(
    session_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentNotification:
    """Returns the data needed to populate the employee consent modal.

    Includes the agent's name, session type, justification, consent
    notice text, and deadline. Called when the employee receives a
    consent notification.
    """
    svc = _get_service(db)
    try:
        payload = await svc.get_consent_notification(uuid.UUID(session_id), current_user)
    except Exception as exc:
        _handle_errors(exc)

    return ConsentNotification(**payload)


@router.post(
    "/sessions/{session_id}/consent",
    summary="Employee grants or denies remote session consent",
)
async def respond_to_consent(
    session_id: str,
    data: ConsentDecision,
    request: Request,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Employee responds to a remote session consent request.

    - `granted: true` — employee approves, agent can now launch session
    - `granted: false` — employee denies, session is terminated

    The exact consent notice shown to the employee is stored immutably
    in the consent record for audit purposes.
    """
    svc = _get_service(db)
    try:
        session, consent = await svc.grant_consent(
            session_id=uuid.UUID(session_id),
            employee=current_user,
            granted=data.granted,
            denial_reason=data.denial_reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    if data.granted:
        return {
            "message": "Consent granted. The IT agent will connect shortly.",
            "session_id": session_id,
            "consent_id": str(consent.id),
            "status": session.status,
        }
    return {
        "message": "Consent denied. The session has been cancelled.",
        "session_id": session_id,
        "status": session.status,
    }


@router.post(
    "/sessions/{session_id}/revoke",
    summary="Employee revokes consent mid-session",
)
async def revoke_consent(
    session_id: str,
    data: ConsentRevoke,
    request: Request,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Employee revokes consent during an active session.

    This immediately terminates the remote session at the provider level.
    The revocation is recorded as an immutable audit event.
    """
    svc = _get_service(db)
    try:
        session = await svc.revoke_consent(
            session_id=uuid.UUID(session_id),
            employee=current_user,
            reason=data.reason,
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
    except Exception as exc:
        _handle_errors(exc)

    return {
        "message": "Consent revoked. The remote session has been terminated.",
        "session_id": session_id,
        "status": session.status,
    }


@router.get(
    "/my-sessions",
    response_model=list[RemoteSessionSummary],
    summary="Employee: list own remote sessions",
)
async def my_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> list[RemoteSessionSummary]:
    """Employee's own remote session history."""
    svc = _get_service(db)
    sessions = await svc.list_sessions(current_user, limit=limit)
    return [RemoteSessionSummary.model_validate(s) for s in sessions]


# ── System Endpoints ──────────────────────────────────────────────────


@router.get(
    "/provider/health",
    response_model=ProviderHealthResponse,
    summary="Check remote support provider health",
)
async def provider_health(
    agent: ITAgentUser,
) -> ProviderHealthResponse:
    """Check that the configured remote support provider is reachable."""
    from app.services.remote_support.providers import build_provider_registry

    provider = next(iter(build_provider_registry().values()))
    healthy = await provider.health_check()

    return ProviderHealthResponse(
        provider_name=provider.provider_name,
        display_name=provider.display_name,
        healthy=healthy,
        capabilities=[c.value for c in provider.supported_capabilities],
        supports_unattended=provider.supports_unattended,
        error=None if healthy else "Provider not configured or unreachable",
    )
