# Prompts Guide — AI-Assisted Development

> How to work effectively with AI coding assistants (GitHub Copilot, Claude, etc.)
> when developing Aditi IT Assist.

---

## 1. Repository Structure for AI Agents

The project is structured to be **"agent-friendly"** — with documentation,
prompts, and conventions that enable productive AI-assisted development.

```
CLAUDE.md             → Master rules (read first)
AGENTS.md             → Multi-agent system spec
agents/               → Individual agent role definitions
  ├── 01-orchestrator.md
  ├── 02-triage.md
  ├── 03-retrieval.md
  ├── 04-resolution.md
  ├── 05-escalation.md
  ├── 06-ticketing.md
  ├── 07-learning.md
  └── 08-copilot.md
skills/               → Implementation patterns (HOW to code)
  ├── backend/
  ├── frontend/
  ├── devops/
  └── product/
prompts/              → Task-specific prompts (copy-paste)
  ├── 01-master-build.md
  ├── 02-backend.md
  ├── 03-frontend.md
  ├── 04-workflow.md
  ├── 05-testing.md
  ├── 06-infrastructure.md
  └── 07-iterative-build.md
.github/copilot-instructions.md → GitHub Copilot context
```

---

## 2. How to Start a Task

### Step 1: Identify the Right Prompt

| Task Type | Start With |
|-----------|-----------|
| New backend feature | `prompts/02-backend.md` |
| New frontend feature | `prompts/03-frontend.md` |
| Workflow changes | `prompts/04-workflow.md` |
| Writing tests | `prompts/05-testing.md` |
| Docker/infra changes | `prompts/06-infrastructure.md` |
| Full feature (multi-layer) | `prompts/01-master-build.md` |
| Iterative building | `prompts/07-iterative-build.md` |

### Step 2: Provide Context

Always reference the relevant documentation:

```
"Read CLAUDE.md and agents/02-triage.md, then implement the triage_node
function in backend/app/workflows/nodes/triage.py following the spec."
```

### Step 3: Be Specific About Scope

```
✅ "Implement the keyword_fallback_classify function that maps keywords
   to categories per the table in agents/02-triage.md"

❌ "Build the triage system"  (too vague)
```

---

## 3. Prompting Patterns

### Pattern: Incremental Implementation

Break large features into small, testable steps:

```
Step 1: "Create the Pydantic schemas for ChatMessage (request + response)"
Step 2: "Create the SQLAlchemy model for chat_messages table"
Step 3: "Create the MessageRepository with create/list methods"
Step 4: "Create the ChatService that uses the repository"
Step 5: "Create the POST /chat/message route using the service"
Step 6: "Write unit tests for ChatService"
```

Each step produces working, testable code before moving to the next.

### Pattern: Reference-Based Implementation

Point AI to an existing pattern to replicate:

```
"Following the same pattern as backend/app/services/chat_service.py,
create a KnowledgeService in backend/app/services/knowledge_service.py
with methods: search(query, category) and get_by_id(article_id)"
```

### Pattern: Spec-Driven Implementation

Let the agent spec drive the implementation:

```
"Read agents/04-resolution.md completely. Implement the resolution_node
function exactly as described in the Algorithm section. Use the confidence
calibration formula from the Confidence Calibration section. Handle all
failure modes listed in the Failure Modes table."
```

### Pattern: Fix and Validate

```
"Run 'make test-backend' and fix any failures. Show me what you changed."
```

### Pattern: Explain Before Implementing

```
"Before writing code, explain how you would implement the vector search
in the retrieval node. What SQL query would you use? How do you handle
the case where pgvector returns no results?"
```

---

## 4. Writing Good Agent Prompts

### For the Triage Agent (LLM System Prompt)

The system prompt must:
- Define the exact output format (JSON schema)
- List all valid categories
- Provide classification examples
- Explicitly state boundaries ("Do NOT attempt resolution")
- Handle edge cases ("If too vague, ask one clarifying question")

### For the Resolution Agent (LLM System Prompt)

The system prompt must:
- Emphasize grounding in knowledge base
- Forbid hallucination ("Only use information from the articles below")
- Specify tone ("Helpful but not overpromising")
- Define step format
- Include confidence context

### For the Ticketing Agent (LLM System Prompt)

The system prompt must:
- Request concise summarization
- Specify professional tone
- Define output structure
- Limit response length

---

## 5. Common Mistakes to Avoid

| Mistake | Why It Fails | Better Approach |
|---------|-------------|-----------------|
| "Build the entire backend" | Too much scope, inconsistent output | Break into 5-6 focused tasks |
| No reference to docs | AI invents its own patterns | Always cite CLAUDE.md or skills/ |
| Asking for "best practice" | Generic advice, not project-specific | Reference specific skill file |
| Skipping validation | Broken code accumulates | "Run tests after each change" |
| Ignoring agent boundaries | Agents do things they shouldn't | "Follow the Boundaries section in agents/X.md" |

---

## 6. Iterative Development Workflow

```
┌─────────────────────────┐
│ 1. Pick a prompt file   │
│    (prompts/0X-*.md)    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 2. Give AI the context  │
│    + specific task       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 3. Review generated code│
│    Check against skills/ │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 4. Run tests & lint     │
│    make test && make lint│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 5. Fix any issues       │
│    "Fix the test failure"│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 6. Commit & move to     │
│    next task             │
└─────────────────────────┘
```

---

## 7. Tips for AI Agents Working on This Repo

1. **Read CLAUDE.md first** — It has the master context and rules
2. **Check existing patterns** — Look at similar files before creating new ones
3. **Run tests after changes** — `make test-backend` or `make test-frontend`
4. **Keep consistency** — Match the style of existing code
5. **Update docs** — If you change architecture, update the relevant `.md` file
6. **Small commits** — One logical change per commit
7. **Don't skip error handling** — Every I/O operation needs try/except
8. **Use the type system** — TypedDict for state, Pydantic for API, TypeScript for frontend
9. **Log decisions** — structlog with context, audit_trail in workflow
10. **When in doubt, escalate** — Ask the human developer rather than guessing

---

## 8. Example Sessions

### Example: Adding a New Knowledge Category

```
Human: "Add VPN troubleshooting to the knowledge base"

AI reads: skills/product/knowledge-base.md for format

Steps:
1. Create backend/app/knowledge_base/seed/vpn.yml with 3-5 articles
2. Add "network/vpn" to category enum in schemas
3. Update triage keyword map to detect VPN issues
4. Write a test that verifies VPN articles are found via search
5. Update agents/02-triage.md categories table
```

### Example: Fixing Low Confidence Scores

```
Human: "The resolution agent is giving low confidence for email issues"

AI reads: agents/04-resolution.md (confidence formula section)

Investigation:
1. Check if knowledge articles exist for email category
2. Verify vector embeddings are populated
3. Check if retrieval is returning relevant articles
4. Review confidence formula weights
5. Run tests with known-good inputs to isolate the problem
```

---

## 9. Maintaining Documentation

When you add or change features:

| Change | Update |
|--------|--------|
| New agent/node | `agents/0X-{name}.md` + `AGENTS.md` registry table |
| New API endpoint | Auto-generated from Pydantic (just keep schemas clean) |
| New skill/pattern | `skills/{domain}/{pattern}.md` |
| New prompt template | `prompts/0X-{name}.md` |
| Architecture change | `docs/architecture/` |
| New config option | `.env.example` + `docs/development/setup.md` |
