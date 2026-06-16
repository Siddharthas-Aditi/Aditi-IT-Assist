"""Triage Agent Node — classifies and categorizes IT issues."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service
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

CLASSIFICATION_PROMPT = """You are a professional IT support classification specialist at Aditi Consulting.
Your role is to accurately categorize employee IT issues to route them to the correct resolution path.

Analyze the user's message carefully and classify their IT issue into one of these categories:
- email/outlook: Email delivery, sync, Outlook crashes, configuration issues
- video-conferencing/zoom: Zoom sign-in, audio/video problems, meeting join failures
- device-management/intune: Intune compliance, device enrollment, MDM sync
- hardware/camera: Camera not working, permissions, driver issues
- hardware/other: Keyboards, monitors, docking stations, peripherals
- software/other: Application installs, crashes, licensing, updates
- network/connectivity: VPN, WiFi, Ethernet, DNS resolution
- access/permissions: Login failures, MFA, password resets, access denied
- other: Issues that don't fit the above categories

Respond ONLY with valid JSON (no markdown, no explanation):
{
  "category": "<category from list above>",
  "subcategory": "<specific issue type>",
  "severity": "low|medium|high|critical",
  "urgency": "low|medium|high",
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": 0.85
}

If the message is too vague to classify confidently, set needs_clarification=true and provide
a polite, professional clarification_question that helps narrow the issue.

User message: {user_message}"""


async def triage_node(state: WorkflowState) -> dict:
    """Classify the user's IT issue and determine category/severity.

    This node:
    1. Extracts the latest user message
    2. Attempts LLM classification via LLMService
    3. Falls back to keyword matching if LLM unavailable
    4. Updates state with classification results
    """
    logger.info("triage_node_start", session_id=state.get("session_id"))

    messages = state.get("messages", [])
    if not messages:
        return {
            "current_node": "triage",
            "needs_clarification": True,
            "clarification_question": (
                "Welcome to Aditi IT Support. I'm your dedicated IT assistant, "
                "here to help resolve technical issues quickly and efficiently. "
                "Please describe the issue you're experiencing, and I'll guide you "
                "through the resolution process."
            ),
            "messages": [
                AIMessage(
                    content=(
                        "Welcome to Aditi IT Support. I'm your dedicated IT assistant, "
                        "here to help resolve technical issues quickly and efficiently. "
                        "Please describe the issue you're experiencing, and I'll guide you "
                        "through the resolution process."
                    )
                )
            ],
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

    # Attempt LLM classification, fall back to keyword matching
    classification = await _classify_issue(user_message)

    audit_entry = {
        "event": "triage.classified",
        "category": classification.get("category"),
        "confidence": classification.get("confidence", 0),
        "method": classification.get("_method", "keyword"),
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


TRIAGE_SYSTEM_PROMPT = (
    "You are a professional IT support triage specialist at Aditi Consulting. "
    "You must respond ONLY with valid JSON as specified. No explanation, no markdown fences. "
    "Be precise, accurate, and always provide a classification even for vague messages."
)


async def _classify_issue(message: str) -> dict:
    """Classify an IT issue from user message.

    Strategy:
    1. If LLMService is available, use structured JSON completion
    2. Otherwise fall back to deterministic keyword matching
    """
    llm = get_llm_service()

    if llm.is_available:
        try:
            prompt = CLASSIFICATION_PROMPT.format(user_message=message)
            result = await llm.complete_json(prompt, system_prompt=TRIAGE_SYSTEM_PROMPT)
            if result and "category" in result:
                result["_method"] = "llm"
                return result
        except Exception as e:
            logger.warning("triage_llm_fallback", error=str(e))

    # Deterministic keyword-based classification (fallback)
    return _keyword_classify(message)


def _keyword_classify(message: str) -> dict:
    """Deterministic keyword-based classification fallback."""
    message_lower = message.lower()

    if any(word in message_lower for word in ["outlook", "email", "mail", "inbox"]):
        return {
            "category": "email/outlook",
            "subcategory": "email-delivery",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["zoom", "video call", "meeting"]):
        return {
            "category": "video-conferencing/zoom",
            "subcategory": "zoom-general",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["intune", "compliance", "non-compliant"]):
        return {
            "category": "device-management/intune",
            "subcategory": "compliance",
            "severity": "high",
            "urgency": "high",
            "needs_clarification": False,
            "confidence": 0.90,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["camera", "webcam", "video device"]):
        return {
            "category": "hardware/camera",
            "subcategory": "camera-access",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": False,
            "confidence": 0.85,
            "_method": "keyword",
        }
    else:
        return {
            "category": "other",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": True,
            "clarification_question": (
                "I'd like to help you with this. Could you provide a few more details? "
                "For example, which application, device, or service is affected, "
                "and when did the issue first occur?"
            ),
            "confidence": 0.3,
            "_method": "keyword",
        }
