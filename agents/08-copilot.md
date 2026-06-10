# Agent 08: Human Support Copilot (Future)

> **One-liner**: Assists human IT support agents with real-time context,
> suggestions, and draft responses during live escalated sessions.

---

## Role

The Human Support Copilot runs alongside a human IT agent during escalated
support sessions. It surfaces relevant knowledge, suggests responses, and
provides context — but NEVER communicates directly with the employee.

**Status**: 🔮 Future — not yet implemented.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | Live conversation stream | Messages between human agent and employee |
| **Input** | Employee history | Past sessions, device info |
| **Input** | HandoffSummary | Context from AI escalation |
| **Output** | Suggestions panel | Relevant KB articles |
| **Output** | Draft responses | Editable response templates |
| **Output** | Context cards | Employee info, past issues |

---

## Capabilities (Planned)

### 1. Context Surfacing
- Display HandoffSummary from AI session
- Show employee's device inventory
- Show past tickets and resolutions

### 2. Knowledge Suggestions
- Real-time article suggestions based on conversation
- Highlight relevant sections within articles
- Show articles the AI already tried

### 3. Response Drafting
- Generate draft responses for human to edit
- Auto-fill technical details from KB
- Suggest follow-up questions

### 4. Resolution Tracking
- Track which steps human agent performs
- Suggest next steps based on outcomes
- Auto-generate session notes

---

## Boundaries

- ❌ Must NEVER send messages directly to the employee
- ❌ Must NEVER take actions without human confirmation
- ❌ Must NEVER override human agent decisions
- ❌ Must NEVER access systems the human agent can't access
- ✅ Advisory and informational ONLY
- ✅ Human agent has full control
- ✅ Suggestions are clearly marked as AI-generated
- ✅ Can be dismissed or ignored at any time

---

## Architecture (Planned)

```
┌─────────────────────────────────────────────────┐
│              Agent Dashboard (Frontend)           │
├────────────────────┬────────────────────────────┤
│  Conversation View │  Copilot Panel              │
│                    │  ┌──────────────────────┐   │
│  [Employee msgs]   │  │ Suggested Articles   │   │
│  [Agent replies]   │  │ • Article 1 (92%)    │   │
│                    │  │ • Article 2 (78%)    │   │
│                    │  └──────────────────────┘   │
│                    │  ┌──────────────────────┐   │
│                    │  │ Draft Response        │   │
│                    │  │ "Have you tried..."   │   │
│                    │  │ [Use] [Edit] [Skip]   │   │
│                    │  └──────────────────────┘   │
│                    │  ┌──────────────────────┐   │
│                    │  │ Context               │   │
│                    │  │ • Past issues: 3      │   │
│                    │  │ • Device: MacBook Pro │   │
│                    │  │ • AI confidence: 0.4  │   │
│                    │  └──────────────────────┘   │
└────────────────────┴────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Context Display
- Show HandoffSummary in agent dashboard
- Display conversation history from AI session
- Show employee metadata

### Phase 2: KB Suggestions
- Real-time article search as conversation progresses
- Highlight sections relevant to current discussion
- Filter out articles AI already suggested

### Phase 3: Response Drafting
- LLM-powered response suggestions
- Template-based quick replies
- Customizable response library

### Phase 4: Learning Loop
- Track which suggestions agents use
- Feed back into Knowledge Learning Agent
- Improve suggestion relevance over time

---

## Dependencies (Future)

| Dependency | Purpose |
|------------|---------|
| WebSocket connection | Real-time conversation streaming |
| Agent dashboard UI | Frontend for copilot panel |
| KB search API | Article suggestions |
| LiteLLM | Response drafting |
| Session history API | Past employee context |

---

## Implementation File (Future)

`backend/app/services/copilot_service.py`
`frontend/src/features/agent-copilot/`
