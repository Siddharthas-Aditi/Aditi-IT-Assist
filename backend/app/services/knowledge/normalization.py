"""Article → retrieval transformation and semantic chunk preparation.

Pure functions (no I/O) that turn a structured knowledge article into:

1. a single flattened ``retrieval_text`` used for keyword/BM25-style matching, and
2. an ordered list of **semantic chunks** — one per meaningful section — each
   carrying a *contextual header* so an embedding/LLM retains the article's
   identity and metadata even when a chunk is read in isolation.

This is the heart of "retrieval-aware" authoring: the same structured fields the
admin edits are deterministically projected into clean, citation-ready chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordered (key, human label) pairs. Order defines chunk_index ordering.
SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("short_summary", "Summary"),
    ("content", "Overview"),
    ("symptoms", "Symptoms"),
    ("probable_causes", "Probable Causes"),
    ("prerequisites", "Prerequisites"),
    ("troubleshooting_steps", "Troubleshooting Steps"),
    ("resolution_steps", "Resolution Steps"),
    ("validation_steps", "Validation Steps"),
    ("references", "References"),
)


@dataclass
class ChunkSpec:
    """A prepared, not-yet-persisted retrieval chunk."""

    chunk_index: int
    section: str
    header: str
    content: str
    token_estimate: int = 0
    metadata: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for budgeting and telemetry."""
    return max(1, len(text) // 4)


def _coerce_step(step: object, index: int) -> str:
    """Render a step (dict or string) into a single readable line."""
    if isinstance(step, dict):
        number = step.get("step_number", index + 1)
        instruction = step.get("instruction") or step.get("text") or ""
        details = step.get("details")
        line = f"{number}. {instruction}".strip()
        if details:
            line = f"{line} — {details}"
        return line
    return f"{index + 1}. {step}"


def _render_section(key: str, value: object) -> str:
    """Render a single section's value into clean text, or '' if empty."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        if key.endswith("steps"):
            return "\n".join(_coerce_step(s, i) for i, s in enumerate(value))
        return "\n".join(f"- {item}" for item in value if item)
    return str(value)


def build_context_header(article: dict, section_label: str) -> str:
    """Build the contextual header prepended to a chunk.

    Includes article identity + key metadata so each chunk is self-describing
    when retrieved out of context.
    """
    parts = [f"Article: {article.get('title', 'Untitled')}", f"Section: {section_label}"]
    for label, key in (
        ("Category", "category"),
        ("Subcategory", "subcategory"),
        ("Product", "product_or_system"),
        ("Platform", "platform"),
        ("Audience", "audience"),
    ):
        val = article.get(key)
        if val:
            parts.append(f"{label}: {val}")
    return " | ".join(parts)


def build_escalation_text(article: dict) -> str:
    """Compose the escalation guidance section, if present."""
    lines: list[str] = []
    criteria = (article.get("escalation_criteria") or "").strip()
    target = (article.get("escalation_target_team") or "").strip()
    if criteria:
        lines.append(f"Escalate when: {criteria}")
    if target:
        lines.append(f"Escalation target team: {target}")
    return "\n".join(lines)


def build_chunks(article: dict) -> list[ChunkSpec]:
    """Produce ordered, contextual chunks from a structured article."""
    chunks: list[ChunkSpec] = []
    index = 0

    for key, label in SECTION_ORDER:
        rendered = _render_section(key, article.get(key))
        if not rendered:
            continue
        header = build_context_header(article, label)
        body = f"{header}\n\n{rendered}"
        chunks.append(
            ChunkSpec(
                chunk_index=index,
                section=key,
                header=header,
                content=body,
                token_estimate=estimate_tokens(body),
                metadata={"section_label": label},
            )
        )
        index += 1

    escalation = build_escalation_text(article)
    if escalation:
        header = build_context_header(article, "Escalation")
        body = f"{header}\n\n{escalation}"
        chunks.append(
            ChunkSpec(
                chunk_index=index,
                section="escalation",
                header=header,
                content=body,
                token_estimate=estimate_tokens(body),
                metadata={"section_label": "Escalation"},
            )
        )

    return chunks


def build_retrieval_text(article: dict) -> str:
    """Flatten the whole article into a single retrieval/search blob."""
    segments: list[str] = [article.get("title", "")]
    tags = article.get("tags") or []
    keywords = article.get("keywords") or []
    if tags:
        segments.append("Tags: " + ", ".join(str(t) for t in tags))
    if keywords:
        segments.append("Keywords: " + ", ".join(str(k) for k in keywords))

    for chunk in build_chunks(article):
        segments.append(chunk.content)

    return "\n\n".join(s for s in segments if s and s.strip())


def build_citation_label(article: dict) -> str:
    """Default citation label shown next to an AI answer grounded in this article."""
    explicit = (article.get("citation_label") or "").strip()
    if explicit:
        return explicit
    title = article.get("title", "Knowledge Article")
    slug = article.get("slug")
    return f"{title} ({slug})" if slug else title
