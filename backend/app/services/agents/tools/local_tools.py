"""Local, read-only tools (Phase 5).

Three tools that take no external action and have no side effects beyond
reading: ``kb_search``, ``mailbox_quota_estimate``, ``ticket_draft``. They
prove the tool-calling contract end-to-end without touching any external
system. Phase 7 adds MCP-backed read tools; Phase 8 adds gated write actions.

Each tool:
* declares a frozen :class:`~app.services.agents.tools.base.ToolSpec`;
* validates input via a Pydantic args model and returns a Pydantic result
  model (the runtime enforces the input contract before ``run`` is called);
* performs no RBAC/approval itself — that is the runtime's job.

``ticket_draft`` deliberately does **not** persist anything: drafting is safe
and read-classified. Real ticket persistence stays in the service layer behind
explicit user confirmation (see ``ChatService._handle_ticketing``) and, in
Phase 8, behind a separate write-classified tool requiring ``ticket:create``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.core.permissions import P
from app.services.agents.tools.base import (
    Approval,
    SideEffect,
    ToolContext,
    ToolSpec,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.knowledge_service import RetrievalResult


# ── kb_search ────────────────────────────────────────────────────────────────


class KbSearchArgs(BaseModel):
    """Arguments for a knowledge-base search."""

    query: str = Field(..., min_length=1, description="Search text describing the issue.")
    category: str | None = Field(
        None, description="Optional category filter, e.g. 'email/outlook'."
    )
    limit: int = Field(5, ge=1, le=10, description="Maximum number of articles to return.")


class KbHit(BaseModel):
    """One retrieved article, trimmed to what an agent needs to reason."""

    title: str
    snippet: str = ""
    category: str | None = None
    citation_label: str | None = None


class KbSearchResult(BaseModel):
    """Result of a knowledge-base search."""

    hits: list[KbHit] = Field(default_factory=list)
    confidence: float = 0.0
    source: str = "keyword"


# A search function returns a RetrievalResult. Injected for testability;
# defaults to the YAML-backed knowledge service (works offline, no DB).
SearchFn = Callable[..., Awaitable["RetrievalResult"]]


class KbSearchTool:
    """Search the governed knowledge base. Read-only; any KB reader may call."""

    spec = ToolSpec(
        name="kb_search",
        description=(
            "Search the internal IT knowledge base for articles relevant to an "
            "issue. Returns published article titles and snippets. Use this "
            "before proposing steps so answers stay grounded in approved KB."
        ),
        args_model=KbSearchArgs,
        result_model=KbSearchResult,
        side_effect=SideEffect.READ,
        required_permissions=(P.KNOWLEDGE_READ.value,),
        approval=Approval.NONE,
    )

    def __init__(self, search_fn: SearchFn | None = None) -> None:
        self._search_fn = search_fn

    async def run(self, args: KbSearchArgs, context: ToolContext) -> KbSearchResult:
        search = self._search_fn or self._default_search
        result = await search(args.query, category=args.category, limit=args.limit)
        hits = [
            KbHit(
                title=str(a.get("title", "Knowledge Article")),
                snippet=_snippet(a),
                category=a.get("category") or args.category,
                citation_label=a.get("citation_label") or a.get("title"),
            )
            for a in (result.articles or [])[: args.limit]
        ]
        return KbSearchResult(hits=hits, confidence=result.confidence, source=result.source)

    @staticmethod
    async def _default_search(query: str, *, category: str | None, limit: int):
        from app.services.knowledge_service import get_knowledge_service

        return await get_knowledge_service().search(query, category=category, limit=limit)


def _snippet(article: dict) -> str:
    """Build a short, safe snippet from whatever content keys exist."""
    for key in ("summary", "snippet", "content", "description"):
        val = article.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:280]
    steps = article.get("steps") or article.get("resolution_steps") or []
    if steps:
        first = steps[0]
        text = first.get("instruction") if isinstance(first, dict) else str(first)
        return (text or "")[:280]
    return ""


# ── mailbox_quota_estimate ─────────────────────────────────────────────────


class MailboxQuotaArgs(BaseModel):
    """Inputs for a mailbox-quota estimate."""

    used_gb: float = Field(..., ge=0, description="Current mailbox size in GB.")
    quota_gb: float = Field(50.0, gt=0, description="Mailbox quota in GB (default 50).")
    warning_threshold: float = Field(
        0.90, ge=0.5, le=1.0, description="Fraction of quota considered 'near full'."
    )


class MailboxQuotaResult(BaseModel):
    """Deterministic quota assessment — pure arithmetic, no external lookup."""

    percent_used: float
    headroom_gb: float
    status: str  # "ok" | "near_full" | "over_quota"
    over_quota: bool
    recommendation: str


class MailboxQuotaEstimateTool:
    """Estimate mailbox quota status from sizes. Pure, read-only, no permissions."""

    spec = ToolSpec(
        name="mailbox_quota_estimate",
        description=(
            "Estimate whether a mailbox is near or over its quota given its "
            "current size and quota in GB. Returns percent used, headroom, and "
            "a recommendation. Pure calculation — does not read the mailbox."
        ),
        args_model=MailboxQuotaArgs,
        result_model=MailboxQuotaResult,
        side_effect=SideEffect.READ,
        required_permissions=(),
        approval=Approval.NONE,
    )

    async def run(self, args: MailboxQuotaArgs, context: ToolContext) -> MailboxQuotaResult:
        percent = (args.used_gb / args.quota_gb) if args.quota_gb else 0.0
        headroom = max(0.0, args.quota_gb - args.used_gb)
        over = args.used_gb >= args.quota_gb
        near = (not over) and percent >= args.warning_threshold

        if over:
            status = "over_quota"
            rec = (
                "Mailbox is at or over quota — new mail may be blocked. Recommend "
                "clearing large/old items and emptying Deleted Items, then archiving."
            )
        elif near:
            status = "near_full"
            rec = (
                f"Mailbox is {percent * 100:.0f}% full. Recommend proactive cleanup "
                "(large attachments, Deleted Items) before it blocks new mail."
            )
        else:
            status = "ok"
            rec = f"Mailbox is {percent * 100:.0f}% full — within healthy range."

        return MailboxQuotaResult(
            percent_used=round(percent * 100, 1),
            headroom_gb=round(headroom, 2),
            status=status,
            over_quota=over,
            recommendation=rec,
        )


# ── ticket_draft ───────────────────────────────────────────────────────────


class TicketDraftArgs(BaseModel):
    """Inputs for composing (not persisting) a support-ticket draft."""

    subject: str = Field(..., min_length=3, description="Short ticket subject line.")
    summary: str = Field(..., min_length=3, description="What the user is experiencing.")
    category: str | None = Field(None, description="Issue category if known.")
    urgency: str = Field("normal", description="Urgency: low | normal | high.")


class TicketDraftResult(BaseModel):
    """A composed draft. ``persisted`` is always False in Phase 5."""

    subject: str
    body: str
    category: str | None = None
    urgency: str = "normal"
    persisted: bool = False


class TicketDraftTool:
    """Compose a support-ticket draft. Read-only: never persists or sends."""

    spec = ToolSpec(
        name="ticket_draft",
        description=(
            "Compose a support-ticket draft (subject + body) from the issue "
            "details. Does NOT create or send the ticket — persistence requires "
            "explicit user confirmation in the service layer."
        ),
        args_model=TicketDraftArgs,
        result_model=TicketDraftResult,
        side_effect=SideEffect.READ,
        required_permissions=(),
        approval=Approval.NONE,
    )

    async def run(self, args: TicketDraftArgs, context: ToolContext) -> TicketDraftResult:
        urgency = args.urgency.lower().strip()
        if urgency not in {"low", "normal", "high"}:
            urgency = "normal"
        body = (
            f"Summary: {args.summary}\n"
            f"Category: {args.category or 'unclassified'}\n"
            f"Urgency: {urgency}\n"
            f"Reported by: {context.user_id or 'unknown'}\n"
            f"Session: {context.session_id or 'n/a'}"
        )
        return TicketDraftResult(
            subject=args.subject.strip(),
            body=body,
            category=args.category,
            urgency=urgency,
            persisted=False,
        )


__all__ = [
    "KbHit",
    "KbSearchArgs",
    "KbSearchResult",
    "KbSearchTool",
    "MailboxQuotaArgs",
    "MailboxQuotaEstimateTool",
    "MailboxQuotaResult",
    "TicketDraftArgs",
    "TicketDraftResult",
    "TicketDraftTool",
]
