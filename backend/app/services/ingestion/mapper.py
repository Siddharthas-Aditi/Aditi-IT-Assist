"""Mapper — converts a validated ingestion candidate into an ArticleCreate.

The mapper is a pure function layer that translates the ingestion domain
(``CandidatePayload`` / candidate ORM fields) into the knowledge authoring
domain (``ArticleCreate`` schema) so the existing ``KnowledgeManagementService``
can persist it as a draft article without modification.
"""

from __future__ import annotations

from app.schemas.knowledge import ArticleCreate, StepSchema


def map_candidate_to_article_create(
    candidate_fields: dict,
    *,
    job_id: str,
    candidate_index: int,
    author_id: str | None = None,
    ownership_group_id: str | None = None,
) -> ArticleCreate:
    """Build an ``ArticleCreate`` payload from a candidate's extracted fields.

    Parameters
    ----------
    candidate_fields:
        Dict of extracted fields — keys mirror ``IngestionCandidate`` columns
        (``extracted_title``, ``extracted_symptoms``, etc.).
    job_id:
        The parent ``IngestionJob`` UUID (string) — recorded as ``source_reference``.
    candidate_index:
        Zero-based position within the job — appended to ``source_reference``.
    author_id:
        Optional override for the article author.  When ``None`` the API layer
        will substitute the current user's ID before persisting.
    ownership_group_id:
        Optional ownership group to assign.
    """
    title = candidate_fields.get("extracted_title") or "Untitled — review required"
    category = candidate_fields.get("extracted_category") or "other"

    troubleshooting_steps = _to_step_schemas(
        candidate_fields.get("extracted_troubleshooting_steps") or []
    )
    resolution_steps = _to_step_schemas(candidate_fields.get("extracted_resolution_steps") or [])
    symptoms = candidate_fields.get("extracted_symptoms") or []
    tags = candidate_fields.get("extracted_tags") or []
    keywords = candidate_fields.get("extracted_keywords") or []

    return ArticleCreate(
        title=title,
        short_summary=candidate_fields.get("extracted_summary"),
        article_type="troubleshooting",
        language="en",
        audience="employee",
        visibility_scope="public_internal",
        category=category,
        subcategory=candidate_fields.get("extracted_subcategory"),
        product_or_system=candidate_fields.get("extracted_product_or_system"),
        platform=candidate_fields.get("extracted_platform"),
        tags=[str(t) for t in tags if t],
        keywords=[str(k) for k in keywords if k],
        ownership_group_id=str(ownership_group_id) if ownership_group_id else None,
        symptoms=[str(s) for s in symptoms if s],
        troubleshooting_steps=troubleshooting_steps,
        resolution_steps=resolution_steps,
        escalation_criteria=candidate_fields.get("extracted_escalation_criteria"),
        source_type="document_ingestion",
        source_reference=f"ingestion:{job_id}:{candidate_index}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_step_schemas(raw_steps: list) -> list[StepSchema]:
    """Coerce raw step dicts or strings into ``StepSchema`` instances."""
    result: list[StepSchema] = []
    for i, step in enumerate(raw_steps, start=1):
        if isinstance(step, dict):
            result.append(
                StepSchema(
                    step_number=int(step.get("step_number", i)),
                    instruction=str(step.get("instruction", "")).strip(),
                    details=str(step.get("details", "")).strip() or None,
                )
            )
        elif isinstance(step, str) and step.strip():
            result.append(
                StepSchema(
                    step_number=i,
                    instruction=step.strip(),
                    details=None,
                )
            )
    return result
