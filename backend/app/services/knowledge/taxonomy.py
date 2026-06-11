"""Taxonomy and ownership-group management + classification validation.

Standardizes article classification: admins manage the controlled vocabulary
(categories, products, platforms, tags, …) and publish-time validation ensures
articles are not missing essential, governed metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.models.knowledge import KnowledgeOwnershipGroup, KnowledgeTaxonomyTerm

if TYPE_CHECKING:
    import uuid

    from app.repositories.knowledge_repository import KnowledgeRepository

logger = get_logger(__name__)

#: Taxonomy dimensions a published article must classify against.
REQUIRED_CLASSIFICATION_TYPES: tuple[str, ...] = ("category",)


class TaxonomyError(ValueError):
    """Raised on invalid taxonomy operations (duplicates, unknown parents)."""


class KnowledgeTaxonomyService:
    """CRUD + validation for the knowledge taxonomy."""

    def __init__(self, repo: KnowledgeRepository) -> None:
        self.repo = repo

    async def list_terms(self, term_type: str | None = None) -> list[KnowledgeTaxonomyTerm]:
        return await self.repo.list_taxonomy(term_type)

    async def grouped(self) -> dict[str, list[KnowledgeTaxonomyTerm]]:
        """Return taxonomy terms grouped by type for the management UI."""
        terms = await self.repo.list_taxonomy()
        grouped: dict[str, list[KnowledgeTaxonomyTerm]] = {}
        for term in terms:
            grouped.setdefault(term.term_type, []).append(term)
        return grouped

    async def create_term(
        self,
        *,
        term_type: str,
        key: str,
        label: str,
        description: str | None = None,
        parent_id: uuid.UUID | None = None,
        ticket_category_mapping: str | None = None,
        sort_order: int = 0,
    ) -> KnowledgeTaxonomyTerm:
        existing = await self.repo.get_taxonomy_by_key(term_type, key)
        if existing:
            raise TaxonomyError(f"Taxonomy term already exists: {term_type}/{key}")
        if parent_id:
            parent = await self.repo.get_taxonomy_term(parent_id)
            if not parent:
                raise TaxonomyError("Parent taxonomy term not found")
        term = KnowledgeTaxonomyTerm(
            term_type=term_type,
            key=key,
            label=label,
            description=description,
            parent_id=parent_id,
            ticket_category_mapping=ticket_category_mapping,
            sort_order=sort_order,
        )
        await self.repo.add_taxonomy_term(term)
        logger.info("taxonomy_term_created", term_type=term_type, key=key)
        return term

    async def update_term(self, term_id: uuid.UUID, changes: dict) -> KnowledgeTaxonomyTerm:
        term = await self.repo.get_taxonomy_term(term_id)
        if not term:
            raise TaxonomyError("Taxonomy term not found")
        for field, value in changes.items():
            if value is not None and hasattr(term, field):
                setattr(term, field, value)
        return term

    async def delete_term(self, term_id: uuid.UUID) -> None:
        term = await self.repo.get_taxonomy_term(term_id)
        if not term:
            raise TaxonomyError("Taxonomy term not found")
        # Soft-deactivate to preserve historical classification integrity.
        term.is_active = False

    async def validate_classification(self, article_dict: dict) -> list[str]:
        """Return classification issues blocking publication.

        Ensures the article's category exists in the controlled vocabulary and
        that required classification dimensions are present.
        """
        issues: list[str] = []
        for term_type in REQUIRED_CLASSIFICATION_TYPES:
            if not article_dict.get(term_type):
                issues.append(f"Missing required classification: {term_type}")

        category = article_dict.get("category")
        if category:
            known = await self.repo.get_taxonomy_by_key("category", category)
            if not known:
                # Non-fatal: warn but allow (admins may add the term later).
                issues.append(
                    f"Category '{category}' is not in the managed taxonomy — "
                    f"add it under Taxonomy to standardize classification"
                )
        return issues

    # ── Ownership groups ────────────────────────────────────────

    async def list_groups(self) -> list[KnowledgeOwnershipGroup]:
        return await self.repo.list_ownership_groups()

    async def create_group(
        self,
        *,
        name: str,
        display_name: str,
        description: str | None = None,
        owner_id: uuid.UUID | None = None,
        default_reviewer_id: uuid.UUID | None = None,
        member_ids: list[str] | None = None,
    ) -> KnowledgeOwnershipGroup:
        group = KnowledgeOwnershipGroup(
            name=name,
            display_name=display_name,
            description=description,
            owner_id=owner_id,
            default_reviewer_id=default_reviewer_id,
            member_ids=member_ids or [],
        )
        await self.repo.add_ownership_group(group)
        logger.info("ownership_group_created", name=name)
        return group
