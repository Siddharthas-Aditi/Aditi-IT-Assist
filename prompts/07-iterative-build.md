# Iterative Build Prompts

> Copy-paste ready prompts for building Aditi IT Assist features incrementally.
> Use these as a starting point, then customize for your specific task.

---

## Phase 1: Knowledge Base

### 1.1 Create Knowledge Seed Data
```
Following the format in skills/product/knowledge-base.md, create 5 knowledge
base articles for the "email/outlook" category:
- Outlook not receiving emails
- Outlook keeps crashing
- Outlook calendar sync issues
- Outlook search not working
- Shared mailbox access problems

Put them in backend/app/knowledge_base/seed/outlook.yml
```

### 1.2 Knowledge Embedding Service
```
Create backend/app/services/embedding_service.py that:
- Takes article text and generates embeddings via LiteLLM
- Stores embeddings in the knowledge_articles table (pgvector)
- Has a batch_embed method for seeding
- Follows skills/backend/llm-integration.md patterns
```

### 1.3 Knowledge Search
```
Create backend/app/services/knowledge_service.py with:
- vector_search(query, category, top_k=5) -> list[KnowledgeResult]
- keyword_search(query, category) -> list[KnowledgeResult]
- combined_search(query, category) -> list[KnowledgeResult]
Following the strategy in agents/03-retrieval.md
```

---

## Phase 2: Workflow Nodes

### 2.1 Triage Node
```
Implement backend/app/workflows/nodes/triage.py following agents/02-triage.md:
- LLM classification with the system prompt from the spec
- Keyword fallback classifier
- Clarification logic (max 3 rounds)
- Returns issue_category, severity, urgency, needs_clarification
Include unit tests in backend/tests/unit/test_workflows/test_triage.py
```

### 2.2 Retrieval Node
```
Implement backend/app/workflows/nodes/retrieval.py following agents/03-retrieval.md:
- Calls KnowledgeService.combined_search
- Sets knowledge_results and knowledge_confidence
- Handles empty results gracefully
Include unit tests.
```

### 2.3 Resolution Node
```
Implement backend/app/workflows/nodes/resolution.py following agents/04-resolution.md:
- RAG generation using retrieved knowledge
- Confidence calibration formula (50% retrieval, 20% coverage, 30% match)
- Hallucination check (verify steps grounded in KB)
- Message formatting (high vs medium confidence templates)
Include unit tests with mocked LLM responses.
```

### 2.4 Escalation + Ticketing
```
Implement backend/app/workflows/nodes/escalation.py and ticketing.py
following agents/05-escalation.md and agents/06-ticketing.md:
- Escalation: deterministic trigger detection, handoff summary builder
- Ticketing: LLM summarization with template fallback, ticket draft format
Include unit tests.
```

### 2.5 Wire the Graph
```
Update backend/app/workflows/graph.py to:
- Register all 5 nodes
- Add conditional edges per the decision table in agents/01-orchestrator.md
- Set entry point to triage
- Add error handling (global catch → escalation)
- Include turn_count increment
Write an integration test that runs a full conversation through the graph.
```

---

## Phase 3: Chat API

### 3.1 Chat Endpoint
```
Create backend/app/api/v1/chat.py with:
- POST /chat/message → processes user message through workflow
- GET /chat/sessions → list user's sessions
- GET /chat/sessions/{id} → get session with messages
Use the ChatService (create if missing) which invokes the workflow graph.
```

### 3.2 Session Persistence
```
Create backend/app/services/session_service.py that:
- Creates sessions in PostgreSQL
- Stores messages as they flow through workflow
- Tracks session status (active, resolved, escalated)
- Loads previous state when continuing a session
```

---

## Phase 4: Frontend Chat

### 4.1 Chat Feature Module
```
Create frontend/src/features/chat/ with:
- ChatContainer.tsx — loads session, manages state
- ChatMessageList.tsx — scrollable message list
- ChatMessage.tsx — individual message bubble (user vs AI styling)
- ChatInput.tsx — text input with send button
- use-chat.ts — hook using React Query for API calls
Following skills/frontend/component-architecture.md
```

### 4.2 Connect to API
```
Add to frontend/src/lib/api.ts:
- chatApi.sendMessage(message, sessionId?) → ChatResponse
- chatApi.getSessions() → SessionList
- chatApi.getSession(id) → SessionDetail
Wire into the chat feature using React Query.
```

---

## Phase 5: Admin & Observability

### 5.1 Admin Knowledge Management
```
Create an admin page for managing knowledge base articles:
- List all articles with category filter
- Create/edit articles
- Trigger re-embedding
- View gap reports from Learning Agent
```

### 5.2 Session Analytics
```
Create an admin dashboard showing:
- Resolution rate (% of sessions resolved without escalation)
- Average confidence score
- Escalation reasons breakdown
- Most common issue categories
- Knowledge gaps (categories with low confidence)
```

---

## How to Use These Prompts

1. **Start with Phase 1** — You need knowledge data before the workflow works
2. **Phase 2 is the core** — Implement nodes one at a time, test each
3. **Phase 3 connects it** — API makes the workflow accessible
4. **Phase 4 is the face** — Users interact through the chat UI
5. **Phase 5 is operational** — Admin tools for monitoring and improvement

Each prompt is self-contained — you can give it to an AI coding assistant
and it should produce working code following project conventions.
