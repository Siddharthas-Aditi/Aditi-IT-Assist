# Agent 05: Escalation

> **One-liner**: Evaluates whether to escalate to human support and prepares
> a comprehensive handoff summary.

---

## Role

The Escalation Agent is the gatekeeper between AI resolution and human
support. It decides whether escalation is warranted, prepares a structured
handoff summary, and determines priority level. It uses deterministic
logic — no LLM calls needed.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | Full `WorkflowState` | All context accumulated so far |
| **Output** | `should_escalate: bool` | Escalation decision |
| **Output** | `escalation_reason: str` | Why we're escalating |
| **Output** | `handoff_summary: HandoffSummary` | Structured context for human |

---

## Algorithm

```python
async def escalation_node(state: WorkflowState) -> dict:
    """Decide on escalation and prepare handoff."""
    logger.info("escalation.start", session_id=state["session_id"])

    # Step 1: Determine escalation reason
    reason = determine_escalation_reason(state)

    # Step 2: Calculate priority
    priority = calculate_priority(state, reason)

    # Step 3: Build handoff summary
    summary = build_handoff_summary(state, reason, priority)

    return {
        "should_escalate": True,
        "escalation_reason": reason,
        "handoff_summary": summary,
        "current_node": "escalation",
        "audit_trail": [{
            "event": "escalation.decided",
            "reason": reason,
            "priority": priority,
        }],
    }
```

---

## Escalation Triggers

| # | Trigger | Priority | Detection Logic |
|---|---------|----------|-----------------|
| 1 | User explicitly requests human | P1 | Message contains "human", "agent", "person", "talk to someone" |
| 2 | Critical severity + low confidence | P1 | `severity == "critical" AND resolution_confidence < 0.5` |
| 3 | System error in previous node | P1 | `audit_trail` contains error events |
| 4 | Resolution confidence < 0.5 | P2 | `resolution_confidence < 0.5` |
| 5 | No knowledge found | P2 | `knowledge_confidence < 0.3` |
| 6 | Resolution confidence < 0.8 | P3 | `0.5 <= resolution_confidence < 0.8` |
| 7 | Max turns exceeded (10) | P3 | `turn_count >= 10` |
| 8 | Multiple failed attempts | P3 | `len(steps_attempted) >= 3` |

### Priority Mapping

| Priority | SLA | Description |
|----------|-----|-------------|
| P1 | 15 min | Critical — user blocked, explicit request, or system failure |
| P2 | 1 hour | High — AI couldn't help, no KB coverage |
| P3 | 4 hours | Normal — low confidence, max turns |
| P4 | 8 hours | Low — informational, non-blocking |

---

## Handoff Summary Schema

```python
class HandoffSummary(TypedDict):
    # User context
    employee_name: str          # From user session
    user_id: str                # Internal ID

    # Issue context
    issue_category: str         # From Triage
    issue_subcategory: str      # From Triage
    issue_description: str      # Natural language summary of the problem
    severity: str               # From Triage
    urgency: str                # From Triage

    # What was attempted
    steps_attempted: list[str]  # Steps AI suggested
    ai_confidence: float        # How confident the AI was
    knowledge_articles_used: list[str]  # Article titles used

    # For the human agent
    recommended_actions: list[str]  # What to try next
    escalation_reason: str      # Why we escalated
    priority: str               # P1/P2/P3/P4
    conversation_turns: int     # How long the conversation was
    conversation_summary: str   # Brief summary of the exchange
```

---

## Reason Determination

```python
def determine_escalation_reason(state: WorkflowState) -> str:
    """Determine the primary reason for escalation."""
    messages_text = " ".join(m.content for m in state["messages"] if hasattr(m, "content"))

    # Check explicit user request (highest priority)
    escalation_phrases = ["talk to someone", "human", "real person", "agent", "escalate"]
    if any(phrase in messages_text.lower() for phrase in escalation_phrases):
        return "user_requested_human"

    # Check for system errors
    errors = [e for e in state.get("audit_trail", []) if "error" in e.get("event", "")]
    if errors:
        return "system_error"

    # Check confidence
    confidence = state.get("resolution_confidence", 0.0)
    if confidence == 0.0:
        return "no_resolution_available"
    if confidence < 0.5:
        return "low_confidence"
    if confidence < 0.8:
        return "medium_confidence"

    # Check turn count
    if state.get("turn_count", 0) >= 10:
        return "max_turns_exceeded"

    return "general_escalation"
```

---

## Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| Missing classification | `issue_category is None` | Use "unknown" + escalate anyway | Incomplete summary |
| Empty conversation | `len(messages) == 0` | Minimal summary with metadata | Less context for human |
| State corruption | Missing required fields | Best-effort summary + log | Degraded handoff quality |

---

## Boundaries

- ❌ Must NEVER dismiss a user's request for human help
- ❌ Must NEVER downgrade severity set by Triage
- ❌ Must NEVER block escalation (always `should_escalate = True` when invoked)
- ❌ Must NOT make LLM calls (deterministic only)
- ✅ Must ALWAYS produce a complete `HandoffSummary`
- ✅ Must preserve ALL conversation context
- ✅ Must log escalation reason to audit trail
- ✅ Must calculate appropriate priority

---

## Testing Checklist

- [ ] Detects explicit user escalation requests
- [ ] Correctly maps confidence levels to reasons
- [ ] Produces valid HandoffSummary for all input states
- [ ] Handles missing/incomplete state gracefully
- [ ] Priority calculation matches documented rules
- [ ] Never returns `should_escalate = False` (this node only fires when escalation is needed)
- [ ] Audit trail includes reason and priority

---

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| WorkflowState | All context | — |
| structlog | Logging | — |

No external dependencies — this agent is purely deterministic.

---

## Implementation File

`backend/app/workflows/nodes/escalation.py`
