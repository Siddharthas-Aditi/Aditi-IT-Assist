# Post-Chat Feedback — Product Workflow

**Aditi IT Assist** collects post-chat feedback from employees after each
resolved support session. The goal is to capture lightweight, actionable
signals without adding friction to the support experience.

---

## 1. Trigger Points

| Event | Trigger | Delivery |
|-------|---------|----------|
| Session status → `resolved` | Immediate | Inline card appended to chat |
| Live agent closes conversation | Immediate | Same card |
| Ticket created + chat closed | Secondary | Ticket detail page banner |
| Survey previously dismissed | Deferred | Re-shown from ticket detail page |

---

## 2. Survey Flow (5 steps, progressive disclosure)

```
Step 1 ─── "Was this session helpful?" ─── Yes / No
              │
Step 2 ─── "Was your issue resolved?" ─── Yes / No
              │
Step 3 ─── "Rate your experience" ─── ⭐ 1–5 stars (optional — can skip)
              │
Step 4 ─── "Anything we could improve?" ─── free text (optional — can skip)
              │
Step 5 ─── Thank-you confirmation
```

- Each step is a distinct visual state in `PostChatFeedbackCard.tsx`.
- The user can dismiss at any step — the partial response is discarded (not submitted).
- Skipping Step 3 or 4 submits without that field (server side stores `null`).

---

## 3. Message-Level Feedback (Secondary)

A thumbs-up / thumbs-down control appears below each AI assistant message
(implemented in `MessageFeedbackControls.tsx`). On thumbs-down, an optional
inline comment box expands.

Message-level feedback is stored in `message_feedback` and is independent of
the post-chat survey.

---

## 4. Idempotency Rules

- **One survey response per session per employee.** Re-submitting merges new
  answers into the existing row (no duplicates).
- **One message reaction per message per employee.** Re-submitting flips the
  vote and updates the comment.

---

## 5. Privacy Rules

- Employees can only submit feedback for their own sessions.
- Employees cannot view other employees' comments or responses.
- IT agents and leads can view feedback linked to their assigned sessions.
- Comment text is only visible to `it_agent` and above — never exposed to
  the employee who wrote it in a cross-user context.
- No survey spam: once submitted for a session, the card is hidden.

---

## 6. Re-accessing the Survey

If the employee dismisses the inline card before submitting:
- A "Rate this session" prompt appears on the `TicketDetailPage` if a ticket
  was created and no feedback has been submitted.
- The prompt links directly to the survey card (scrolls to it).

---

## 7. Frontend Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `PostChatFeedbackCard` | `features/chat/` | 5-step wizard |
| `MessageFeedbackControls` | `features/chat/` | Thumbs up/down per message |
| `FeedbackReviewPage` | `pages/admin/` | Admin review queue |
| `feedbackApi.ts` | `features/chat/` | React Query hooks |
