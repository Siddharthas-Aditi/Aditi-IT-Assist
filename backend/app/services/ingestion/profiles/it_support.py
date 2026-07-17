"""Default IT support document parser profile.

Covers the broad range of IT support documents produced by Aditi Consulting:
onboarding guides, SOPs, KB exports, ticket templates, and ad-hoc docs.

Section markers include every common label variant seen in real IT docs.
Adding a new variant requires only a list entry here — no code change.
"""

from __future__ import annotations

import re

from app.services.ingestion.profiles.base import (
    ConfidenceWeights,
    DetectionCriteria,
    ParserProfile,
    ReviewThresholds,
)

IT_SUPPORT_PROFILE = ParserProfile(
    name="it_support_v1",
    version="1.2.0",
    description=(
        "General IT support documents: SOPs, KB articles, ticket exports, onboarding guides."
    ),
    # ── Section markers ───────────────────────────────────────────────────────
    # Keys map to ExtractionCandidate field names.
    # Values are ALL common label variants; matching is case-insensitive prefix.
    section_markers={
        "symptoms": [
            "symptoms",
            "symptom",
            "signs",
            "indicators",
            "observable",
            "issue",
            "problem",
            "problem description",
            "user report",
            "reported issue",
            "what the user sees",
            "error",
            "errors",
        ],
        "probable_causes": [
            "cause",
            "causes",
            "root cause",
            "reason",
            "reasons",
            "probable cause",
            "likely cause",
            "why",
        ],
        "troubleshooting_steps": [
            "troubleshooting",
            "troubleshoot",
            "troubleshooting steps",
            "diagnosis",
            "diagnostic steps",
            "investigate",
            "investigation",
            "check",
            "checks",
            "verify",
            "verification steps",
            "initial steps",
            "first steps",
            "investigation steps",
        ],
        "resolution_steps": [
            "resolution",
            "solution",
            "fix",
            "resolve",
            "steps to resolve",
            "steps to fix",
            "how to fix",
            "corrective action",
            "action",
            "actions",
            "recommended fix",
            "permanent fix",
            "workaround",
            "steps",
            "procedure",
            "instructions",
        ],
        "validation_steps": [
            "validation",
            "verify fix",
            "confirm",
            "confirmation",
            "test",
            "testing",
            "post-fix check",
            "sanity check",
        ],
        "escalation_criteria": [
            "escalate",
            "escalation",
            "escalation criteria",
            "if the issue persists",
            "if unresolved",
            "contact",
            "reach out",
            "contact it",
            "contact support",
            "when to escalate",
            "further assistance",
        ],
    },
    # ── Heading detection extras (on top of universal heuristics) ─────────────
    heading_signals=[
        re.compile(
            r"^(?:issue|problem|topic|article|kb|note|important|warning|tip)\s*[:\-–]", re.I
        ),
        re.compile(r"^(?:section|part|chapter)\s+\d", re.I),
    ],
    # ── Topic separator patterns ───────────────────────────────────────────────
    # Lines matching these always force a new topic segment.
    topic_separators=[
        re.compile(r"^[-=*_]{3,}\s*$"),  # --- or === or ***
        re.compile(r"^-{2,}\s+[A-Z]"),  # -- HEADING
        re.compile(r"^\[{1,2}[A-Z][^\]]+\]{1,2}\s*$"),  # [SECTION] or [[SECTION]]
    ],
    # ── Confidence weights ────────────────────────────────────────────────────
    confidence_weights=ConfidenceWeights(
        title=0.25,
        category=0.15,
        short_summary=0.05,
        symptoms=0.10,
        troubleshooting_steps=0.08,
        resolution_steps=0.22,
        escalation_criteria=0.05,
        tags=0.05,
        product_or_system=0.05,
    ),
    # ── Review thresholds ─────────────────────────────────────────────────────
    thresholds=ReviewThresholds(high=0.75, medium=0.50, low=0.30),
    # ── Detection ─────────────────────────────────────────────────────────────
    detection=DetectionCriteria(
        keyword_signals=[
            "outlook",
            "zoom",
            "vpn",
            "intune",
            "sharepoint",
            "teams",
            "resolution",
            "symptoms",
            "troubleshoot",
            "escalate",
            "it support",
            "helpdesk",
            "service desk",
        ],
        min_keyword_matches=1,
    ),
)
