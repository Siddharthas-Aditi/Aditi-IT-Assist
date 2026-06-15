"""Knowledge management service — authoring, governance, versioning, feedback.

This is the write-side orchestrator. It owns:
- draft creation and structured updates,
- governed lifecycle transitions (delegating rules to ``lifecycle``),
- version snapshots on meaningful transitions,
- index (re)build on publish / removal on archive,
- review notes, feedback capture, and quality scoring,
- audit logging of every state change (via ``AuditService``).

It never enforces *coarse* role access (the API layer does, via
``require_permissions``); instead it enforces the *fine-grained, per-action*
permission for a transition using the actor's resolved permission set.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.models.knowledge import (
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeFeedback,
    KnowledgeReviewNote,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.audit_service import AuditService
from app.services.knowledge import lifecycle, normalization
from app.services.knowledge.indexing import KnowledgeIndexingService
from app.services.knowledge.serializers import article_detail, article_to_dict

if TYPE_CHECKING:
    from app.models.auth import User

logger = get_logger(__name__)

DEFAULT_REVIEW_INTERVAL_DAYS = 180

# Fields copied verbatim from an update payload onto the article.
_DIRECT_UPDATE_FIELDS = (
    "title",
    "short_summary",
    "article_type",
    "language",
    "audience",
    "visibility_scope",
    "category",
    "subcategory",
    "product_or_system",
    "platform",
    "issue_type",
    "severity_hint",
    "tags",
    "keywords",
    "content",
    "symptoms",
    "probable_causes",
    "prerequisites",
    "escalation_criteria",
    "escalation_target_team",
    "references",
    "related_articles",
    "citation_label",
    "source_type",
    "source_reference",
    "ownership_group_id",
    "review_interval_days",
)
_STEP_FIELDS = ("troubleshooting_steps", "resolution_steps", "validation_steps")


class KnowledgeManagementError(ValueError):
    """Raised on invalid authoring operations."""


class KnowledgeManagementService:
    """Write-side service for the knowledge base."""

    def __init__(self, db) -> None:
        self.db = db
        self.repo = KnowledgeRepository(db)
        self.indexing = KnowledgeIndexingService(self.repo)
        self.audit = AuditService(db)

    # ── Slugs ───────────────────────────────────────────────────

    @staticmethod
    def _slugify(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug[:80] or "article"

    async def _unique_slug(self, title: str) -> str:
        base = self._slugify(title)
        candidate = base
        suffix = 1
        while await self.repo.get_by_slug(candidate):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    # ── Reads ───────────────────────────────────────────────────

    async def get_article(self, article_id: uuid.UUID) -> KnowledgeArticle | None:
        return await self.repo.get(article_id)

    async def list_articles(self, **filters) -> tuple[list[KnowledgeArticle], int]:
        return await self.repo.list(**filters)

    async def review_queue(self) -> list[KnowledgeArticle]:
        return await self.repo.list_review_queue()

    async def stale_articles(self) -> list[KnowledgeArticle]:
        return await self.repo.list_stale()

    async def find_duplicate_hints(
        self, title: str, exclude_id: uuid.UUID | None = None
    ) -> list[dict]:
        rows = await self.repo.find_duplicates(title, exclude_id=exclude_id)
        return [{"id": str(r.id), "title": r.title, "status": r.status} for r in rows]

    # ── Create / update ─────────────────────────────────────────

    async def create_draft(self, actor: User, data) -> KnowledgeArticle:
        """Create a new draft article from a validated create payload."""
        now = datetime.now(UTC)
        interval = data.review_interval_days or DEFAULT_REVIEW_INTERVAL_DAYS
        article = KnowledgeArticle(
            slug=await self._unique_slug(data.title),
            title=data.title,
            short_summary=data.short_summary,
            article_type=data.article_type,
            status="draft",
            version=1,
            language=data.language,
            audience=data.audience,
            visibility_scope=data.visibility_scope,
            category=data.category,
            subcategory=data.subcategory,
            product_or_system=data.product_or_system,
            platform=data.platform,
            issue_type=data.issue_type,
            severity_hint=data.severity_hint,
            tags=data.tags,
            keywords=data.keywords,
            ownership_group_id=uuid.UUID(data.ownership_group_id)
            if data.ownership_group_id
            else None,
            content=data.content,
            symptoms=data.symptoms,
            probable_causes=data.probable_causes,
            prerequisites=data.prerequisites,
            troubleshooting_steps=[s.model_dump() for s in data.troubleshooting_steps],
            resolution_steps=[s.model_dump() for s in data.resolution_steps],
            validation_steps=[s.model_dump() for s in data.validation_steps],
            escalation_criteria=data.escalation_criteria,
            escalation_target_team=data.escalation_target_team,
            references=data.references,
            related_articles=data.related_articles,
            citation_label=data.citation_label,
            source_type=data.source_type or "authored",
            source_reference=data.source_reference,
            author_id=actor.id,
            next_review_due_at=now + timedelta(days=interval),
            embedding_status="not_indexed",
        )
        article.citation_label = article.citation_label or normalization.build_citation_label(
            article_to_dict(article)
        )
        self._recompute_quality(article)
        await self.repo.add(article)
        # Prepare retrieval text + chunks so the preview is immediately useful.
        await self.indexing.prepare_article(article)
        await self.audit.log(
            "knowledge.article_created",
            "knowledge_article",
            actor=actor,
            resource_id=str(article.id),
            description=f"Draft article '{article.title}' created",
        )
        logger.info("knowledge_article_created", article_id=str(article.id), author=actor.email)
        return article

    async def update_article(self, actor: User, article_id: uuid.UUID, data) -> KnowledgeArticle:
        """Apply a partial update to a draft/in-review/approved article.

        Published articles are immutable in place — callers must first run the
        ``create_revision`` transition (which forks a new draft).
        """
        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        if article.status == "published":
            raise KnowledgeManagementError(
                "Published articles cannot be edited directly. Create a new revision first."
            )
        if article.status == "archived":
            raise KnowledgeManagementError("Archived articles must be restored before editing.")

        payload = data.model_dump(exclude_unset=True)
        for field in _DIRECT_UPDATE_FIELDS:
            if field in payload:
                setattr(article, field, payload[field])
        for field in _STEP_FIELDS:
            if data and getattr(data, field, None) is not None:
                setattr(article, field, [s.model_dump() for s in getattr(data, field)])

        article.citation_label = article.citation_label or normalization.build_citation_label(
            article_to_dict(article)
        )
        self._recompute_quality(article)
        await self.indexing.prepare_article(article)
        await self.audit.log(
            "knowledge.article_updated",
            "knowledge_article",
            actor=actor,
            resource_id=str(article.id),
            description=f"Article '{article.title}' updated",
            metadata={"change_summary": payload.get("change_summary")},
        )
        return article

    # ── Lifecycle ───────────────────────────────────────────────

    async def transition(
        self,
        actor: User,
        actor_permissions: set[str],
        article_id: uuid.UUID,
        action_key: str,
        *,
        note: str | None = None,
        change_summary: str | None = None,
    ) -> KnowledgeArticle:
        """Move an article through its governed lifecycle."""
        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")

        action = lifecycle.assert_transition(action_key, article.status)
        if action.permission not in actor_permissions:
            raise PermissionError(
                f"Permission '{action.permission}' required to {action.label.lower()}"
            )

        # Submit-for-review gate: must have minimum viable content.
        if action_key == "submit_for_review":
            issues = lifecycle.validate_for_submit(article_to_dict(article))
            if issues:
                raise KnowledgeManagementError(
                    "Article is not ready to submit for review: " + "; ".join(issues)
                )

        # Publish-readiness gate.
        if action.requires_publish_validation:
            issues = lifecycle.validate_for_publish(article_to_dict(article))
            if issues:
                raise KnowledgeManagementError(
                    "Article is not ready to publish: " + "; ".join(issues)
                )

        from_status = article.status
        to_status = action.to_state

        if action.snapshots_version:
            self._snapshot_version(article, actor, change_summary or action.label)

        now = datetime.now(UTC)
        article.status = to_status

        # Governance side-effects per transition.
        if action_key == "approve":
            article.reviewer_id = actor.id
            article.is_approved = True
        elif action_key == "publish":
            article.approver_id = actor.id
            article.published_at = now
            article.last_reviewed_at = now
            article.is_published = True
            article.is_approved = True
            article.approved_by = actor.id
            if article.next_review_due_at is None:
                article.next_review_due_at = now + timedelta(days=DEFAULT_REVIEW_INTERVAL_DAYS)
            await self.indexing.index_article(article)
        elif action_key == "archive":
            article.archived_at = now
            article.is_published = False
            await self.indexing.remove_from_index(article)
        elif action_key == "create_revision":
            # Fork: bump version, reset publication flags for the new draft.
            article.version += 1
            article.is_published = False
            article.is_approved = False
            article.published_at = None
        elif action_key in ("request_changes", "reject"):
            article.is_approved = False

        if note:
            self.db.add(
                KnowledgeReviewNote(
                    article_id=article.id,
                    reviewer_id=actor.id,
                    decision="approved"
                    if action_key == "approve"
                    else (
                        "rejected"
                        if action_key == "reject"
                        else ("changes_requested" if action_key == "request_changes" else "comment")
                    ),
                    note=note,
                    from_status=from_status,
                    to_status=to_status,
                )
            )

        await self.audit.log(
            f"knowledge.{action_key}",
            "knowledge_article",
            actor=actor,
            resource_id=str(article.id),
            description=f"Article '{article.title}': {from_status} → {to_status}",
            old_value={"status": from_status},
            new_value={"status": to_status},
            severity="info" if action_key != "publish" else "notice",
        )
        logger.info(
            "knowledge_transition",
            article_id=str(article.id),
            action=action_key,
            from_status=from_status,
            to_status=to_status,
            actor=actor.email,
        )
        return article

    def _snapshot_version(
        self, article: KnowledgeArticle, actor: User, change_summary: str
    ) -> None:
        snapshot = article_detail(article)
        version = KnowledgeArticleVersion(
            article_id=article.id,
            version=article.version,
            title=article.title,
            status=article.status,
            change_summary=change_summary,
            snapshot=snapshot,
            author_id=actor.id,
        )
        self.db.add(version)

    # ── Review notes ────────────────────────────────────────────

    async def add_review_note(
        self, actor: User, article_id: uuid.UUID, decision: str, note: str
    ) -> KnowledgeReviewNote:
        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        review_note = KnowledgeReviewNote(
            article_id=article.id,
            reviewer_id=actor.id,
            decision=decision,
            note=note,
            from_status=article.status,
            to_status=article.status,
        )
        await self.repo.add_review_note(review_note)
        await self.audit.log(
            "knowledge.review_note_added",
            "knowledge_article",
            actor=actor,
            resource_id=str(article.id),
            description=f"Review note ({decision}) added",
        )
        return review_note

    async def list_review_notes(self, article_id: uuid.UUID) -> list[KnowledgeReviewNote]:
        return await self.repo.list_review_notes(article_id)

    # ── Versions ────────────────────────────────────────────────

    async def list_versions(self, article_id: uuid.UUID) -> list[KnowledgeArticleVersion]:
        return await self.repo.list_versions(article_id)

    async def get_version(
        self, article_id: uuid.UUID, version: int
    ) -> KnowledgeArticleVersion | None:
        return await self.repo.get_version(article_id, version)

    # ── Feedback ────────────────────────────────────────────────

    async def submit_feedback(
        self,
        article_id: uuid.UUID,
        user: User | None,
        *,
        rating: int | None = None,
        was_helpful: bool | None = None,
        comment: str | None = None,
        source: str = "portal",
        resolved_issue: bool | None = None,
        session_id: uuid.UUID | None = None,
    ) -> KnowledgeFeedback:
        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        feedback = KnowledgeFeedback(
            article_id=article.id,
            user_id=user.id if user else None,
            rating=rating,
            was_helpful=was_helpful,
            comment=comment,
            source=source,
            resolved_issue=resolved_issue,
            session_id=session_id,
        )
        await self.repo.add_feedback(feedback)

        if was_helpful is False:
            article.negative_feedback_count += 1
        if resolved_issue:
            article.successful_resolution_count += 1

        agg = await self.repo.feedback_aggregate(article.id)
        if agg["count"]:
            helpful_ratio = agg["helpful_count"] / agg["count"]
            article.feedback_score = round(helpful_ratio, 3)
            article.helpfulness_score = article.feedback_score
        self._recompute_quality(article)
        logger.info("knowledge_feedback", article_id=str(article.id), helpful=was_helpful)
        return feedback

    async def list_feedback(self, article_id: uuid.UUID) -> list[KnowledgeFeedback]:
        return await self.repo.list_feedback(article_id)

    # ── Quality / author tools ──────────────────────────────────────

    async def get_completeness(self, article_id: uuid.UUID):
        """Return a ``CompletenessReport`` for an article."""
        from app.services.knowledge.quality import compute_completeness

        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        return compute_completeness(article_to_dict(article))

    async def get_author_warnings(self, article_id: uuid.UUID):
        """Return a list of ``AuthorWarning`` for the editor view."""
        from app.services.knowledge.quality import get_author_warnings

        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        return get_author_warnings(article_to_dict(article))

    async def get_stale_analysis(self, article_id: uuid.UUID):
        """Return a ``StaleAnalysis`` for an article."""
        from app.services.knowledge.quality import detect_staleness

        article = await self.repo.get(article_id)
        if not article:
            raise KnowledgeManagementError("Article not found")
        return detect_staleness(article_to_dict(article))

    async def create_from_template(
        self, actor: "User", template_key: str, overrides: dict
    ) -> "KnowledgeArticle":
        """Create a draft article pre-filled from a template.

        ``overrides`` may supply title, category, subcategory, ownership_group_id,
        or any other ``ArticleCreate``-compatible fields.  Template defaults are
        applied first; overrides win.
        """
        from app.schemas.knowledge import ArticleCreate
        from app.services.knowledge.templates import get_template

        template = get_template(template_key)
        if template is None:
            raise KnowledgeManagementError(f"Unknown template key: {template_key!r}")

        # Merge: template defaults < caller overrides.
        merged: dict = {
            "title": template.label,
            "category": template.category,
            "subcategory": template.subcategory,
            "product_or_system": template.product_or_system,
            **template.defaults,
            **{k: v for k, v in overrides.items() if v is not None},
        }

        # Coerce step dicts into StepSchema objects for ArticleCreate.
        from app.schemas.knowledge import StepSchema

        for step_field in ("troubleshooting_steps", "resolution_steps", "validation_steps"):
            raw_steps = merged.get(step_field) or []
            merged[step_field] = [
                StepSchema(**s) if isinstance(s, dict) else s for s in raw_steps
            ]

        data = ArticleCreate(**merged)
        return await self.create_draft(actor, data)

    # ── Quality scoring ─────────────────────────────────────────

    @staticmethod
    def _recompute_quality(article: KnowledgeArticle) -> None:
        """Heuristic 0–1 quality score combining completeness + outcomes."""
        score = 0.0
        # Structural completeness (max 0.6)
        if article.short_summary:
            score += 0.1
        if article.resolution_steps or article.troubleshooting_steps:
            score += 0.2
        if article.symptoms:
            score += 0.1
        if article.tags:
            score += 0.1
        if article.escalation_criteria:
            score += 0.1
        # Outcome signals (max 0.4)
        if article.feedback_score is not None:
            score += 0.3 * article.feedback_score
        usage = article.usage_count or 0
        resolved = article.successful_resolution_count or 0
        if usage:
            score += 0.1 * min(1.0, resolved / usage)
        article.quality_score = round(min(1.0, score), 3)
        article.confidence_level = article.quality_score
