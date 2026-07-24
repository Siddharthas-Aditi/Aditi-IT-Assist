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

---

## Scenario 14: Mid-conversation topic switch (the ITA-000007 regression)

**Expected behavior**: Agent recognizes `NEW_TOPIC`, resets the diagnostic
context, and asks what the new issue is. **No ticket is created.**

```
Turn 1: User: "Hi, mailbox is full"
        Bot:  confirm-understanding ("…just to make sure…")
Turn 2: User: "yes"
        Bot:  troubleshooting steps for mailbox-full
Turn 3: User: "I have an another problem"
        Expected: NEW_TOPIC intent → reset → "Of course — what's the new issue?"
        Must NOT: create a ticket, repeat mailbox-full steps, or auto-escalate
```
Automated in `backend/tests/unit/test_chat_golden_conversations.py::
TestMailboxFullThenAnotherProblem`. Intent-layer regressors in
`tests/unit/test_intent_classifier.py::TestNewTopic`.

---

## Scenario 15: Explicit human handoff creates a ticket

**Expected behavior**: When the user types "connect me with a specialist",
the supervisor routes to `ESCALATE`, the chat service creates a ticket with
the structured handoff package, and the queue exposes it for pickup.

```
Turn 1: User: "VPN keeps disconnecting"
        Bot:  clarification or grounded steps
Turn 2: User: "please connect me with a specialist"
        Expected: ticket created, HandoffPackage v1.0 attached,
                  user message confirms ticket number
        Must NOT: silently retry the AI; the user asked for a human
```
Automated in `tests/unit/test_chat_golden_conversations.py::
TestExplicitEscalationCreatesTicket`.

---

## Scenario 16: Atomic claim — no duplicate pickup

**Expected behavior**: Two IT specialists racing to claim the same chat
end up with exactly one claimer; the other gets HTTP 409.

```
Setup: ticket T in status 'triaged', assigned_to = NULL
Action: specialist A and specialist B both POST /specialist-queue/claim
        with body { ticket_id: T }
Expected:
  • exactly one 200 OK with ClaimResponse (assigned_to = winner)
  • the other gets 409 with the winner's name in the message
```
Atomic SQL contract is in `services/specialist_queue_service.py::claim`.

---

## Scenario 17: Specialist resolution → KB improvement candidate

**Expected behavior**: When an IT specialist resolves a chat-derived ticket
with "Send to KB Improvement queue" checked, a `KnowledgeCandidate` is
created (state=proposed), NOT a published article.

```
Action: POST /specialist-queue/resolve
        { ticket_id, resolution_notes, propose_knowledge_candidate: true }
Expected:
  • ticket.status = 'resolved'
  • new KnowledgeCandidate row, state='proposed',
    source='specialist_resolution', source_ticket_id=<this>
  • no row in knowledge_articles
  • response carries knowledge_candidate_id
```

---

## Scenario 18: Web fallback gates

**Expected behavior**: Web fallback runs only when the specialist's
`web_fallback_allowed` is `True`, after the per-specialist soft cap, and
every kept result becomes a `KnowledgeCandidate`.

```
Case A: zoom_meetings, 3rd delegation reached, KB confidence 0.4
        Expected: supervisor → WEB_FALLBACK
        Service: filters to OFFICIAL + VENDOR + TRUSTED_COMMUNITY tiers
        Result: each kept result → KnowledgeCandidate (web_fallback)

Case B: outlook (web_fallback_allowed=False), 3rd delegation reached
        Expected: supervisor → ESCALATE
        Service: refuses if called directly; logs web_research_blocked
```
Registry contract in `tests/unit/test_agent_registry.py`; routing in
`tests/unit/test_supervisor.py`.

---

## Scenario 19: Supervisor handoff cap

**Expected behavior**: After 8 agent-to-agent handoffs in one session, the
supervisor escalates rather than continuing to ping between specialists.

```
SessionMetrics.handoffs = 10 (any further turn)
Expected: supervisor.decide(...) → NextAction.ESCALATE
          reason contains "handoff cap"
```
Automated in `tests/unit/test_supervisor.py::TestGuardrails`.

---

## Scenario 20: Loop detection

**Expected behavior**: Two consecutive no-progress turns (no new slot
filled, no new step tried) force escalation.

```
SessionMetrics.loop_signals = 2
Expected: supervisor → ESCALATE, reason "loop detected"
```
Automated in `tests/unit/test_supervisor.py::TestGuardrails`.

---

## Scenario 21: Confident issue — no forced confirm turn (fluid chat)

**Flag**: `FEATURE_FLUID_CHAT=true`.

**Expected behavior**: A well-specified issue (subtype confidence ≥
`FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE`) goes straight to grounded resolution on
the first turn — no forced "is that what you're experiencing?" round-trip.

```
Turn 1: User: "my outlook mailbox is full"
        Expected: subtype=mailbox-full detected immediately; the FIRST reply
                  already contains help (mentions mailbox/storage/space)
        Must NOT: reply with a bare confirm-only question ("is that right?",
                  "did I get that right?", "is that what you're experiencing?")
```
Automated in `backend/tests/unit/test_chat_golden_conversations.py::
TestFluidChat::test_confident_issue_no_confirm_turn`.

---

## Scenario 22: No repeated question across turns (fluid chat)

**Flag**: `FEATURE_FLUID_CHAT=true`.

**Expected behavior**: Across a multi-turn conversation the bot never
re-emits the exact same question verbatim — each clarification narrows in on
new information instead of looping.

```
Turn 1: User: "I need software installed"
Turn 2: User: "docker desktop"
Turn 3: User: "for development"
Expected: every turn whose reply is a question (follow_up_question set, or
          the content contains "?") is textually distinct from every
          question asked earlier in the same session
```
Automated in `backend/tests/unit/test_chat_golden_conversations.py::
TestFluidChat::test_no_repeated_question`.

---

## Scenario 23: Unknown install request — honest hand-off, no fabricated steps (fluid chat)

**Flag**: `FEATURE_FLUID_CHAT=true`.

**Expected behavior**: When the KB has no article for the actual request
(e.g. installing Docker Desktop — a same-family "software" request but with
no subtype-matched article), the agent must not dress up a generic,
unrelated troubleshooting ladder as if it were a real fix. It must instead
hand off honestly (offer a specialist / ticket).

```
Turn 1: User: "I need to install docker desktop"
Turn 2: User: "to develop my application"
Turn 3: User: "yes"
Turn 4: User: "no specific error, it's just not installed yet"
Turn 5: User: "yes"
Expected: final reply does NOT contain "run as administrator" or
          "restart your computer" (or any other fabricated generic step);
          the reply offers a specialist / sets requires_escalation or
          escalation_offered
```

This is the probe for the Task-6 weak-match honest-handoff gate: a
same-family, wrong-subtype, high-relevance generic article could otherwise
score high enough (e.g. ~0.55) to slip past a naive `confidence < 0.35`
check and still be presented as a resolution. In this codebase the gate in
`backend/app/workflows/nodes/resolution.py` (`_score_confidence` /
`compute_resolution_confidence`) already folds `has_subtype_article` into
the composite confidence, so a subtype-less match is pulled below
`FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE` (0.35) before the honest-handoff check
runs — no additional change to `resolution.py` was needed to pass this
scenario (verified: the gap did not manifest here; see
`task-7-report.md`). A confident, subtype-matched issue (Scenario 21) still
returns steps unaffected — see
`backend/tests/unit/test_resolution_node.py::
test_fluid_confident_match_still_returns_steps`.

Automated in `backend/tests/unit/test_chat_golden_conversations.py::
TestFluidChat::test_docker_install_no_fabricated_generic_steps`.
