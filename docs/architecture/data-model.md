# Data Model — Aditi IT Assist

## Entity Relationship Diagram

```
┌──────────┐       ┌───────────────┐       ┌──────────────┐
│  User    │───1:N─│ SupportSession│───1:N─│   Message    │
└──────────┘       └───────────────┘       └──────────────┘
                          │                        │
                          │1:N                     │
                          ▼                        │
                   ┌──────────────┐                │
                   │    Ticket    │                │
                   └──────────────┘                │
                          │                        │
                          │1:N                     │
                          ▼                        │
                   ┌──────────────┐                │
                   │  Escalation  │                │
                   └──────────────┘                │
                                                   │
┌──────────────────┐                              │
│ KnowledgeArticle │◄────────────referenced_by─────┘
└──────────────────┘
         │
         │1:N
         ▼
┌──────────────────┐
│  AuditEvent      │
└──────────────────┘
```

## Tables

### users
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique, indexed |
| full_name | VARCHAR(255) | Display name |
| employee_id | VARCHAR(50) | Aditi employee ID |
| department | VARCHAR(100) | Department |
| role | ENUM | employee, it_agent, admin |
| is_active | BOOLEAN | Account status |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update |

### support_sessions
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| status | ENUM | active, awaiting_user, resolved, escalated, closed |
| issue_category | VARCHAR(100) | Classified category |
| issue_subcategory | VARCHAR(100) | Sub-category |
| severity | ENUM | low, medium, high, critical |
| urgency | ENUM | low, medium, high |
| confidence_score | FLOAT | Final AI confidence |
| resolution_summary | TEXT | How it was resolved |
| created_at | TIMESTAMP | Session start |
| resolved_at | TIMESTAMP | Resolution time |
| closed_at | TIMESTAMP | Close time |

### messages
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → support_sessions |
| role | ENUM | user, assistant, system |
| content | TEXT | Message content |
| metadata | JSONB | Agent info, confidence, etc. |
| created_at | TIMESTAMP | Message time |

### knowledge_articles
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| title | VARCHAR(500) | Article title |
| category | VARCHAR(100) | Issue category |
| subcategory | VARCHAR(100) | Sub-category |
| content | TEXT | Full article content |
| steps | JSONB | Structured resolution steps |
| tags | VARCHAR[] | Search tags |
| embedding | VECTOR(1536) | pgvector embedding |
| is_published | BOOLEAN | Visibility |
| author_id | UUID | FK → users |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update |

### tickets
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → support_sessions |
| title | VARCHAR(500) | Ticket title |
| description | TEXT | Full description |
| priority | ENUM | low, medium, high, critical |
| status | ENUM | draft, open, in_progress, resolved, closed |
| assigned_to | UUID | FK → users (nullable) |
| external_ticket_id | VARCHAR(100) | External system reference |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update |

### escalations
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → support_sessions |
| ticket_id | UUID | FK → tickets (nullable) |
| reason | TEXT | Why escalated |
| handoff_summary | JSONB | Structured summary for agent |
| escalated_to | UUID | FK → users (nullable) |
| status | ENUM | pending, accepted, resolved |
| created_at | TIMESTAMP | Escalation time |
| resolved_at | TIMESTAMP | Resolution time |

### audit_events
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → support_sessions (nullable) |
| event_type | VARCHAR(100) | Event classification |
| actor | VARCHAR(100) | Agent or user identifier |
| payload | JSONB | Event details |
| created_at | TIMESTAMP | Event time |

## Indexes

- `users.email` — unique index
- `support_sessions.user_id` — foreign key index
- `support_sessions.status` — filter index
- `messages.session_id` — foreign key index, ordered by created_at
- `knowledge_articles.embedding` — IVFFlat or HNSW vector index
- `knowledge_articles.category` — filter index
- `tickets.session_id` — foreign key index
- `audit_events.session_id` — foreign key index
- `audit_events.event_type` — filter index
