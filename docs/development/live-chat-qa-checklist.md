# Live Chat QA Checklist

Manual + automated verification for the chat → live-specialist flow. Pairs with
the unit tests in `backend/tests/unit/test_escalation_gating.py` and
`test_specialist_chat_service.py`.

## Setup

```bash
docker compose up --build -d
docker compose exec backend uv run python -m scripts.seed_enterprise
# Employee: employee@aditi.com / employee123
# Specialist: agent@aditi.com / agent123
```

## No-direct-connect policy

- [ ] As the employee, first message "connect me to a live specialist" → the AI
      asks for a problem description; **no ticket** is created.
- [ ] "help" / "issue" / "I need a human" alone → still asks for details.
- [ ] After describing a real issue (e.g. "Outlook won't send mail, error 0x800"),
      a human request now routes to escalation.
- [ ] Automated: `pytest tests/unit/test_escalation_gating.py`.

## AI-first resolution

- [ ] A known issue gets grounded steps before any escalation offer.
- [ ] Repeated "still not working" eventually surfaces the "Connect with a
      specialist" button (grounded help exhausted).

## Ticket + handoff

- [ ] Clicking "Connect with a specialist" creates exactly one ticket; clicking
      again does **not** create a duplicate.
- [ ] The ticket appears in `/operations/queue` with summary + priority.

## Waiting + same-window

- [ ] After connecting, the employee sees **"Please wait while I connect you to a
      live IT specialist."**
- [ ] When the specialist starts the chat, the banner flips to "An IT specialist
      has joined"; clicking continues in the same window.
- [ ] Refreshing either side rehydrates the transcript and current status.

## Specialist notification

- [ ] On `/operations/queue` with sound ON, a brand-new unclaimed handoff plays
      the chime once (not on every 15s poll).
- [ ] Desktop notification appears if permission granted.
- [ ] Muting silences subsequent chimes.

## Typing indicators

- [ ] Specialist typing → employee sees "IT specialist is typing…".
- [ ] Employee typing → specialist sees "User is typing…".
- [ ] Indicator disappears shortly after the other side stops / sends.
- [ ] Typing does **not** keep an idle session alive (only a real message does).

## Idle timeout (use short overrides to test fast)

Start a session with small thresholds, e.g. `idle_warning_seconds=10`,
`idle_end_seconds=20` (via the API), then:

- [ ] After the warning threshold, both sides see the idle warning banner +
      system message; copy states the correct grace window.
- [ ] Sending a message clears the warning (back to active).
- [ ] After the end threshold with no reply, the session auto-ends
      (`ended_by_timeout`), shown on both sides.
- [ ] Default (no override) = 7-minute warning + 2-minute grace.
- [ ] Automated: `pytest tests/unit/test_specialist_chat_service.py`.

## Duplicate claim / fallback

- [ ] Two specialists claiming the same ticket: one wins, the other gets a 409
      "already claimed" notice and the queue refreshes.
- [ ] No specialist available: after ~15 minutes, the system shows a fallback
      message offering ticket/email follow-up.
- [ ] User can click "Cancel" on the waiting banner to stop waiting.
- [ ] After cancelling, the user can continue chatting with the AI.

## Cancel waiting

- [ ] The Cancel button on the waiting banner sends POST /chat/cancel-waiting.
- [ ] After cancel, the waiting banner disappears and a confirmation message
      appears in the transcript.
- [ ] The ticket remains open for async follow-up.

## Specialist unavailable timeout

- [ ] GET /chat/waiting-status/{session_id} returns specialist_available=true
      within the first 15 minutes.
- [ ] After 15 minutes of waiting, specialist_available=false and a fallback
      message is returned.
- [ ] Frontend shows the fallback message in the chat transcript.
- [ ] Automated: `pytest tests/unit/test_chat_live_support_flow.py`.

## Close-out

- [ ] Specialist "Resolve & end" sets a typed `resolved` reason.
- [ ] Resolution notes can be proposed as a knowledge candidate (not published).

## Gates

```bash
make lint            # ruff + eslint (--max-warnings=0)
make test-backend    # pytest
make test-frontend   # vitest
```
