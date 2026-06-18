# Critical Bugs Found & Fixes Required

**Date**: June 18, 2026  
**Status**: 5 Critical Issues Identified

---

## Bug #1: Issue_Resolved Flag Reset ⚠️ CRITICAL

**Location**: `backend/app/services/agents/chat_service.py` line 136  
**Severity**: CRITICAL  
**Impact**: User starting new issue after resolution is incorrectly categorized as continuation of previous issue

### Problem
```python
# Line 136 in chat_service.py
state["issue_resolved"] = False  # ❌ WRONG - resets every turn
```

When user says "I have another issue" after previous issue was resolved, the triage node doesn't know the prior issue was resolved, so it doesn't call `reset_issue_context()`. This causes the agent to assume the new issue is the same category as the previous one.

**Chat Log Evidence:**
```
User: "it worked thanks"
Agent: ✅ Sets issue_resolved=True in previous turn
User: "I have another issue"  
Agent: ❌ Assumes it's Outlook/email (from previous context, should reset)
```

### Root Cause
Line 136 unconditionally resets `issue_resolved` to False for every new turn. But the triage node checks `if diag_ctx.issue_resolved:` at line 270 to detect post-resolution context and reset appropriately.

### Fix
**Don't reset issue_resolved.** Let it persist from the diagnostic_context:

```python
# REMOVE line 136 entirely
# state["issue_resolved"] = False  ← DELETE THIS

# Instead, let it come from diagnostic_context:
# issue_resolved is preserved via diagnostic_context.to_dict() / from_dict()
```

---

## Bug #2: Duplicate Agent Messages 

**Location**: `backend/app/workflows/` (likely in graph.py or multiple nodes)  
**Severity**: HIGH  
**Impact**: Chat responses appear twice in the UI

### Problem
In the chat log, agent responses appear duplicated:
```
Agent: "I can see this is an Outlook/email issue. Could you tell me what's specifically happening?"
Agent: "I can see this is an Outlook/email issue. Could you tell me what's specifically happening?"  ← DUPLICATE
```

### Root Cause
**Hypothesis**: Messages are being appended to the workflow state multiple times, likely:
1. A node is returning `messages` AND the orchestrator is also appending it
2. Or, the workflow graph is concatenating messages twice

### Investigation Needed
- [ ] Check if resolution_node, escalation_node, or triage_node are returning duplicate messages
- [ ] Verify graph.py is not double-appending messages
- [ ] Check if frontend is showing both workflow response + accumulated messages

### Temporary Fix
Implement message deduplication in chat_service._format_response():

```python
def _format_response(self, session_id: str, result: dict, ...):
    messages = result.get("messages", [])
    content = "..."
    
    seen = set()
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            msg_hash = hash(msg.content)  # ← Add deduplication
            if msg_hash not in seen:
                content = msg.content
                seen.add(msg_hash)
                break
```

---

## Bug #3: Tickets Not Persisting to Database

**Location**: `backend/app/services/agents/chat_service.py` lines 280-374  
**Severity**: CRITICAL  
**Impact**: Chat says "ticket created" but no ticket appears in My Tickets or Live Queue

### Problem
Chat log shows:
```
Agent: "✅ I've created ticket **ITA-000006** and handed it to our IT specialists..."
But then: My Tickets page shows blank (no actual ticket displayed)
```

### Root Cause
Multiple potential causes:
1. **Idempotency map only in-memory**: Line 29 uses `_session_tickets: dict[str, dict] = {}` (in-memory only)
   - When page reloads, the dict is cleared
   - No persistence to database

2. **Ticket may not be created at all**: Line 294 checks `if not result.get("escalation_confirmed"):`
   - If escalation_confirmed is False, returns None (no ticket)
   - But the agent response still claims it created one

3. **No verification**: After `_persist_and_queue()`, there's no check that ticket actually got created

### Fix
1. **Persist idempotency map to database:**
```python
# BEFORE (line 29):
_session_tickets: dict[str, dict] = {}  # ❌ Lost on restart

# AFTER - use database:
# Create a session_tickets table in PostgreSQL
# Query it instead of the dict
```

2. **Always confirm escalation before claiming success:**
```python
# In the response message (chat_service.py line 231):
if ticket_ref is not None:  # Only if ticket ACTUALLY exists
    content = f"✅ I've created ticket **{ticket_ref.ticket_number}**..."
else:
    content = "I'd like to connect you with our IT team. Click below to confirm."
```

---

## Bug #4: Live Queue & My Tickets Pages Showing Dummy Data

**Location**: `frontend/src/pages/` (needs investigation)  
**Severity**: HIGH  
**Impact**: Pages show placeholder content instead of real tickets from backend

### Problem
```
Pages show:
- "Queue items will appear here. Connect to backend to see live data."
- "Team queue with workload balancing and SLA oversight coming soon."
- Single dummy ticket: "IT Support Request - hardware/other (unable to connect mouse)"
```

### Root Cause
Frontend pages are likely:
1. Not calling the backend API to fetch real tickets
2. Using hardcoded/seeded placeholder data
3. Not wired to the `/api/v1/tickets` endpoint

### Fix
Wire frontend pages to fetch real data:
```typescript
// In Live Queue component:
const { data: tickets } = useQuery({
  queryKey: ['live-queue'],
  queryFn: async () => {
    const res = await api.get('/api/v1/tickets');
    return res.data.items;
  },
});

// Render real tickets instead of placeholder
{tickets.map(ticket => (
  <TicketRow key={ticket.id} ticket={ticket} />
))}
```

---

## Bug #5: Wrong Data Types / Clickability Issues

**Location**: Multiple frontend components  
**Severity**: MEDIUM  
**Impact**: Some elements don't respond to clicks, navigation broken

### Problem
```
- Live Support Queue shows status badges (3, 5, 2, 12) but no actual ticket items
- Clicking on ticket number should open details, but nothing happens
- "Connect with specialist" button may not trigger escalation
```

### Root Cause
Likely:
1. Event handlers not wired up
2. Links pointing to wrong routes
3. Components expecting different data structure than API returns

### Fix
1. Verify all buttons have onClick handlers
2. Verify all links use React Router `<Link>` or `useNavigate()`
3. Verify API response type matches component expectations

---

## Fix Order (Priority)

1. **🔴 BUG #1 (Issue_Resolved)** - 5 minute fix, blocks everything else
2. **🔴 BUG #3 (Tickets not persisting)** - 15 minute fix, critical for escalation
3. **🟡 BUG #4 (Dummy data)** - 20 minute fix, users won't see real results
4. **🟡 BUG #2 (Duplicate messages)** - 10 minute investigation, 5 minute fix
5. **🟡 BUG #5 (Clickability)** - 15 minute audit, UI polish

---

## Testing Plan

After each fix, test:
```
✓ Start new chat
✓ Say "I have an Outlook issue" → mailbox full
✓ Confirm steps work
✓ Say "it worked thanks"
✓ Say "I have another issue"  
✓ Say "I can't login to Slack"  ← Should reset to Slack, not assume Outlook
✓ Request escalation
✓ Check My Tickets page → should show real ticket
✓ Check Live Queue page → should show the new ticket
✓ Reload page → ticket should still be there (verify DB persistence)
✓ No duplicate messages in chat log
```

---

## Files to Modify

| File | Issue | Severity |
|------|-------|----------|
| `backend/app/services/agents/chat_service.py` | #1, #3 | CRITICAL |
| `backend/app/models/` | #3 (need session_tickets table) | CRITICAL |
| `backend/app/repositories/` | #3 (need ticket fetching) | CRITICAL |
| `backend/app/workflows/graph.py` | #2 | HIGH |
| `frontend/src/pages/TicketsPage.tsx` | #4, #5 | HIGH |
| `frontend/src/pages/LiveQueuePage.tsx` | #4, #5 | HIGH |
| `frontend/src/components/ChatInterface.tsx` | #2 | MEDIUM |

