# Agent 02: Intake & Triage

> **One-liner**: Classifies the user's IT issue through natural language
> understanding, asks clarifying questions when needed.

---

## Role

The Triage Agent is the first responder. It takes the user's initial message
(or follow-up to a clarification question), understands what's wrong, and
produces a structured classification that the rest of the pipeline uses.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | `messages: list[BaseMessage]` | Full conversation history |
| **Input** | `turn_count: int` | Current turn number |
| **Output** | `issue_category: str` | Primary category |
| **Output** | `issue_subcategory: str` | Specific problem type |
| **Output** | `severity: str` | low / medium / high / critical |
| **Output** | `urgency: str` | low / medium / high |
| **Output** | `impact: str` | individual / team / department / organization |
| **Output** | `needs_clarification: bool` | Whether to ask follow-up |
| **Output** | `clarification_question: str | None` | The question to ask |

---

## Algorithm

```python
async def triage_node(state: WorkflowState) -> dict:
    """Classify the user's IT issue."""
    logger.info("triage.start", session_id=state["session_id"])

    user_message = get_latest_user_message(state["messages"])

    # Step 1: Try LLM classification
    try:
        classification = await llm_classify(user_message, state["messages"])
    except (TimeoutError, ConnectionError):
        # Step 2: Fallback to keyword classifier
        classification = keyword_classify(user_message)

    # Step 3: Check if we need clarification
    if classification.confidence < 0.3 and state.get("turn_count", 0) < 3:
        return {
            "needs_clarification": True,
            "clarification_question": classification.suggested_question,
            "current_node": "triage",
            "audit_trail": [{"event": "triage.needs_clarification"}],
        }

    # Step 4: Return classification
    return {
        "issue_category": classification.category,
        "issue_subcategory": classification.subcategory,
        "severity": classification.severity,
        "urgency": classification.urgency,
        "impact": classification.impact,
        "needs_clarification": False,
        "current_node": "triage",
        "audit_trail": [{"event": "triage.classified", ...}],
    }
```

---

## Prompt Template

```
SYSTEM: You are an IT support triage agent for Aditi Consulting.
Your job is to classify the user's IT issue into a structured format.

Classify the following message into:
- category: One of [email/outlook, video-conferencing/zoom, device-management/intune,
  hardware/camera, hardware/other, software/other, network/connectivity,
  access/permissions, other]
- subcategory: A more specific problem type
- severity: low | medium | high | critical
- urgency: low | medium | high
- impact: individual | team | department | organization

If the message is too vague to classify confidently, respond with a single
clarifying question. Do NOT try to solve the problem — only classify it.

Respond in JSON format only.

USER: {user_message}

CONVERSATION HISTORY: {history_summary}
```

---

## Categories Reference

| Category | Keywords / Signals | Severity Indicators |
|----------|-------------------|---------------------|
| `email/outlook` | email, outlook, inbox, calendar, meeting invite | Critical if org-wide |
| `video-conferencing/zoom` | zoom, teams, video, audio, call | High if meeting in progress |
| `device-management/intune` | intune, compliance, MDM, enrollment | Medium default |
| `hardware/camera` | camera, webcam, video feed | Medium default |
| `hardware/other` | keyboard, mouse, monitor, dock | Low-Medium |
| `software/other` | install, update, crash, license | Varies |
| `network/connectivity` | vpn, wifi, internet, network, slow | High if can't work |
| `access/permissions` | login, password, access denied, MFA | High if locked out |
| `other` | — | Medium default |

---

## Keyword Fallback Classifier

When the LLM is unavailable, use deterministic keyword matching:

```python
KEYWORD_MAP = {
    "email/outlook": ["email", "outlook", "inbox", "calendar", "meeting invite"],
    "video-conferencing/zoom": ["zoom", "teams", "video call", "audio", "screen share"],
    "device-management/intune": ["intune", "compliance", "mdm", "company portal"],
    "hardware/camera": ["camera", "webcam", "video feed"],
    "network/connectivity": ["vpn", "wifi", "internet", "network", "dns", "proxy"],
    "access/permissions": ["login", "password", "access denied", "mfa", "locked out"],
}

def keyword_classify(message: str) -> Classification:
    message_lower = message.lower()
    scores = {}
    for category, keywords in KEYWORD_MAP.items():
        scores[category] = sum(1 for kw in keywords if kw in message_lower)
    best = max(scores, key=scores.get)
    return Classification(category=best if scores[best] > 0 else "other", ...)
```

---

## Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| LLM timeout (>10s) | `asyncio.TimeoutError` | Keyword fallback | Lower accuracy |
| LLM returns invalid JSON | `json.JSONDecodeError` | Retry once → keyword | Brief delay |
| LLM returns wrong schema | Missing required fields | Keyword fallback | Lower accuracy |
| User message empty | `len(message.strip()) == 0` | Ask clarification | Extra turn |
| User message in non-English | Detect via LLM | Attempt anyway, ask if unclear | Best effort |
| Max clarifications (3) | Counter check | Force classify as "other" | May misclassify |
| LLM completely down | `ConnectionError` | Keyword + log alert | Degraded accuracy |

---

## Boundaries

- ❌ Must NOT attempt to resolve the issue
- ❌ Must NOT search the knowledge base
- ❌ Must NOT access external APIs
- ❌ Must NOT make assumptions about the user's environment
- ✅ Maximum 3 clarification rounds before forced classification
- ✅ Must always produce a category (never return None)
- ✅ Must log classification confidence to audit trail
- ✅ Must respect conversation history (don't re-ask answered questions)

---

## Testing Checklist

- [ ] Classifies clear issues correctly (one-shot)
- [ ] Asks clarification for vague messages ("it's broken")
- [ ] Falls back to keyword classifier when LLM unavailable
- [ ] Never exceeds 3 clarification rounds
- [ ] Handles empty messages gracefully
- [ ] Produces valid severity/urgency/impact values
- [ ] Audit trail entry created for every classification

---

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| LiteLLM | LLM classification | Keyword classifier |
| structlog | Logging | — |
| State machine | Turn counting | — |

---

## Implementation File

`backend/app/workflows/nodes/triage.py`
