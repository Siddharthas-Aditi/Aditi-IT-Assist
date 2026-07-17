"""Intelligent resolution strategy selector.

Instead of rigid linear routing (KB → LLM → escalate), this module
implements a pluggable strategy pattern where resolution can choose
from multiple approaches based on confidence and available data.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext

logger = get_logger(__name__)


class ResolutionStrategy(StrEnum):
    """Strategy for generating resolution guidance."""

    GROUNDED_LLM = "grounded_llm"  # Use LLM to explain KB steps (high quality)
    DIRECT_STEPS = "direct_steps"  # Raw KB steps (fallback)
    WEB_SEARCH = "web_search"  # External sources (for novel issues)
    SIMPLIFIED = "simplified"  # Ultra-simple 1-step guidance
    ESCALATE = "escalate"  # Human handoff
    UNKNOWN_ISSUE = "unknown_issue"  # Issue not recognizable


@dataclass
class StrategyDecision:
    """Decision on which strategy to use and why."""

    strategy: ResolutionStrategy
    confidence: float  # 0.0–1.0
    reasoning: str  # Why we chose this strategy
    should_retry: bool = False  # Whether user should get "let me try something else"

    def __repr__(self) -> str:
        return f"{self.strategy.value} (conf={self.confidence:.2f}): {self.reasoning}"


class ResolutionStrategySelector:
    """Intelligent selector that chooses best resolution approach."""

    def __init__(
        self,
        kb_articles: list[dict],
        subtype_match_count: int = 0,
        has_failed_steps: bool = False,
        diag_ctx: DiagnosticContext | None = None,
    ):
        """
        Args:
            kb_articles: Knowledge articles retrieved (may include cross-family)
            subtype_match_count: Number of articles matching exact issue subtype
            has_failed_steps: Whether user already tried steps without success
            diag_ctx: Diagnostic context for sentiment/urgency
        """
        self.kb_articles = kb_articles
        self.subtype_match_count = subtype_match_count
        self.has_failed_steps = has_failed_steps
        self.diag_ctx = diag_ctx or DiagnosticContext()

    def select(self) -> StrategyDecision:
        """Choose the best strategy for this situation."""

        # ── User asked for simpler explanation ──
        if self._user_confused():
            return StrategyDecision(
                strategy=ResolutionStrategy.SIMPLIFIED,
                confidence=0.7,
                reasoning="User asked for simpler/clearer explanation",
            )

        # ── We have exact subtype match → use grounded LLM ──
        if self.subtype_match_count > 0:
            return StrategyDecision(
                strategy=ResolutionStrategy.GROUNDED_LLM,
                confidence=0.85,
                reasoning=(
                    f"Found {self.subtype_match_count} article(s) matching exact issue subtype"
                ),
            )

        # ── We have same-category articles but no exact subtype match ──
        if self.kb_articles and self.subtype_match_count == 0:
            # Could be close match (e.g. WiFi steps for internet issue)
            # Try LLM but with lower confidence
            return StrategyDecision(
                strategy=ResolutionStrategy.GROUNDED_LLM,
                confidence=0.55,  # Risky, but try
                reasoning=(
                    f"Found {len(self.kb_articles)} same-family articles but no exact subtype match"
                ),
                should_retry=True,  # If this fails, escalate
            )

        # ── No KB articles at all → try web search ──
        if not self.kb_articles:
            return StrategyDecision(
                strategy=ResolutionStrategy.WEB_SEARCH,
                confidence=0.4,
                reasoning="No knowledge base articles found; trying external sources",
            )

        # ── Steps already failed, user still stuck → escalate ──
        if self.has_failed_steps and self.subtype_match_count == 0:
            return StrategyDecision(
                strategy=ResolutionStrategy.ESCALATE,
                confidence=0.0,
                reasoning="User tried available steps without success; human expertise needed",
            )

        # ── Default: escalate ──
        return StrategyDecision(
            strategy=ResolutionStrategy.ESCALATE,
            confidence=0.0,
            reasoning="No clear path forward; escalating to IT team",
        )

    def _user_confused(self) -> bool:
        """Check if user is asking for simpler explanation."""
        # This would need the actual message; for now use context flag if available
        return getattr(self.diag_ctx, "_user_asked_simpler", False)


# Helper: Map strategy to which agent node should handle it
STRATEGY_HANDLER = {
    ResolutionStrategy.GROUNDED_LLM: "resolution_node",
    ResolutionStrategy.DIRECT_STEPS: "resolution_node",
    ResolutionStrategy.WEB_SEARCH: "resolution_node",
    ResolutionStrategy.SIMPLIFIED: "resolution_node",
    ResolutionStrategy.ESCALATE: "escalation_node",
    ResolutionStrategy.UNKNOWN_ISSUE: "escalation_node",
}
