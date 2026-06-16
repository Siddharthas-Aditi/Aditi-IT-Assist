"""Triage Agent Node — classifies and categorizes IT issues."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

# Known issue categories for classification — aligned with KB seed taxonomy
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

Aditi Consulting uses the following tools and systems internally:
- Email & calendar: Microsoft Outlook / Microsoft 365
- Video conferencing: Zoom (primary), Microsoft Teams
- Device management: Microsoft Intune (MDM), Azure AD / Entra ID
- HR & payroll: Keka, greytHR
- IT ticketing: Freshservice
- Remote support: TeamViewer
- Activity monitoring: ActivTrak
- VoIP: 3CX (BLR-3CX, VDR-3CX)
- Identity & MFA: Microsoft Entra ID / Azure AD, Multi-factor authentication
- Network: VPN, corporate Wi-Fi, LAN

Analyze the user's message carefully and classify their IT issue into EXACTLY one of these categories:
- email/outlook: Email delivery, sync, Outlook crashes, calendar issues, Microsoft 365 access
- video-conferencing/zoom: Zoom sign-in, audio/video problems, meeting join failures, Teams issues
- device-management/intune: Intune compliance, device enrollment, MDM sync, Azure AD join
- hardware/camera: Camera not working, permissions, driver issues, webcam
- hardware/other: Keyboards, monitors, docking stations, peripherals, printers
- software/other: Application installs, crashes, licensing, updates, Keka, greytHR, Freshservice
- network/connectivity: VPN, Wi-Fi, Ethernet, DNS resolution, 3CX, internet access
- access/permissions: Login failures, MFA, password resets, access denied, account lockout
- other: Issues that don't clearly fit the above categories

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "category": "<category from list above>",
  "subcategory": "<specific issue type, e.g. 'zoom-audio' or 'outlook-sync'>",
  "severity": "low|medium|high|critical",
  "urgency": "low|medium|high",
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": 0.85
}}

Set severity=critical for: complete system outage, security breach, data loss, all users affected.
Set severity=high for: individual cannot work, MFA locked out, VPN down.
Set severity=medium for: degraded functionality, intermittent issue.
Set severity=low for: cosmetic issues, minor inconveniences.

CLARIFICATION RULES — set needs_clarification=true in TWO situations:
1. The category cannot be determined at all (truly unclassifiable message).
2. The category IS identifiable but the specific symptom is too vague to resolve without more detail.
   This is the more common case. Examples that require clarification:
   - "I have an Outlook issue" → category=email/outlook, but ASK: which specific problem?
   - "Zoom is not working" → category=video-conferencing/zoom, but ASK: audio, video, or can't join?
   - "I can't access something" → category=access/permissions, but ASK: which app or resource?
   - "Software problem" → category=software/other, but ASK: which application?
   Messages that do NOT need clarification (specific enough to act on immediately):
   - "Outlook is not syncing emails" — specific symptom clear
   - "I can't hear audio in Zoom" — specific symptom clear
   - "My account is locked" — specific symptom clear
   - "Device is non-compliant in Intune" — specific symptom clear

When needs_clarification=true, write a SHORT, friendly clarification_question that names the
specific category you identified and asks for the missing symptom detail. Example:
"I can see this is an Outlook issue — could you tell me more about what's happening?
For example: are emails not arriving, is Outlook slow, or is there a sync or calendar problem?"

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
                "Welcome to Aditi IT Support. I'm your dedicated AI assistant, "
                "here to help resolve your IT issues quickly. "
                "Please describe the problem you're experiencing — include the affected "
                "application or device, and when the issue started."
            ),
            "messages": [
                AIMessage(
                    content=(
                        "Welcome to Aditi IT Support. I'm your dedicated AI assistant, "
                        "here to help resolve your IT issues quickly. "
                        "Please describe the problem you're experiencing — include the affected "
                        "application or device, and when the issue started."
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
            "clarification_question": "Could you describe your IT issue in more detail?",
        }

    # Attempt LLM classification, fall back to keyword matching
    classification = await _classify_issue(user_message)

    audit_entry = {
        "event": "triage.classified",
        "category": classification.get("category"),
        "confidence": classification.get("confidence", 0),
        "method": classification.get("_method", "keyword"),
    }

    needs_clarification = classification.get("needs_clarification", False)
    clarification_question = classification.get("clarification_question")

    result: dict = {
        "current_node": "triage",
        "issue_category": classification.get("category"),
        "issue_subcategory": classification.get("subcategory"),
        "severity": classification.get("severity", "medium"),
        "urgency": classification.get("urgency", "medium"),
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "audit_trail": [audit_entry],
    }

    # When asking for clarification, add the question as an AI message so the
    # graph routes to END and the question is returned directly to the user.
    if needs_clarification and clarification_question:
        result["messages"] = [AIMessage(content=clarification_question)]

    return result


TRIAGE_SYSTEM_PROMPT = (
    "You are a professional IT support triage specialist at Aditi Consulting. "
    "Aditi Consulting is an IT services company with offices in India (Bengaluru, Hyderabad, Chennai) "
    "and internationally. Employees use Microsoft 365, Zoom, Intune-managed devices, Keka for HR, "
    "Freshservice for IT ticketing, and 3CX for VoIP. "
    "Respond ONLY with valid JSON as specified. No explanation, no markdown fences. "
    "Be precise and always provide a classification even for vague messages."
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
                # Validate category is in our known list; fall back if unknown
                if result["category"] in ISSUE_CATEGORIES:
                    result["_method"] = "llm"
                    return result
                logger.warning("triage_unknown_category", category=result.get("category"))
                result["category"] = "other"
                result["_method"] = "llm"
                return result
        except Exception as e:
            logger.warning("triage_llm_fallback", error=str(e))

    # Deterministic keyword-based classification (fallback)
    return _keyword_classify(message)


_VAGUE_SUFFIXES = [
    "issue", "problem", "not working", "broken", "help", "trouble",
    "error", "fault", "issues", "problems",
]


def _is_vague(message: str, keywords: list[str]) -> bool:
    """Return True if message only names a tool/category without a specific symptom."""
    words = message.lower().split()
    # Vague = message is short (≤6 words) AND has no symptom beyond the keyword
    symptom_words = [
        "sync", "syncing", "slow", "crash", "crashing", "audio", "video", "camera",
        "hear", "sound", "connect", "login", "locked", "complian", "enroll",
        "install", "send", "receive", "open", "load", "update", "calendar",
        "password", "reset", "access", "denied", "missing", "disappear",
        "black screen", "freeze", "hang", "drop", "disconnect", "not starting",
    ]
    has_symptom = any(s in message.lower() for s in symptom_words)
    return len(words) <= 8 and not has_symptom


def _keyword_classify(message: str) -> dict:
    """Deterministic keyword-based classification fallback."""
    message_lower = message.lower()

    if any(word in message_lower for word in ["outlook", "email", "mail", "inbox", "calendar", "office 365", "microsoft 365"]):
        vague = _is_vague(message, ["outlook", "email", "mail"])
        return {
            "category": "email/outlook",
            "subcategory": "email-delivery",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is an Outlook or email issue. Could you tell me a bit more about what's happening? "
                "For example: are emails not arriving, is Outlook running slow, is there a calendar sync problem, "
                "or are you having trouble logging in?"
            ) if vague else None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["zoom", "video call", "meeting", "teams", "webinar"]):
        vague = _is_vague(message, ["zoom", "meeting", "teams"])
        return {
            "category": "video-conferencing/zoom",
            "subcategory": "zoom-general",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is a Zoom or Teams issue. Could you describe what's going wrong? "
                "For example: is there no audio, is the camera not showing, or are you unable to join the meeting at all?"
            ) if vague else None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["intune", "compliance", "non-compliant", "mdm", "device enroll"]):
        vague = _is_vague(message, ["intune", "compliance"])
        return {
            "category": "device-management/intune",
            "subcategory": "compliance",
            "severity": "high",
            "urgency": "high",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is an Intune or device compliance issue. What is the device showing? "
                "For example: does Company Portal say 'Not compliant', or are you blocked from accessing Office apps?"
            ) if vague else None,
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
            "clarification_question": None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["vpn", "wifi", "wi-fi", "internet", "network", "ethernet", "3cx", "voip"]):
        vague = _is_vague(message, ["vpn", "network", "wifi"])
        return {
            "category": "network/connectivity",
            "subcategory": "connectivity",
            "severity": "high",
            "urgency": "high",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is a network or connectivity issue. Could you describe what's happening? "
                "For example: is the VPN disconnecting, is Wi-Fi not connecting, or is a specific application unreachable?"
            ) if vague else None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["password", "login", "mfa", "locked", "access denied", "permission", "authenticat"]):
        vague = _is_vague(message, ["password", "login", "mfa", "locked"])
        return {
            "category": "access/permissions",
            "subcategory": "access-denied",
            "severity": "high",
            "urgency": "high",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is an access or login issue. Could you tell me more? "
                "For example: is your account locked, has your password expired, or is MFA not working on your phone?"
            ) if vague else None,
            "confidence": 0.85,
            "_method": "keyword",
        }
    elif any(word in message_lower for word in ["keka", "greyhr", "freshservice", "ruddr", "sixth sense", "install", "software", "application", "app crash"]):
        vague = _is_vague(message, ["software", "application", "app"])
        return {
            "category": "software/other",
            "subcategory": "software-general",
            "severity": "medium",
            "urgency": "medium",
            "needs_clarification": vague,
            "clarification_question": (
                "I can see this is a software or application issue. Could you tell me which application, "
                "and what specifically is happening — for example, is it crashing, failing to install, "
                "or showing a licence error?"
            ) if vague else None,
            "confidence": 0.80,
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
                "Which application or device is affected, and what specifically is happening?"
            ),
            "confidence": 0.3,
            "_method": "keyword",
        }
