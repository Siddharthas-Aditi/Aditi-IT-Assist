# Skill: LangGraph Workflow Patterns

> Implementation standards for the LangGraph agent workflow in Aditi IT Assist.

---

## Pattern 1: Node Definition

Every workflow node follows this structure:

```python
import structlog
from langchain_core.messages import AIMessage
from app.workflows.state import WorkflowState

logger = structlog.get_logger()


async def node_name(state: WorkflowState) -> dict:
    """One-sentence description of what this node does.

    Inputs: List what state fields this node reads
    Outputs: List what state fields this node modifies
    """
    logger.info("node_name.start", session_id=state.get("session_id"))

    # 1. Extract needed state
    messages = state.get("messages", [])
    category = state.get("issue_category")

    # 2. Process (business logic here)
    result = await do_the_work(messages, category)

    # 3. Build audit entry
    audit_entry = {
        "event": "node_name.completed",
        "timestamp": datetime.utcnow().isoformat(),
        "result_summary": str(result),
    }

    # 4. Return ONLY modified fields
    logger.info("node_name.complete", result=result)
    return {
        "field_to_update": result.value,
        "current_node": "node_name",
        "audit_trail": [audit_entry],
    }
```

---

## Pattern 2: State Updates

Nodes return ONLY the fields they modify. LangGraph handles merging:

```python
# ✅ CORRECT: Return only what changed
async def triage_node(state: WorkflowState) -> dict:
    return {
        "issue_category": "email/outlook",
        "severity": "medium",
        "current_node": "triage",
        "audit_trail": [{"event": "triage.classified"}],
    }

# ❌ WRONG: Returning the entire state
async def triage_node(state: WorkflowState) -> dict:
    return {**state, "issue_category": "email/outlook"}  # Never spread full state
```

### Message Accumulation

Messages use `add_messages` annotation — they append, never replace:

```python
from langchain_core.messages import AIMessage, HumanMessage

# This APPENDS to the message list (doesn't replace)
return {
    "messages": [AIMessage(content="Here are some steps to try...")],
}
```

---

## Pattern 3: Conditional Routing

Routing functions are pure, deterministic functions:

```python
from langgraph.graph import END

def route_after_triage(state: WorkflowState) -> str:
    """Deterministic routing after triage completes."""
    # Safety: max turns
    if state.get("turn_count", 0) >= 10:
        return "escalation"

    # Needs clarification → return to user
    if state.get("needs_clarification"):
        return END

    # Classified → get knowledge
    if state.get("issue_category"):
        return "retrieval"

    # Fallback
    return "escalation"
```

**Rules for routing functions:**
- No LLM calls
- No I/O (database, network)
- No side effects
- Always handle unknown states (fallback to escalation)
- Log routing decisions

---

## Pattern 4: Graph Construction

```python
from langgraph.graph import StateGraph, END
from app.workflows.state import WorkflowState

def build_support_workflow() -> StateGraph:
    """Build the LangGraph workflow for IT support."""
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("triage", triage_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("resolution", resolution_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("ticketing", ticketing_node)

    # Set entry point
    graph.set_entry_point("triage")

    # Add conditional edges
    graph.add_conditional_edges("triage", route_after_triage)
    graph.add_conditional_edges("retrieval", route_after_retrieval)
    graph.add_conditional_edges("resolution", route_after_resolution)
    graph.add_conditional_edges("escalation", route_after_escalation)
    graph.add_edge("ticketing", END)

    return graph.compile()
```

---

## Pattern 5: Error Handling in Nodes

Nodes must handle errors gracefully and route to escalation:

```python
async def resolution_node(state: WorkflowState) -> dict:
    """Generate resolution — handles LLM failures gracefully."""
    try:
        result = await generate_resolution(state)
        return {
            "resolution_steps": result.steps,
            "resolution_confidence": result.confidence,
            "current_node": "resolution",
        }
    except TimeoutError:
        logger.error("resolution.timeout", session_id=state.get("session_id"))
        return {
            "resolution_confidence": 0.0,
            "resolution_steps": [],
            "current_node": "resolution",
            "audit_trail": [{"event": "resolution.error", "error": "timeout"}],
        }
    except Exception as e:
        logger.error("resolution.unexpected_error", error=str(e))
        return {
            "resolution_confidence": 0.0,
            "resolution_steps": [],
            "current_node": "resolution",
            "audit_trail": [{"event": "resolution.error", "error": str(e)}],
        }
```

---

## Pattern 6: LLM Calls Within Nodes

Always use the abstracted LLM service, never call providers directly:

```python
from app.services.llm_service import LLMService

async def triage_with_llm(messages: list, llm: LLMService) -> Classification:
    """Use LLM for classification with proper error handling."""
    prompt = build_classification_prompt(messages)

    try:
        response = await llm.generate(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for classification
            max_tokens=500,
            timeout=10,
        )
        return parse_classification(response)
    except Exception:
        return keyword_fallback_classify(messages)
```

---

## Pattern 7: Testing Workflow Nodes

```python
import pytest
from app.workflows.nodes.triage import triage_node

@pytest.mark.asyncio
async def test_triage_classifies_email_issue():
    """Triage correctly classifies an email issue."""
    state = {
        "messages": [HumanMessage(content="I'm not receiving emails in Outlook")],
        "session_id": "test-session",
        "turn_count": 0,
    }

    result = await triage_node(state)

    assert result["issue_category"] == "email/outlook"
    assert result["needs_clarification"] is False
    assert result["current_node"] == "triage"


@pytest.mark.asyncio
async def test_triage_asks_clarification_for_vague_message():
    """Triage asks clarification for vague messages."""
    state = {
        "messages": [HumanMessage(content="it's broken")],
        "session_id": "test-session",
        "turn_count": 0,
    }

    result = await triage_node(state)

    assert result["needs_clarification"] is True
    assert result["clarification_question"] is not None
```

---

## Anti-Patterns

| Anti-Pattern | Why It's Wrong | Correct Approach |
|-------------|----------------|------------------|
| Modifying state in-place | State is immutable between nodes | Return new dict with changes |
| LLM calls in routing functions | Must be deterministic | LLM calls only in node bodies |
| Returning full state spread | Unclear what changed | Return only modified fields |
| No error handling in nodes | One failure crashes entire workflow | Try/except with graceful degradation |
| Hardcoded model names | Can't swap providers | Use LLM service abstraction |
| No audit trail entries | Can't debug or explain decisions | Always append to audit_trail |

---

## State Fields Reference

| Field | Set By | Type | Purpose |
|-------|--------|------|---------|
| `messages` | All nodes | `list[BaseMessage]` | Conversation (append-only) |
| `session_id` | Entry | `str` | Session tracking |
| `issue_category` | Triage | `str \| None` | Primary classification |
| `issue_subcategory` | Triage | `str \| None` | Specific problem |
| `severity` | Triage | `str \| None` | Impact level |
| `knowledge_results` | Retrieval | `list[dict]` | Found articles |
| `knowledge_confidence` | Retrieval | `float` | Best match score |
| `resolution_steps` | Resolution | `list[dict]` | Generated steps |
| `resolution_confidence` | Resolution | `float` | Overall confidence |
| `should_escalate` | Escalation | `bool` | Escalation decision |
| `handoff_summary` | Escalation | `dict \| None` | Human agent context |
| `ticket_draft` | Ticketing | `dict \| None` | Support ticket |
| `turn_count` | Graph | `int` | Safety counter |
| `audit_trail` | All nodes | `list[dict]` | Decision log (append-only) |

---

## File Locations

| Concern | Path |
|---------|------|
| State definition | `backend/app/workflows/state.py` |
| Graph construction | `backend/app/workflows/graph.py` |
| Triage node | `backend/app/workflows/nodes/triage.py` |
| Retrieval node | `backend/app/workflows/nodes/retrieval.py` |
| Resolution node | `backend/app/workflows/nodes/resolution.py` |
| Escalation node | `backend/app/workflows/nodes/escalation.py` |
| Ticketing node | `backend/app/workflows/nodes/ticketing.py` |
| Node tests | `backend/tests/unit/test_workflows/` |
