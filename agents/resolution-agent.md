# Resolution Agent

## Role
Generates clear, step-by-step troubleshooting guidance based on retrieved knowledge articles.

## Inputs
- Knowledge articles (from Retrieval Agent)
- Issue classification (from Triage Agent)
- User conversation context

## Outputs
- `resolution_steps`: Ordered list of troubleshooting steps
- `resolution_confidence`: Float 0.0-1.0
- AI message with formatted guidance

## Strategy
- RAG (Retrieval Augmented Generation) pattern
- Uses retrieved knowledge as primary source
- LLM synthesizes steps into natural conversation
- Includes confidence score based on knowledge quality

## Confidence Scoring
- `>= 0.8`: High confidence — present resolution directly
- `0.5 - 0.8`: Medium — present with disclaimer, offer escalation
- `< 0.5`: Low — do not present, route to escalation

## Implementation
- File: `backend/app/workflows/nodes/resolution.py`

## Boundaries
- Must NEVER invent steps not found in knowledge base
- Must ALWAYS cite which knowledge article the steps come from
- Must ALWAYS include a confidence score
- Must offer escalation option if confidence < 0.8
- Must not make promises about resolution ("this should fix it" vs "try this")
