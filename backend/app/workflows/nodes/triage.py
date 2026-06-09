"""Triage Agent Node — classifies and categorizes IT issues."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

# Known issue categories for classification
ISSUE_CATEGORIES = [
    "email/outlook",
    "video-conferencing/zoom",
    "device-management/intune",
    "hardware/camera",
    "hardware/other",
    "software/other",
    "network/connectivity",
    "access/permissions",
    "other",
]

CLASSIFICATION_PROMPT = """You are an IT support triage specialist at Aditi Consulting.
Analyze the user's message and classify their IT issue.

Categories:
- email/outlook: Email not receiving, Outlook slow, sync issues
- video-conferencing/zoom: Zoom sign-in, audio, video issues
- device-management/intune: Intune compliance, device management
- hardware/camera: Camera not working, permissions
- hardware/other: Other hardware issues
- software/other: Other software issues
- network/connectivity: VPN, WiFi, internet issues
- access/permissions: Login, access denied issues
- other: Anything else

Respond with JSON:
{
  "category": "<category>",
  "subcategory": "<specific issue>",
  "severity": "low|medium|high|critical",
  "urgency": "low|medium|high",
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": 0.85
}

If the message is too vague to classify, set needs_clarification=true and provide
a clarification_question.

User message: {user_message}"""


async def triage_node(state: WorkflowState) -> dict:
    """Classify the user's IT issue and determine category/severity.

    This node:
    1. Extracts the latest user message
    2. Calls LLM for classification
    3. Updates state with classification results
    """
    logger.info("triage_node_start", session_id=state.get("session_id"))

    messages = state.get("messages", [])
    if not messages:
        return {
            "current_node": "triage",
            "needs_clarification": True,
            "clarification_question": "Hi! I'm here to help with your IT issue. Could you describe what problem you're experiencing?",
            "messages": [AIMessage(content="Hi! I'm here to help with your IT issue. Could you describe what problem you're experiencing?")],
        }

    # Get the latest user message
    user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_message = msg.content
            break

    if not user_message:
        return {
            "current_node": "triage",
            "needs_clarification": True,
            "clarification_question": "Could you describe your IT issue?",
        }

    # Perform classification
    # TODO(team): Replace with actual LLM call via LiteLLM
    classification = await _classify_issue(user_message)

    audit_entry = {
        "event": "triage.classified",
        "category": classification.get("category"),
        "confidence": classification.get("confidence", 0),
    }

    return {
        "current_node": "triage",
        "issue_category": classification.get("category"),
        "issue_subcategory": classification.get("subcategory"),
        "severity": classification.get("severity", "medium"),
        "urgency": classification.get("urgency", "medium"),
        "needs_clarification": classification.get("needs_clarification", False),
        "clarification_question": classification.get("clarification_question"),
        "audit_trail": [audit_entry],
    }


async def _classify_issue(message: str) -> dict:
    """Classify an IT issue from user message.

    Uses keyword matching as fallback when LLM is unavailable.
    Production: uses LiteLLM with structured output.
    """
    message_lower = message.lower()

    # Deterministic keyword-based classification (fallback)
    if any(word in message_lower for word in ["outlook", "email", "mail", "inbox"]):
        return {
            "category": "email/outlook",
            "subcategory": "email-delivery",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
        }
    elif any(word in message_lower for word in ["zoom", "video call", "meeting"]):
        return {
            "category": "video-conferencing/zoom",
            "subcategory": "zoom-general",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
        }
    elif any(word in message_lower for word in ["intune", "compliance", "non-compliant"]):
        return {
            "category": "device-management/intune",
            "subcategory": "compliance",
            "severity": "high",
            "urgency": "high",
            "needs_clarification": False,
            "confidence": 0.90,
        }
    elif any(word in message_lower for word in ["camera", "webcam", "video device"]):
        return {
            "category": "hardware/camera",
            "subcategory": "camera-access",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
        }
    else:
        return {
            "category": "other",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": True,
            "clarification_question": "Could you provide more details about your issue? For example, what application or device is affected?",
            "confidence": 0.3,
        }
