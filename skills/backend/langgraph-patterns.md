# LangGraph Patterns

## Node Definition
```python
async def node_name(state: WorkflowState) -> dict:
    """Node description — what this agent does."""
    logger.info("node_start", session_id=state.get("session_id"))

    # Process state
    result = await do_work(state)

    # Build audit entry
    audit_entry = {"event": "node.completed", "result": result}

    # Return only the fields that changed
    return {
        "current_node": "node_name",
        "field_to_update": result,
        "audit_trail": [audit_entry],
    }
```

## Routing Functions
```python
def route_after_node(state: WorkflowState) -> str:
    """Deterministic routing based on state."""
    if condition_a(state):
        return "next_node_a"
    if condition_b(state):
        return "next_node_b"
    return END
```

## State Management
- Use TypedDict for type safety
- Return only changed fields from nodes
- Use `Annotated[list, add_messages]` for message accumulation
- Never mutate state directly

## Error Handling
- Wrap LLM calls in try/except
- Provide fallback behavior
- Log errors with context
- Route to escalation on failure
