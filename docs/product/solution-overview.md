# Solution Overview — Aditi IT Assist

## What We're Building

An **agentic AI-powered IT support platform** that functions as the intelligent first
responder for all employee IT issues at Aditi Consulting.

## How It Works

### Employee Experience
1. Employee opens Aditi IT Assist chat interface
2. Describes their issue in natural language
3. AI asks clarifying questions if needed
4. AI identifies the issue category and retrieves relevant solutions
5. AI provides step-by-step troubleshooting guidance
6. If resolved → session closes with satisfaction check
7. If not resolved → seamless escalation to human agent with full context

### Agent System Architecture
The platform uses a **multi-agent workflow** powered by LangGraph:

```
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                      │
│  (Routes conversation flow based on state and context)    │
└───────────┬───────────────────────────────────┬──────────┘
            │                                   │
    ┌───────▼───────┐                  ┌───────▼────────┐
    │ Triage Agent  │                  │ Escalation     │
    │ (Classify &   │                  │ Agent          │
    │  clarify)     │                  │ (Handoff)      │
    └───────┬───────┘                  └───────┬────────┘
            │                                   │
    ┌───────▼───────┐                  ┌───────▼────────┐
    │ Knowledge     │                  │ Ticket/Email   │
    │ Retrieval     │                  │ Agent          │
    │ Agent         │                  │ (Draft)        │
    └───────┬───────┘                  └────────────────┘
            │
    ┌───────▼───────┐
    │ Resolution    │
    │ Agent         │
    │ (Guide user)  │
    └───────────────┘
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| AI Framework | LangGraph | Native state machine support, typed state, conditional edges |
| LLM Provider | LiteLLM abstraction | Swap providers without code changes |
| Vector Store | pgvector | Co-located with PostgreSQL, no extra infra |
| Dependency Mgmt | uv | Fast, reliable, lockfile support, drop-in pip replacement |
| Frontend State | Zustand | Lightweight, TypeScript-first, no boilerplate |
| UI Components | shadcn/ui + Radix | Accessible, customizable, enterprise-grade |

## Differentiation from Basic Chatbot

This is NOT a wrapper around ChatGPT. Key differences:

1. **Structured workflow** — deterministic state machine, not free-form LLM conversation
2. **Confidence scoring** — AI knows when it doesn't know
3. **Knowledge-grounded** — answers come from curated playbooks, not hallucination
4. **Escalation-aware** — graceful handoff preserves all context
5. **Audit trail** — every decision is logged for compliance
6. **Domain-specific** — optimized for IT support patterns at Aditi
7. **Extensible** — new knowledge and agents can be added without rewriting core
