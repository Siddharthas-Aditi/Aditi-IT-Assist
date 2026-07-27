"""Idempotent seed for the ticket category hierarchy (L1 → L2 → L3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.ticket_category_service import TicketCategoryService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

STARTER_TREE: dict[str, dict[str, list[str]]] = {
    "Incident": {
        "System Login Issue": ["Password Reset", "Account Locked"],
        "Network Connectivity": ["VPN", "Wi-Fi", "DNS"],
        "O365 Apps": ["Outlook", "Teams", "OneDrive"],
        "Laptop Not Booting": ["Hardware Diagnosis"],
        "Zoom Issue": ["Audio", "Video", "Sign-in"],
        "Laptop Performance Issue": ["Slow Performance"],
    },
    "Service Requests": {
        "DL Creation": ["New Distribution List"],
        "Application Access": ["Slack", "Webex", "Zoom"],
        "New Joiner Credential Creation": ["Standard Onboarding"],
        "Shared Mailbox Access": ["Grant Access"],
        "Hardware Request": ["Laptop", "Monitor", "Headset"],
        "License Request": ["Software License"],
    },
    "SPAM Email": {"General": ["Reported Spam"]},
    "Others": {"General": ["Uncategorized"]},
    "Freshworks": {"General": ["Freshworks Request"]},
}


async def seed_ticket_categories(db: AsyncSession) -> int:
    """Seed the starter category tree. Skips if any categories already exist."""
    svc = TicketCategoryService(db)
    existing = await svc.list_all(active_only=False)
    if existing:
        return 0

    created = 0
    for l1_name, subs in STARTER_TREE.items():
        l1 = await svc.create(name=l1_name, level=1)
        created += 1
        for l2_name, items in subs.items():
            l2 = await svc.create(name=l2_name, level=2, parent_id=l1.id)
            created += 1
            for item_name in items:
                await svc.create(name=item_name, level=3, parent_id=l2.id)
                created += 1
    return created
