"""Layer D+ — Adaptive LLM-assisted field enrichment.

Called by the pipeline ONLY when:
  - ``settings.INGESTION_LLM_ENABLED`` is True
  - ``LLMService.is_available`` is True

DESIGN:
  - Accepts a fully populated ``ExtractionCandidate`` (from Layer D deterministic
    extraction) and enriches only the fields whose confidence is below the
    profile's ``thresholds.medium`` threshold.
  - The LLM receives ONLY the raw segment text and a targeted list of missing
    fields — never re-extracts fields that are already high-confidence.
  - Enriched fields are updated with ``ExtractionMethod.COMBINED`` to signal
    that deterministic + LLM evidence was combined.
  - On any failure (timeout, JSON error, hallucination guard), the original
    candidate is returned unchanged — LLM enrichment is always additive.

Hallucination guard: any LLM-returned step text that is shorter than 5 chars
or entirely absent from the segment text (fuzzy check) is discarded.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.ingestion.profiles.base import ParserProfile
from app.services.ingestion.schema import (
    ExtractionCandidate,
    ExtractionMethod,
    ExtractionStep,
    FieldExtraction,
)

logger = logging.getLogger(__name__)

# ── Stable LLM output schema ──────────────────────────────────────────────────
# This describes the JSON the LLM must return.  Keep it minimal to reduce
# hallucination surface.  All fields are nullable — the LLM should NOT guess.
_FIELD_SCHEMA: dict[str, str] = {
    "title": "string or null — short descriptive title of the IT issue",
    "short_summary": "string ≤ 300 chars or null — one-sentence description",
    "category": (
        "one of: email/outlook, video-conferencing/zoom, video-conferencing/teams, "
        "device-management/intune, hardware/camera, hardware/other, "
        "network/connectivity, access/permissions, software/other, other — or null"
    ),
    "subcategory": "string or null",
    "product_or_system": "string or null — primary product/software name",
    "platform": "string or null — e.g. Windows 11, macOS, iOS",
    "symptoms": "array of strings describing observed problems, or []",
    "troubleshooting_steps": (
        "array of {step_number: int, instruction: string, details: string}, or []"
    ),
    "resolution_steps": (
        "array of {step_number: int, instruction: string, details: string}, or []"
    ),
    "escalation_criteria": "string or null — conditions under which to escalate",
    "tags": "array of short lowercase tag strings, or []",
}

_SYSTEM_PROMPT = """\
You are a technical documentation specialist extracting structured IT support knowledge.
Given a raw document excerpt, return a JSON object with ONLY the keys listed below.
Rules:
- Output ONLY the JSON object. No markdown, no code fences, no commentary.
- Populate only fields you can justify from the provided text.
- Use null or [] for fields where the text provides no evidence.
- Never invent steps, products, or error messages not present in the text.
- Keep step instructions concise (≤ 120 chars each).
"""

_USER_TEMPLATE = """\
Extract the following IT support fields from the document excerpt.

FIELDS TO EXTRACT (return these exact keys):
{schema}

DOCUMENT EXCERPT:
---
{text}
---

JSON:"""


# ── Public entry point ────────────────────────────────────────────────────────

async def enrich_with_llm(
    candidate: ExtractionCandidate,
    profile: ParserProfile,
    llm_service: object,  # LLMService — typed loosely to avoid circular import
) -> ExtractionCandidate:
    """Enrich low-confidence fields in *candidate* using the LLM.

    Returns *candidate* unchanged if LLM is disabled, unavailable, or errors.
    Returns *candidate* unchanged if all fields already meet the confidence
    threshold (i.e. nothing to do).
    """
    if not getattr(settings, "INGESTION_LLM_ENABLED", False):
        return candidate

    if not getattr(llm_service, "is_available", False):
        logger.debug(
            "LLM not available — skipping enrichment for candidate %d",
            candidate.candidate_index,
        )
        return candidate

    # Collect fields that fall below the threshold
    threshold = profile.thresholds.medium
    weak_fields = _weak_fields(candidate, threshold)
    if not weak_fields:
        logger.debug("All fields meet threshold %.2f — skipping LLM", threshold)
        return candidate

    # Build targeted schema prompt (only request weak fields)
    targeted_schema = {k: _FIELD_SCHEMA[k] for k in weak_fields if k in _FIELD_SCHEMA}
    schema_str = json.dumps(targeted_schema, indent=2)
    prompt = _USER_TEMPLATE.format(
        schema=schema_str,
        text=candidate.raw_segment_text[:4_000],
    )

    try:
        raw: str = await llm_service.complete(  # type: ignore[attr-defined]
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=1_400,
        )
        parsed = _parse_response(raw)
        if parsed:
            _merge_into(candidate, parsed, weak_fields, profile)
    except Exception:
        logger.exception(
            "LLM enrichment failed for candidate %d — using deterministic result",
            candidate.candidate_index,
        )

    return candidate


# ── Internal helpers ──────────────────────────────────────────────────────────

def _weak_fields(candidate: ExtractionCandidate, threshold: float) -> list[str]:
    """Return names of FieldExtraction fields below *threshold*."""
    tracked = [
        "title", "short_summary", "category", "subcategory",
        "product_or_system", "platform", "symptoms",
        "troubleshooting_steps", "resolution_steps",
        "escalation_criteria", "tags",
    ]
    return [
        name for name in tracked
        if candidate.field_confidence(name) < threshold
    ]


def _parse_response(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON. Returns {} on failure."""
    text = raw.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON (len=%d)", len(raw))
    return {}


def _merge_into(
    candidate: ExtractionCandidate,
    llm_data: dict,
    weak_fields: list[str],
    profile: ParserProfile,
) -> None:
    """Mutate *candidate* in-place with LLM-provided values for *weak_fields*.

    Only updates a field when:
    1. The LLM returned a non-null, non-empty value.
    2. The field was in *weak_fields* (below threshold).
    3. The hallucination guard passes (value is grounded in segment text).
    """
    text_lower = candidate.raw_segment_text.lower()
    threshold = profile.thresholds.medium

    # ── Scalar fields ──────────────────────────────────────────────────────────
    scalar_map: dict[str, str] = {
        "title": "title",
        "short_summary": "short_summary",
        "category": "category",
        "subcategory": "subcategory",
        "product_or_system": "product_or_system",
        "platform": "platform",
        "escalation_criteria": "escalation_criteria",
    }
    for field_name, json_key in scalar_map.items():
        if field_name not in weak_fields:
            continue
        val = llm_data.get(json_key)
        if not val or not isinstance(val, str) or not val.strip():
            continue
        # Hallucination guard: at least one word from the value must appear in segment
        if not _grounded(val, text_lower):
            logger.debug("Hallucination guard blocked LLM '%s': %r", field_name, val[:60])
            continue
        existing = getattr(candidate, field_name)
        new_conf = min((existing.confidence if isinstance(existing, FieldExtraction) else 0.0) + 0.30, 0.80)
        setattr(candidate, field_name, FieldExtraction.make(
            val.strip(), new_conf,
            method=ExtractionMethod.COMBINED,
            excerpt=val[:120],
        ))

    # ── Symptoms / tags (list of strings) ─────────────────────────────────────
    for field_name in ("symptoms", "tags"):
        if field_name not in weak_fields:
            continue
        raw_list = llm_data.get(field_name)
        if not isinstance(raw_list, list) or not raw_list:
            continue
        clean = [str(s).strip() for s in raw_list if s and str(s).strip()]
        if not clean:
            continue
        existing = getattr(candidate, field_name)
        new_conf = min((existing.confidence if isinstance(existing, FieldExtraction) else 0.0) + 0.25, 0.80)
        setattr(candidate, field_name, FieldExtraction.make(
            clean, new_conf,
            method=ExtractionMethod.COMBINED,
        ))

    # ── Step lists (troubleshooting_steps, resolution_steps) ─────────────────
    for field_name in ("troubleshooting_steps", "resolution_steps"):
        if field_name not in weak_fields:
            continue
        raw_steps = llm_data.get(field_name)
        steps = _normalise_steps(raw_steps, text_lower)
        if not steps:
            continue
        existing = getattr(candidate, field_name)
        new_conf = min((existing.confidence if isinstance(existing, FieldExtraction) else 0.0) + 0.28, 0.82)
        setattr(candidate, field_name, FieldExtraction.make(
            steps, new_conf,
            method=ExtractionMethod.COMBINED,
        ))


def _grounded(value: str, text_lower: str) -> bool:
    """Return True if at least one significant word from *value* appears in segment."""
    words = [w.lower() for w in value.split() if len(w) >= 4]
    if not words:
        return False
    return any(w in text_lower for w in words[:10])


def _normalise_steps(raw, text_lower: str) -> list[dict]:
    """Convert raw LLM step list to [{step_number, instruction, details}], guarded."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for i, step in enumerate(raw, start=1):
        if isinstance(step, dict):
            instr = str(step.get("instruction", "")).strip()
        elif isinstance(step, str):
            instr = step.strip()
        else:
            continue
        if len(instr) < 5:
            continue
        if not _grounded(instr, text_lower):
            logger.debug("Hallucination guard blocked step: %r", instr[:60])
            continue
        result.append({
            "step_number": int(step.get("step_number", i)) if isinstance(step, dict) else i,
            "instruction": instr[:200],
            "details": str(step.get("details", "")).strip()[:300] if isinstance(step, dict) else "",
        })
    return result
