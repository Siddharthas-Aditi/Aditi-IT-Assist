# Workflows — Aditi IT Assist

## Primary Support Workflow

### Sequence Diagram

```
Employee          Frontend          Backend API       Agent Workflow       LLM/KB
   │                 │                  │                  │                │
   │─── Type msg ───►│                  │                  │                │
   │                 │── POST /chat ───►│                  │                │
   │                 │                  │── invoke graph ─►│                │
   │                 │                  │                  │── classify ───►│
   │                 │                  │                  │◄── category ───│
   │                 │                  │                  │── search KB ──►│
   │                 │                  │                  │◄── articles ───│
   │                 │                  │                  │── generate ───►│
   │                 │                  │                  │◄── steps ──────│
   │                 │◄── response ─────│◄── state ────────│                │
   │◄── Display ─────│                  │                  │                │
```

## Workflow States

### New Session Flow
```
START → triage → retrieve → resolve → END (success)
                                    └→ escalate → draft_ticket → END
```

### Clarification Flow
```
START → triage → (needs_clarification) → respond_to_user → triage → ...
```

### Immediate Escalation Flow
```
START → triage → escalate → draft_ticket → END
```

## State Transitions

| From | To | Condition |
|------|----|-----------|
| START | triage | Always (new message) |
| triage | retrieve | Issue classified successfully |
| triage | triage | Needs clarification (ask user) |
| triage | escalate | Cannot classify after 3 attempts |
| retrieve | resolve | Knowledge found (confidence > 0.3) |
| retrieve | escalate | No knowledge found |
| resolve | END | High confidence (>= 0.8) |
| resolve | END | Medium confidence (0.5-0.8) with disclaimer |
| resolve | escalate | Low confidence (< 0.5) |
| escalate | draft_ticket | Escalation approved |
| escalate | END | User declines escalation |
| draft_ticket | END | Draft created |

## Background Workflows

### Knowledge Learning (Async)
```
Resolved Session → Extract Patterns → Identify Gaps → Suggest Articles → Human Review
```

### Knowledge Indexing (Async)
```
New Article Created → Generate Embedding → Store in pgvector → Update Search Index
```

## Error Handling Workflows

### LLM Failure
```
LLM Call Failed → Retry (3x with backoff) → Fallback Response → Log Error
```

### Database Failure
```
DB Query Failed → Return Cached Response (Redis) → Degrade Gracefully → Alert
```

## Conversation Lifecycle

1. **Session Created**: User sends first message
2. **Active**: Agents processing, user interacting
3. **Awaiting User**: AI asked question, waiting for response
4. **Resolved**: Issue resolved by AI
5. **Escalated**: Handed off to human
6. **Closed**: Session ended (resolved or escalated)

## Audit Trail Events

Every workflow execution logs:
- `session.created` — new support session
- `triage.classified` — issue categorized
- `knowledge.searched` — KB query executed
- `resolution.generated` — steps created
- `resolution.confidence` — confidence score recorded
- `escalation.triggered` — escalation decision
- `ticket.drafted` — support ticket created
- `session.resolved` — issue resolved
- `session.closed` — session ended
