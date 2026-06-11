"""Serialization helpers — knowledge ORM models → API/schema-friendly dicts.

Keeps the conversion logic in one place so the API layer stays thin and the
``ArticleDetail``/``ArticleSummary`` shapes never drift across endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.services.knowledge.lifecycle import LIFECYCLE_ACTIONS

if TYPE_CHECKING:
    from app.models.knowledge import (
        KnowledgeArticle,
        KnowledgeArticleVersion,
        KnowledgeChunk,
        KnowledgeFeedback,
        KnowledgeOwnershipGroup,
        KnowledgeReviewNote,
        KnowledgeTaxonomyTerm,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def is_stale(article: KnowledgeArticle, *, now: datetime | None = None) -> bool:
    """An article is stale when published and past its next review date."""
    if article.status != "published" or article.next_review_due_at is None:
        return False
    now = now or datetime.now(UTC)
    due = article.next_review_due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due <= now


def article_to_dict(article: KnowledgeArticle) -> dict:
    """Plain dict view used by normalization and validation (storage-agnostic)."""
    return {
        "id": str(article.id),
        "slug": article.slug,
        "title": article.title,
        "short_summary": article.short_summary,
        "article_type": article.article_type,
        "status": article.status,
        "category": article.category,
        "subcategory": article.subcategory,
        "product_or_system": article.product_or_system,
        "platform": article.platform,
        "audience": article.audience,
        "tags": article.tags or [],
        "keywords": article.keywords or [],
        "content": article.content,
        "symptoms": article.symptoms or [],
        "probable_causes": article.probable_causes or [],
        "prerequisites": article.prerequisites or [],
        "troubleshooting_steps": article.troubleshooting_steps or [],
        "resolution_steps": article.resolution_steps or [],
        "validation_steps": article.validation_steps or [],
        "escalation_criteria": article.escalation_criteria,
        "escalation_target_team": article.escalation_target_team,
        "references": article.references or [],
        "related_articles": article.related_articles or [],
        "citation_label": article.citation_label,
        "ownership_group_id": str(article.ownership_group_id)
        if article.ownership_group_id
        else None,
    }


def available_actions(status: str) -> list[str]:
    return [key for key, action in LIFECYCLE_ACTIONS.items() if status in action.from_states]


def article_summary(article: KnowledgeArticle) -> dict:
    return {
        "id": str(article.id),
        "slug": article.slug,
        "title": article.title,
        "short_summary": article.short_summary,
        "status": article.status,
        "article_type": article.article_type,
        "category": article.category,
        "subcategory": article.subcategory,
        "product_or_system": article.product_or_system,
        "platform": article.platform,
        "audience": article.audience,
        "version": article.version,
        "tags": article.tags or [],
        "ownership_group_id": str(article.ownership_group_id)
        if article.ownership_group_id
        else None,
        "embedding_status": article.embedding_status,
        "quality_score": article.quality_score,
        "view_count": article.view_count,
        "usage_count": article.usage_count,
        "feedback_score": article.feedback_score,
        "next_review_due_at": _iso(article.next_review_due_at),
        "is_stale": is_stale(article),
        "updated_at": _iso(article.updated_at),
    }


def article_detail(article: KnowledgeArticle) -> dict:
    data = article_summary(article)
    data.update(
        {
            "content": article.content,
            "keywords": article.keywords or [],
            "issue_type": article.issue_type,
            "severity_hint": article.severity_hint,
            "visibility_scope": article.visibility_scope,
            "symptoms": article.symptoms or [],
            "probable_causes": article.probable_causes or [],
            "prerequisites": article.prerequisites or [],
            "troubleshooting_steps": article.troubleshooting_steps or [],
            "resolution_steps": article.resolution_steps or [],
            "validation_steps": article.validation_steps or [],
            "escalation_criteria": article.escalation_criteria,
            "escalation_target_team": article.escalation_target_team,
            "references": article.references or [],
            "related_articles": article.related_articles or [],
            "citation_label": article.citation_label,
            "source_type": article.source_type,
            "source_reference": article.source_reference,
            "author_id": str(article.author_id) if article.author_id else None,
            "reviewer_id": str(article.reviewer_id) if article.reviewer_id else None,
            "approver_id": str(article.approver_id) if article.approver_id else None,
            "confidence_level": article.confidence_level,
            "last_reviewed_at": _iso(article.last_reviewed_at),
            "published_at": _iso(article.published_at),
            "archived_at": _iso(article.archived_at),
            "indexed_at": _iso(article.indexed_at),
            "index_version": article.index_version,
            "successful_resolution_count": article.successful_resolution_count,
            "negative_feedback_count": article.negative_feedback_count,
            "available_actions": available_actions(article.status),
            "created_at": _iso(article.created_at),
        }
    )
    return data


def version_summary(version: KnowledgeArticleVersion) -> dict:
    return {
        "id": str(version.id),
        "version": version.version,
        "title": version.title,
        "status": version.status,
        "change_summary": version.change_summary,
        "author_id": str(version.author_id) if version.author_id else None,
        "created_at": _iso(version.created_at),
    }


def chunk_to_dict(chunk: KnowledgeChunk) -> dict:
    return {
        "chunk_index": chunk.chunk_index,
        "section": chunk.section,
        "header": chunk.header,
        "content": chunk.content,
        "token_estimate": chunk.token_estimate,
        "embedding_status": chunk.embedding_status,
    }


def feedback_to_dict(fb: KnowledgeFeedback) -> dict:
    return {
        "id": str(fb.id),
        "article_id": str(fb.article_id),
        "rating": fb.rating,
        "was_helpful": fb.was_helpful,
        "comment": fb.comment,
        "source": fb.source,
        "created_at": _iso(fb.created_at),
    }


def review_note_to_dict(note: KnowledgeReviewNote) -> dict:
    return {
        "id": str(note.id),
        "reviewer_id": str(note.reviewer_id) if note.reviewer_id else None,
        "decision": note.decision,
        "note": note.note,
        "from_status": note.from_status,
        "to_status": note.to_status,
        "created_at": _iso(note.created_at),
    }


def taxonomy_to_dict(term: KnowledgeTaxonomyTerm) -> dict:
    return {
        "id": str(term.id),
        "term_type": term.term_type,
        "key": term.key,
        "label": term.label,
        "description": term.description,
        "parent_id": str(term.parent_id) if term.parent_id else None,
        "ticket_category_mapping": term.ticket_category_mapping,
        "sort_order": term.sort_order,
        "is_active": term.is_active,
    }


def ownership_group_to_dict(group: KnowledgeOwnershipGroup) -> dict:
    return {
        "id": str(group.id),
        "name": group.name,
        "display_name": group.display_name,
        "description": group.description,
        "owner_id": str(group.owner_id) if group.owner_id else None,
        "default_reviewer_id": str(group.default_reviewer_id)
        if group.default_reviewer_id
        else None,
        "member_ids": group.member_ids or [],
        "is_active": group.is_active,
    }
