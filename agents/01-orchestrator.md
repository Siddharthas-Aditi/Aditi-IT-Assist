# Agent 01: Orchestrator

> **One-liner**: Routes conversation flow between agents using deterministic,
> auditable logic — no LLM calls.

---

## Role

The Orchestrator is NOT a standalone node. It is implemented as **conditional
edge functions** in the LangGraph state machine. It examines the current
`WorkflowState` and returns the name of the next node to execute.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | `WorkflowState` | Complete state after a node executes |
| **Output** | `str` | Node name: `"triage"`, `"retrieval"`, `"resolution"`, `"escalation"`, `"ticketing"`, or `END` |

---

## Algorithm

```python
def route_after_triage(state: WorkflowState) -> str:
    """Route after triage completes."""
    if state.get("needs_clarification"):
        return END  # Return clarification question to user

    if not state.get("issue_category"):
        return END  # Should not happen; safety fallback

    return "retrieval"


def route_after_retrieval(state: WorkflowState) -> str:
    """Route after knowledge retrieval."""
    if state.get("knowledge_confidence", 0.0) < 0.3:
        return "escalation"  # Nothing useful found

    return "resolution"


def route_after_resolution(state: WorkflowState) -> str:
    """Route after resolution attempt."""
    confidence = state.get("resolution_confidence", 0.0)

    if confidence >= 0.8:
        return END  # High confidence — deliver to user

    return "escalation"  # Low confidence — escalate


def route_after_escalation(state: WorkflowState) -> str:
    """Route after escalation decision."""
    if state.get("should_escalate"):
        return "ticketing"

    return END  # Escalation declined (rare)
```

---

## Decision Table (Complete)

| Current State | Condition | Routes To | Rationale |
|---------------|-----------|-----------|-----------|
| Entry | `turn_count == 0` | `triage` | Every conversation starts with classification |
| After Triage | `needs_clarification == True` | `END` | Ask user for more info |
| After Triage | `issue_category is set` | `retrieval` | Classified → get knowledge |
| After Retrieval | `knowledge_confidence >= 0.3` | `resolution` | Found something useful |
| After Retrieval | `knowledge_confidence < 0.3` | `escalation` | Nothing in KB |
| After Resolution | `confidence >= 0.8` | `END` | High confidence answer |
| After Resolution | `confidence < 0.8` | `escalation` | Uncertain → human help |
| After Escalation | `should_escalate == True` | `ticketing` | Create ticket |
| After Escalation | `should_escalate == False` | `END` | Rare: escalation declined |
| Any | `turn_count >= 10` | `escalation` | Safety limit |
| Any | Node raises exception | `escalation` | Error recovery |

---

## Safety Invariants

1. **No infinite loops**: `turn_count >= 10` forces escalation
2. **No LLM calls**: All routing is pure Python logic
3. **Deterministic**: Same state always produces same routing decision
4. **Logged**: Every routing decision is appended to `audit_trail`
5. **Fallback safe**: Unknown conditions always route to `escalation`

---

## Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Infinite routing loop | `turn_count >= 10` | Force escalation immediately |
| Missing state fields | `state.get()` returns None | Use safe defaults, route to escalation |
| Node threw exception | LangGraph error handler | Catch error, add context, route to escalation |
| State corruption | Type mismatch | Log error + force escalation with context |

---

## Boundaries

- ❌ Must NEVER make LLM API calls
- ❌ Must NEVER perform I/O (database, network, file)
- ❌ Must NEVER modify state (routing functions are pure)
- ❌ Must NEVER suppress user escalation requests
- ✅ Must ALWAYS be deterministic
- ✅ Must ALWAYS log routing decisions
- ✅ Must ALWAYS respect turn limits

---

## Testing

```python
# Test cases for routing functions
def test_routes_to_triage_on_first_message():
    state = {"turn_count": 0, "issue_category": None}
    assert route_entry(state) == "triage"

def test_routes_to_escalation_on_max_turns():
    state = {"turn_count": 10}
    assert route_entry(state) == "escalation"

def test_routes_to_end_on_high_confidence():
    state = {"resolution_confidence": 0.9}
    assert route_after_resolution(state) == END
```

---

## Implementation File

`backend/app/workflows/graph.py` — conditional edges in `StateGraph`
