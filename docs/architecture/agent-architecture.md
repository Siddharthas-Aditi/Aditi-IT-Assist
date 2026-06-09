# Agent Architecture — Aditi IT Assist

## Design Philosophy

The agent system follows these principles:
1. **Single Responsibility** — each agent does one thing well
2. **Explicit State** — all context passes through typed WorkflowState
3. **Deterministic Routing** — orchestrator uses rules, not LLM, for routing decisions
4. **Confidence Transparency** — agents report certainty honestly
5. **Graceful Degradation** — system works even if LLM fails (fallback paths)
6. **Audit Everything** — every decision is logged

## LangGraph Workflow

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(WorkflowState)

# Add nodes
workflow.add_node("triage", triage_node)
workflow.add_node("retrieve", retrieval_node)
workflow.add_node("resolve", resolution_node)
workflow.add_node("escalate", escalation_node)
workflow.add_node("draft_ticket", ticket_node)

# Define edges
workflow.set_entry_point("triage")
workflow.add_edge("triage", "retrieve")
workflow.add_conditional_edges("retrieve", route_after_retrieval)
workflow.add_conditional_edges("resolve", route_after_resolution)
workflow.add_conditional_edges("escalate", route_after_escalation)
workflow.add_edge("draft_ticket", END)
```

## State Schema

```python
class WorkflowState(TypedDict):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_id: str

    # Classification
    issue_category: str | None
    issue_subcategory: str | None
    severity: Literal["low", "medium", "high", "critical"] | None
    urgency: Literal["low", "medium", "high"] | None
    impact: Literal["individual", "team", "department", "organization"] | None

    # Knowledge
    knowledge_results: list[dict]
    knowledge_confidence: float

    # Resolution
    resolution_steps: list[dict]
    resolution_confidence: float
    steps_attempted: list[str]

    # Escalation
    should_escalate: bool
    escalation_reason: str | None
    handoff_summary: dict | None

    # Ticket
    ticket_draft: dict | None
    ticket_created: bool

    # Meta
    current_node: str
    turn_count: int
    audit_trail: list[dict]
```

## Agent Details

### Triage Agent
**Node**: `triage_node`
**LLM Call**: Yes (classification)
**Prompt Strategy**: Few-shot classification with known categories
**Output**: Updates `issue_category`, `severity`, `urgency`, `impact`
**Fallback**: If LLM fails, ask user to select from category list

### Knowledge Retrieval Agent
**Node**: `retrieval_node`
**LLM Call**: No (vector search only)
**Strategy**: Embed user query → search pgvector → rank results
**Output**: Updates `knowledge_results`, `knowledge_confidence`
**Fallback**: If no results, flag for escalation

### Resolution Agent
**Node**: `resolution_node`
**LLM Call**: Yes (RAG-based generation)
**Strategy**: Use retrieved knowledge + conversation context to generate steps
**Output**: Updates `resolution_steps`, `resolution_confidence`
**Constraints**:
- Steps must reference knowledge source
- Cannot invent steps not in knowledge base
- Must include confidence score

### Escalation Agent
**Node**: `escalation_node`
**LLM Call**: Minimal (summary generation)
**Strategy**: Compile conversation into structured handoff
**Output**: Updates `handoff_summary`, `should_escalate`
**Logic**:
- Always escalate if user explicitly requests
- Always escalate if confidence < 0.5
- Suggest escalation if confidence < 0.8

### Ticket/Email Agent
**Node**: `ticket_node`
**LLM Call**: Yes (formatting)
**Strategy**: Format handoff into ticket template
**Output**: Updates `ticket_draft`, `ticket_created`
**Template Fields**: title, description, category, priority, steps_attempted, context

## Routing Functions

```python
def route_after_retrieval(state: WorkflowState) -> str:
    if not state["knowledge_results"]:
        return "escalate"
    if state["knowledge_confidence"] < 0.3:
        return "escalate"
    return "resolve"

def route_after_resolution(state: WorkflowState) -> str:
    if state["resolution_confidence"] >= 0.8:
        return END  # Provide resolution to user
    if state["resolution_confidence"] >= 0.5:
        return END  # Provide with disclaimer
    return "escalate"

def route_after_escalation(state: WorkflowState) -> str:
    if state["should_escalate"]:
        return "draft_ticket"
    return END
```

## Adding a New Agent

1. Create `agents/new-agent.md` with full specification
2. Define node function in `backend/app/workflows/nodes/new_agent.py`
3. Add state fields to `backend/app/workflows/state.py`
4. Register node in `backend/app/workflows/graph.py`
5. Add routing edges
6. Write tests in `backend/tests/unit/test_workflows/`
7. Update this document
