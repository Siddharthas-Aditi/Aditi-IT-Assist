"""Knowledge authoring quality — completeness scoring, stale detection, author warnings.

All functions are **pure** (no I/O). They accept a plain ``article_dict`` (as
produced by ``article_to_dict`` / ``article_detail``) so they are
storage-agnostic and trivially unit-testable.

Completeness dimensions
-----------------------
* identity        — title, summary, citation label
* categorisation  — category, subcategory, product, platform, tags/keywords
* content         — symptoms, causes, steps, body, validation steps
* governance      — ownership group, audience, review interval, escalation info

Each dimension is scored 0–1; the composite ``score`` is a weighted average
mapped to 0–100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# ─────────────────────────────────────────────────────────────────────
# Completeness
# ─────────────────────────────────────────────────────────────────────


@dataclass
class DimensionScore:
    name: str
    label: str
    score: float  # 0.0 – 1.0
    earned: list[str] = field(default_factory=list)  # what contributed
    missing: list[str] = field(default_factory=list)  # what would improve it


@dataclass
class CompletenessReport:
    score: float  # overall 0 – 100
    grade: str  # A / B / C / D / F
    dimensions: list[DimensionScore]
    ready_for_review: bool  # enough to submit
    ready_for_publish: bool  # all hard blockers cleared
    blocking_issues: list[str]  # hard blockers
    suggestions: list[str]  # non-blocking improvements


_GRADE_THRESHOLDS = [(90, "A"), (75, "B"), (55, "C"), (35, "D")]


def _grade(score: float) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def _list_has(v: object) -> bool:
    return bool(v) and len(v) > 0  # type: ignore[arg-type]


def compute_completeness(article: dict) -> CompletenessReport:
    """Compute a multi-dimension completeness report for an article dict."""

    # ── Identity (weight 0.25) ──────────────────────────────────────
    id_earned: list[str] = []
    id_missing: list[str] = []
    id_score = 0.0

    if article.get("title", "").strip():
        id_score += 0.40
        id_earned.append("Title present")
    else:
        id_missing.append("Title is required")

    summary = article.get("short_summary") or ""
    if summary.strip() and len(summary.strip()) >= 30:
        id_score += 0.35
        id_earned.append("Short summary ≥ 30 chars")
    elif summary.strip():
        id_score += 0.15
        id_missing.append("Short summary is too brief (< 30 chars)")
    else:
        id_missing.append("Short summary missing — used in search results & AI citations")

    if article.get("citation_label", "").strip():
        id_score += 0.25
        id_earned.append("Citation label set")
    else:
        id_missing.append("Citation label missing — shown next to AI-generated answers")

    # ── Categorisation (weight 0.20) ────────────────────────────────
    cat_earned: list[str] = []
    cat_missing: list[str] = []
    cat_score = 0.0

    if article.get("category", "").strip():
        cat_score += 0.30
        cat_earned.append("Category set")
    else:
        cat_missing.append("Category is required")

    if article.get("subcategory", "").strip():
        cat_score += 0.15
        cat_earned.append("Subcategory set")
    else:
        cat_missing.append("Subcategory improves retrieval precision")

    if article.get("product_or_system", "").strip():
        cat_score += 0.15
        cat_earned.append("Product/system set")
    else:
        cat_missing.append("Product or system name aids routing")

    tags = article.get("tags") or []
    if len(tags) >= 3:
        cat_score += 0.25
        cat_earned.append(f"{len(tags)} tags")
    elif len(tags) >= 1:
        cat_score += 0.12
        cat_missing.append("Add 3+ tags for better retrieval filtering")
    else:
        cat_missing.append("No tags — at least one required to publish")

    keywords = article.get("keywords") or []
    if len(keywords) >= 3:
        cat_score += 0.15
        cat_earned.append(f"{len(keywords)} keywords")
    else:
        cat_missing.append("Keywords improve full-text search ranking")

    # ── Content (weight 0.35) ───────────────────────────────────────
    cnt_earned: list[str] = []
    cnt_missing: list[str] = []
    cnt_score = 0.0

    symptoms = article.get("symptoms") or []
    if _list_has(symptoms):
        cnt_score += 0.15
        cnt_earned.append(f"{len(symptoms)} symptom(s) listed")
    else:
        cnt_missing.append("Symptoms help the AI triage agent match issues")

    causes = article.get("probable_causes") or []
    if _list_has(causes):
        cnt_score += 0.10
        cnt_earned.append(f"{len(causes)} probable cause(s)")
    else:
        cnt_missing.append("Probable causes improve diagnosis quality")

    res_steps = article.get("resolution_steps") or []
    ts_steps = article.get("troubleshooting_steps") or []
    if _list_has(res_steps) and len(res_steps) >= 2:
        cnt_score += 0.30
        cnt_earned.append(f"{len(res_steps)} resolution step(s)")
    elif _list_has(res_steps):
        cnt_score += 0.15
        cnt_missing.append("Add more resolution steps for a complete fix guide")
    elif _list_has(ts_steps):
        cnt_score += 0.20
        cnt_missing.append("Resolution steps preferred over troubleshooting-only")
    else:
        cnt_missing.append("No resolution or troubleshooting steps — required to publish")

    if _list_has(article.get("validation_steps")):
        cnt_score += 0.15
        cnt_earned.append("Validation steps present")
    else:
        cnt_missing.append("Validation steps confirm the fix worked")

    if (article.get("content") or "").strip():
        cnt_score += 0.15
        cnt_earned.append("Body content present")
    else:
        cnt_missing.append("Body content adds context for complex issues")

    if (article.get("escalation_criteria") or "").strip():
        cnt_score += 0.15
        cnt_earned.append("Escalation criteria defined")
    else:
        cnt_missing.append("Define when to escalate — keeps agents consistent")

    # ── Governance (weight 0.20) ─────────────────────────────────────
    gov_earned: list[str] = []
    gov_missing: list[str] = []
    gov_score = 0.0

    if article.get("ownership_group_id"):
        gov_score += 0.40
        gov_earned.append("Ownership group assigned")
    else:
        gov_missing.append("Ownership group required to publish")

    if (article.get("audience") or "").strip():
        gov_score += 0.20
        gov_earned.append("Audience set")
    else:
        gov_missing.append("Audience not specified")

    review_interval = article.get("review_interval_days")
    if review_interval and 30 <= int(review_interval) <= 365:
        gov_score += 0.20
        gov_earned.append(f"Review interval: {review_interval}d")
    elif review_interval:
        gov_score += 0.10
        gov_missing.append("Review interval is outside 30–365 day recommended range")
    else:
        gov_missing.append("Review interval not set — defaults to 180 days")

    if (article.get("escalation_target_team") or "").strip():
        gov_score += 0.20
        gov_earned.append("Escalation team named")
    else:
        gov_missing.append("Escalation target team not set")

    # ── Composite ────────────────────────────────────────────────────
    weights = {"identity": 0.25, "categorisation": 0.20, "content": 0.35, "governance": 0.20}
    composite = (
        id_score * weights["identity"]
        + cat_score * weights["categorisation"]
        + cnt_score * weights["content"]
        + gov_score * weights["governance"]
    ) * 100

    dimensions = [
        DimensionScore(
            "identity", "Identity & Discovery", round(id_score, 3), id_earned, id_missing
        ),
        DimensionScore(
            "categorisation", "Categorisation", round(cat_score, 3), cat_earned, cat_missing
        ),
        DimensionScore("content", "Content Quality", round(cnt_score, 3), cnt_earned, cnt_missing),
        DimensionScore("governance", "Governance", round(gov_score, 3), gov_earned, gov_missing),
    ]

    # Hard blockers (block publication)
    blocking: list[str] = []
    if not article.get("title", "").strip():
        blocking.append("Title is missing")
    if not (article.get("short_summary") or "").strip():
        blocking.append("Short summary is missing")
    if not article.get("category", "").strip():
        blocking.append("Category is missing")
    if not _list_has(article.get("tags")):
        blocking.append("At least one tag is required")
    if not article.get("ownership_group_id"):
        blocking.append("Ownership group must be assigned")
    if not article.get("citation_label", "").strip():
        blocking.append("Citation label is missing")
    if not (_list_has(res_steps) or _list_has(ts_steps) or (article.get("content") or "").strip()):
        blocking.append("Article has no actionable content (steps or body)")

    # Suggestions = non-blocking missing items
    suggestions = [m for dim in dimensions for m in dim.missing if m not in blocking]
    score = round(composite, 1)

    # Ready for review = title + category + some content present (3 hard blockers cleared)
    review_blockers = sum(
        1
        for check in [
            article.get("title", "").strip(),
            article.get("category", "").strip(),
            _list_has(res_steps) or _list_has(ts_steps) or (article.get("content") or "").strip(),
        ]
        if not check
    )

    return CompletenessReport(
        score=score,
        grade=_grade(score),
        dimensions=dimensions,
        ready_for_review=review_blockers == 0,
        ready_for_publish=len(blocking) == 0,
        blocking_issues=blocking,
        suggestions=suggestions,
    )


# ─────────────────────────────────────────────────────────────────────
# Stale detection
# ─────────────────────────────────────────────────────────────────────


@dataclass
class StaleAnalysis:
    is_stale: bool
    staleness_score: float  # 0.0 (fresh) – 1.0 (very stale)
    days_since_update: int | None
    days_overdue: int | None  # None if not overdue
    reasons: list[str]
    recommendations: list[str]


def detect_staleness(article: dict) -> StaleAnalysis:
    """Analyse an article dict and return a staleness assessment."""
    now = datetime.now(UTC)
    reasons: list[str] = []
    recommendations: list[str] = []
    staleness_score = 0.0
    days_since_update: int | None = None
    days_overdue: int | None = None

    # Find the most recent modification timestamp
    for ts_field in ("updated_at", "published_at", "last_reviewed_at"):
        raw = article.get(ts_field)
        if raw:
            try:
                updated = (
                    datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if isinstance(raw, str)
                    else (raw if raw.tzinfo else raw.replace(tzinfo=UTC))
                )
                days = (now - updated).days
                if days_since_update is None or days < days_since_update:
                    days_since_update = days
            except (ValueError, TypeError):
                pass

    # Review due date overdue?
    raw_due = article.get("next_review_due_at")
    if raw_due:
        try:
            due_dt = (
                datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
                if isinstance(raw_due, str)
                else (raw_due if raw_due.tzinfo else raw_due.replace(tzinfo=UTC))
            )
            if now > due_dt:
                days_overdue = (now - due_dt).days
                reasons.append(f"Review overdue by {days_overdue} day(s)")
                staleness_score += min(0.5, days_overdue / 365)
                recommendations.append("Schedule a content review with the ownership team")
        except (ValueError, TypeError):
            pass

    # Age-based staleness
    if days_since_update is not None:
        if days_since_update > 365:
            reasons.append(f"Not updated in {days_since_update} days (> 1 year)")
            staleness_score += 0.4
            recommendations.append(
                "Verify all steps are still accurate for current software versions"
            )
        elif days_since_update > 180:
            reasons.append(f"Not updated in {days_since_update} days (> 6 months)")
            staleness_score += 0.2

    # Low resolution rate as a quality/currency signal
    usage = article.get("usage_count") or 0
    resolved = article.get("successful_resolution_count") or 0
    if usage >= 10:
        rate = resolved / usage
        if rate < 0.3:
            reasons.append(f"Low resolution rate ({rate:.0%}) — may be outdated or unclear")
            staleness_score += 0.25
            recommendations.append("Review steps against current UI/process; add known workarounds")

    # Negative feedback accumulation
    neg_feedback = article.get("negative_feedback_count") or 0
    if neg_feedback >= 3:
        reasons.append(f"{neg_feedback} pieces of negative feedback received")
        staleness_score += min(0.2, neg_feedback * 0.04)
        recommendations.append("Read feedback comments and update the article accordingly")

    if not reasons:
        recommendations.append("Content appears fresh — next review is on schedule")

    return StaleAnalysis(
        is_stale=staleness_score >= 0.4 or bool(days_overdue),
        staleness_score=round(min(1.0, staleness_score), 3),
        days_since_update=days_since_update,
        days_overdue=days_overdue,
        reasons=reasons,
        recommendations=recommendations,
    )


# ─────────────────────────────────────────────────────────────────────
# Author warnings
# ─────────────────────────────────────────────────────────────────────


@dataclass
class AuthorWarning:
    severity: str  # "error" | "warning" | "info"
    field: str | None  # form field this relates to
    message: str
    guidance: str | None = None


def get_author_warnings(article: dict) -> list[AuthorWarning]:
    """Return inline warnings for the article editor.

    ``error``   — blocks publication (critical fields absent).
    ``warning`` — strongly recommended, degrades retrieval quality.
    ``info``    — nice-to-have enhancements.
    """
    warnings: list[AuthorWarning] = []
    res_steps = article.get("resolution_steps") or []
    ts_steps = article.get("troubleshooting_steps") or []

    # ── Errors (publish blockers) ──────────────────────────────────
    if not (article.get("short_summary") or "").strip():
        warnings.append(
            AuthorWarning(
                severity="error",
                field="short_summary",
                message="Short summary is required to publish.",
                guidance="Write 1–2 sentences describing the problem and solution.",
            )
        )

    if not _list_has(article.get("tags")):
        warnings.append(
            AuthorWarning(
                severity="error",
                field="tags",
                message="At least one tag is required.",
                guidance="Tags are used to filter knowledge results in the AI retrieval pipeline.",
            )
        )

    if not article.get("ownership_group_id"):
        warnings.append(
            AuthorWarning(
                severity="error",
                field="ownership_group_id",
                message="Ownership group must be assigned before publishing.",
                guidance="Assign the team responsible for maintaining this article.",
            )
        )

    if not (article.get("citation_label") or "").strip():
        warnings.append(
            AuthorWarning(
                severity="error",
                field="citation_label",
                message="Citation label is missing.",
                guidance=(
                    "This label appears next to AI-generated answers that cite this article."
                ),
            )
        )

    if not (_list_has(res_steps) or _list_has(ts_steps) or (article.get("content") or "").strip()):
        warnings.append(
            AuthorWarning(
                severity="error",
                field="resolution_steps",
                message="Article has no actionable content.",
                guidance="Add resolution steps, troubleshooting steps, or body content.",
            )
        )

    # ── Warnings (highly recommended) ──────────────────────────────
    if not _list_has(article.get("symptoms")):
        warnings.append(
            AuthorWarning(
                severity="warning",
                field="symptoms",
                message="No symptoms listed.",
                guidance=(
                    "Symptoms help the AI triage agent match this article to user-described issues."
                ),
            )
        )

    if not (article.get("escalation_criteria") or "").strip():
        warnings.append(
            AuthorWarning(
                severity="warning",
                field="escalation_criteria",
                message="Escalation criteria not defined.",
                guidance="Specify when this issue should be escalated to a human IT agent.",
            )
        )

    if not _list_has(article.get("validation_steps")):
        warnings.append(
            AuthorWarning(
                severity="warning",
                field="validation_steps",
                message="No validation steps provided.",
                guidance=("Tell users how to confirm the fix worked (e.g., 'Send a test email')."),
            )
        )

    summary = (article.get("short_summary") or "").strip()
    if summary and len(summary) < 30:
        warnings.append(
            AuthorWarning(
                severity="warning",
                field="short_summary",
                message="Short summary is very brief.",
                guidance="Aim for at least 30 characters to ensure it is useful in search results.",
            )
        )

    # ── Info (enhancements) ──────────────────────────────────────────
    if not _list_has(article.get("probable_causes")):
        warnings.append(
            AuthorWarning(
                severity="info",
                field="probable_causes",
                message="Probable causes not listed.",
                guidance="Helps the resolution agent explain why the issue occurred.",
            )
        )

    if not (article.get("subcategory") or "").strip():
        warnings.append(
            AuthorWarning(
                severity="info",
                field="subcategory",
                message="Subcategory not set.",
                guidance="Subcategory narrows retrieval results for better precision.",
            )
        )

    tags = article.get("tags") or []
    if 0 < len(tags) < 3:
        warnings.append(
            AuthorWarning(
                severity="info",
                field="tags",
                message=f"Only {len(tags)} tag(s) — 3+ recommended.",
                guidance="More tags improve retrieval recall across different search terms.",
            )
        )

    if not (article.get("product_or_system") or "").strip():
        warnings.append(
            AuthorWarning(
                severity="info",
                field="product_or_system",
                message="Product/system not specified.",
                guidance="Helps route the article to the right product category.",
            )
        )

    return warnings
