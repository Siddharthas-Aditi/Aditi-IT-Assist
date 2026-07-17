"""Admin / IT-Lead knowledge management & governance endpoints.

Mounted under ``/knowledge/admin``. Every endpoint is permission-gated; the
fine-grained per-transition permission is enforced inside the management
service using the actor's resolved permission set, so the *same* transition
endpoint correctly returns 403 for an actor lacking that specific capability
(e.g. an agent attempting to ``publish``).
"""

import uuid
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.permissions import P
from app.models.auth import User
from app.schemas.knowledge import (
    ArticleCreate,
    ArticleDetail,
    ArticleListResponse,
    ArticleSummary,
    ArticleTemplateSchema,
    ArticleUpdate,
    AuthorWarningSchema,
    CompletenessReportSchema,
    DuplicateHintSchema,
    FeedbackSchema,
    IndexingStatusResponse,
    KnowledgeAnalyticsSummary,
    LifecycleTransitionRequest,
    OwnershipGroupCreate,
    OwnershipGroupSchema,
    ReindexRequest,
    ReindexResult,
    RetrievalPreviewResponse,
    ReviewNoteCreate,
    ReviewNoteSchema,
    StaleAnalysisSchema,
    TaxonomyTermCreate,
    TaxonomyTermSchema,
    TaxonomyTermUpdate,
    VersionDetailSchema,
    VersionSchema,
)
from app.services.auth.dependencies import require_permissions
from app.services.auth.service import AuthService
from app.services.knowledge import normalization
from app.services.knowledge.analytics import KnowledgeAnalyticsService
from app.services.knowledge.indexing import KnowledgeIndexingService
from app.services.knowledge.lifecycle import LifecycleError
from app.services.knowledge.management import KnowledgeManagementError, KnowledgeManagementService
from app.services.knowledge.serializers import (
    article_detail,
    article_summary,
    article_to_dict,
    feedback_to_dict,
    ownership_group_to_dict,
    review_note_to_dict,
    taxonomy_to_dict,
    version_summary,
)
from app.services.knowledge.taxonomy import KnowledgeTaxonomyService, TaxonomyError

logger = get_logger(__name__)
router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]

# Permission-gated actor dependencies (role-agnostic; auditors admitted to reads).
InternalReader = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_VIEW_INTERNAL))]
Author = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_CREATE))]
Editor = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_UPDATE_OWN))]
Reviewer = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_REVIEW))]
TaxonomyAdmin = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_MANAGE_CATEGORIES))]
OwnershipAdmin = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_MANAGE_OWNERSHIP))]
Reindexer = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_REINDEX))]
AnalyticsViewer = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_VIEW_ANALYTICS))]


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid id") from exc


async def _require_article(service: KnowledgeManagementService, article_id: str):
    article = await service.get_article(_parse_uuid(article_id))
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


# ─────────────────────────────────────────────────────────────────────
# Article listing & CRUD
# ─────────────────────────────────────────────────────────────────────


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    actor: InternalReader,
    db: DBDep,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    product_or_system: str | None = None,
    platform: str | None = None,
    audience: str | None = None,
    ownership_group_id: str | None = None,
    search: str | None = None,
    review_due: bool = False,
    limit: int = 25,
    offset: int = 0,
) -> ArticleListResponse:
    """List/search/filter knowledge articles for management views."""
    from datetime import datetime

    service = KnowledgeManagementService(db)
    statuses = [status_filter] if status_filter else None
    articles, total = await service.list_articles(
        statuses=statuses,
        category=category,
        product_or_system=product_or_system,
        platform=platform,
        audience=audience,
        ownership_group_id=_parse_uuid(ownership_group_id) if ownership_group_id else None,
        search=search,
        review_due_before=datetime.now(UTC) if review_due else None,
        limit=limit,
        offset=offset,
    )
    return ArticleListResponse(
        articles=[ArticleSummary(**article_summary(a)) for a in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/review-queue", response_model=list[ArticleSummary])
async def review_queue(actor: Reviewer, db: DBDep) -> list[ArticleSummary]:
    """Articles awaiting review (status = in_review)."""
    service = KnowledgeManagementService(db)
    return [ArticleSummary(**article_summary(a)) for a in await service.review_queue()]


@router.get("/stale", response_model=list[ArticleSummary])
async def stale_articles(actor: InternalReader, db: DBDep) -> list[ArticleSummary]:
    """Published articles past their next review date."""
    service = KnowledgeManagementService(db)
    return [ArticleSummary(**article_summary(a)) for a in await service.stale_articles()]


@router.get("/duplicates", response_model=list[DuplicateHintSchema])
async def duplicate_hints(
    actor: InternalReader, db: DBDep, title: str
) -> list[DuplicateHintSchema]:
    """Lightweight duplicate-title hints for the editor."""
    service = KnowledgeManagementService(db)
    rows = await service.find_duplicate_hints(title)
    return [DuplicateHintSchema(**r) for r in rows]


@router.post("/articles", response_model=ArticleDetail, status_code=201)
async def create_article(data: ArticleCreate, actor: Author, db: DBDep) -> ArticleDetail:
    """Create a new draft article."""
    service = KnowledgeManagementService(db)
    article = await service.create_draft(actor, data)
    return ArticleDetail(**article_detail(article))


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: str, actor: InternalReader, db: DBDep) -> ArticleDetail:
    """Get full article detail for the editor / detail view."""
    service = KnowledgeManagementService(db)
    article = await _require_article(service, article_id)
    return ArticleDetail(**article_detail(article))


@router.patch("/articles/{article_id}", response_model=ArticleDetail)
async def update_article(
    article_id: str, data: ArticleUpdate, actor: Editor, db: DBDep
) -> ArticleDetail:
    """Apply a partial update to a non-published article."""
    service = KnowledgeManagementService(db)
    try:
        article = await service.update_article(actor, _parse_uuid(article_id), data)
    except KnowledgeManagementError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 409
        raise HTTPException(status_code=code, detail=detail) from exc
    return ArticleDetail(**article_detail(article))


# ─────────────────────────────────────────────────────────────────────
# Lifecycle transitions
# ─────────────────────────────────────────────────────────────────────


@router.post("/articles/{article_id}/transition", response_model=ArticleDetail)
async def transition_article(
    article_id: str,
    data: LifecycleTransitionRequest,
    actor: InternalReader,
    db: DBDep,
) -> ArticleDetail:
    """Move an article through its governed lifecycle (per-action permission)."""
    service = KnowledgeManagementService(db)
    permissions = await AuthService(db).get_user_permissions(actor)
    try:
        article = await service.transition(
            actor,
            permissions,
            _parse_uuid(article_id),
            data.action,
            note=data.note,
            change_summary=data.change_summary,
            ownership_group_id=data.ownership_group_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LifecycleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except KnowledgeManagementError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return ArticleDetail(**article_detail(article))


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: str,
    actor: InternalReader,
    db: DBDep,
) -> None:
    """Permanently delete an article (requires knowledge:delete permission).

    Removes the article from the vector index first if it was published.
    """
    service = KnowledgeManagementService(db)
    permissions = await AuthService(db).get_user_permissions(actor)
    try:
        await service.delete_article(actor, permissions, _parse_uuid(article_id))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KnowledgeManagementError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 422
        raise HTTPException(status_code=code, detail=detail) from exc
    await db.commit()


# ─────────────────────────────────────────────────────────────────────
# Versions
# ─────────────────────────────────────────────────────────────────────


@router.get("/articles/{article_id}/versions", response_model=list[VersionSchema])
async def list_versions(article_id: str, actor: InternalReader, db: DBDep) -> list[VersionSchema]:
    """Version history for an article (also visible to auditors)."""
    service = KnowledgeManagementService(db)
    versions = await service.list_versions(_parse_uuid(article_id))
    return [VersionSchema(**version_summary(v)) for v in versions]


@router.get("/articles/{article_id}/versions/{version}", response_model=VersionDetailSchema)
async def get_version(
    article_id: str, version: int, actor: InternalReader, db: DBDep
) -> VersionDetailSchema:
    """Get a single version snapshot (for diff / restore preview)."""
    service = KnowledgeManagementService(db)
    snap = await service.get_version(_parse_uuid(article_id), version)
    if not snap:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionDetailSchema(**version_summary(snap), snapshot=snap.snapshot)


# ─────────────────────────────────────────────────────────────────────
# Retrieval preview
# ─────────────────────────────────────────────────────────────────────


@router.get("/articles/{article_id}/preview", response_model=RetrievalPreviewResponse)
async def retrieval_preview(
    article_id: str, actor: InternalReader, db: DBDep
) -> RetrievalPreviewResponse:
    """Preview exactly how an article will be presented to the AI retrieval layer."""
    service = KnowledgeManagementService(db)
    article = await _require_article(service, article_id)
    article_dict = article_to_dict(article)
    chunks = normalization.build_chunks(article_dict)
    warnings: list[str] = []
    if not chunks:
        warnings.append("No retrievable content — add summary, steps, or body content.")
    if article.status != "published":
        warnings.append(
            f"Article is '{article.status}'. It will NOT be retrievable by the "
            "chat agent until published."
        )
    return RetrievalPreviewResponse(
        article_id=str(article.id),
        citation_label=normalization.build_citation_label(article_dict),
        chunking_strategy=article.chunking_strategy,
        retrieval_text=normalization.build_retrieval_text(article_dict),
        chunks=[
            {
                "chunk_index": c.chunk_index,
                "section": c.section,
                "header": c.header,
                "content": c.content,
                "token_estimate": c.token_estimate,
                "embedding_status": article.embedding_status,
            }
            for c in chunks
        ],
        total_tokens=sum(c.token_estimate for c in chunks),
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────
# Review notes & feedback (reads)
# ─────────────────────────────────────────────────────────────────────


@router.get("/articles/{article_id}/review-notes", response_model=list[ReviewNoteSchema])
async def list_review_notes(
    article_id: str, actor: InternalReader, db: DBDep
) -> list[ReviewNoteSchema]:
    service = KnowledgeManagementService(db)
    notes = await service.list_review_notes(_parse_uuid(article_id))
    return [ReviewNoteSchema(**review_note_to_dict(n)) for n in notes]


@router.post(
    "/articles/{article_id}/review-notes", response_model=ReviewNoteSchema, status_code=201
)
async def add_review_note(
    article_id: str, data: ReviewNoteCreate, actor: Reviewer, db: DBDep
) -> ReviewNoteSchema:
    service = KnowledgeManagementService(db)
    try:
        note = await service.add_review_note(
            actor, _parse_uuid(article_id), data.decision, data.note
        )
    except KnowledgeManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewNoteSchema(**review_note_to_dict(note))


@router.get("/articles/{article_id}/feedback", response_model=list[FeedbackSchema])
async def list_feedback(article_id: str, actor: InternalReader, db: DBDep) -> list[FeedbackSchema]:
    service = KnowledgeManagementService(db)
    items = await service.list_feedback(_parse_uuid(article_id))
    return [FeedbackSchema(**feedback_to_dict(f)) for f in items]


# ─────────────────────────────────────────────────────────────────────
# Taxonomy & ownership
# ─────────────────────────────────────────────────────────────────────


@router.get("/taxonomy", response_model=list[TaxonomyTermSchema])
async def list_taxonomy(
    actor: InternalReader, db: DBDep, term_type: str | None = None
) -> list[TaxonomyTermSchema]:
    service = KnowledgeTaxonomyService(_repo(db))
    terms = await service.list_terms(term_type)
    return [TaxonomyTermSchema(**taxonomy_to_dict(t)) for t in terms]


@router.post("/taxonomy", response_model=TaxonomyTermSchema, status_code=201)
async def create_taxonomy_term(
    data: TaxonomyTermCreate, actor: TaxonomyAdmin, db: DBDep
) -> TaxonomyTermSchema:
    service = KnowledgeTaxonomyService(_repo(db))
    try:
        term = await service.create_term(
            term_type=data.term_type,
            key=data.key,
            label=data.label,
            description=data.description,
            parent_id=_parse_uuid(data.parent_id) if data.parent_id else None,
            ticket_category_mapping=data.ticket_category_mapping,
            sort_order=data.sort_order,
        )
    except TaxonomyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaxonomyTermSchema(**taxonomy_to_dict(term))


@router.patch("/taxonomy/{term_id}", response_model=TaxonomyTermSchema)
async def update_taxonomy_term(
    term_id: str, data: TaxonomyTermUpdate, actor: TaxonomyAdmin, db: DBDep
) -> TaxonomyTermSchema:
    service = KnowledgeTaxonomyService(_repo(db))
    try:
        term = await service.update_term(_parse_uuid(term_id), data.model_dump(exclude_unset=True))
    except TaxonomyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaxonomyTermSchema(**taxonomy_to_dict(term))


@router.delete("/taxonomy/{term_id}", status_code=204)
async def delete_taxonomy_term(term_id: str, actor: TaxonomyAdmin, db: DBDep) -> None:
    service = KnowledgeTaxonomyService(_repo(db))
    try:
        await service.delete_term(_parse_uuid(term_id))
    except TaxonomyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ownership-groups", response_model=list[OwnershipGroupSchema])
async def list_ownership_groups(actor: InternalReader, db: DBDep) -> list[OwnershipGroupSchema]:
    service = KnowledgeTaxonomyService(_repo(db))
    groups = await service.list_groups()
    return [OwnershipGroupSchema(**ownership_group_to_dict(g)) for g in groups]


@router.post("/ownership-groups", response_model=OwnershipGroupSchema, status_code=201)
async def create_ownership_group(
    data: OwnershipGroupCreate, actor: OwnershipAdmin, db: DBDep
) -> OwnershipGroupSchema:
    service = KnowledgeTaxonomyService(_repo(db))
    group = await service.create_group(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        owner_id=_parse_uuid(data.owner_id) if data.owner_id else None,
        default_reviewer_id=_parse_uuid(data.default_reviewer_id)
        if data.default_reviewer_id
        else None,
        member_ids=data.member_ids,
    )
    return OwnershipGroupSchema(**ownership_group_to_dict(group))


# ─────────────────────────────────────────────────────────────────────
# Quality, completeness, stale analysis, templates
# ─────────────────────────────────────────────────────────────────────


@router.get("/articles/{article_id}/completeness", response_model=CompletenessReportSchema)
async def article_completeness(
    article_id: str, actor: InternalReader, db: DBDep
) -> CompletenessReportSchema:
    """Return a multi-dimension completeness report for an article."""
    service = KnowledgeManagementService(db)
    try:
        report = await service.get_completeness(_parse_uuid(article_id))
    except KnowledgeManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from dataclasses import asdict

    return CompletenessReportSchema(**asdict(report))


@router.get("/articles/{article_id}/warnings", response_model=list[AuthorWarningSchema])
async def article_warnings(
    article_id: str, actor: InternalReader, db: DBDep
) -> list[AuthorWarningSchema]:
    """Return inline author warnings for the editor view."""
    service = KnowledgeManagementService(db)
    try:
        raw = await service.get_author_warnings(_parse_uuid(article_id))
    except KnowledgeManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        AuthorWarningSchema(
            severity=w.severity, field=w.field, message=w.message, guidance=w.guidance
        )
        for w in raw
    ]


@router.get("/articles/{article_id}/stale-analysis", response_model=StaleAnalysisSchema)
async def article_stale_analysis(
    article_id: str, actor: InternalReader, db: DBDep
) -> StaleAnalysisSchema:
    """Return a detailed staleness analysis for a published article."""
    service = KnowledgeManagementService(db)
    try:
        result = await service.get_stale_analysis(_parse_uuid(article_id))
    except KnowledgeManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from dataclasses import asdict

    return StaleAnalysisSchema(**asdict(result))


@router.get("/templates", response_model=list[ArticleTemplateSchema])
async def list_article_templates(actor: Author, db: DBDep) -> list[ArticleTemplateSchema]:
    """List available article scaffolding templates."""
    from app.services.knowledge.templates import list_templates

    return [
        ArticleTemplateSchema(
            key=t.key,
            label=t.label,
            category=t.category,
            subcategory=t.subcategory,
            product_or_system=t.product_or_system,
            description=t.description,
            icon=t.icon,
        )
        for t in list_templates()
    ]


@router.post(
    "/articles/from-template/{template_key}", response_model=ArticleDetail, status_code=201
)
async def create_article_from_template(
    template_key: str,
    actor: Author,
    db: DBDep,
    title: str | None = None,
    ownership_group_id: str | None = None,
) -> ArticleDetail:
    """Create a draft article pre-filled from a named template.

    Pass ``title`` and ``ownership_group_id`` as query params to override
    the template defaults immediately.
    """
    service = KnowledgeManagementService(db)
    overrides: dict = {}
    if title:
        overrides["title"] = title
    if ownership_group_id:
        overrides["ownership_group_id"] = ownership_group_id
    try:
        article = await service.create_from_template(actor, template_key, overrides)
    except KnowledgeManagementError as exc:
        detail = str(exc)
        code = 400 if "Unknown template" in detail else 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return ArticleDetail(**article_detail(article))


# ─────────────────────────────────────────────────────────────────────
# Indexing
# ─────────────────────────────────────────────────────────────────────


@router.get("/indexing/status", response_model=IndexingStatusResponse)
async def indexing_status(actor: InternalReader, db: DBDep) -> IndexingStatusResponse:
    service = KnowledgeIndexingService(_repo(db))
    return IndexingStatusResponse(**await service.get_status())


@router.post("/indexing/reindex", response_model=ReindexResult)
async def reindex(data: ReindexRequest, actor: Reindexer, db: DBDep) -> ReindexResult:
    service = KnowledgeIndexingService(_repo(db))
    ids = [_parse_uuid(a) for a in data.article_ids] if data.article_ids else None
    result = await service.reindex(article_ids=ids, only_stale=data.only_stale)
    logger.info(
        "knowledge_reindex_triggered",
        actor=actor.email,
        **{k: v for k, v in result.items() if k != "errors"},
    )
    return ReindexResult(**result)


# ─────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────


@router.get("/analytics/summary", response_model=KnowledgeAnalyticsSummary)
async def analytics_summary(actor: AnalyticsViewer, db: DBDep) -> KnowledgeAnalyticsSummary:
    service = KnowledgeAnalyticsService(db)
    return KnowledgeAnalyticsSummary(**await service.summary())


@router.get("/analytics/articles/{article_id}")
async def article_analytics(article_id: str, actor: AnalyticsViewer, db: DBDep) -> dict:
    service = KnowledgeAnalyticsService(db)
    result = await service.article_detail(_parse_uuid(article_id))
    if not result:
        raise HTTPException(status_code=404, detail="Article not found")
    return result


def _repo(db: AsyncSession):
    """Local factory to build a repository (keeps imports localized)."""
    from app.repositories.knowledge_repository import KnowledgeRepository

    return KnowledgeRepository(db)
