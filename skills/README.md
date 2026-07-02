# skills/ — Implementation Standards

This directory defines HOW to implement things correctly in Aditi IT Assist.
Each skill file is a reference for AI coding agents and human developers.

> Two flavors live here:
> - `backend/ frontend/ devops/ product/` — **implementation standards** by technology
>   (patterns to copy).
> - `playbooks/` — **task-oriented playbooks** for recurring changes (how to safely do a
>   specific kind of work end-to-end). Start there when the work matches a named task
>   (API change, migration, escalation, retrieval, etc.). See `playbooks/README.md`.

## Directory Structure

```
skills/
├── README.md                      ← This file
├── playbooks/                     ← Task-oriented dev playbooks (see playbooks/README.md)
├── backend/
│   ├── fastapi-patterns.md        ← API route, service, DI patterns
│   ├── langgraph-workflows.md     ← LangGraph node and state patterns
│   ├── database-patterns.md       ← SQLAlchemy, migrations, queries
│   └── llm-integration.md         ← LiteLLM abstraction patterns
├── frontend/
│   ├── component-architecture.md  ← React component patterns
│   ├── state-management.md        ← Zustand + React Query patterns
│   └── design-system.md           ← Aditi theme, Tailwind, shadcn
├── devops/
│   ├── docker-patterns.md         ← Container best practices
│   └── testing-patterns.md        ← Testing strategies & tools
└── product/
    ├── knowledge-base.md          ← KB authoring & structure
    └── support-workflows.md       ← IT support domain knowledge
```

## How to Use Skills

1. **Before implementing**: Read the relevant skill file
2. **During code review**: Check implementation matches skill patterns
3. **When adding patterns**: Update the relevant skill file
4. **When onboarding**: Use skills as a learning reference

## Skill File Structure

Each skill file follows this format:
- **Pattern name** with brief description
- **When to use** — triggers for this pattern
- **Code example** — copy-paste-ready implementation
- **Anti-patterns** — what NOT to do
- **Related files** — where this pattern is used in the codebase
