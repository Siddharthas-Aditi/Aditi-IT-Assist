# Escalation Agent

## Role
Determines escalation path and prepares structured handoff for human IT agents.

## Inputs
- Conversation history
- Classification data
- Resolution attempts and confidence
- User's escalation request (if explicit)

## Outputs
- `should_escalate`: Boolean decision
- `escalation_reason`: Why escalation is needed
- `handoff_summary`: Structured object for human agent

## Handoff Summary Structure
```json
{
  "employee_name": "string",
  "issue_category": "string",
  "issue_description": "string",
  "steps_attempted": ["string"],
  "ai_confidence": 0.0,
  "recommended_actions": ["string"],
  "severity": "string",
  "urgency": "string"
}
```

## Implementation
- File: `backend/app/workflows/nodes/escalation.py`

## Boundaries
- Must NEVER dismiss a user's request for human help
- Must ALWAYS provide a complete handoff summary
- Must preserve all conversation context
- Must not make autonomous decisions about ticket priority without context
