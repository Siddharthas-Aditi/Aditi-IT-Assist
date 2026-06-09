# AGENTS.md - Multi-Agent System Design for Aditi IT Assist

## System Agents

This document defines the logical agents in the Aditi IT Assist platform.
Each agent is a discrete node in the LangGraph workflow with defined inputs,
outputs, tools, and decision boundaries.

---

## 1. Orchestrator Agent

**Purpose**: Routes the conversation flow between agents based on state.

**Inputs**: Current workflow state, user message history, classification results
**Outputs**: Next agent to invoke, updated state
**Decision Logic**:
- New conversation → Triage Agent
- Needs more info → Triage Agent (clarification mode)
- Classified issue → Knowledge Retrieval Agent
- Has resolution steps → Resolution Agent
- Low confidence / user requests help → Escalation Agent
- Escalation approved → Ticket/Email Agent

---

## 2. Intake & Triage Agent

**Purpose**: Understands the user's issue, asks clarifying questions, classifies the problem.

**Inputs**: User message, conversation history
**Outputs**: Issue classification, severity, urgency, impact, category
**Tools**: Classification prompt, entity extraction
**Boundaries**: Must not attempt resolution. Only classifies and clarifies.

**Categories**:
- `email/outlook`
- `video-conferencing/zoom`
- `device-management/intune`
- `hardware/camera`
- `hardware/other`
- `software/other`
- `network/connectivity`
- `access/permissions`
- `other`

---

## 3. Knowledge Retrieval Agent

**Purpose**: Searches the knowledge base for relevant troubleshooting playbooks.

**Inputs**: Issue classification, user description, category
**Outputs**: Relevant knowledge articles, ranked by relevance
**Tools**: Vector similarity search (pgvector), keyword search fallback
**Boundaries**: Returns information only. Does not synthesize or advise.

---

## 4. Resolution Agent

**Purpose**: Generates step-by-step troubleshooting guidance using retrieved knowledge.

**Inputs**: Knowledge articles, issue context, user conversation
**Outputs**: Resolution steps, confidence score, follow-up questions
**Tools**: LLM generation with retrieved context (RAG pattern)
**Boundaries**:
- Must cite knowledge source
- Must include confidence score (0.0 to 1.0)
- Must offer escalation option if confidence < 0.8
- Must not make up steps not found in knowledge base

---

## 5. Escalation Agent

**Purpose**: Determines escalation path and prepares handoff.

**Inputs**: Conversation history, classification, attempted resolution, confidence
**Outputs**: Escalation decision, handoff summary, priority level
**Decision Logic**:
- Check if human agents are available (future: queue check)
- Prepare structured summary for human agent
- If no human available → route to Ticket/Email Agent

**Handoff Summary Includes**:
- Employee name and ID
- Issue category and description
- Steps already attempted
- AI confidence assessment
- Recommended next actions for human agent
- Severity/urgency/impact ratings

---

## 6. Ticket / Email Drafting Agent

**Purpose**: Creates structured support tickets or email drafts.

**Inputs**: Escalation summary, conversation history, user info
**Outputs**: Formatted ticket or email draft
**Tools**: Template engine, email formatter
**Boundaries**:
- Must preserve all conversation context
- Must include categorization metadata
- Must follow company ticket format
- Draft only — does not send without approval

---

## 7. Knowledge Learning Agent

**Purpose**: Identifies gaps in knowledge base and suggests new articles.

**Inputs**: Resolved sessions, unresolved sessions, user feedback
**Outputs**: Knowledge gap reports, suggested new articles
**Boundaries**:
- Runs asynchronously (not in real-time conversation flow)
- Suggestions require human review before publishing
- Tracks resolution success rates by category

---

## 8. Human Support Copilot Agent (Future)

**Purpose**: Assists human IT agents with context and suggestions during live support.

**Inputs**: Live conversation between human agent and employee
**Outputs**: Contextual suggestions, relevant KB articles, draft responses
**Boundaries**:
- Advisory only — human agent makes all decisions
- Must not send messages directly to employee
- Surfaces relevant information proactively

---

## Agent Communication Protocol

Agents communicate through the shared **WorkflowState** object:

```python
class WorkflowState(TypedDict):
    messages: list[Message]
    classification: IssueClassification | None
    knowledge_results: list[KnowledgeArticle]
    resolution_steps: list[ResolutionStep]
    confidence_score: float
    escalation_decision: EscalationDecision | None
    ticket_draft: TicketDraft | None
    current_agent: str
    next_agent: str
    session_id: str
    user_id: str
    metadata: dict
```

## Agent Boundaries (Safety Rails)

1. No agent may access systems outside its defined tools
2. No agent may bypass the orchestrator's routing
3. Resolution Agent must never fabricate steps not in knowledge base
4. Escalation Agent must never dismiss user requests for human help
5. All agents must log their decisions for audit trail
6. Confidence scores must be calibrated honestly (not inflated)

## Adding New Agents

1. Define the agent in `agents/new-agent.md`
2. Implement the node in `backend/app/workflows/nodes/`
3. Register the node in `backend/app/workflows/graph.py`
4. Add state fields if needed in `backend/app/workflows/state.py`
5. Write unit tests in `backend/tests/unit/test_workflows/`
6. Update `docs/architecture/agent-architecture.md`
