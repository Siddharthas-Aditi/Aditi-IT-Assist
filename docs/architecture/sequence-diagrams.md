# Sequence Diagrams — Aditi IT Assist

## 1. New Support Session

```
┌──────┐          ┌────────┐         ┌───────┐         ┌──────────┐
│ User │          │Frontend│         │Backend│         │  Agents  │
└──┬───┘          └───┬────┘         └───┬───┘         └────┬─────┘
   │                  │                  │                   │
   │── Open Chat ────►│                  │                   │
   │                  │── GET /session ─►│                   │
   │                  │◄─ session_id ────│                   │
   │                  │                  │                   │
   │── "Outlook not  │                  │                   │
   │    receiving    ─►│                  │                   │
   │    emails"       │── POST /chat ───►│                   │
   │                  │                  │── invoke_graph ──►│
   │                  │                  │                   │── triage
   │                  │                  │                   │── retrieve
   │                  │                  │                   │── resolve
   │                  │                  │◄── state ─────────│
   │                  │◄─ AI response ───│                   │
   │◄── Display ──────│                  │                   │
   │    "Let me help  │                  │                   │
   │     with your    │                  │                   │
   │     Outlook..."  │                  │                   │
```

## 2. Escalation Flow

```
┌──────┐          ┌────────┐         ┌───────┐         ┌──────────┐
│ User │          │Frontend│         │Backend│         │  Agents  │
└──┬───┘          └───┬────┘         └───┬───┘         └────┬─────┘
   │                  │                  │                   │
   │── "This didn't  │                  │                   │
   │    work, I need ─►│                  │                   │
   │    human help"   │── POST /chat ───►│                   │
   │                  │                  │── invoke_graph ──►│
   │                  │                  │                   │── escalate
   │                  │                  │                   │── draft_ticket
   │                  │                  │◄── state ─────────│
   │                  │◄─ escalation ────│                   │
   │◄── "I'll connect│                  │                   │
   │     you with... │                  │                   │
   │     Here's the  │                  │                   │
   │     ticket draft"│                  │                   │
   │                  │                  │                   │
   │── Approve draft ─►│                  │                   │
   │                  │── POST /ticket ─►│                   │
   │                  │                  │── create_ticket ──►
   │                  │◄─ ticket_id ─────│                   │
   │◄── "Ticket #123 │                  │                   │
   │     created"     │                  │                   │
```

## 3. Knowledge Article Creation (Admin)

```
┌───────┐         ┌────────┐         ┌───────┐         ┌────────┐
│ Admin │         │Frontend│         │Backend│         │pgvector│
└──┬────┘         └───┬────┘         └───┬───┘         └───┬────┘
   │                  │                  │                  │
   │── Create article►│                  │                  │
   │                  │── POST /knowledge►│                  │
   │                  │                  │── generate ──────►│
   │                  │                  │   embedding       │
   │                  │                  │◄── stored ────────│
   │                  │◄─ article_id ────│                  │
   │◄── "Article      │                  │                  │
   │     published"   │                  │                  │
```

## 4. Authentication Flow (Future - Azure AD)

```
┌──────┐          ┌────────┐         ┌───────┐         ┌──────────┐
│ User │          │Frontend│         │Backend│         │ Azure AD │
└──┬───┘          └───┬────┘         └───┬───┘         └────┬─────┘
   │                  │                  │                   │
   │── Login ────────►│                  │                   │
   │                  │── redirect ─────────────────────────►│
   │◄── SSO login ──────────────────────────────────────────│
   │── credentials ─────────────────────────────────────────►│
   │◄── auth_code ──────────────────────────────────────────│
   │                  │◄─ auth_code ─────│                   │
   │                  │                  │── exchange code ──►│
   │                  │                  │◄── tokens ────────│
   │                  │◄─ JWT token ─────│                   │
   │◄── Logged in ────│                  │                   │
```
