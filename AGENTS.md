# AGENTS.md — Multi-Agent System Design

> **Aditi IT Assist** uses a LangGraph-based multi-agent workflow to resolve
> employee IT issues. This document is the authoritative reference for the
> agent system architecture.

---

## System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH STATE MACHINE                         │
│                                                                        │
│  ┌──────────┐    ┌────────┐    ┌───────────┐    ┌────────────┐       │
│  │Orchestrator│──→│ Triage │──→│ Knowledge │──→│ Resolution │       │
│  └──────────┘    └────────┘    │ Retrieval │    └──────┬─────┘       │
│       ↑              ↑         └───────────┘           │              │
│       │              │                                  │              │
│       │         clarification                  confidence < 0.8       │
│       │              │                                  │              │
│       │              ▼                                  ▼              │
│       │          [END:user]                    ┌────────────┐         │
│       │                                        │ Escalation │         │
│       │                                        └──────┬─────┘         │
│       │                                               │               │
│       │                                               ▼               │
│       │                                        ┌────────────┐         │
│       └────────────────────────────────────────│  Ticketing │         │
│                                                └────────────┘         │
│                                                                        │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │  ASYNC AGENTS (not in real-time flow)                          │    │
│  │  • Knowledge Learning Agent — analyzes gaps                    │    │
│  │  • Human Support Copilot — assists live agents (future)        │    │
│  └───────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Registry

| # | Agent | Node File | Real-Time | LLM Required |
|---|-------|-----------|-----------|--------------|
| 1 | Orchestrator | `graph.py` (conditional edges) | ✅ | ❌ |
| 2 | Intake & Triage | `nodes/triage.py` | ✅ | ✅ |
| 3 | Knowledge Retrieval | `nodes/retrieval.py` | ✅ | ❌ |
| 4 | Resolution | `nodes/resolution.py` | ✅ | ✅ |
| 5 | Escalation | `nodes/escalation.py` | ✅ | ❌ |
| 6 | Ticketing | `nodes/ticketing.py` | ✅ | ✅ |
| 7 | Knowledge Learning | (async task) | ❌ | ✅ |
| 8 | Human Support Copilot | (future) | ❌ | ✅ |

---

## 1. Orchestrator Agent

**Purpose**: Routes conversation flow between agents using deterministic logic.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | `WorkflowState` | Full current state |
| **Outputs** | `str` | Next node name to invoke |
| **Dependencies** | None | Pure function on state |

### Decision Table

| Condition | Routes To | Rationale |
|-----------|-----------|-----------|
| `turn_count == 0` | `triage` | First message always triaged |
| `needs_clarification == True` | `END` | Return question to user |
| `issue_category is None` | `triage` | Not yet classified |
| `knowledge_results is empty` | `retrieval` | Need knowledge |
| `resolution_confidence >= 0.8` | `END` | High-confidence answer |
| `resolution_confidence > 0 && < 0.8` | `escalation` | Low confidence |
| `should_escalate == True` | `ticketing` | Escalation approved |
| `turn_count >= 10` | `escalation` | Safety: max turns |
| *(fallback)* | `escalation` | Unknown state → escalate |

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Infinite loop | `turn_count >= 10` | Force escalation |
| Invalid state | Missing required fields | Log + escalate |
| Node exception | Unhandled error in any node | Catch → escalation with error context |

### Implementation Notes
- Implemented as **conditional edges** in LangGraph, NOT as a separate node
- Uses pure functions — no LLM calls, no I/O
- Every routing decision is logged to `audit_trail`
- Must be 100% deterministic for reproducibility

---

## 2. Intake & Triage Agent

**Purpose**: Understands the user's IT issue, asks clarifying questions, classifies the problem.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | `messages`, `conversation history` | User's description |
| **Outputs** | `issue_category`, `severity`, `urgency`, `needs_clarification` | Classification |
| **Dependencies** | LiteLLM (classification), keyword fallback | |

### Output Schema

```python
{
    "issue_category": "email/outlook",       # Primary category
    "issue_subcategory": "email-delivery",   # Specific problem
    "severity": "medium",                     # low | medium | high | critical
    "urgency": "high",                        # low | medium | high
    "impact": "individual",                   # individual | team | department | org
    "needs_clarification": False,             # Whether to ask follow-up
    "clarification_question": None,           # Question text (if needed)
}
```

### Categories

| Category | Subcategories | Example Issues |
|----------|--------------|----------------|
| `email/outlook` | delivery, sync, crash, config | "Not receiving emails" |
| `video-conferencing/zoom` | audio, video, signin, connection | "Can't join meetings" |
| `device-management/intune` | compliance, sync, enrollment | "Device not compliant" |
| `hardware/camera` | permissions, driver, quality | "Camera black screen" |
| `hardware/other` | keyboard, monitor, docking | "Second monitor not detected" |
| `software/other` | install, crash, license, update | "App keeps crashing" |
| `network/connectivity` | vpn, wifi, ethernet, dns | "VPN won't connect" |
| `access/permissions` | login, mfa, password, rbac | "Access denied" |
| `other` | — | Uncategorizable issues |

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM timeout | 10s timeout on classification call | Use keyword fallback classifier |
| LLM returns invalid JSON | JSON parse error | Retry once, then keyword fallback |
| User message too vague | Confidence < 0.3 on classification | Set `needs_clarification = True` |
| Max clarifications exceeded | `clarification_count >= 3` | Classify as "other", proceed |
| LLM unavailable | ConnectionError | Keyword classifier + log alert |

### Boundaries
- ❌ Must NOT attempt resolution
- ❌ Must NOT search knowledge base
- ❌ Must NOT access external systems
- ✅ Maximum 3 clarification rounds
- ✅ Must always produce a classification (even if low confidence)

---

## 3. Knowledge Retrieval Agent

**Purpose**: Searches the knowledge base for relevant troubleshooting playbooks.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | `issue_category`, `issue_subcategory`, user description | Search context |
| **Outputs** | `knowledge_results[]`, `knowledge_confidence` | Ranked articles |
| **Dependencies** | pgvector (similarity search), PostgreSQL (keyword fallback) | |

### Search Strategy

```
1. Vector similarity search (pgvector)
   - Embed user description + category
   - Top-5 results with cosine similarity > 0.7

2. Keyword fallback (if vector results < 3)
   - Full-text search on title + content
   - Category filter match

3. Score combination
   - Weighted: 0.7 * vector_score + 0.3 * keyword_score
   - Filter out results below 0.5 combined score
```

### Output Schema

```python
{
    "knowledge_results": [
        {
            "article_id": "uuid",
            "title": "Outlook not receiving emails",
            "content": "Step-by-step troubleshooting...",
            "category": "email/outlook",
            "relevance_score": 0.92,
            "source": "vector_search",
        }
    ],
    "knowledge_confidence": 0.87,  # Best match score
}
```

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| No results found | `len(results) == 0` | Set confidence to 0.0, route to escalation |
| pgvector unavailable | ConnectionError to DB | Keyword-only search |
| All results low relevance | Best score < 0.5 | Set confidence to score, let Resolution decide |
| Embedding model failure | Exception in embed call | Use category-only filter search |

### Boundaries
- ❌ Must NOT synthesize or advise
- ❌ Must NOT modify knowledge base
- ✅ Returns information only
- ✅ Must return confidence score with results
- ✅ Results must be ordered by relevance

---

## 4. Resolution Agent

**Purpose**: Generates step-by-step troubleshooting guidance from retrieved knowledge.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | `knowledge_results`, `issue_*`, `messages` | Full context |
| **Outputs** | `resolution_steps[]`, `resolution_confidence`, AI message | Guidance |
| **Dependencies** | LiteLLM (generation), knowledge articles | |

### Output Schema

```python
{
    "resolution_steps": [
        {"step_number": 1, "instruction": "Open Outlook settings", "details": "Click File > Options"},
        {"step_number": 2, "instruction": "Check account sync", "details": "..."},
    ],
    "resolution_confidence": 0.85,
    # Also appends a formatted message to `messages` for the user
}
```

### Confidence Calibration

| Score Range | Meaning | Behavior |
|-------------|---------|----------|
| 0.8 – 1.0 | High — strong KB match, clear steps | Present resolution directly |
| 0.5 – 0.8 | Medium — partial match or generic | Present with disclaimer + escalation offer |
| 0.0 – 0.5 | Low — weak/no KB match | Skip resolution, route to escalation |

**Confidence is derived from**:
- `knowledge_confidence` (retrieval quality): 50% weight
- Number of relevant articles: 20% weight
- Category specificity match: 30% weight

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM timeout | 15s timeout | Return "unable to generate" + escalate |
| LLM hallucination risk | Steps not found in KB text | Compare generated steps against KB content |
| Empty knowledge | `knowledge_results == []` | Skip generation, confidence = 0.0 |
| LLM refusal | "I cannot help" response | Set confidence to 0.0, escalate |

### Boundaries
- ❌ Must NEVER invent steps not found in knowledge base
- ❌ Must NEVER make promises ("this will fix it")
- ✅ Must ALWAYS cite which knowledge article steps come from
- ✅ Must ALWAYS include confidence score
- ✅ Must offer escalation if confidence < 0.8
- ✅ Use language like "try this" not "do this"

---

## 5. Escalation Agent

**Purpose**: Determines escalation path and prepares structured handoff summary.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | Full state (history, classification, attempts) | Everything |
| **Outputs** | `should_escalate`, `handoff_summary`, `escalation_reason` | Decision |
| **Dependencies** | None (deterministic) | |

### Escalation Triggers

| Trigger | Priority |
|---------|----------|
| User explicitly requests human help | P1 — Immediate |
| Resolution confidence < 0.5 | P2 — High |
| Resolution confidence < 0.8 after 2+ attempts | P2 — High |
| Max turns (10) exceeded | P3 — Normal |
| Agent error / exception | P1 — Immediate |
| Critical severity + low confidence | P1 — Immediate |

### Handoff Summary Schema

```python
HandoffSummary = {
    "employee_name": str,
    "issue_category": str,
    "issue_description": str,         # Natural language summary
    "steps_attempted": list[str],     # What was already tried
    "ai_confidence": float,           # How confident the AI was
    "recommended_actions": list[str], # Suggestions for human agent
    "severity": str,
    "urgency": str,
    "conversation_turns": int,
    "escalation_reason": str,
}
```

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Incomplete state | Missing classification | Generate partial summary with available info |
| No conversation context | Empty messages | Create minimal summary from metadata |

### Boundaries
- ❌ Must NEVER dismiss user's request for human help
- ❌ Must NEVER downgrade severity
- ✅ Must ALWAYS provide complete handoff summary
- ✅ Must preserve ALL conversation context
- ✅ Must log escalation reason to audit trail

---

## 6. Ticketing Agent

**Purpose**: Creates structured support tickets or email drafts from escalation context.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | `handoff_summary`, `messages`, user info | Context |
| **Outputs** | `ticket_draft` (TicketDraft) | Formatted draft |
| **Dependencies** | LiteLLM (summarization), templates | |

### Ticket Format

```python
TicketDraft = {
    "title": str,                    # "[Category] Brief description"
    "description": str,              # Full context with formatting
    "category": str,                 # Mapped to ticketing system categories
    "priority": str,                 # P1/P2/P3/P4
    "steps_attempted": list[str],    # What was tried
    "conversation_summary": str,     # AI-generated summary
}
```

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM unavailable | Timeout/connection error | Template-based ticket (no AI summary) |
| Missing context | Handoff summary incomplete | Generate with available fields + [INCOMPLETE] flag |

### Boundaries
- ❌ Must NOT send tickets without user approval (draft only)
- ❌ Must NOT modify priority without context
- ✅ Must preserve all conversation context
- ✅ Must follow company ticket format template
- ✅ Must include AI confidence assessment in ticket

---

## 7. Knowledge Learning Agent (Async)

**Purpose**: Identifies gaps in the knowledge base and suggests new articles.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | Resolved sessions, unresolved sessions, feedback | Historical data |
| **Outputs** | Gap reports, suggested articles | Improvements |
| **Dependencies** | Database (session history), LiteLLM | |
| **Trigger** | Scheduled (daily) or on low-confidence threshold | |

### Process

```
1. Analyze sessions with confidence < 0.5 in last 24h
2. Cluster unresolved issues by category
3. Identify categories with high escalation rates
4. Generate suggested KB article outlines
5. Submit to admin review queue
```

### Boundaries
- ❌ NOT in real-time conversation flow
- ❌ Must NOT auto-publish articles
- ✅ Runs asynchronously (background worker)
- ✅ All suggestions require human review
- ✅ Tracks resolution success rates by category

---

## 8. Human Support Copilot Agent (Future)

**Purpose**: Assists human IT agents with context and suggestions during live support.

### Interface

| Field | Type | Description |
|-------|------|-------------|
| **Inputs** | Live conversation, employee history | Real-time |
| **Outputs** | Suggestions, relevant KB articles, draft responses | Advisory |
| **Dependencies** | Knowledge base, conversation context | |

### Boundaries
- ❌ Advisory ONLY — human makes all decisions
- ❌ Must NOT send messages directly to employee
- ✅ Surfaces relevant information proactively
- ✅ Provides draft responses for human to edit/approve

---

## Shared State (WorkflowState)

All agents communicate through a shared `WorkflowState` TypedDict:

```python
class WorkflowState(TypedDict):
    # Messages (LangGraph accumulator)
    messages: Annotated[list[BaseMessage], add_messages]

    # Identity
    session_id: str
    user_id: str

    # Classification (Triage Agent)
    issue_category: str | None
    issue_subcategory: str | None
    severity: Literal["low", "medium", "high", "critical"] | None
    urgency: Literal["low", "medium", "high"] | None
    impact: Literal["individual", "team", "department", "organization"] | None

    # Knowledge (Retrieval Agent)
    knowledge_results: list[dict]
    knowledge_confidence: float

    # Resolution (Resolution Agent)
    resolution_steps: list[ResolutionStep]
    resolution_confidence: float
    steps_attempted: list[str]

    # Escalation (Escalation Agent)
    should_escalate: bool
    escalation_reason: str | None
    handoff_summary: HandoffSummary | None

    # Ticket (Ticketing Agent)
    ticket_draft: TicketDraft | None
    ticket_created: bool

    # Control
    current_node: str
    turn_count: int
    needs_clarification: bool
    clarification_question: str | None
    audit_trail: list[dict]
```

### State Update Rules

1. Each node returns ONLY the fields it modifies
2. Messages use `add_messages` annotation (append-only)
3. `audit_trail` uses list annotation (append-only)
4. Nodes must NEVER mutate state directly
5. State is immutable between nodes

---

## Safety Rails

| # | Rule | Enforcement |
|---|------|-------------|
| 1 | No agent may access systems outside its defined tools | Code review + DI |
| 2 | No agent may bypass orchestrator routing | Graph structure enforces |
| 3 | Resolution must never fabricate steps | KB citation required |
| 4 | Escalation must never dismiss human requests | Explicit trigger check |
| 5 | All decisions logged to audit trail | Enforced in each node |
| 6 | Confidence scores calibrated honestly | Formula-based, not arbitrary |
| 7 | Maximum 10 turns per session | Orchestrator enforces |
| 8 | 30-second timeout per node | LangGraph config |
| 9 | Fallback to escalation on any error | Global error handler |

---

## Adding a New Agent

1. **Spec**: Create `agents/new-agent.md` (follow existing format)
2. **State**: Add fields to `backend/app/workflows/state.py` if needed
3. **Node**: Implement in `backend/app/workflows/nodes/new_agent.py`
4. **Graph**: Register in `backend/app/workflows/graph.py`
5. **Tests**: Write in `backend/tests/unit/test_workflows/test_new_agent.py`
6. **Skills**: Add implementation patterns to `skills/backend/` if novel
7. **Docs**: Update this file + `docs/architecture/agent-architecture.md`

---

## Metrics & Observability

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Avg resolution confidence | Resolution Agent | < 0.5 sustained |
| Escalation rate | Escalation Agent | > 40% of sessions |
| Avg turns to resolution | Orchestrator | > 5 turns |
| Triage accuracy | Manual review | < 80% correct |
| Knowledge gap rate | Learning Agent | > 20% no-result searches |
| Node execution time | LangGraph metrics | > 10s any node |
| LLM error rate | LiteLLM | > 5% failures |

---

## Knowledge Management (KB)

The agent's answer quality depends on the governed knowledge base. Key rules for
agents and contributors working in this area:

- **Retrieval is published-only for employees.** The chat agent must ground answers
  in published, approved content via `KnowledgeRetrievalService` (or the YAML dev
  fallback). Never surface drafts/in-review/archived content to employee chat.
- **Cite sources.** Retrieval returns `citation_label` + snippet per hit; the
  retrieval node emits `knowledge_citations` into `WorkflowState` for traceable,
  explainable answers.
- **Low confidence → escalate.** Composite retrieval confidence below the
  `LOW_CONFIDENCE_THRESHOLD` should bias the orchestrator toward escalation.
- **Boundaries**: KB management (`services/knowledge/management.py`), KB retrieval
  (`retrieval.py`), and indexing (`indexing.py`) are separate — the workflow only
  consumes retrieval.
- **Lifecycle**: `draft → in_review → approved → published → archived`; publish
  indexes, archive de-indexes, both snapshot a version. Rules live in
  `services/knowledge/lifecycle.py` (pure, unit-tested).
- **Record outcomes**: usage / successful-resolution / feedback feed `quality_score`
  and ranking. Use `KnowledgeRetrievalService.record_usage()` when an article helped.

Docs: `docs/architecture/knowledge-management.md`,
`docs/architecture/retrieval-and-indexing.md`,
`docs/product/knowledge-workflow.md`,
`docs/security/knowledge-access-control.md`.

---

## Document Ingestion Pipeline

> Not a conversational agent — a background ETL pipeline for admin-uploaded documents.

The document ingestion pipeline converts uploaded IT support documents (DOCX,
PDF, PPTX, TXT, Markdown) into structured `IngestionCandidate` records that
reviewers can promote to draft `KnowledgeArticle` entries.

### Design Principle: Schema-Stable, Parser-Flexible

`ExtractionCandidate` in `services/ingestion/schema.py` is the stable contract.
How a document is parsed (profiles, strategies) may evolve freely — the output
schema does not change without a version bump.

### Pipeline Layers

| Layer | File | Responsibility |
|-------|------|----------------|
| A | `extractor.py` | Raw text from any file format |
| B | `normalizer.py` | Typed `NormalizedLine` sequence |
| — | `profiles/` | Document-family configuration (no code change for new formats) |
| C | `segmenter.py` | Topic boundaries + `section_map` |
| D | `field_extractor.py` | Deterministic multi-strategy field extraction |
| D+ | `llm_extractor.py` | Optional LLM enrichment for low-confidence fields |
| — | `confidence.py` | Weighted composite score |

### Adding a New Document Format

Create a new `ParserProfile` in `services/ingestion/profiles/` and register it.
**No changes to the extraction engine are needed.**
See `docs/development/parser-rules.md` for the step-by-step guide.

### Key Rules
- ❌ The pipeline must NEVER auto-publish articles — candidates require human review
- ❌ LLM enrichment must NEVER invent steps not grounded in the source text
- ✅ Every extracted field carries `confidence`, `method`, and `source_excerpt`
- ✅ Candidates with `confidence_level = LOW` or `VERY_LOW` set `review_required = True`
- ✅ All pipeline stages are logged with per-stage timing in `processing_summary`

Docs: `docs/architecture/document-ingestion.md`,
`docs/architecture/knowledge-ingestion-pipeline.md`,
`docs/development/parser-rules.md`,
`docs/development/extraction-schema.md`.
