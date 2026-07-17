"""Compress diagnostic context into concise summary for long conversations."""

import logging
from dataclasses import dataclass

from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


@dataclass
class ContextSummary:
    """Compressed view of conversation so far."""

    issue_one_liner: str  # "Outlook mailbox full, user cleared cache but still failing"
    entity: str  # "Outlook"
    attempted_solutions: list[str]  # ["Cleared cache", "Restarted"]
    current_status: str  # "Issue persists after 2 attempts"
    key_facts: dict  # {"uses_2fa": true, "device": "windows"}
    turn_count: int


class ContextSummarizerService:
    """Summarize DiagnosticContext to reduce LLM prompt size."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def summarize(self, diagnostic_context: DiagnosticContext) -> ContextSummary:
        """
        Compress diagnostic context into 2-3 sentence summary.

        Input: 60+ fields of accumulated history
        Output: Concise summary for LLM prompt injection

        Args:
            diagnostic_context: The accumulated diagnostic context from conversation

        Returns:
            ContextSummary with issue_one_liner and key facts
        """
        filled_slots = diagnostic_context.get_filled_slots()

        device_type = diagnostic_context.device_type or "Unknown"
        platform_os = diagnostic_context.platform_os or "Unknown"

        # Build summary prompt
        summary_prompt = f"""
Summarize this IT support conversation in 2-3 sentences:

**Issue Type**: {diagnostic_context.issue_subtype or "Unknown"}
**System/Product**: {diagnostic_context.normalized_system}
**Problem**: {diagnostic_context.exact_problem_statement}
**Attempts Made**: {", ".join(diagnostic_context.attempted_steps or ["None yet"])}
**Key Environment**: Device: {device_type}, OS: {platform_os}

Output format:
"User has [issue with system]. Tried [attempts] but [result]. [key blocker or fact if any]."

Be concise. Focus on what matters for next troubleshooting step.
        """

        try:
            summary_text = await self.llm.complete(
                prompt=summary_prompt,
                system_prompt=(
                    "You are a support ticket analyst. Summarize conversations "
                    "concisely for internal handoff."
                ),
                temperature=0.3,  # Deterministic
            )

            logger.info(f"Context summarized: {summary_text[:100]}...")

            return ContextSummary(
                issue_one_liner=summary_text.strip(),
                entity=diagnostic_context.normalized_system or "Unknown",
                attempted_solutions=diagnostic_context.attempted_steps or [],
                current_status=diagnostic_context.exact_problem_statement or "Unknown status",
                key_facts=filled_slots,
                turn_count=len(diagnostic_context.suggested_steps or [])
                + len(diagnostic_context.failed_steps or []),
            )
        except Exception as e:
            logger.error(f"Context summarization failed: {e}. Using fallback summary.")
            # Fallback: simple concatenation
            return ContextSummary(
                issue_one_liner=(
                    f"{diagnostic_context.issue_subtype} on {diagnostic_context.normalized_system}"
                ),
                entity=diagnostic_context.normalized_system or "Unknown",
                attempted_solutions=diagnostic_context.attempted_steps or [],
                current_status=diagnostic_context.exact_problem_statement or "Ongoing issue",
                key_facts=filled_slots,
                turn_count=len(diagnostic_context.suggested_steps or [])
                + len(diagnostic_context.failed_steps or []),
            )

    def should_summarize(self, turn_count: int) -> bool:
        """
        Decide if we should create a summary at this turn.

        Summarize every 10 turns to compress context.

        Args:
            turn_count: Current turn number (number of messages exchanged)

        Returns:
            True if we should create a summary now
        """
        return turn_count > 0 and turn_count % 10 == 0
