"""Controlled web-research agent.

Wraps :class:`app.services.web_search_service.WebSearchService` with the
governance layer required for production use:

1. **Policy gate** — the calling code asks
   :func:`is_web_fallback_allowed_for(specialist)` before invoking; this
   service refuses if the registry's
   :attr:`SpecialistAgentSpec.web_fallback_allowed` is False.
2. **Trust-tier filter** — only sources at the configured minimum trust tier
   are returned. Default: ``official`` and ``vendor`` for general issues;
   ``trusted_community`` allowed only when the specialist's spec explicitly
   opts in.
3. **Candidate creation** — every web-research run automatically creates a
   ``KnowledgeCandidate`` row (via
   :class:`app.services.knowledge.improvement.KnowledgeImprovementService`)
   so SMEs see what the assistant found externally. We do NOT auto-publish.
4. **Audit log** — full request/response/policy-decision is written to
   :class:`AuditEvent` so security review can trace every external content
   pull.

Why a wrapper (not "just call WebSearchService")
------------------------------------------------
Production assistants must be defensive about external content. Without this
layer, a misrouted call could pull untrusted blog content directly into a
user-facing response, or grow the KB with unreviewed material. The wrapper
gives us a single chokepoint where every governance rule applies.

What this service does NOT do
-----------------------------
* It does NOT make the routing decision (the supervisor does).
* It does NOT write the search result into a user response (the specialist /
  response agent does).
* It does NOT directly write to production KB (only candidates).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.services.agents.registry import (
    SpecialistAgentSpec,
    get_agent,
)
from app.services.web_search_service import (
    DomainTrust,
    WebSearchProvider,
    WebSearchResult,
    WebSearchService,
)

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.knowledge.improvement import KnowledgeImprovementService

logger = get_logger(__name__)


# Trust-tier policy. The specialist registry can opt up; the floor below is
# the minimum a specialist must clear to even be considered.
_DEFAULT_ALLOWED_TIERS: tuple[DomainTrust, ...] = (
    DomainTrust.OFFICIAL,
    DomainTrust.VENDOR,
)

# Specialists explicitly OK with community sources (still excludes blogs).
_COMMUNITY_OK_SPECIALISTS: frozenset[str] = frozenset(
    {
        "zoom_meetings",  # zoom community forums are well-moderated
        "network_vpn",  # vendor forums are routinely the right answer
    }
)


@dataclass(frozen=True)
class WebResearchPolicyDecision:
    """Why this call was allowed/blocked. Returned alongside results for audit."""

    allowed: bool
    reason: str
    allowed_tiers: tuple[DomainTrust, ...]
    specialist_name: str | None


@dataclass(frozen=True)
class WebResearchOutcome:
    """Results + policy decision + candidate IDs that were created."""

    results: tuple[WebSearchResult, ...]
    policy: WebResearchPolicyDecision
    candidate_ids: tuple[str, ...] = ()


def is_web_fallback_allowed_for(specialist: SpecialistAgentSpec | None) -> bool:
    """Pre-flight check the supervisor calls before routing here."""
    if specialist is None:
        return False
    return specialist.web_fallback_allowed


def _allowed_tiers_for(specialist: SpecialistAgentSpec | None) -> tuple[DomainTrust, ...]:
    if specialist is None:
        return _DEFAULT_ALLOWED_TIERS
    tiers = list(_DEFAULT_ALLOWED_TIERS)
    if specialist.name in _COMMUNITY_OK_SPECIALISTS:
        tiers.append(DomainTrust.TRUSTED_COMMUNITY)
    return tuple(tiers)


class ControlledWebResearchAgent:
    """Governance layer over the raw web search service.

    Construct with the search backend and (optionally) an improvement service.
    If ``improvement_service`` is None we still return results but skip the
    candidate-creation step — useful in tests.
    """

    def __init__(
        self,
        *,
        search: WebSearchProvider | None = None,
        improvement_service: KnowledgeImprovementService | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        self.search = search or WebSearchService()
        self.improvement_service = improvement_service
        self.db = db

    async def _audit(
        self,
        *,
        action: str,
        resource_id: str | None,
        description: str,
        new_value: dict,
        severity: str = "info",
    ) -> None:
        """Best-effort audit write. Audit failures must never break research."""
        if self.db is None:
            return
        try:
            from app.services.audit_service import AuditService

            await AuditService(self.db).log(
                action=action,
                resource_type="web_research",
                resource_id=resource_id,
                description=description,
                new_value=new_value,
                severity=severity,
            )
        except Exception as exc:  # pragma: no cover - defensive, audit must not break flow
            logger.warning("web_research_audit_failed", action=action, error=str(exc))

    async def research(
        self,
        *,
        query: str,
        specialist_name: str,
        category: str | None,
        subtype: str | None,
        system: str | None,
        session_id: str | None = None,
    ) -> WebResearchOutcome:
        """Run a policy-gated web search.

        The supervisor is expected to have already checked
        :func:`is_web_fallback_allowed_for` — this method re-checks as a
        defensive measure. A blocked call returns an empty
        :class:`WebResearchOutcome` with the policy reason populated.
        """
        spec = get_agent(specialist_name)
        if not isinstance(spec, SpecialistAgentSpec):
            policy = WebResearchPolicyDecision(
                allowed=False,
                reason=f"unknown specialist {specialist_name!r}",
                allowed_tiers=(),
                specialist_name=specialist_name,
            )
            logger.warning("web_research_blocked", **policy.__dict__)
            await self._audit(
                action="web_research.blocked",
                resource_id=specialist_name,
                description=f"web research blocked: unknown specialist {specialist_name!r}",
                new_value={"specialist": specialist_name, "reason": policy.reason},
                severity="warning",
            )
            return WebResearchOutcome(results=(), policy=policy)

        if not is_web_fallback_allowed_for(spec):
            policy = WebResearchPolicyDecision(
                allowed=False,
                reason="specialist does not permit web fallback",
                allowed_tiers=(),
                specialist_name=spec.name,
            )
            logger.warning("web_research_blocked", **policy.__dict__)
            await self._audit(
                action="web_research.blocked",
                resource_id=spec.name,
                description=(
                    f"web research blocked: specialist {spec.name!r} does not permit web fallback"
                ),
                new_value={"specialist": spec.name, "reason": policy.reason},
                severity="warning",
            )
            return WebResearchOutcome(results=(), policy=policy)

        tiers = _allowed_tiers_for(spec)
        raw = await self.search.search(
            query=query,
            category=category or "",
            system=system or "",
        )
        filtered = tuple(r for r in raw if r.trust_level in tiers)

        policy = WebResearchPolicyDecision(
            allowed=True,
            reason="ok",
            allowed_tiers=tiers,
            specialist_name=spec.name,
        )
        logger.info(
            "web_research_completed",
            specialist=spec.name,
            results_in=len(raw),
            results_out=len(filtered),
            tiers=[t.value for t in tiers],
        )

        candidate_ids: tuple[str, ...] = ()
        if filtered and self.improvement_service is not None:
            ids: list[str] = []
            for r in filtered:
                cand = await self.improvement_service.record_web_fallback_used(
                    url=r.url,
                    snippet=f"{r.title}\n{r.snippet}",
                    category=category,
                    subtype=subtype,
                )
                ids.append(str(cand.id))
            candidate_ids = tuple(ids)

        await self._audit(
            action="web_research.completed",
            resource_id=spec.name,
            description=f"web research completed for specialist {spec.name!r}",
            new_value={
                "specialist": spec.name,
                "results_in": len(raw),
                "results_out": len(filtered),
                "tiers": [t.value for t in tiers],
                "candidate_ids": list(candidate_ids),
            },
        )

        return WebResearchOutcome(
            results=filtered,
            policy=policy,
            candidate_ids=candidate_ids,
        )


def build_default_web_research_agent(db: AsyncSession) -> ControlledWebResearchAgent | None:
    """Wire the configured web-search provider + improvement service, or None when off."""
    from app.services.web_search_service import get_web_search_provider

    provider = get_web_search_provider()
    if provider is None:
        return None
    from app.services.knowledge.improvement import KnowledgeImprovementService

    return ControlledWebResearchAgent(
        search=provider,
        improvement_service=KnowledgeImprovementService(db),
        db=db,
    )


__all__ = [
    "ControlledWebResearchAgent",
    "WebResearchOutcome",
    "WebResearchPolicyDecision",
    "build_default_web_research_agent",
    "is_web_fallback_allowed_for",
]
