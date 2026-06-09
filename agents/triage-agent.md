# Triage Agent

## Role
Understands the user's IT issue through natural language, asks clarifying questions
when needed, and produces a structured classification.

## Inputs
- User message (latest)
- Conversation history
- Previous classification attempts (if any)

## Outputs
- `issue_category`: Primary category (e.g., "email/outlook")
- `issue_subcategory`: Specific problem (e.g., "email-delivery")
- `severity`: low | medium | high | critical
- `urgency`: low | medium | high
- `needs_clarification`: Boolean
- `clarification_question`: Question to ask user (if needed)

## Categories
- `email/outlook` — Email not receiving, Outlook slow, sync issues
- `video-conferencing/zoom` — Sign-in, audio, video issues
- `device-management/intune` — Compliance, device sync
- `hardware/camera` — Camera not working, permissions
- `hardware/other` — Other hardware issues
- `software/other` — Other software issues
- `network/connectivity` — VPN, WiFi, internet
- `access/permissions` — Login, access denied
- `other` — Anything else

## Tools
- LLM classification prompt (few-shot)
- Keyword-based fallback classifier

## Implementation
- File: `backend/app/workflows/nodes/triage.py`
- Uses LiteLLM for LLM classification
- Falls back to keyword matching if LLM unavailable

## Boundaries
- Must NOT attempt resolution (that's the Resolution Agent's job)
- Must NOT search knowledge base (that's the Retrieval Agent's job)
- Maximum 3 clarification attempts before defaulting to "other"
- Must always produce a classification (even if low confidence)
