# Failure Cases and Golden Conversations

> Documented failure modes, root cause analysis, and fixed conversation flows.

---

## Failure Case #1: Sixth Sense Login Issue (June 2026)

### Observed Behavior (BEFORE)

```
User: Hi
Bot:  Hello! I'm your Aditi IT Support assistant...

User: I am having issue with sixthsenses
Bot:  I can see this is a General IT issue. Could you tell me what's
      specifically happening?
      [Which system?] [What application?]

User: I am unable to login to sixth senses
Bot:  I've drafted a support ticket for you:
      Title: IT Support Request - other
      Priority: medium
      Category: other
```

### Root Cause Analysis

| # | Cause | File | Fix |
|---|-------|------|-----|
| 1 | No entity normalization — "sixthsenses" not recognized | `triage.py` | Added `entity_normalizer.py` with alias registry |
| 2 | Keyword classifier had no Sixth Sense mapping | `triage.py` `_keyword_classify()` | Entity normalization runs before keyword fallback |
| 3 | Fell through to `"other"` category | `triage.py` | Entity match overrides category |
| 4 | OTHER_PLAYBOOK has minimal questions | `playbooks.py` | Added `SIXTH_SENSE_PLAYBOOK` |
| 5 | Low confidence → immediate escalation | `graph.py` | Escalation requires diagnostic attempt |
| 6 | Chat service reset diagnostic context between turns | `chat_service.py` | Context now persists across all turns |
| 7 | No login-specific diagnostic path | — | Intent detection + playbook questions |

### Fixed Behavior (AFTER)

```
User: Hi
Bot:  Hello! I'm your Aditi IT Support assistant...

User: I am having issue with sixthsenses
Bot:  I see you're having trouble with Sixth Sense (Naukri). Can you
      tell me what's happening?
      [Can't log in] [Account locked] [Unhandled Message] [OTP issue]

User: I am unable to login to sixth senses
Bot:  Got it — a Sixth Sense login issue. This is common and usually
      resolves itself. Here's what to do:

      1. Stop all login attempts immediately.
      2. Wait 1 hour for auto-unlock.
      3. Reset your password on naukri.com.
      4. Update the new password in Sixth Sense portal.

      Did this help?
```

### Verification

Tests in `tests/unit/test_sixth_sense_flow.py` and `test_entity_normalizer.py`
cover:
- `test_sixthsenses_misspelled_is_recognized` — the exact typo
- `test_sixth_sense_login_classified_correctly` — login intent detection
- `test_triage_does_not_jump_to_escalation` — no premature ticket
- `test_context_preserved_between_turns` — state persistence
- `test_sixth_sense_has_playbook` — playbook routing

---

## Golden Conversation Patterns

### Pattern: Known System + Clear Symptom → Direct Resolution

```
User: I can't receive emails in Outlook
Bot:  [Recognizes Outlook + not-receiving-emails]
      [Retrieves Outlook email delivery KB]
      [Provides 2-3 steps]
      Did this resolve the issue?
```

### Pattern: Known System + Vague Symptom → Clarification → Resolution

```
User: I have an Outlook issue
Bot:  [Recognizes Outlook, symptom unclear]
      I can see this is an Outlook issue. What's specifically happening?
      [Not receiving] [Can't send] [Slow] [Crashing] [Calendar sync]
User: Not receiving emails
Bot:  [Retrieves relevant KB]
      [Provides focused steps]
```

### Pattern: Misspelled System → Fuzzy Match → Playbook

```
User: sixthsenses login issue
Bot:  [Fuzzy matches "sixthsenses" → sixth_sense]
      [Applies SIXTH_SENSE_PLAYBOOK]
      [Provides login-specific guidance]
```

### Pattern: Unknown System → Generic Triage → Escalation

```
User: The XYZ tool is broken
Bot:  [No entity match]
      Which system or application is affected?
User: Our internal project tracker
Bot:  Could you describe what's happening in more detail?
User: It keeps showing a 500 error when I try to save
Bot:  [Retrieves general troubleshooting]
      I wasn't able to find a specific solution in our knowledge base.
      Would you like me to create a support ticket?
```

### Pattern: User Requests Human → Immediate Escalation

```
User: I need to talk to someone
Bot:  [Detects live_agent_requested]
      Absolutely — I'll connect you with our IT team right away.
      Would you like me to create a support ticket?
```
