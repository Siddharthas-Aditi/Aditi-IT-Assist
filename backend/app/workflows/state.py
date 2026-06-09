"""Workflow state definition for the LangGraph agent system."""

from typing import Annotated, Literal, TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class ResolutionStep(TypedDict):
    """A single troubleshooting step."""

    step_number: int
    instruction: str
    details: str | None


class HandoffSummary(TypedDict):
    """Structured summary for human agent handoff."""

    employee_name: str
    issue_category: str
    issue_description: str
    steps_attempted: list[str]
    ai_confidence: float
    recommended_actions: list[str]
    severity: str
    urgency: str


class TicketDraft(TypedDict):
    """Draft ticket for escalated issues."""

    title: str
    description: str
    category: str
    priority: str
    steps_attempted: list[str]
    conversation_summary: str


class WorkflowState(TypedDict):
    """Complete state for the LangGraph support workflow.

    This state flows through all agent nodes and accumulates
    context as the conversation progresses.
    """

    # Conversation messages (using LangGraph's message accumulator)
    messages: Annotated[list[BaseMessage], add_messages]

    # Session identification
    session_id: str
    user_id: str

    # Classification (set by Triage Agent)
    issue_category: str | None
    issue_subcategory: str | None
    severity: Literal["low", "medium", "high", "critical"] | None
    urgency: Literal["low", "medium", "high"] | None
    impact: Literal["individual", "team", "department", "organization"] | None

    # Knowledge retrieval (set by Knowledge Agent)
    knowledge_results: list[dict]
    knowledge_confidence: float

    # Resolution (set by Resolution Agent)
    resolution_steps: list[ResolutionStep]
    resolution_confidence: float
    steps_attempted: list[str]

    # Escalation (set by Escalation Agent)
    should_escalate: bool
    escalation_reason: str | None
    handoff_summary: HandoffSummary | None

    # Ticket (set by Ticket Agent)
    ticket_draft: TicketDraft | None
    ticket_created: bool

    # Meta
    current_node: str
    turn_count: int
    needs_clarification: bool
    clarification_question: str | None
    audit_trail: list[dict]
