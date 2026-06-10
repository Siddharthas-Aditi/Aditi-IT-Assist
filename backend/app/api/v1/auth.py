"""Authentication endpoints — local auth + SAML SSO integration.

This module provides:
- Local email/password authentication (immediate)
- SAML 2.0 SSO endpoints (extensible stubs for enterprise integration)
- Session management (me, logout)

SAML Endpoints:
    GET  /auth/saml/login       — Initiate SSO (redirect to IdP)
    POST /auth/saml/acs         — Assertion Consumer Service (IdP callback)
    GET  /auth/saml/metadata    — SP metadata XML (for IdP registration)
    GET  /auth/saml/sls         — Single Logout Service callback
    POST /auth/saml/logout      — Initiate SAML logout
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.auth.dependencies import CurrentUser
from app.services.auth.service import AuthenticationError, AuthService

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Request/Response Schemas
# ─────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response schema."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    """User info included in auth responses."""

    id: str
    email: str
    full_name: str
    role: str
    roles: list[str]


class RegisterRequest(BaseModel):
    """User registration request (admin or self-service)."""

    email: EmailStr
    password: str
    full_name: str
    department: str | None = None
    employee_id: str | None = None


class MeResponse(BaseModel):
    """Current user profile response."""

    id: str
    email: str
    full_name: str
    role: str
    roles: list[str]
    department: str | None
    employee_id: str | None
    is_active: bool


class SAMLStatusResponse(BaseModel):
    """SAML configuration status response."""

    enabled: bool
    configured: bool
    provider_name: str | None = None
    idp_display_name: str | None = None
    login_url: str
    metadata_url: str


# ─────────────────────────────────────────────────────────────────────
# Local Auth Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Authenticate user with email/password and return JWT.

    For SAML SSO login, use GET /auth/saml/login instead.
    """
    auth_service = AuthService(db)
    try:
        result = await auth_service.login(
            email=data.email,
            password=data.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
        ) from e

    return LoginResponse(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        user=UserInfo(**result["user"]),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Register a new user (development only — production uses SSO)."""
    auth_service = AuthService(db)
    try:
        user = await auth_service.register_user(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
            department=data.department,
            employee_id=data.employee_id,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e.message)) from e

    return {"message": "User registered successfully", "user_id": str(user.id)}


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: CurrentUser) -> MeResponse:
    """Get current authenticated user profile."""
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.primary_role,
        roles=current_user.role_names,
        department=current_user.department,
        employee_id=current_user.employee_id,
        is_active=current_user.is_active,
    )


@router.post("/logout")
async def logout(current_user: CurrentUser) -> dict[str, str]:
    """Logout user (invalidate current session).

    For SAML users, also initiates SLO if configured.
    """
    # TODO: Implement token blacklisting via Redis
    # TODO: For SAML sessions, check if SLO should be initiated
    return {"message": "Logged out successfully"}


# ─────────────────────────────────────────────────────────────────────
# SAML SSO Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get("/saml/status", response_model=SAMLStatusResponse)
async def saml_status() -> SAMLStatusResponse:
    """Check SAML SSO configuration status.

    Used by the frontend to determine whether to show SSO login button.
    """
    return SAMLStatusResponse(
        enabled=settings.SAML_ENABLED,
        configured=bool(settings.SAML_IDP_ENTITY_ID),
        provider_name="saml" if settings.SAML_ENABLED else None,
        idp_display_name=None,  # TODO: Load from IdP config
        login_url=f"{settings.API_V1_PREFIX}/auth/saml/login",
        metadata_url=f"{settings.API_V1_PREFIX}/auth/saml/metadata",
    )


@router.get("/saml/login", response_model=None)
async def saml_login(
    relay_state: str | None = Query(
        None,
        description="URL to redirect to after successful authentication",
    ),
    idp: str | None = Query(
        None,
        description="IdP identifier for multi-IdP setups (default: primary)",
    ),
) -> dict | RedirectResponse:
    """Initiate SAML SSO login flow.

    Flow:
        1. Generates SAML AuthnRequest
        2. Returns redirect URL to IdP SSO endpoint
        3. User authenticates at IdP
        4. IdP POSTs SAML assertion to /auth/saml/acs

    Query Parameters:
        relay_state: Frontend URL to redirect back to after auth
        idp: Identity Provider ID (for orgs with multiple IdPs)

    Returns:
        302 Redirect to IdP (when implemented)
        JSON status message (current stub)
    """
    if not settings.SAML_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML SSO is not enabled. Contact your administrator.",
        )

    from app.services.auth.providers.saml import SAMLAuthProvider

    provider = SAMLAuthProvider()
    result = await provider.initiate_login(relay_state=relay_state, idp_id=idp)

    if result.error:
        # Not yet implemented — return informational response
        return {
            "message": "SAML SSO login",
            "status": "not_configured",
            "error": result.error,
            "docs": "See docs/security/saml-roadmap.md for setup instructions",
            "supported_idps": ["Microsoft Entra ID", "Okta", "OneLogin", "PingFederate"],
        }

    # When implemented: redirect to IdP
    return RedirectResponse(url=result.redirect_url, status_code=302)


@router.post("/saml/acs", response_model=None)
async def saml_acs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict | RedirectResponse:
    """SAML Assertion Consumer Service (ACS) callback.

    This endpoint receives the SAML Response from the IdP after
    successful user authentication. It is a POST endpoint because
    IdPs use the HTTP-POST binding for assertions.

    Flow:
        1. IdP POSTs base64-encoded SAML Response
        2. We validate the XML signature against IdP certificate
        3. Extract user attributes (email, name, groups)
        4. Map groups to internal RBAC roles
        5. JIT-provision user if first login
        6. Issue internal JWT
        7. Redirect to frontend with token

    The form data contains:
        SAMLResponse: Base64-encoded SAML Response XML
        RelayState: Original relay_state from login initiation
    """
    if not settings.SAML_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML SSO is not enabled",
        )

    # Parse form data from IdP POST
    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState")

    if not saml_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing SAMLResponse in callback",
        )

    from app.services.auth.providers.saml import SAMLAuthProvider

    provider = SAMLAuthProvider()
    auth_result = await provider.process_callback(
        saml_response=str(saml_response),
        relay_state=str(relay_state) if relay_state else None,
        request_data={
            "http_host": request.url.hostname,
            "script_name": str(request.url.path),
            "server_port": request.url.port,
            "https": "on" if request.url.scheme == "https" else "off",
        },
    )

    if not auth_result.success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_result.error or "SAML authentication failed",
        )

    # TODO: When implemented:
    # 1. Look up or JIT-provision user from auth_result.claims
    # 2. Create internal JWT session
    # 3. Redirect to frontend with token:
    #    redirect_url = f"{relay_state or '/'}?token={jwt_token}"
    #    return RedirectResponse(url=redirect_url, status_code=302)

    return {
        "message": "SAML ACS callback received",
        "status": "processing_not_implemented",
        "provider_user_id": auth_result.provider_user_id,
    }


@router.get("/saml/metadata")
async def saml_metadata() -> Response:
    """Return SP SAML metadata XML for IdP registration.

    This XML document is imported into the Identity Provider (Entra, Okta, etc.)
    to configure the trust relationship.

    Includes:
        - SP Entity ID
        - ACS endpoint URL (HTTP-POST binding)
        - SLS endpoint URL (HTTP-Redirect binding)
        - Organization info
        - Desired NameID format

    Content-Type: application/xml
    """
    from app.services.auth.providers.saml import SAMLAuthProvider, SAMLSPConfig

    sp_config = SAMLSPConfig(
        entity_id=settings.SAML_SP_ENTITY_ID,
        acs_url=settings.SAML_SP_ACS_URL,
        sls_url=settings.SAML_SP_SLS_URL,
    )
    provider = SAMLAuthProvider(sp_config=sp_config)
    metadata = await provider.get_metadata()

    return Response(
        content=metadata or "",
        media_type="application/xml",
        headers={"Content-Disposition": "inline; filename=sp-metadata.xml"},
    )


@router.get("/saml/sls", response_model=None)
async def saml_sls(
    request: Request,
) -> dict | RedirectResponse:
    """SAML Single Logout Service (SLS) callback.

    Called by the IdP after processing our LogoutRequest, OR
    called by the IdP to initiate IdP-initiated logout.

    Query Parameters (from IdP redirect):
        SAMLResponse: Logout response (SP-initiated flow)
        SAMLRequest: Logout request (IdP-initiated flow)
    """
    if not settings.SAML_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML SSO is not enabled",
        )

    from app.services.auth.providers.saml import SAMLAuthProvider

    provider = SAMLAuthProvider()
    result = await provider.process_slo_response(
        saml_response=request.query_params.get("SAMLResponse"),
        saml_request=request.query_params.get("SAMLRequest"),
    )

    if result.success:
        # Redirect to frontend login page after successful logout
        return RedirectResponse(url="/login?slo=success", status_code=302)

    return {"message": "SLO processing failed", "error": result.error}


@router.post("/saml/logout", response_model=None)
async def saml_logout(
    current_user: CurrentUser,
) -> dict | RedirectResponse:
    """Initiate SAML Single Logout for current user.

    If the user authenticated via SAML, this sends a LogoutRequest
    to the IdP to terminate the SSO session globally.

    If the user authenticated locally, performs local logout only.
    """
    # TODO: Check if user's session was created via SAML
    # If so, initiate SLO with the IdP:
    # from app.services.auth.providers.saml import SAMLAuthProvider
    # provider = SAMLAuthProvider()
    # result = await provider.initiate_logout(
    #     user_id=str(current_user.id),
    #     session_index=current_user_session.saml_session_index,
    #     name_id=current_user_session.saml_name_id,
    # )
    # if result.redirect_url:
    #     return RedirectResponse(url=result.redirect_url, status_code=302)

    return {"message": "Logged out successfully", "slo_initiated": False}
