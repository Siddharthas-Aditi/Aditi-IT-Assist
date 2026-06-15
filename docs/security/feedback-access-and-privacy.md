# Feedback Access Control & Privacy

---

## 1. Permission Matrix

| Permission | Code | Roles |
|------------|------|-------|
| Submit conversation feedback | `feedback:submit` | employee, it_agent, it_lead, it_admin |
| View own feedback | `feedback:view_own` | employee, it_agent, it_lead, it_admin |
| View feedback analytics | `feedback:view_analytics` | it_lead, it_admin |
| Review flagged feedback | `feedback:review` | it_lead, it_admin |

---

## 2. Data Access Rules

### Employees
- May **submit** feedback only for sessions where `session.user_id = current_user.id`.
  Attempting to submit for another user's session returns `403 Forbidden`.
- May **view** their own submitted survey response (`GET /feedback/conversation/{id}`).
- May **NOT** read others' comments or analytics aggregates.

### IT Agents
- May view feedback attached to sessions assigned to them
  (`GET /feedback/conversation/{id}/all`).
- May NOT read global analytics.

### IT Lead / IT Admin
- Full read access to analytics, article health, agent summaries, and the
  review queue.
- May NOT modify feedback records — feedback is append/update by submitter only.

### Security Auditors
- No explicit feedback permissions; they use the audit log to trace submission
  events if needed.

---

## 3. Comment Privacy

- `ConversationFeedback.comment` is never returned to the submitting employee
  after submission (the `GET /conversation/{id}` endpoint returns the full record
  including the comment, which is acceptable since it is their own comment).
- Comments from other employees are **never** returned through any employee-facing
  endpoint.
- Admin / lead endpoints return comments for review purposes.

---

## 4. No Survey Spam

- The `PostChatFeedbackCard` is displayed **once** per session after resolution.
- Once feedback is submitted for a session, the card is hidden permanently for
  that session (frontend checks `useSessionFeedback(sessionId)` on load).
- No email surveys, no repeat prompts within the same session.
- No feedback is collected for sessions that are still `active` or
  `awaiting_agent`.

---

## 5. Audit Trail

Feedback submission events are logged to `structlog` at `INFO` level with:
- `session_id`, `user_id`, `quality_bucket`, `review_flag`

No comment text is included in log output.
