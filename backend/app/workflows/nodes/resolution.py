"""Resolution Agent Node — generates step-by-step troubleshooting guidance."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

RESOLUTION_PROMPT = """You are a professional IT Support Specialist at Aditi Consulting's internal help desk.
Your role is to provide clear, actionable troubleshooting guidance to employees based on verified internal knowledge base articles.

Communication guidelines:
- Be professional, empathetic, and concise
- Address the user respectfully
- Present steps in a clear numbered format
- Include expected outcomes for each step
- If confidence is below 80%, offer to escalate to a human specialist
- Never guess or invent steps not supported by the knowledge articles
- Always cite which knowledge source the steps come from
- End with a supportive closing that invites follow-up questions

Knowledge base articles (verified internal documentation):
{knowledge_articles}

Employee's issue: {user_issue}
Classified category: {category}

Provide a professional, helpful resolution response with numbered steps. Start with a brief acknowledgment of the issue, then present the steps, and close with a follow-up offer."""


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

    # Generate resolution from knowledge
    resolution = await _generate_resolution(knowledge_results, state)

    # Build AI response message
    response_content = _format_resolution_message(resolution)

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

    # Attempt LLM-powered resolution synthesis
    llm = get_llm_service()
    if llm.is_available:
        try:
            return await _llm_resolution(knowledge_results, state, llm)
        except Exception as e:
            logger.warning("resolution_llm_fallback", error=str(e))

    # Fallback: extract steps directly from best article
    return _direct_resolution(knowledge_results, state)


RESOLUTION_SYSTEM_PROMPT = (
    "You are a professional IT Support Specialist at Aditi Consulting's internal help desk. "
    "You provide accurate, empathetic, and actionable support grounded exclusively in the "
    "provided knowledge base articles. Never invent steps not found in the knowledge base. "
    "Maintain a professional, respectful tone at all times. "
    "Format your response with clear numbered steps and expected outcomes."
)


async def _llm_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    llm: object,
) -> dict:
    """Use LLM to synthesize a natural language resolution."""
    from app.services.llm_service import LLMService

    assert isinstance(llm, LLMService)

    # Format knowledge articles for the prompt
    articles_text = "\n\n".join(
        f"Article: {a.get('title', 'Untitled')}\n"
        f"Category: {a.get('category', 'general')}\n"
        f"Steps: {a.get('steps', [])}\n"
        f"Content: {a.get('content', '')[:1000]}"
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
    )

    content = await llm.complete(prompt, system_prompt=RESOLUTION_SYSTEM_PROMPT)

    # LLM returns prose — wrap as a single "step" for consistent format
    steps = [{"step_number": 1, "instruction": content, "details": None}]
    confidence = min(0.95, state.get("knowledge_confidence", 0.5) + 0.15)

    return {"steps": steps, "confidence": confidence, "method": "llm"}


def _direct_resolution(knowledge_results: list[dict], state: WorkflowState) -> dict:
    """Extract steps directly from the best matching article (fallback)."""
    best_article = knowledge_results[0]
    steps = best_article.get("steps", [])
    confidence = min(0.9, state.get("knowledge_confidence", 0.5) + 0.1)

    formatted_steps = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, dict):
            formatted_steps.append({
                "step_number": i,
                "instruction": step.get("instruction", step.get("step", "")),
                "details": step.get("details"),
            })
        elif isinstance(step, str):
            formatted_steps.append({
                "step_number": i,
                "instruction": step,
                "details": None,
            })

    return {"steps": formatted_steps, "confidence": confidence, "method": "direct"}


def _format_resolution_message(resolution: dict) -> str:
    """Format resolution into a professional user-friendly message."""
    if not resolution["steps"]:
        return (
            "Thank you for contacting Aditi IT Support. I've reviewed your issue but "
            "I'm unable to provide a confident resolution based on our current knowledge base. "
            "I'd recommend connecting you with a specialist who can assist further.\n\n"
            "Would you like me to escalate this to our IT support team?"
        )

    confidence = resolution["confidence"]
    lines = []

    if confidence >= 0.8:
        lines.append(
            "Thank you for reaching out. I've identified a solution for your issue. "
            "Please follow these steps:\n"
        )
    else:
        lines.append(
            "Thank you for contacting IT Support. Based on our knowledge base, "
            "here are some troubleshooting steps that may resolve your issue:\n"
        )

    for step in resolution["steps"]:
        lines.append(f"**Step {step['step_number']}**: {step['instruction']}")
        if step.get("details"):
            lines.append(f"   _{step['details']}_")
        lines.append("")

    if confidence >= 0.8:
        lines.append(
            "\nPlease let me know if these steps resolved your issue, or if you need "
            "further assistance. I'm here to help."
        )
    else:
        lines.append(
            "\nIf these steps don't fully resolve your issue, I can connect you with "
            "a specialist from our IT support team for additional assistance. "
            "Just let me know how it goes."
        )

    return "\n".join(lines)
