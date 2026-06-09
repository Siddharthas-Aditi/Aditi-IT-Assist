# Agents Directory

This directory contains specifications for each logical agent in the Aditi IT Assist system.
Each file describes one agent's role, inputs, outputs, tools, and constraints.

## Agents

| Agent | File | Purpose |
|-------|------|---------|
| Orchestrator | `orchestrator.md` | Routes conversation between agents |
| Triage | `triage-agent.md` | Classifies and categorizes issues |
| Retrieval | `retrieval-agent.md` | Searches knowledge base |
| Resolution | `resolution-agent.md` | Generates troubleshooting steps |
| Escalation | `escalation-agent.md` | Handles human handoff |
| Ticketing | `ticketing-agent.md` | Creates ticket/email drafts |
| Learning | `learning-agent.md` | Identifies knowledge gaps |
| Human Copilot | `human-support-copilot.md` | Assists human agents (future) |

## How to Use

When implementing or modifying an agent:
1. Read its specification file first
2. Check `backend/app/workflows/nodes/` for the implementation
3. Ensure changes maintain the agent's boundaries
4. Update the spec if behavior changes
