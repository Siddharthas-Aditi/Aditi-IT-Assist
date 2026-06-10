"""Shared test fixtures for Aditi IT Assist backend tests.

Provides:
- Mock authenticated users for all role types
- Auth dependency overrides for API endpoint tests
- In-memory async DB session for unit tests
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.auth.dependencies import get_current_active_user


# ─────────────────────────────────────────────────────────────────────
# Mock user factories
# ─────────────────────────────────────────────────────────────────────


def make_mock_user(
    role: str = "employee",
    roles: list[str] | None = None,
) -> MagicMock:
    """Create a mock User object for testing."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@test.aditi.com"
    user.full_name = f"Test {role.title()}"
    user.department = "Engineering"
    user.employee_id = f"EMP-{role.upper()[:3]}-001"
    user.is_active = True
    user.is_verified = True
    user.primary_role = role
    user.role_names = roles or [role]

    # Role assignment mocks
    assignment = MagicMock()
    assignment.role = MagicMock()
    assignment.role.name = role
    assignment.role.priority = {
        "employee": 0,
        "it_agent": 10,
        "it_lead": 20,
        "it_admin": 30,
        "security_auditor": 5,
    }.get(role, 0)
    user.role_assignments = [assignment]
    return user


@pytest.fixture
def mock_employee():
    return make_mock_user("employee")


@pytest.fixture
def mock_it_agent():
    return make_mock_user("it_agent", ["it_agent"])


@pytest.fixture
def mock_it_lead():
    return make_mock_user("it_lead", ["it_lead"])


@pytest.fixture
def mock_it_admin():
    return make_mock_user("it_admin", ["it_admin"])


@pytest.fixture
def mock_auditor():
    return make_mock_user("security_auditor", ["security_auditor"])


# ─────────────────────────────────────────────────────────────────────
# Auth-overridden test clients
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    """Unauthenticated test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def employee_client(mock_employee):
    """Test client authenticated as a regular employee."""
    app.dependency_overrides[get_current_active_user] = lambda: mock_employee
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def agent_client(mock_it_agent):
    """Test client authenticated as an IT agent."""
    app.dependency_overrides[get_current_active_user] = lambda: mock_it_agent
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def lead_client(mock_it_lead):
    """Test client authenticated as an IT lead."""
    app.dependency_overrides[get_current_active_user] = lambda: mock_it_lead
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(mock_it_admin):
    """Test client authenticated as an IT admin."""
    app.dependency_overrides[get_current_active_user] = lambda: mock_it_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
