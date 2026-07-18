"""Seed data for enterprise IT assist platform.

Creates roles, permissions, sample users, and test data for local development.
Run: uv run python -m scripts.seed_enterprise
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.permissions import (
    PERMISSION_REGISTRY,
    UserRole,
    get_effective_permissions,
)
from app.core.security import hash_password
from app.models.auth import Permission, Role, RolePermission, User, UserRoleAssignment
from app.models.ticket import Ticket

# ─────────────────────────────────────────────────────────────────────
# Permission Definitions — sourced from core/permissions.py registry
# ─────────────────────────────────────────────────────────────────────

PERMISSIONS: list[tuple[str, str, str, str]] = [
    (p.code, p.name, p.resource.value, p.action.value) for p in PERMISSION_REGISTRY
]

# ─────────────────────────────────────────────────────────────────────
# Role → Permission Matrix — uses effective (inherited) permissions
# ─────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, list[str]] = {
    role.value: sorted(get_effective_permissions(role)) for role in UserRole
}

# ─────────────────────────────────────────────────────────────────────
# Sample Users (local dev only)
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Seed roster — LOCAL DEV / TEAM SEED ONLY.
# These credentials are committed so colleagues get the same users when they
# run `python -m scripts.seed_enterprise`. Each password can be overridden via
# an env var (e.g. SEED_HAREESH_PASSWORD) without editing this file.
# SECURITY: do NOT reuse these credentials in staging/production. Rotate them
# and provision real users out-of-band before any non-local deployment.
# ─────────────────────────────────────────────────────────────────────
SAMPLE_USERS = [
    {
        "email": "hareesh@aditiconsulting.com",
        "full_name": "Hareesh",
        "employee_id": "IT-ADMIN",
        "department": "IT Operations",
        "job_title": "IT Administrator",
        "password": os.getenv("SEED_HAREESH_PASSWORD", "Hareesh@2026"),
        "role": "it_admin",
    },
    {
        "email": "sagar@aditiconsulting.com",
        "full_name": "Sagar",
        "employee_id": "IT-011",
        "department": "IT Support",
        "job_title": "IT Team Lead",
        "password": os.getenv("SEED_SAGAR_PASSWORD", "Sagar@2026"),
        "role": "it_lead",
    },
    {
        "email": "madhukar@aditiconsulting.com",
        "full_name": "Madhukar",
        "employee_id": "IT-012",
        "department": "IT Support",
        "job_title": "IT Team Lead",
        "password": os.getenv("SEED_MADHUKAR_PASSWORD", "Madhukar@2026"),
        "role": "it_lead",
    },
    {
        "email": "siddhartha@aditiconsulting.com",
        "full_name": "Siddhartha",
        "employee_id": "EMP-001",
        "department": "Engineering",
        "job_title": "Software Engineer",
        "password": os.getenv("SEED_SIDDHARTHA_PASSWORD", "Siddhartha@2026"),
        "role": "employee",
    },
    {
        "email": "naresh@aditiconsulting.com",
        "full_name": "Naresh",
        "employee_id": "EMP-002",
        "department": "Engineering",
        "job_title": "Software Engineer",
        "password": os.getenv("SEED_NARESH_PASSWORD", "Naresh@2026"),
        "role": "employee",
    },
]


async def seed_permissions(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed permission definitions."""
    perm_ids: dict[str, uuid.UUID] = {}
    for code, name, resource, action in PERMISSIONS:
        existing = await db.execute(select(Permission).where(Permission.code == code))
        perm = existing.scalar_one_or_none()
        if not perm:
            perm = Permission(code=code, name=name, resource=resource, action=action)
            db.add(perm)
            await db.flush()
        perm_ids[code] = perm.id
    return perm_ids


async def seed_roles(db: AsyncSession, perm_ids: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    """Seed role definitions with permission assignments."""
    role_configs = [
        ("employee", "Employee", "Standard employee role", 10),
        ("it_agent", "IT Support Agent", "IT support team member", 20),
        ("it_lead", "IT Team Lead", "IT support team leader", 30),
        ("it_admin", "IT Administrator", "Full administrative access", 40),
        ("security_auditor", "Security Auditor", "Read-only audit access", 15),
    ]

    role_ids: dict[str, uuid.UUID] = {}
    for name, display_name, description, priority in role_configs:
        existing = await db.execute(select(Role).where(Role.name == name))
        role = existing.scalar_one_or_none()
        if not role:
            role = Role(
                name=name,
                display_name=display_name,
                description=description,
                is_system=True,
                priority=priority,
            )
            db.add(role)
            await db.flush()
        role_ids[name] = role.id

        # Assign permissions to role
        for perm_code in ROLE_PERMISSIONS.get(name, []):
            if perm_code in perm_ids:
                existing_rp = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm_ids[perm_code],
                    )
                )
                if not existing_rp.scalar_one_or_none():
                    db.add(RolePermission(role_id=role.id, permission_id=perm_ids[perm_code]))

    return role_ids


async def seed_users(db: AsyncSession, role_ids: dict[str, uuid.UUID]) -> dict[str, User]:
    """Seed sample users with role assignments."""
    users: dict[str, User] = {}
    for user_data in SAMPLE_USERS:
        existing = await db.execute(select(User).where(User.email == user_data["email"]))
        user = existing.scalar_one_or_none()
        if not user:
            user = User(
                email=user_data["email"],
                full_name=user_data["full_name"],
                employee_id=user_data["employee_id"],
                department=user_data["department"],
                job_title=user_data.get("job_title"),
                hashed_password=hash_password(user_data["password"]),
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            await db.flush()

            # Assign role
            role_name = user_data["role"]
            if role_name in role_ids:
                db.add(UserRoleAssignment(user_id=user.id, role_id=role_ids[role_name]))

        users[user_data["email"]] = user
    return users


async def seed_sample_tickets(db: AsyncSession, users: dict[str, User]) -> None:
    """Seed sample tickets for demo/testing."""
    alice = users.get("alice.johnson@aditi.com")
    bob = users.get("bob.williams@aditi.com")
    charlie = users.get("charlie.agent@aditi.com")

    if not alice or not bob or not charlie:
        return

    now = datetime.now(UTC)

    sample_tickets = [
        {
            "ticket_number": "ITA-000001",
            "title": "Outlook not syncing emails on laptop",
            "description": (
                "My Outlook desktop app stopped syncing new emails since this morning. "
                "Web version works fine."
            ),
            "requester_id": alice.id,
            "assigned_to": charlie.id,
            "priority": "high",
            "status": "in_progress",
            "category": "email/outlook",
            "source": "chat",
            "sla_response_target": now + timedelta(hours=4),
            "sla_resolution_target": now + timedelta(hours=12),
            "first_response_at": now - timedelta(hours=1),
        },
        {
            "ticket_number": "ITA-000002",
            "title": "VPN connection drops frequently",
            "description": (
                "VPN disconnects every 15-20 minutes when working from home. "
                "Using GlobalProtect client."
            ),
            "requester_id": bob.id,
            "priority": "medium",
            "status": "new",
            "category": "network/connectivity",
            "source": "chat",
            "sla_response_target": now + timedelta(hours=8),
            "sla_resolution_target": now + timedelta(hours=48),
        },
        {
            "ticket_number": "ITA-000003",
            "title": "Cannot access SharePoint site",
            "description": (
                "Getting 'Access Denied' when trying to access the Engineering team SharePoint."
            ),
            "requester_id": alice.id,
            "assigned_to": charlie.id,
            "priority": "medium",
            "status": "waiting_for_user",
            "category": "access/permissions",
            "source": "manual",
            "sla_response_target": now + timedelta(hours=8),
            "sla_resolution_target": now + timedelta(hours=48),
            "first_response_at": now - timedelta(hours=2),
        },
        {
            "ticket_number": "ITA-000004",
            "title": "Laptop camera not working in Teams",
            "description": "Camera shows black screen in Microsoft Teams. Works in other apps.",
            "requester_id": bob.id,
            "assigned_to": charlie.id,
            "priority": "low",
            "status": "resolved",
            "category": "hardware/camera",
            "source": "chat",
            "resolution_notes": "Updated camera driver and reset Teams cache. Camera working now.",
            "resolved_at": now - timedelta(hours=3),
            "sla_response_target": now + timedelta(hours=24),
            "sla_resolution_target": now + timedelta(hours=120),
        },
        {
            "ticket_number": "ITA-000005",
            "title": "Critical: Production server unresponsive",
            "description": (
                "Production app server not responding to health checks. All services affected."
            ),
            "requester_id": alice.id,
            "priority": "critical",
            "status": "escalated",
            "category": "software/other",
            "source": "manual",
            "sla_response_target": now + timedelta(hours=1),
            "sla_resolution_target": now + timedelta(hours=4),
        },
    ]

    for ticket_data in sample_tickets:
        existing = await db.execute(
            select(Ticket).where(Ticket.ticket_number == ticket_data["ticket_number"])
        )
        if not existing.scalar_one_or_none():
            db.add(Ticket(**ticket_data))


async def run_seed() -> None:
    """Run all seed operations."""
    async with async_session_factory() as db:
        print("🌱 Seeding enterprise data...")

        print("  → Permissions...")
        perm_ids = await seed_permissions(db)
        print(f"    ✓ {len(perm_ids)} permissions")

        print("  → Roles...")
        role_ids = await seed_roles(db, perm_ids)
        print(f"    ✓ {len(role_ids)} roles")

        print("  → Users...")
        users = await seed_users(db, role_ids)
        print(f"    ✓ {len(users)} users")

        print("  → Sample tickets...")
        await seed_sample_tickets(db, users)
        print("    ✓ Sample tickets created")

        print("  → Knowledge base (structured articles)...")
        from app.knowledge_base.structured_seed import seed_knowledge

        kb_count = await seed_knowledge(db, users)
        print(f"    ✓ {kb_count} knowledge articles seeded (published + indexed)")

        await db.commit()
        print("\n✅ Enterprise seed complete!")
        print("\n📋 Seeded users (local dev — rotate before any real deployment):")
        print("  Admin:     hareesh@aditiconsulting.com / Hareesh@2026")
        print("  IT Lead:   sagar@aditiconsulting.com / Sagar@2026")
        print("  IT Lead:   madhukar@aditiconsulting.com / Madhukar@2026")
        print("  Employee:  siddhartha@aditiconsulting.com / Siddhartha@2026")
        print("  Employee:  naresh@aditiconsulting.com / Naresh@2026")


if __name__ == "__main__":
    asyncio.run(run_seed())
