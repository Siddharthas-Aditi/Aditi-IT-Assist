"""Optional LLM-assisted field extraction for ingestion candidates.

Called by the pipeline ONLY when:
  - ``settings.INGESTION_LLM_ENABLED`` is True
  - ``LLMService.is_available`` is True

The LLM is given the raw segment text and asked to fill in missing or
low-confidence fields using a strict JSON output schema.  If the LLM call
fails or returns invalid JSON the original deterministic payload is returned
unchanged — LLM enrichment is always additive, never replacing.

Confidence delta: successful enrichment can raise ``CandidatePayload.confidence``
by up to +0.15 (capped at 0.95).
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.ingestion.parser import CandidatePayload

logger = logging.getLogger(__name__)

# ── JSON output schema sent to the LLM ───────────────────────────────────────
_OUTPUT_SCHEMA = {
    "title": "string or null",
    "short_summary": "string (≤ 250 chars) or null",
    "category": "one of: email/outlook, video-conferencing/zoom, video-conferencing/teams, device-management/intune, hardware/camera, hardware/other, network/connectivity, access/permissions, software/other, other",
    "subcategory": "string or null",
    "product_or_system": "string or null — the primary software/hardware product name",
    "platform": "string or null — e.g. Windows, macOS, iOS",
    "symptoms": "array of strings describing observed problems",
    "troubleshooting_steps": "array of {step_number: int, instruction: string, details: string}",
    "resolution_steps": "array of {step_number: int, instruction: string, details: string}",
    "escalation_criteria": "string or null — when to escalate to human support",
    "tags": "array of short lowercase tag strings",
}

_SYSTEM_PROMPT = """\
You are a technical documentation specialist extracting structured IT support knowledge.
Given a raw document excerpt, extract the requested fields as valid JSON.
Rules:
- Output ONLY the JSON object — no markdown, no code fences, no explanation.
- Only populate fields you are confident about from the provided text.
- Never invent steps, products, or procedures that are not in the text.
- Keep instructions concise and actionable.
- Use null for fields where you are not confident.
"""

_USER_TEMPLATE = """\
Extract structured IT support article fields from the following document excerpt.

OUTPUT SCHEMA (return exactly these keys):
{schema}

DOCUMENT EXCERPT:
---
{text}
---

JSON:"""


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def enrich_candidate(
    candidate: CandidatePayload,
    llm_service: object,  # LLMService — typed loosely to avoid circular import
) -> CandidatePayload:
    """Return a (possibly enriched) copy of *candidate*.

    If LLM enrichment is disabled or unavailable, returns *candidate* unchanged.
    If the LLM call fails, logs the error and returns *candidate* unchanged.
    """
    if not settings.INGESTION_LLM_ENABLED:
        return candidate

    if not getattr(llm_service, "is_available", False):
        logger.debug("LLM not available — skipping enrichment for candidate %d", candidate.candidate_index)
        return candidate

    schema_str = json.dumps(_OUTPUT_SCHEMA, indent=2)
    prompt = _USER_TEMPLATE.format(
        schema=schema_str,
        text=candidate.raw_segment_text[:4000],  # Limit context to avoid token overflow
    )

    try:
        raw_response: str = await llm_service.complete(  # type: ignore[attr-defined]
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=1200,
        )
        extracted = _parse_llm_response(raw_response)
        return _merge(candidate, extracted)
    except Exception:
        logger.exception(
            "LLM enrichment failed for candidate %d — using deterministic payload",
            candidate.candidate_index,
        )
        return candidate


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_llm_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON, returning {} on failure."""
    text = raw.strip()
    # Strip markdown code fences if present
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON content (len=%d)", len(raw))
    return {}


def _merge(original: CandidatePayload, enriched: dict) -> CandidatePayload:
    """Merge *enriched* fields into *original*, never overwriting non-empty values."""
    if not enriched:
        return original

    def _pick(orig_val, new_val):
        """Return *orig_val* if it has content, otherwise *new_val*."""
        if orig_val:
            return orig_val
        return new_val or orig_val

    def _pick_list(orig_list: list, new_list) -> list:
        if orig_list:
            return orig_list
        if isinstance(new_list, list) and new_list:
            return new_list
        return orig_list

    merged = CandidatePayload(
        candidate_index=original.candidate_index,
        raw_segment_text=original.raw_segment_text,
        title=_pick(original.title, enriched.get("title")),
        summary=_pick(original.summary, enriched.get("short_summary")),
        category=_pick(original.category, enriched.get("category")),
        subcategory=_pick(original.subcategory, enriched.get("subcategory")),
        product_or_system=_pick(original.product_or_system, enriched.get("product_or_system")),
        platform=_pick(original.platform, enriched.get("platform")),
        symptoms=_pick_list(original.symptoms, enriched.get("symptoms")),
        troubleshooting_steps=_pick_list(
            original.troubleshooting_steps,
            _normalise_steps(enriched.get("troubleshooting_steps")),
        ),
        resolution_steps=_pick_list(
            original.resolution_steps,
            _normalise_steps(enriched.get("resolution_steps")),
        ),
        escalation_criteria=_pick(
            original.escalation_criteria, enriched.get("escalation_criteria")
        ),
        tags=_pick_list(original.tags, enriched.get("tags")),
        keywords=original.keywords,
        confidence=min(original.confidence + 0.15, 0.95),
    )
    return merged


def _normalise_steps(steps_raw) -> list[dict] | None:
    """Ensure each step is a {step_number, instruction, details} dict."""
    if not isinstance(steps_raw, list):
        return None
    result: list[dict] = []
    for i, step in enumerate(steps_raw, start=1):
        if isinstance(step, dict):
            result.append({
                "step_number": int(step.get("step_number", i)),
                "instruction": str(step.get("instruction", "")).strip(),
                "details": str(step.get("details", "")).strip(),
            })
        elif isinstance(step, str):
            result.append({"step_number": i, "instruction": step.strip(), "details": ""})
    return result or None
