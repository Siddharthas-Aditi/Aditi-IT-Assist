# Prompts Guide — Aditi IT Assist

## Overview

This guide explains how to use AI coding assistants (GitHub Copilot, Claude, etc.)
effectively when developing Aditi IT Assist. The project is structured to be
"agent-friendly" — with documentation, prompts, and conventions that enable
productive AI-assisted development.

## Repository Structure for AI Agents

```
prompts/          → Task-specific generation prompts
agents/           → Agent role definitions and behaviors
skills/           → Reusable implementation standards
commands/         → Shell commands and expected outcomes
CLAUDE.md         → Master context file for Claude
AGENTS.md         → Multi-agent system specification
.github/copilot-instructions.md → GitHub Copilot context
```

## Using Prompts Effectively

### 1. Start with Context
Always reference the relevant prompt file when starting a new task:
- "Read `prompts/backend-agent-prompt.md` and implement the ticket service"
- "Following `skills/frontend/react-ui-system.md`, create the chat component"

### 2. Be Specific About Scope
- ✅ "Implement the `triage_node` function in `backend/app/workflows/nodes/triage.py`"
- ❌ "Build the backend"

### 3. Reference Architecture
- "According to `docs/architecture/agent-architecture.md`, the triage agent should..."
- "Following the data model in `docs/architecture/data-model.md`, create the migration"

### 4. Chain Prompts
For complex features, use a sequence:
1. "Generate the Pydantic schemas for the ticket model"
2. "Now create the SQLAlchemy model based on those schemas"
3. "Create the repository with CRUD operations"
4. "Create the service layer"
5. "Create the API route that uses the service"
6. "Write tests for the service layer"

## Prompt Files

| File | Use When |
|------|----------|
| `prompts/master-build-prompt.md` | Full project context |
| `prompts/backend-agent-prompt.md` | Backend implementation |
| `prompts/frontend-agent-prompt.md` | Frontend implementation |
| `prompts/architecture-agent-prompt.md` | Design decisions |
| `prompts/qa-agent-prompt.md` | Testing and quality |
| `prompts/docker-agent-prompt.md` | Infrastructure |
| `prompts/docs-agent-prompt.md` | Documentation |

## Skill Files

Skill files define HOW to implement things correctly in this project:

| File | Teaches |
|------|---------|
| `skills/backend/fastapi-standards.md` | FastAPI patterns |
| `skills/backend/langgraph-patterns.md` | LangGraph workflow patterns |
| `skills/frontend/react-ui-system.md` | Component architecture |
| `skills/frontend/aditi-theme.md` | Design system |
| `skills/devops/docker-standards.md` | Container best practices |

## Example Workflow

### Adding a New Knowledge Category

1. Create knowledge YAML:
   "Following the format in `backend/app/knowledge_base/seed/outlook.yml`,
   create a new playbook for VPN connectivity issues"

2. Update models if needed:
   "Add 'vpn/connectivity' to the issue category enum in schemas"

3. Seed the data:
   "Update `scripts/seed_data.py` to load the new VPN knowledge"

4. Test retrieval:
   "Write a test that searches for VPN issues and verifies the new
   articles are returned"

## Tips for AI Agents

1. **Read CLAUDE.md first** — it has the master context
2. **Check existing patterns** — look at similar files before creating new ones
3. **Run tests after changes** — `make test-backend` or `make test-frontend`
4. **Keep consistency** — match the style of existing code
5. **Update docs** — if you change architecture, update the relevant .md file
