# Ticketing Lifecycle

> Enterprise helpdesk ticket management with SLA tracking.

## Status Flow

```
                  ┌─────────────────────────────────────────────┐
                  │                                             │
  ┌─────┐  assign  ┌─────────┐  work  ┌─────────────┐  need info  ┌──────────────────┐
  │ New │─────────▶│ Triaged │──────▶│ In Progress │───────────▶│ Waiting for User │
  └─────┘          └─────────┘        └─────────────┘            └──────────────────┘
    │                   │                     │                           │
    │                   │                     │    user responds          │
    │                   │                     │◀─────────────────────────┘
    │    escalate       │    escalate         │
    │──────────────────▶│───────────────────▶│
    ▼                   ▼                     ▼
┌───────────┐                          ┌──────────┐       ┌────────┐
│ Escalated │                          │ Resolved │──────▶│ Closed │
└───────────┘                          └──────────┘       └────────┘
                                              ▲
                                              │ reopen
                                              │
                                       ┌──────────┐
                                       │ (Closed) │
                                       └──────────┘
```

## SLA Targets

| Priority | First Response | Resolution |
|----------|---------------|------------|
| Critical | 1 hour | 4 hours |
| High | 4 hours | 12 hours |
| Medium | 8 hours | 48 hours |
| Low | 24 hours | 120 hours (5 days) |

## Ticket Fields

### Core
- `ticket_number` — Sequential unique identifier (ITA-000001)
- `title` — Brief description
- `description` — Full issue description
- `requester_id` — Employee who created the ticket

### Classification
- `category` — email/outlook, network/connectivity, hardware/*, etc.
- `subcategory` — More specific classification
- `priority` — low, medium, high, critical
- `severity` — Business impact level
- `impact` — individual, team, department, organization
- `urgency` — How quickly it needs resolution

### Assignment
- `assigned_to` — IT agent responsible
- `escalated_to` — Higher-level agent if escalated

### SLA Tracking
- `sla_response_target` — When first response is due
- `sla_resolution_target` — When resolution is due
- `first_response_at` — When first response occurred
- `resolved_at` — When marked resolved
- `closed_at` — When formally closed

### Source
- `chat` — Created from AI support chat
- `email` — Created from email (future)
- `manual` — Manually created
- `remote_session_followup` — Follow-up from remote assist
- `api` — Created via API

### AI Metadata
- `ai_confidence` — AI's confidence in its resolution
- `ai_summary` — AI-generated ticket summary
- `suggested_articles` — Knowledge articles that may help

## Comments vs Internal Notes

| Type | Visible to Employee | Use Case |
|------|-------------------|----------|
| Comment (reply) | ✅ Yes | Communication with requester |
| Internal Note | ❌ No | IT team discussion, investigation notes |
| AI Suggestion | ❌ No | AI copilot recommendations |
| System Event | ✅ Yes | Status changes, assignments |

## Activity Feed (Timeline)

Every ticket has a chronological timeline:
- Ticket created
- Status changes
- Assignments/reassignments
- Comments added
- Internal notes added (visible to IT only)
- SLA breach warnings
- Escalation events
- Resolution notes
