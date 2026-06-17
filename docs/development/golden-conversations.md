# Golden Conversations — Chat Quality Test Set

> Reference conversations used to validate the multi-turn diagnostic behavior.
> Run these scenarios after any changes to the chat architecture.

---

## Scenario 1: Vague Outlook Query → Clarification → Resolution

**Expected behavior**: Agent asks follow-up before resolving.

```
Turn 1:
  User: "I have an Outlook issue"
  Expected: Clarification question + quick-reply options
  Must NOT: Dump all Outlook troubleshooting content

Turn 2:
  User: "Not receiving emails"
  Expected: 2-3 specific steps for email delivery
  Must NOT: Include steps for Outlook crashes or calendar issues

Turn 3:
  User: "That worked, thanks!"
  Expected: Confirmation acknowledgment, session close
```

---

## Scenario 2: Specific Query → Direct Resolution (No Clarification)

**Expected behavior**: Agent proceeds directly when enough context exists.

```
Turn 1:
  User: "My Outlook is not syncing emails since this morning"
  Expected: Direct resolution steps for sync issues
  Must NOT: Ask clarification (symptom is already specific)
```

---

## Scenario 3: Zoom Audio → Progressive Diagnosis

```
Turn 1:
  User: "Zoom is not working"
  Expected: Clarification (audio? video? sign-in? can't join?)

Turn 2:
  User: "No audio / can't hear"
  Expected: 2-3 steps for Zoom audio issues
  Must include: Check audio settings, test speaker, check Zoom audio device

Turn 3:
  User: "Still not working"
  Expected: Additional steps or escalation offer
```

---

## Scenario 4: Immediate Escalation Request

**Expected behavior**: Agent escalates immediately, does not ask diagnostic questions.

```
Turn 1:
  User: "I need to talk to a real person about my computer"
  Expected: Acknowledge request + initiate escalation
  Must NOT: Ask clarifying questions
```

---

## Scenario 5: Camera Issue → Hardware Flow

```
Turn 1:
  User: "My camera isn't working"
  Expected: Clarification about specific camera issue

Turn 2:
  User: "Black screen in Zoom"
  Expected: Steps for camera black screen
  Must include: Check privacy settings, restart app, check device manager
```

---

## Scenario 6: Intune Non-Compliance → Targeted Resolution

```
Turn 1:
  User: "My device is showing non-compliant in Company Portal"
  Expected: Direct resolution (specific enough symptom)
  Steps should include: Check compliance status, sync device, verify policies
```

---

## Scenario 7: Account Lockout → High-Priority Flow

```
Turn 1:
  User: "My account is locked and I can't log into anything"
  Expected: Direct resolution for account lockout
  Should note urgency, offer escalation path
```

---

## Scenario 8: Topic Shift Mid-Conversation

```
Turn 1:
  User: "I have a Zoom issue"
  Expected: Clarification about Zoom problem

Turn 2:
  User: "Actually, my real problem is that Outlook keeps crashing"
  Expected: Agent recognizes topic shift, starts fresh classification for Outlook
  Must NOT: Confuse Zoom context with Outlook issue
```

---

## Scenario 9: Max Clarification Exhaustion

```
Turn 1:
  User: "Something is wrong"
  Expected: Clarification (which system/app?)

Turn 2:
  User: "My computer"
  Expected: Clarification (what's happening specifically?)

Turn 3:
  User: "It's just not right"
  Expected: Clarification (third and final attempt)

Turn 4:
  User: "I don't know"
  Expected: Agent proceeds with best-effort or offers escalation
  Must NOT: Ask a 4th clarification question
```

---

## Scenario 10: VPN Issue with Specific Error

```
Turn 1:
  User: "VPN gives me error 'authentication failed' every time I try to connect"
  Expected: Direct resolution (specific symptom + error message)
  Must include: Steps for VPN authentication failures
  Must NOT: Ask "what connectivity issue are you experiencing?"
```

---

## Quality Metrics

For each scenario, measure:
- **Clarification rate**: Was clarification asked when it should/shouldn't be?
- **Dump rate**: Were irrelevant KB articles included?
- **Step count**: Were responses concise (2-4 steps)?
- **Resolution relevance**: Were steps specific to the actual issue?
- **Escalation appropriateness**: Was escalation offered at the right time?

---

## Scenario 11: Outlook Mailbox Full → Storage Cleanup → Progression → Escalation (regression)

This is the canonical regression for the "inbox full → password reset / Windows
Update / repeated steps" bug. Automated as
`backend/tests/unit/test_outlook_mailbox_full_flow.py`.

```
Turn 1:
  User: "I have an issue with outlook"
  Expected: Clarification question + quick-reply chips (incl. "Mailbox / inbox full")
  Detected: system=outlook, subtype=None
  Must NOT: dump steps; ask a generic "what system?" question

Turn 2:
  User: "my inbox is full"
  Detected: issue_category=email/outlook, issue_subtype=mailbox-full (high conf)
  Grounding: keeps outlook-mailbox-full FIRST; rejects any access/* or
             device-management/* articles (logged in retrieval_trace.rejected)
  Expected steps (in order, storage cleanup):
    1. Check current mailbox size / quota
    2. Empty the Deleted Items folder
    3. Empty the Junk Email folder
  Must NOT contain: "change/reset password", "Windows Update", "wait 15 minutes",
                    account-lock / auto-unlock language
  Confidence: high (grounded subtype match)

Turn 3:
  User: "it did not work"
  Behavior: marks the prior 3 steps as failed; ADVANCES — does not repeat
  Expected NEXT steps (disjoint from turn 2):
    4. Delete/clean up large attachments
    5. Empty Sent Items of old large messages
    6. Archive older email

Turn 4+:
  User: keeps saying "still not working"
  Behavior: continues advancing through remaining grounded steps, then, when the
            mailbox-full playbook is exhausted, ESCALATES with a summary of what
            was tried (escalation_reason set; offers a ticket).
  Must NOT: loop on the same steps or invent new ungrounded steps.
```

### Pass/fail assertions (mirrors the test)
- Turn 1: `needs_clarification == True`, `issue_category == "email/outlook"`,
  `issue_subtype` empty.
- Turn 2: `issue_subtype == "mailbox-full"`; response/steps mention
  Deleted/Junk/mailbox; response contains **none** of
  {password, windows update, wait 15, auto-unlock}; `resolution_confidence ≥ 0.6`.
- Turn 3: second step set is **disjoint** from the first.
- Exhaustion: `resolution_steps == []` and `resolution_confidence == 0.0`
  (routes to escalation).

---

## Scenario 12: Cross-topic contamination guard

```
Context: issue_category=email/outlook, subtype=mailbox-full
Retriever returns (by raw score): [password-reset (0.95), windows-update (0.9),
                                   outlook-mailbox-full (0.5)]
Expected after grounding:
  kept    = [outlook-mailbox-full, ...other email/* ]
  rejected= [password-reset (cross-domain: access), windows-update (device-management)]
```
Automated in `backend/tests/unit/test_grounding.py`.

---

## Scenario 13: Confidence calibration

```
Grounded subtype answer (mailbox-full + matching article) → final >= 0.7
Ungrounded / cross-domain answer                          → final <= 0.25
Repeated failures (loop_counter, failed_attempts > 0)     → final reduced
```
Automated in `backend/tests/unit/test_confidence.py`.
