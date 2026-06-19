# Employee Chat Experience

> What an Aditi employee sees and feels when using the IT Assist chat. The
> goal is conversational, professional, and grounded — closer to a great
> human IT analyst than to an FAQ bot.

---

## 1. Principles

1. **Talk first, not form-first.** Never make the user fill structured
   fields before describing their problem.
2. **Confirm understanding briefly.** One concise "did I get that right?"
   per issue, not a checklist of questions.
3. **One natural reply per turn.** Two to four sentences in conversational
   prose; structured steps shown separately when relevant.
4. **Progressive disclosure.** Three steps at a time, not the whole article
   dump.
5. **Never repeat a failed step.** If the user says it didn't work, the
   next batch must be new content.
6. **No pretending.** If the KB is silent, the bot says so and offers a
   specialist — it never invents.
7. **Explicit human handoff.** A ticket is only created when the user
   confirms.

---

## 2. Lifecycle of a chat turn

| Phase | What the user sees | What's happening |
|---|---|---|
| Greeting | "Hi there 👋 I'm the Aditi IT Support Assistant. What can I help with?" | Triage emits a warm intro when no issue is active. |
| Problem description | User types: *"Mailbox is full"*. | Intent classifier → `CONTINUE`; entity normalizer → `outlook`; subtype classifier → `mailbox-full`. |
| Confirm understanding | "Got it — just to make sure I've understood: your mailbox is full. Have I got that?" (varied openers) | One concise yes/no question. Quick-reply chips. |
| Solution turn | Natural reply ("It looks like your mailbox is full — that'll stop new mail until we free up space. The best place to start is to check your current mailbox size and quota …") + structured 3-step block beneath. | Specialist renders message; UI renders steps panel. |
| Follow-up: works | User says "Yes that worked!" → "Great — glad that resolved it 🎉." | `POSITIVE_FEEDBACK` → resolved close. |
| Follow-up: doesn't work | User says "didn't help" → "Thanks for trying — no worries, let's keep going. A good next step is to …" | `NEGATIVE_FEEDBACK` → next batch (no repeats). |
| New topic mid-flow | User says "I have another problem" → "Of course — what's the new issue?" | `NEW_TOPIC` → reset context; **no ticket created**. |
| Out of grounded steps | "I've gone through the things I can confidently help with. Want me to connect you with our IT team?" (offer, with chip) | Supervisor → `ESCALATE`. **Ticket is offered, not created.** |
| Explicit human ask | User clicks "Connect with a specialist" or types "talk to someone" → "✅ Ticket ITA-000123 created — a specialist will follow up." | `ESCALATE_REQUEST` → service creates ticket *with* full handoff package. |

---

## 3. Visible affordances

- **Quick-reply chips** for confirm questions and escalate offers.
- **Structured step panel** beside the natural reply (so the prose isn't a
  numbered dump).
- **Connect with a specialist** button visible whenever escalation is
  offered, hidden when a ticket already exists.
- **External-source badge** ("Vendor", "Official") on any web-fallback
  content the assistant surfaces.

---

## 4. What we deliberately don't do

- **Long disclaimers.** One short note is enough; the user is an employee,
  not a stranger.
- **Apology spam.** A single warm sentence on failure, then progress.
- **Numbered step dumps inside the natural reply.** The UI has a panel for
  that — the reply stays human.
- **Auto-create tickets.** Ever. Even after exhaustion, the bot offers and
  waits for explicit confirm.
- **Re-asking the same question.** If the user already gave information,
  the diagnostic context carries it forward.

---

## 5. Edge-case behaviors

| Situation | Behavior |
|---|---|
| User types nothing | Bot stays quiet (no auto-reply). |
| User types greeting mid-flow ("hey there") | Continues active issue; no reset. |
| User says "thanks!" after a fix | Warm close + invitation to start a new chat next time. |
| User typo on a system name ("outloook") | Entity normalizer fuzzy-matches; the bot picks up Outlook. |
| Same step suggested twice | Never. Tried-step memory enforces. |
| 10-turn limit reached | Auto-escalate with apology. |
| Backend error | "I'm having a temporary issue. Try again in a moment or email it-support@aditiconsulting.com." |

---

## 6. Acceptance tests

The behaviors above are covered by golden conversations in
[`docs/development/golden-conversations.md`](../development/golden-conversations.md)
and by the pytest suite under `backend/tests/unit/test_chat_*.py`. Any
behavior change here must update both.
