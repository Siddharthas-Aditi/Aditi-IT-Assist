# Analytics Architecture

> Metrics, dashboards, and reporting for IT leadership.

## Dashboard Metrics

### Ticket Metrics
- **Ticket volume** — Total tickets created in period
- **Status distribution** — Breakdown by current status
- **Priority distribution** — Breakdown by priority level
- **Category distribution** — Top 10 issue categories
- **Source distribution** — Where tickets originate

### Performance Metrics
- **Average first response time** — Time to first agent response
- **Average resolution time** — Time from creation to resolution
- **SLA at risk** — Tickets within 1 hour of SLA breach
- **SLA breached** — Tickets past their SLA target

### AI Metrics
- **AI resolution rate** — % of sessions resolved without human
- **Average AI confidence** — Mean confidence score across sessions
- **Escalation rate** — % of sessions that escalate
- **Live handoff rate** — Sessions transferred to human agent

### Remote Support Metrics
- **Sessions initiated** — Total remote sessions requested
- **Sessions completed** — Successfully completed sessions
- **Consent rate** — % of requests where employee granted consent
- **Average session duration** — How long remote sessions last

### Agent Metrics
- **Agent workload** — Active tickets per agent
- **Agent resolution rate** — Tickets resolved per agent per day
- **Agent response time** — Individual first response time

## Data Sources

```
Real-time queries:
├── Ticket table (status, priority, category counts)
├── Support sessions (AI metrics)
├── Remote support sessions (remote metrics)
└── User assignments (workload)

Periodic snapshots (analytics_snapshots table):
├── Hourly aggregations
├── Daily summaries
└── Weekly reports
```

## API Endpoints

| Endpoint | Access | Description |
|----------|--------|-------------|
| `GET /analytics/dashboard` | IT Lead, Admin | Full dashboard metrics |
| `GET /analytics/workload` | IT Lead, Admin | Agent workload data |

## Frontend Components

- Metric cards with trend indicators
- Bar/line charts for volume over time
- Pie charts for category/priority distribution
- Agent workload progress bars
- SLA breach alert badges
- Date range filter controls
