# Multi-Turn Chat Design — Conversational Triage Architecture

> This document describes the upgraded chat architecture that makes the
> Aditi IT Assist agent behave like a real L1 IT support analyst.

---

## Problem Statement

The previous chat implementation had a single-pass architecture:
1. User sends message → Triage classifies → Retrieval searches → Resolution dumps answer

This caused **answer dumping** for vague queries. When a user said "I have an
Outlook issue," the system would retrieve all Outlook KB articles and dump every
possible fix at once.

## Solution: Multi-Turn Diagnostic Conversations

The upgraded architecture introduces a **diagnostic conversation layer** between
user input and answer generation. It behaves like a human IT support analyst:

1. **Understand** — classify the broad category
2. **Clarify** — ask the minimum questions needed to understand the specific issue
3. **Retrieve** — search knowledge using the specific, focused context
4. **Resolve** — provide 2-3 targeted steps (not full KB dumps)
5. **Confirm** — check if the steps worked before providing more

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONVERSATION TURN                              │
│                                                                   │
│  User Message                                                     │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────────┐                                            │
│  │  Diagnostic Engine │◄── DiagnosticContext (persisted)         │
│  │  - Slot Extraction │                                          │
│  │  - Context Update  │                                          │
│  └────────┬───────────┘                                          │
│           │                                                       │
│           ▼                                                       │
│  ┌──────────────────┐                                            │
│  │ Clarify-or-Answer │◄── Playbook (per category)               │
│  │    Policy          │                                          │
│  └────────┬───────────┘                                          │
│           │                                                       │
│      ┌────┴────┐                                                 │
│      │         │                                                  │
│  CLARIFY    ANSWER                                               │
│      │         │                                                  │
│      ▼         ▼                                                  │
│  Ask Q +    Targeted                                             │
│  Quick     Retrieval →                                            │
│  Replies   Resolution                                             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. DiagnosticContext (`services/agents/diagnostic_state.py`)

Structured state accumulated across conversation turns:

| Field | Purpose |
|-------|---------|
| `issue_category` | Broad category (email/outlook, zoom, etc.) |
| `symptom` | Specific symptom (not-receiving-emails, no-audio) |
| `exact_problem_statement` | User's own description |
| `error_message` | Quoted error text |
| `device_type` | Laptop, desktop, mobile |
| `platform_os` | Windows, Mac, iOS |
| `steps_already_tried` | What the user already attempted |
| `phase` | Current diagnostic phase |
| `clarification_count` | How many follow-ups asked |

### 2. Issue Playbooks (`services/agents/playbooks.py`)

Per-category troubleshooting guides that define:
- **Required slots** — what must be filled before answering
- **Questions** — in priority order, with quick-reply options
- **Retrieval hints** — category filters, boost terms
- **Escalation triggers** — conditions for human handoff

### 3. Diagnostic Engine (`services/agents/diagnostic_engine.py`)

The decision-making brain:
- **Slot extraction** — extracts structured info from free-text messages
- **Clarify-or-answer policy** — decides if we have enough context
- **Phase transitions** — manages conversation flow

### 4. Upgraded Triage Node (`workflows/nodes/triage.py`)

Now multi-turn aware:
- First turn: classify + check specificity
- Follow-up turns: extract slots + re-evaluate
- Returns quick-reply options for frontend chips

### 5. Targeted Retrieval (`workflows/nodes/retrieval.py`)

Context-aware search:
- Builds focused queries from diagnostic context
- Uses symptom + category (not just raw message)
- Limits results (top-3 instead of top-5)
- Adjusts confidence based on query specificity

### 6. Progressive Resolution (`workflows/nodes/resolution.py`)

Concise, step-by-step responses:
- 2-3 steps per response (not full KB dump)
- Asks "did this resolve your issue?" after steps
- Uses diagnostic context for focused generation

---

## Conversation Phases

| Phase | Behavior |
|-------|----------|
| `INTAKE` | First message received, category identified |
| `CLARIFYING` | Asking follow-up questions |
| `DIAGNOSING` | Enough context, searching knowledge base |
| `RESOLVING` | Providing troubleshooting steps |
| `CONFIRMING` | Checking if resolution worked |
| `ESCALATING` | Handing off to human agent |

---

## Clarify-or-Answer Decision Logic

```python
if user.requested_live_agent:
    → proceed to escalation
elif clarification_count >= max (3):
    → proceed with best-effort answer
elif playbook.has_enough_context(filled_slots):
    → proceed to retrieval + resolution
else:
    → ask next question from playbook
```

---

## Example: Before vs After

### Before (Bad)
```
User: "I have an Outlook issue"
Bot: [dumps 5 KB articles worth of Outlook troubleshooting for email delivery,
      sync, crash, calendar, and search issues all at once]
```

### After (Good)
```
User: "I have an Outlook issue"
Bot: "I can see this is an Outlook/email issue. Could you tell me what's
      specifically happening?"
      [Quick replies: Not receiving emails | Can't send | Outlook slow |
       Calendar sync | Sign-in issue | Something else]

User: "Not receiving emails"
Bot: "Got it — let me help you with email delivery. Here's what to try:
      1. Check your Junk/Spam folder for misrouted emails
      2. Open Outlook → File → Account Settings → verify your account status
      3. Try Send/Receive All Folders (Ctrl+Shift+F9)

      Let me know if that resolves the issue!"
```

---

## Frontend Changes

- **QuickReplies** component — clickable chips for disambiguation
- **ResolutionConfirm** component — "Did this resolve your issue?" buttons
- Progressive conversation flow instead of one-shot dumps
- Clearer visual distinction between questions and answers

---

## Escalation Triggers

The system escalates to a human agent when:
1. User explicitly requests live support
2. Resolution confidence remains low after 2+ attempts
3. Max clarification rounds exceeded without enough context
4. Knowledge base has no relevant articles
5. Issue appears high-impact or security-related

---

## Testing Strategy

Tests validate the conversation architecture works correctly:
- Vague queries trigger follow-up (not dumps)
- Slot extraction works for all categories
- Playbooks return correct questions
- Context persists across turns
- Escalation triggers at correct thresholds
- Specific queries skip clarification
