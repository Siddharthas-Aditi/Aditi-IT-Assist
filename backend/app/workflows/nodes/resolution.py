"""Resolution Agent Node — generates step-by-step troubleshooting guidance."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

RESOLUTION_PROMPT = """You are an IT support resolution specialist at Aditi Consulting.
Based on the knowledge base articles provided, generate clear step-by-step
troubleshooting instructions for the user.

Rules:
- Only use steps found in the knowledge base articles
- Be clear and specific in each step
- Number your steps
- Include expected outcomes for each step
- If you're unsure, say so and offer to escalate
- Rate your confidence from 0.0 to 1.0

Knowledge articles:
{knowledge_articles}

User's issue: {user_issue}
Category: {category}

Generate a helpful resolution response."""


async def resolution_node(state: WorkflowState) -> dict:
    """Generate resolution steps from retrieved knowledge.

    This node:
    1. Takes knowledge articles from retrieval
    2. Synthesizes step-by-step guidance via LLM
    3. Assigns confidence score
    4. Returns formatted resolution
    """
    logger.info(
        "resolution_node_start",
        session_id=state.get("session_id"),
        knowledge_count=len(state.get("knowledge_results", [])),
    )

    knowledge_results = state.get("knowledge_results", [])
    knowledge_confidence = state.get("knowledge_confidence", 0)

    # Generate resolution from knowledge
    resolution = await _generate_resolution(knowledge_results, state)

    # Build AI response message
    response_content = _format_resolution_message(resolution)

    audit_entry = {
        "event": "resolution.generated",
        "confidence": resolution["confidence"],
        "steps_count": len(resolution["steps"]),
    }

    return {
        "current_node": "resolve",
        "resolution_steps": resolution["steps"],
        "resolution_confidence": resolution["confidence"],
        "messages": [AIMessage(content=response_content)],
        "audit_trail": [audit_entry],
    }


async def _generate_resolution(knowledge_results: list[dict], state: dict) -> dict:
    """Generate resolution steps from knowledge articles.

    Production: uses LLM with RAG pattern.
    Fallback: returns steps directly from knowledge articles.
    """
    if not knowledge_results:
        return {"steps": [], "confidence": 0.0}

    # Use steps directly from the best matching article
    best_article = knowledge_results[0]
    steps = best_article.get("steps", [])

    # Calculate confidence
    confidence = min(0.9, state.get("knowledge_confidence", 0.5) + 0.1)

    formatted_steps = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, dict):
            formatted_steps.append({
                "step_number": i,
                "instruction": step.get("instruction", step.get("step", "")),
                "details": step.get("details", None),
            })
        elif isinstance(step, str):
            formatted_steps.append({
                "step_number": i,
                "instruction": step,
                "details": None,
            })

    return {"steps": formatted_steps, "confidence": confidence}


def _format_resolution_message(resolution: dict) -> str:
    """Format resolution into a user-friendly message."""
    if not resolution["steps"]:
        return (
            "I found some information about your issue, but I'm not confident "
            "enough in the resolution. Would you like me to connect you with "
            "a human IT support agent?"
        )

    confidence = resolution["confidence"]
    lines = []

    if confidence >= 0.8:
        lines.append("I can help you with that! Here are the steps to resolve your issue:\n")
    else:
        lines.append(
            "I found some steps that might help. Please try them and let me know "
            "if the issue persists:\n"
        )

    for step in resolution["steps"]:
        lines.append(f"**Step {step['step_number']}**: {step['instruction']}")
        if step.get("details"):
            lines.append(f"   _{step['details']}_")
        lines.append("")

    if confidence < 0.8:
        lines.append(
            "\nIf these steps don't resolve your issue, I can escalate to a "
            "human support agent. Just let me know!"
        )

    return "\n".join(lines)
