"""Structured knowledge seed data + seeding routine.

Provides realistic, *structured* knowledge articles (the new model format),
ownership groups, and a taxonomy aligned with the ticket categories. Articles
are seeded as **published** and indexed so the governed retrieval path and the
admin UI are immediately populated for local development and demos.

Run indirectly via ``scripts.seed_enterprise`` (see ``run_seed``).
"""
# ruff: noqa: E501 — seed data contains long instructional content strings

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.knowledge import (
    KnowledgeArticle,
    KnowledgeOwnershipGroup,
    KnowledgeTaxonomyTerm,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge.indexing import KnowledgeIndexingService
from app.services.knowledge.management import KnowledgeManagementService

if TYPE_CHECKING:
    from app.models.auth import User

logger = get_logger(__name__)


# ── Ownership groups ─────────────────────────────────────────────────

OWNERSHIP_GROUPS = [
    {
        "name": "endpoint-productivity",
        "display_name": "Endpoint & Productivity",
        "description": "Owns Outlook, Teams, Office, and device-related articles.",
    },
    {
        "name": "network-access",
        "display_name": "Network & Access",
        "description": "Owns VPN, connectivity, SSO, and access-permission articles.",
    },
]


# ── Taxonomy (aligned with ticket categories) ────────────────────────

TAXONOMY_TERMS = [
    ("category", "email/outlook", "Email — Outlook", "email/outlook"),
    ("category", "collaboration/zoom", "Collaboration — Zoom", "collaboration/zoom"),
    ("category", "hardware/camera", "Hardware — Camera", "hardware/camera"),
    ("category", "device/intune", "Device — Intune", "device/intune"),
    ("category", "network/connectivity", "Network — Connectivity", "network/connectivity"),
    ("category", "access/permissions", "Access — Permissions", "access/permissions"),
    ("platform", "windows", "Windows", None),
    ("platform", "macos", "macOS", None),
    ("product", "microsoft_outlook", "Microsoft Outlook", None),
    ("product", "zoom", "Zoom", None),
    ("product", "microsoft_intune", "Microsoft Intune", None),
]


# ── Articles ─────────────────────────────────────────────────────────

ARTICLES = [
    {
        "slug": "outlook-not-receiving-or-slow",
        "title": "Outlook Not Receiving Email or Running Slow",
        "short_summary": "Resolve Outlook desktop issues where mail stops syncing or the app is slow.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "email-delivery",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "sync_failure",
        "severity_hint": "medium",
        "tags": ["outlook", "email", "sync", "slow", "not receiving"],
        "keywords": ["work offline", "send receive", "ost", "add-ins"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "New emails are not arriving in the desktop app",
            "Outlook is slow to open or freezes",
            "Web mail works but desktop does not",
        ],
        "probable_causes": [
            "Work Offline mode is enabled",
            "Corrupted OST/data file or oversized mailbox",
            "A misbehaving COM add-in",
        ],
        "prerequisites": ["Outlook desktop installed", "Corporate network or VPN access"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable Work Offline",
                "details": "Send/Receive tab → ensure 'Work Offline' is not active.",
            },
            {
                "step_number": 2,
                "instruction": "Verify connectivity / VPN",
                "details": "Confirm internet access and that VPN is connected if required.",
            },
            {
                "step_number": 3,
                "instruction": "Disable non-essential add-ins",
                "details": "File → Options → Add-ins → COM Add-ins → uncheck non-essential ones, restart.",
            },
            {
                "step_number": 4,
                "instruction": "Repair the data file",
                "details": "File → Account Settings → Data Files → run Inbox Repair if mailbox is large/corrupt.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Send a test email to yourself and confirm it arrives within a minute.",
            },
        ],
        "escalation_criteria": "Steps do not restore sync, or the mailbox is over quota.",
        "escalation_target_team": "Endpoint & Productivity",
        "references": [
            {"label": "MS — Outlook is offline", "url": "https://support.microsoft.com"}
        ],
    },
    {
        "slug": "zoom-no-audio-or-video",
        "title": "Zoom Meeting Has No Audio or Video",
        "short_summary": "Fix Zoom calls where the mic, speaker, or camera is not working.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "collaboration/zoom",
        "subcategory": "av-devices",
        "product_or_system": "zoom",
        "platform": "windows",
        "issue_type": "device_access",
        "severity_hint": "medium",
        "tags": ["zoom", "audio", "video", "camera", "microphone"],
        "keywords": ["device permissions", "speaker test", "camera privacy"],
        "ownership_group": "endpoint-productivity",
        "symptoms": ["Others cannot hear you", "Your camera shows a black screen in Zoom"],
        "probable_causes": ["Wrong device selected", "OS camera/mic privacy blocking Zoom"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Select the correct devices",
                "details": "Zoom Settings → Audio/Video → choose the right mic, speaker, camera.",
            },
            {
                "step_number": 2,
                "instruction": "Allow OS privacy access",
                "details": "Windows Settings → Privacy → Camera/Microphone → enable for Zoom.",
            },
            {
                "step_number": 3,
                "instruction": "Close apps holding the camera",
                "details": "Quit Teams/Camera app that may lock the device, then rejoin.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Use Zoom's 'Test Speaker & Microphone' and confirm the camera preview.",
            },
        ],
        "escalation_criteria": "Devices still fail after selecting and granting access.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "vpn-disconnects-frequently",
        "title": "VPN Disconnects Frequently When Working Remotely",
        "short_summary": "Stabilize a corporate VPN connection that drops every few minutes.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "network/connectivity",
        "subcategory": "vpn",
        "product_or_system": "globalprotect",
        "platform": "windows",
        "issue_type": "connectivity_drop",
        "severity_hint": "high",
        "tags": ["vpn", "connectivity", "globalprotect", "disconnect"],
        "keywords": ["wifi power management", "mtu", "split tunnel"],
        "ownership_group": "network-access",
        "symptoms": ["VPN drops every 15–20 minutes", "Reconnect prompts repeatedly"],
        "probable_causes": [
            "Wi-Fi adapter power saving",
            "Unstable home network",
            "Outdated VPN client",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable Wi-Fi power saving",
                "details": "Device Manager → network adapter → Power Management → uncheck 'allow the computer to turn off this device'.",
            },
            {
                "step_number": 2,
                "instruction": "Update the VPN client",
                "details": "Install the latest approved GlobalProtect version.",
            },
            {
                "step_number": 3,
                "instruction": "Test on a wired connection",
                "details": "Connect via Ethernet to isolate Wi-Fi instability.",
            },
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Stay connected for 30 minutes without a drop."},
        ],
        "escalation_criteria": "Drops persist on a wired connection with the latest client.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "intune-device-not-compliant",
        "title": "Device Shows Not Compliant in Intune",
        "short_summary": "Bring a managed device back into Intune compliance to restore access.",
        "article_type": "how_to",
        "audience": "it_staff",
        "visibility_scope": "it_only",
        "category": "device/intune",
        "subcategory": "compliance",
        "product_or_system": "microsoft_intune",
        "platform": "windows",
        "issue_type": "compliance",
        "severity_hint": "high",
        "tags": ["intune", "compliance", "mdm", "conditional access"],
        "keywords": ["company portal", "sync", "encryption", "defender"],
        "ownership_group": "network-access",
        "symptoms": ["Conditional Access blocks apps", "Company Portal shows 'Not compliant'"],
        "probable_causes": ["Pending policy sync", "Disk encryption off", "Defender out of date"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Force a sync",
                "details": "Company Portal → Settings → Sync, or Settings → Accounts → Access work/school → Info → Sync.",
            },
            {
                "step_number": 2,
                "instruction": "Remediate flagged settings",
                "details": "Enable BitLocker, update Defender definitions, enable firewall as flagged.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Re-run sync and confirm Company Portal reports 'Compliant'.",
            },
        ],
        "escalation_criteria": "Device stays non-compliant after remediation and sync.",
        "escalation_target_team": "Network & Access",
    },
]


async def _get_or_create_group(repo: KnowledgeRepository, db, spec: dict, owner: User | None):
    existing = (
        await db.execute(
            select(KnowledgeOwnershipGroup).where(KnowledgeOwnershipGroup.name == spec["name"])
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    group = KnowledgeOwnershipGroup(
        name=spec["name"],
        display_name=spec["display_name"],
        description=spec.get("description"),
        owner_id=owner.id if owner else None,
    )
    await repo.add_ownership_group(group)
    return group


async def _ensure_taxonomy(
    repo: KnowledgeRepository, term_type: str, key: str, label: str, mapping: str | None
) -> None:
    existing = await repo.get_taxonomy_by_key(term_type, key)
    if existing:
        return
    await repo.add_taxonomy_term(
        KnowledgeTaxonomyTerm(
            term_type=term_type,
            key=key,
            label=label,
            ticket_category_mapping=mapping,
        )
    )


async def seed_knowledge(db, users: dict[str, User]) -> int:
    """Seed ownership groups, taxonomy, and published structured articles."""
    repo = KnowledgeRepository(db)
    indexing = KnowledgeIndexingService(repo)

    lead = users.get("edward.lead@aditi.com")
    admin = users.get("admin@aditi.com")
    now = datetime.now(UTC)

    # Ownership groups
    groups: dict[str, KnowledgeOwnershipGroup] = {}
    for spec in OWNERSHIP_GROUPS:
        group = await _get_or_create_group(repo, db, spec, lead)
        groups[spec["name"]] = group

    # Taxonomy
    for term_type, key, label, mapping in TAXONOMY_TERMS:
        await _ensure_taxonomy(repo, term_type, key, label, mapping)
    await db.flush()

    seeded = 0
    for spec in ARTICLES:
        if await repo.get_by_slug(spec["slug"]):
            continue
        group = groups.get(spec.get("ownership_group", ""))
        article = KnowledgeArticle(
            slug=spec["slug"],
            title=spec["title"],
            short_summary=spec.get("short_summary"),
            article_type=spec.get("article_type", "troubleshooting"),
            status="published",
            version=1,
            audience=spec.get("audience", "employee"),
            visibility_scope=spec.get("visibility_scope", "public_internal"),
            category=spec["category"],
            subcategory=spec.get("subcategory"),
            product_or_system=spec.get("product_or_system"),
            platform=spec.get("platform"),
            issue_type=spec.get("issue_type"),
            severity_hint=spec.get("severity_hint"),
            tags=spec.get("tags", []),
            keywords=spec.get("keywords", []),
            ownership_group_id=group.id if group else None,
            symptoms=spec.get("symptoms", []),
            probable_causes=spec.get("probable_causes", []),
            prerequisites=spec.get("prerequisites", []),
            troubleshooting_steps=spec.get("troubleshooting_steps", []),
            resolution_steps=spec.get("resolution_steps", []),
            validation_steps=spec.get("validation_steps", []),
            escalation_criteria=spec.get("escalation_criteria"),
            escalation_target_team=spec.get("escalation_target_team"),
            references=spec.get("references", []),
            citation_label=spec["title"],
            source_type="seed",
            author_id=lead.id if lead else None,
            reviewer_id=lead.id if lead else None,
            approver_id=admin.id if admin else None,
            approved_by=admin.id if admin else None,
            is_published=True,
            is_approved=True,
            published_at=now,
            last_reviewed_at=now,
            next_review_due_at=now + timedelta(days=180),
        )
        KnowledgeManagementService._recompute_quality(article)
        await repo.add(article)
        await indexing.index_article(article)
        seeded += 1

    logger.info("knowledge_seeded", articles=seeded, groups=len(groups))
    return seeded
