"""Resolution Agent Node — concise, grounded troubleshooting guidance.

This upgraded resolution node:
1. Generates focused responses based on diagnostic context
2. Provides next-step guidance (not full KB dumps)
3. Asks whether the step resolved the issue
4. Uses progressive disclosure — fewer steps at a time
"""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

RESOLUTION_SYSTEM_PROMPT = (
    "You are a friendly, concise IT Support Specialist at Aditi Consulting's internal help desk. "
    "You help employees troubleshoot IT issues step-by-step.\n\n"
    "IMPORTANT RULES:\n"
    "- Be brief and conversational — like a helpful colleague, not a manual\n"
    "- Give 2-3 steps at most per response\n"
    "- After giving steps, ask if they worked\n"
    "- Never dump all possible solutions at once\n"
    "- Only use information from the provided knowledge base articles\n"
    "- If you're not confident, say so and offer to escalate\n"
    "- Use plain language, avoid jargon\n"
    "- Format steps with numbers for clarity"
)

RESOLUTION_PROMPT = """Based on the employee's specific issue and the knowledge base articles below,
provide a focused troubleshooting response.

Employee's specific issue:
- Category: {category}
- Problem: {problem_description}
- Symptom: {symptom}
{additional_context}

Knowledge base articles (use ONLY these as your source):
{knowledge_articles}

RESPONSE GUIDELINES:
1. Start with a brief acknowledgment (one sentence)
2. Give the 2-3 most likely resolution steps for THIS specific symptom
3. End by asking if the steps resolved the issue
4. Do NOT list every possible solution — just the most relevant ones
5. Keep the total response under 200 words
6. If steps require admin access, mention that escalation is available

Respond now:"""


def _get_steps(article: dict) -> list:
    """Extract steps from an article dict, supporting both DB and YAML field names."""
    return (
        article.get("resolution_steps")
        or article.get("troubleshooting_steps")
        or article.get("steps")
        or []
    )


async def resolution_node(state: WorkflowState) -> dict:
    """Generate focused, progressive resolution from retrieved knowledge.

    This node:
    1. Uses diagnostic context for targeted response generation
    2. Provides 2-3 steps at a time (not full dump)
    3. Asks whether steps resolved the issue
    4. Tracks resolution confidence for escalation decisions
    """
    logger.info(
        "resolution_node_start",
        session_id=state.get("session_id"),
        knowledge_count=len(state.get("knowledge_results", [])),
    )

    knowledge_results = state.get("knowledge_results", [])
    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})

    resolution = await _generate_resolution(knowledge_results, state, diag_ctx)
    response_content = resolution["response"]

    # Update diagnostic context
    diag_ctx.resolution_attempts += 1
    diag_ctx.resolution_confidence = resolution["confidence"]
    diag_ctx.phase = DiagnosticPhase.CONFIRMING

    audit_entry = {
        "event": "resolution.generated",
        "confidence": resolution["confidence"],
        "steps_count": len(resolution["steps"]),
        "method": resolution.get("method", "direct"),
        "resolution_attempt": diag_ctx.resolution_attempts,
    }

    return {
        "current_node": "resolve",
        "resolution_steps": resolution["steps"],
        "resolution_confidence": resolution["confidence"],
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "messages": [AIMessage(content=response_content)],
        "audit_trail": [audit_entry],
    }


async def _generate_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
) -> dict:
    """Generate focused resolution using LLM or direct extraction."""
    if not knowledge_results:
        return {
            "steps": [],
            "confidence": 0.0,
            "method": "none",
            "response": (
                "I wasn't able to find a specific solution for this in our knowledge base. "
                "Would you like me to create a support ticket so our IT team can assist you directly?"
            ),
        }

    llm = get_llm_service()
    if llm.is_available:
        try:
            return await _llm_resolution(knowledge_results, state, diag_ctx, llm)
        except Exception as e:
            logger.warning("resolution_llm_fallback", error=str(e))

    return _direct_resolution(knowledge_results, state, diag_ctx)


async def _llm_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
    llm: object,
) -> dict:
    """Use LLM to generate concise, targeted resolution."""
    from app.services.llm_service import LLMService

    assert isinstance(llm, LLMService)

    # Format only the most relevant articles (top 2)
    articles_text = "\n\n".join(
        f"Article: {a.get('title', 'Untitled')}\n"
        f"Steps: {_get_steps(a)}\n"
        f"Content: {(a.get('content') or a.get('snippet') or '')[:800]}"
        for a in knowledge_results[:2]
    )

    # Build problem description from diagnostic context
    problem_desc = (
        diag_ctx.exact_problem_statement
        or diag_ctx.symptom
        or "not specified"
    )
    symptom = diag_ctx.symptom or diag_ctx.issue_subcategory or "general issue"

    # Additional context from slots
    additional = []
    if diag_ctx.platform_os:
        additional.append(f"- Platform: {diag_ctx.platform_os}")
    if diag_ctx.device_type:
        additional.append(f"- Device: {diag_ctx.device_type}")
    if diag_ctx.error_message:
        additional.append(f"- Error message: {diag_ctx.error_message}")
    if diag_ctx.steps_already_tried:
        additional.append(f"- Already tried: {', '.join(diag_ctx.steps_already_tried)}")

    additional_text = "\n".join(additional) if additional else "None"

    prompt = RESOLUTION_PROMPT.format(
        category=state.get("issue_category", "other"),
        problem_description=problem_desc,
        symptom=symptom,
        additional_context=additional_text,
        knowledge_articles=articles_text,
    )

    content = await llm.complete(prompt, system_prompt=RESOLUTION_SYSTEM_PROMPT)

    steps = [{"step_number": 1, "instruction": content, "details": None}]
    confidence = min(0.95, state.get("knowledge_confidence", 0.5) + 0.15)

    return {"steps": steps, "confidence": confidence, "method": "llm", "response": content}


def _direct_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
) -> dict:
    """Extract steps directly from the best matching article (no-LLM fallback)."""
    best_article = knowledge_results[0]
    raw_steps = _get_steps(best_article)
    confidence = min(0.9, state.get("knowledge_confidence", 0.5) + 0.1)

    # Only take the first 3 steps for progressive disclosure
    formatted_steps = []
    for i, step in enumerate(raw_steps[:3], 1):
        if isinstance(step, dict):
            formatted_steps.append({
                "step_number": i,
                "instruction": step.get("instruction") or step.get("step") or str(step),
                "details": step.get("details") or step.get("expected_outcome"),
            })
        elif isinstance(step, str):
            formatted_steps.append({
                "step_number": i,
                "instruction": step,
                "details": None,
            })

    # Build concise response
    response = _format_concise_response(formatted_steps, best_article, confidence, diag_ctx)

    return {
        "steps": formatted_steps,
        "confidence": confidence,
        "method": "direct",
        "response": response,
    }


def _format_concise_response(
    steps: list[dict],
    article: dict,
    confidence: float,
    diag_ctx: DiagnosticContext,
) -> str:
    """Format a concise, human-like resolution response."""
    if not steps:
        return (
            "I couldn't find specific steps for this issue in our knowledge base. "
            "Would you like me to escalate this to our IT team?"
        )

    lines: list[str] = []

    # Brief acknowledgment
    symptom = diag_ctx.symptom or diag_ctx.exact_problem_statement or "your issue"
    lines.append(f"Got it — let me help you with {symptom}. Here's what to try:\n")

    # Steps (concise)
    for step in steps:
        lines.append(f"**{step['step_number']}.** {step['instruction']}")
        if step.get("details"):
            lines.append(f"   _{step['details']}_")

    # Follow-up question
    lines.append("")
    if confidence >= 0.8:
        lines.append("Let me know if that resolves the issue!")
    else:
        lines.append(
            "Try these steps and let me know how it goes. "
            "If the issue persists, I can escalate to our IT team."
        )

    return "\n".join(lines)

