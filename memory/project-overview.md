# Project Overview — Aditi IT Assist

## Mission

Give Aditi Consulting employees fast, trustworthy resolution of internal IT issues
through an AI-first support experience, and give IT specialists a clean, context-rich
handoff when the AI can't resolve an issue — all under enterprise-grade governance
(RBAC, audit, human-in-the-loop, no fabricated advice).

## What the product does

Aditi IT Assist is an internal IT service platform. An employee describes an IT
problem in chat. A multi-agent LangGraph workflow triages the issue, classifies its
subtype, retrieves **only relevant, published** knowledge, guides grounded
troubleshooting (tracking tried steps and advancing on failure), and escalates to a
live IT specialist when grounded help is exhausted or the user asks for a human.
Escalation creates an immutable transcript snapshot + structured context so the
specialist never makes the employee repeat themselves. Specialists work a queue,
claim tickets atomically, chat live in the same window, and can (behind flags)
take governed, human-approved actions via MCP-backed tools. Leads/admins manage
users, knowledge, analytics, and audit logs.

## Users (personas)

- **Employee** — submits IT issues via chat; sees only their own tickets/chats;
  never sees internal notes, drafts, or debug traces.
- **IT Agent (`it_agent`)** — works the specialist queue, live chat, tickets;
  sees debug/handoff context; read-level integration tools.
- **IT Lead (`it_lead`)** — everything an agent has, plus assignment, approvals for
  write actions, background-task control, analytics.
- **IT Admin (`it_admin`)** — user/role management, KB governance, full admin console.
- **Security Auditor (`security_auditor`)** — read access to audit logs; compliance.

## Core value pillars (the quality bar)

1. **Grounded AI** — the chat agent never fabricates IT advice; retrieval is
   published-only and subtype-scoped; confidence can't be high without grounding.
2. **Reliable handoff** — escalation always captures a minimally-useful problem
   statement first, persists immutable context, and hands off in-window.
3. **Ticket integrity** — tickets persist only on explicit confirmation; idempotent
   per session; full lifecycle + SLA.
4. **Governance** — RBAC everywhere, every mutation audited, writes are
   human-approved, KB changes are review-gated, no uncontrolled self-learning.
5. **Enterprise engineering** — typed contracts, versioned configs, evaluation
   datasets, real integrations (no dummy data in product flows).

## Tech stack (summary)

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, LangGraph, LiteLLM,
  PostgreSQL 16 + pgvector, Redis 7, Alembic, `uv`, Ruff, pytest.
- **Frontend**: React 18, TypeScript (strict), Vite, Tailwind, shadcn/ui + Radix,
  React Query, Zustand, Vitest + RTL, Playwright (e2e), ESLint.
- **Infra**: Docker Compose (postgres, redis, backend, frontend), GitHub Actions CI.

## Where to go next

- Architecture & where code lives → `memory/architecture-map.md`
- Entities & invariants → `memory/domain-model.md`
- Find a feature's files → `memory/feature-map.md`
- What's shipped vs. behind flags → `memory/current-rollout-state.md`
- Operating rules for agents → root `CLAUDE.md`, `AGENTS.md`
- How to actually do work → `docs/development/engineering-workflow.md`
