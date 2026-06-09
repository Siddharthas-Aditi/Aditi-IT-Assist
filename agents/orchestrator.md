# Orchestrator Agent

## Role
Routes the conversation flow between specialized agents based on the current state.

## Inputs
- Current WorkflowState
- User message history
- Classification results from triage
- Confidence scores

## Outputs
- Next agent to invoke
- Updated state metadata

## Decision Logic
```
IF new_conversation → Triage Agent
IF needs_clarification → Return to user (END with question)
IF classified_and_no_knowledge → Escalation Agent
IF has_knowledge → Resolution Agent
IF low_confidence → Escalation Agent
IF user_requests_human → Escalation Agent
IF escalation_approved → Ticket Agent
```

## Implementation
- File: `backend/app/workflows/graph.py`
- The orchestrator is implemented as conditional edges in the LangGraph state machine
- Uses deterministic routing functions, NOT LLM-based decisions
- This ensures predictable, auditable behavior

## Boundaries
- Must not make LLM calls for routing decisions
- Must always log the routing decision to audit trail
- Must respect user's explicit escalation requests
- Must never loop infinitely (max 5 turns per session)

## Safety Rails
- Maximum conversation turns: 10
- Timeout: 30 seconds per agent node
- Fallback: If any agent errors, route to escalation
