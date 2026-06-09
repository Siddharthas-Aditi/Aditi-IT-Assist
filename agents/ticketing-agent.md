# Ticketing Agent

## Role
Creates structured support ticket or email drafts from escalation context.

## Implementation
- File: `backend/app/workflows/nodes/ticketing.py`

## Boundaries
- Draft only — does not send without user approval
- Must preserve all conversation context in ticket
- Must follow company ticket format
