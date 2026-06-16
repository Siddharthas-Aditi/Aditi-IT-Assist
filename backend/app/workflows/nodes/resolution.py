"""Resolution Agent Node — generates step-by-step troubleshooting guidance."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

RESOLUTION_SYSTEM_PROMPT = (
    "You are a professional IT Support Specialist at Aditi Consulting's internal help desk. "
    "Aditi Consulting is an IT services company. Employees use Microsoft 365 (Outlook, Teams), "
    "Zoom, Intune-managed Windows/Mac devices, Azure AD / Entra ID for identity, "
    "Keka and greytHR for HR, Freshservice for IT tickets, TeamViewer for remote support, "
    "3CX for VoIP, and ActivTrak for activity monitoring. "
    "You provide accurate, empathetic, and actionable support grounded exclusively in the "
    "provided knowledge base articles. "
    "Never invent steps not found in the knowledge base. "
    "If the knowledge base does not cover the issue, say so honestly and offer to escalate. "
    "Maintain a professional, respectful tone. "
    "Format your response with clear numbered steps and expected outcomes for each step."
)

RESOLUTION_PROMPT = """You are a professional IT Support Specialist at Aditi Consulting's internal help desk.

Your task is to resolve the employee's IT issue using ONLY the verified knowledge base articles provided below.

Communication guidelines:
- Open with a brief, empathetic acknowledgment of the specific issue (1-2 sentences)
- Present numbered resolution steps clearly — each step should have an expected outcome
- Use plain language; avoid jargon unless the employee is clearly technical
- If confidence is below 80%, proactively offer to escalate to a human specialist
- Always cite the knowledge article you're drawing from
- Close with an invitation for follow-up (e.g. "Let me know if that resolves the issue")
- Escalation path: Freshservice ticket → IT Lead → IT Admin (only if steps don't resolve)

Knowledge base articles (verified Aditi internal documentation):
{knowledge_articles}

Employee's issue: {user_issue}
Issue category: {category}
Severity: {severity}

Provide a clear, professional resolution response with numbered steps."""


def _get_steps(article: dict) -> list:
    """Extract steps from an article dict, supporting both DB and YAML field names."""
    return (
        article.get("resolution_steps")
        or article.get("troubleshooting_steps")
        or article.get("steps")
        or []
    )


async def resolution_node(state: WorkflowState) -> dict:
    """Generate resolution steps from retrieved knowledge.

    This node:
    1. Takes knowledge articles from retrieval
    2. If LLM available — synthesizes user-friendly guidance via RAG
    3. Otherwise extracts steps directly from knowledge articles
    4. Returns formatted resolution with confidence
    """
    logger.info(
        "resolution_node_start",
        session_id=state.get("session_id"),
        knowledge_count=len(state.get("knowledge_results", [])),
    )

    knowledge_results = state.get("knowledge_results", [])

    resolution = await _generate_resolution(knowledge_results, state)
    response_content = _format_resolution_message(resolution, state)

    audit_entry = {
        "event": "resolution.generated",
        "confidence": resolution["confidence"],
        "steps_count": len(resolution["steps"]),
        "method": resolution.get("method", "direct"),
    }

    return {
        "current_node": "resolve",
        "resolution_steps": resolution["steps"],
        "resolution_confidence": resolution["confidence"],
        "messages": [AIMessage(content=response_content)],
        "audit_trail": [audit_entry],
    }


async def _generate_resolution(knowledge_results: list[dict], state: WorkflowState) -> dict:
    """Generate resolution steps from knowledge articles.

    Strategy:
    1. If LLMService is available — use RAG prompt for natural language generation
    2. Otherwise — extract steps directly from the best matching article
    """
    if not knowledge_results:
        return {"steps": [], "confidence": 0.0, "method": "none"}

    llm = get_llm_service()
    if llm.is_available:
        try:
            return await _llm_resolution(knowledge_results, state, llm)
        except Exception as e:
            logger.warning("resolution_llm_fallback", error=str(e))

    return _direct_resolution(knowledge_results, state)


async def _llm_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    llm: object,
) -> dict:
    """Use LLM to synthesize a natural language resolution."""
    from app.services.llm_service import LLMService

    assert isinstance(llm, LLMService)

    # Format knowledge articles for the prompt, using correct field names
    articles_text = "\n\n".join(
        f"Article: {a.get('title', 'Untitled')}\n"
        f"Category: {a.get('category', 'general')}\n"
        f"Summary: {a.get('short_summary') or ''}\n"
        f"Resolution Steps: {_get_steps(a)}\n"
        f"Content: {(a.get('content') or a.get('snippet') or '')[:1200]}"
        for a in knowledge_results[:3]
    )

    user_issue = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "human":
            user_issue = msg.content
            break

    prompt = RESOLUTION_PROMPT.format(
        knowledge_articles=articles_text,
        user_issue=user_issue,
        category=state.get("issue_category", "other"),
        severity=state.get("severity", "medium"),
    )

    content = await llm.complete(prompt, system_prompt=RESOLUTION_SYSTEM_PROMPT)

    # LLM returns well-structured prose — wrap as a single "step" for consistent format
    steps = [{"step_number": 1, "instruction": content, "details": None}]
    confidence = min(0.95, state.get("knowledge_confidence", 0.5) + 0.15)

    return {"steps": steps, "confidence": confidence, "method": "llm"}


def _direct_resolution(knowledge_results: list[dict], state: WorkflowState) -> dict:
    """Extract steps directly from the best matching article (no-LLM fallback)."""
    best_article = knowledge_results[0]
    raw_steps = _get_steps(best_article)
    confidence = min(0.9, state.get("knowledge_confidence", 0.5) + 0.1)

    formatted_steps = []
    for i, step in enumerate(raw_steps, 1):
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

    return {"steps": formatted_steps, "confidence": confidence, "method": "direct"}


def _format_resolution_message(resolution: dict, state: WorkflowState) -> str:
    """Format resolution into a professional user-facing message."""
    if not resolution["steps"]:
        return (
            "Thank you for contacting Aditi IT Support. I've reviewed your issue but "
            "I'm unable to find a matching resolution in our knowledge base. "
            "I'd recommend raising a Freshservice ticket so our IT team can assist directly.\n\n"
            "Would you like me to escalate this to our IT support team?"
        )

    confidence = resolution["confidence"]
    method = resolution.get("method", "direct")

    # LLM method returns fully-formatted prose — return as-is
    if method == "llm" and len(resolution["steps"]) == 1:
        return resolution["steps"][0]["instruction"]

    # Direct method — build structured response
    lines = []
    if confidence >= 0.8:
        lines.append(
            "I've found a resolution for your issue in our knowledge base. "
            "Please follow these steps:\n"
        )
    else:
        lines.append(
            "Based on our knowledge base, here are some troubleshooting steps "
            "that should resolve your issue:\n"
        )

    for step in resolution["steps"]:
        lines.append(f"**Step {step['step_number']}**: {step['instruction']}")
        if step.get("details"):
            lines.append(f"   _{step['details']}_")
        lines.append("")

    if confidence >= 0.8:
        lines.append(
            "Let me know if these steps resolved your issue, or if you need "
            "further assistance — I'm here to help."
        )
    else:
        lines.append(
            "If these steps don't fully resolve your issue, I can raise a Freshservice ticket "
            "to connect you with an IT specialist. Just let me know how it goes."
        )

    return "\n".join(lines)
