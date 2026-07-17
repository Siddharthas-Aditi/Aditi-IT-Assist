# Conversational One-Step-at-a-Time Chat (B1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the employee chat guide troubleshooting like a human specialist — one concrete step per turn (click-path in prose), proactively offering a live specialist after 3 consecutive misses, with LLM-phrased escalation and ticketing messages.

**Architecture:** Reduce the resolver's per-turn batch to 1 (reusing the existing tried-step progression), add a miss-threshold escalation gate, and route escalation/ticketing wording through the existing warm-persona LLM generator pattern (`conversation_messages.py`) with deterministic fallbacks. Frontend renders the single-step reply as prose (no timeline card). No control-flow/guardrail changes.

**Tech Stack:** Python 3.12 / FastAPI / pytest / Ruff (backend); React 18 / TypeScript / Vitest / ESLint (frontend).

## Global Constraints

- Backend line length ≤ 100; `cd backend && uv run ruff check . && uv run ruff format --check .` clean.
- Frontend: strict TS, no `any`; `cd frontend && npm run lint` (max-warnings=0) and `npm run typecheck` clean.
- LLM only *phrases*. Steps come only from grounded KB. Escalation gating (`handoff_context_sufficient`) and ticket explicit-confirmation + idempotency are unchanged. Every new LLM generator has a deterministic fallback equal to today's wording so no-LLM behavior is preserved.
- New config settings are additive with safe defaults (`RESOLUTION_STEP_BATCH_SIZE=1`, `RESOLUTION_MISS_ESCALATE_THRESHOLD=3`).
- Run backend commands from `backend/` via `uv`; frontend from `frontend/` via `npm`.

---

### Task 1: Config + one-step batch + single-step prose

**Files:**
- Modify: `backend/app/core/config.py` (add settings near line 208, after `LIVE_CHAT_IDLE_*`)
- Modify: `backend/app/workflows/nodes/resolution.py` (`_BATCH_SIZE` line 22 + use at line 305; `RESOLUTION_PROMPT`/`RESOLUTION_SYSTEM_PROMPT` lines 24-60; `_format_concise_response` lines 539-583)
- Test: `backend/tests/unit/test_resolution_one_step.py` (create)

**Interfaces:**
- Consumes: `get_settings()` from `app.core.config`; `_build_progression`, `_render_resolution`, `DiagnosticContext`.
- Produces: resolver presents `settings.RESOLUTION_STEP_BATCH_SIZE` (default 1) steps/turn; single-step fallback prose includes the click-path and omits the "laid out below" pointer.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_resolution_one_step.py`:

```python
"""B1: the resolver presents one step per turn and advances on the next turn."""

import pytest

from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes import resolution as R


def _kb():
    return [
        {
            "title": "Laptop Keyboard Not Working",
            "category": "hardware/laptop",
            "subcategory": "keyboard-not-working",
            "resolution_steps": [
                {"step_number": 1, "instruction": "Check for physical obstructions",
                 "details": "Remove dust or debris; ensure no key is stuck."},
                {"step_number": 2, "instruction": "Restart the laptop",
                 "details": "Restart and test the keyboard again."},
                {"step_number": 3, "instruction": "Test with the On-Screen Keyboard",
                 "details": "Settings -> Accessibility -> Keyboard."},
            ],
        }
    ]


def _ctx():
    ctx = DiagnosticContext()
    ctx.issue_category = "hardware/laptop"
    ctx.issue_subtype = "keyboard-not-working"
    ctx.symptom = "keyboard not working"
    return ctx


@pytest.mark.asyncio
async def test_presents_single_step_first_turn():
    ctx = _ctx()
    state = {"knowledge_results": _kb(), "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert len(result["resolution_steps"]) == 1
    assert result["resolution_steps"][0]["instruction"] == "Check for physical obstructions"


@pytest.mark.asyncio
async def test_advances_to_next_step_after_failure():
    ctx = _ctx()
    # Simulate step 1 already suggested and failed.
    ctx.record_suggested_steps(["Check for physical obstructions"])
    ctx.mark_last_batch_failed()
    state = {"knowledge_results": _kb(), "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert len(result["resolution_steps"]) == 1
    assert result["resolution_steps"][0]["instruction"] == "Restart the laptop"


def test_fallback_prose_single_step_has_no_below_pointer():
    steps = [{"step_number": 1, "instruction": "Restart the laptop",
              "details": "Settings -> Update."}]
    ctx = _ctx()
    prose = R._format_concise_response(steps, _kb()[0], 0.7, ctx)
    assert "just below" not in prose.lower()
    assert "laid out" not in prose.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_resolution_one_step.py -v`
Expected: FAIL — `test_presents_single_step_first_turn` gets 3 steps (batch=3); fallback still says "laid out below".

- [ ] **Step 3: Add config settings**

In `backend/app/core/config.py`, after the `LIVE_CHAT_IDLE_END_SECONDS` line (~209) add:

```python
    # ── Conversational chat (B1) ─────────────────────────────────────
    # How many troubleshooting steps to present per turn. 1 = guide one step
    # at a time like a human specialist.
    RESOLUTION_STEP_BATCH_SIZE: int = 1
    # Proactively offer a live specialist after this many consecutive steps
    # fail to resolve the issue (instead of walking every remaining step).
    RESOLUTION_MISS_ESCALATE_THRESHOLD: int = 3
```

- [ ] **Step 4: Use the config batch size in resolution.py**

In `backend/app/workflows/nodes/resolution.py`:
- Add import at the top (with the other `app.core` imports): `from app.core.config import get_settings`
- Delete the module constant `_BATCH_SIZE = 3` (line 22) and its comment (line 21).
- At the batch slice (line 305), replace:

```python
    batch = remaining[:_BATCH_SIZE]
```
with:
```python
    batch_size = max(1, get_settings().RESOLUTION_STEP_BATCH_SIZE)
    batch = remaining[:batch_size]
```

- [ ] **Step 5: Update the prompts to put the click-path in prose**

In `RESOLUTION_SYSTEM_PROMPT` (lines 24-41), replace the line:
```python
    "- The precise click-by-click steps are shown to the user separately, so you don't need\n"
    "  to repeat them verbatim — summarise the gist naturally and point to them.\n"
```
with:
```python
    "- Include the concrete actions (e.g. the exact menu path like Settings > "
    "Accessibility > Keyboard) naturally inside your sentences — the user does NOT "
    "see a separate steps list, so the how-to must live in your reply.\n"
    "- Focus on the SINGLE next step; do not preview later steps.\n"
```

In `RESOLUTION_PROMPT` (lines 43-60), replace the "Approved next steps" paragraph (lines 50-53):
```python
Approved next steps you may rely on (the user already sees these as a numbered list —
explain them naturally in your own words, do NOT paste them as a list, and do NOT add
any step that is not here):
{knowledge_articles}
```
with:
```python
The approved next step you may rely on (explain it naturally in your own words,
including the exact click-path/actions, and do NOT add any step that is not here.
The user does NOT see a separate list — put the how-to in your reply):
{knowledge_articles}
```

- [ ] **Step 6: Fix the single-step fallback prose**

In `_format_concise_response` (lines 539-583), change the multi-step pointer (lines 570-571) so it only fires for genuine multi-step batches AND, for the single-step case, weave the detail in. Replace:

```python
    if len(steps) > 1:
        parts.append("I've laid out the exact steps for you just below.")
```
with:
```python
    detail = steps[0].get("details")
    if len(steps) == 1 and detail:
        parts.append(f"Specifically: {detail}")
    elif len(steps) > 1:
        parts.append("Here are the exact steps to try.")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_resolution_one_step.py -v`
Expected: PASS.

- [ ] **Step 8: Lint + commit**

```bash
cd backend && uv run ruff check app/core/config.py app/workflows/nodes/resolution.py tests/unit/test_resolution_one_step.py && uv run ruff format --check app/core/config.py app/workflows/nodes/resolution.py
cd ..
git add backend/app/core/config.py backend/app/workflows/nodes/resolution.py backend/tests/unit/test_resolution_one_step.py
git commit -m "feat(chat): one step at a time — batch size config + click-path in prose"
```

---

### Task 2: Proactive escalation after N consecutive misses

**Files:**
- Modify: `backend/app/workflows/nodes/resolution.py` (in `resolution_node`, after `_build_progression` at line 267, before the exhaustion check at line 270)
- Test: `backend/tests/unit/test_resolution_one_step.py` (append)

**Interfaces:**
- Consumes: `DiagnosticContext.failed_steps` (each miss appends one step when batch=1), `settings.RESOLUTION_MISS_ESCALATE_THRESHOLD`, `DiagnosticPhase.ESCALATING`.
- Produces: when `len(failed_steps) >= threshold`, the node routes to escalation (sets `phase=ESCALATING`, `escalation_reason`, empty `resolution_steps`) even if steps remain.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_resolution_one_step.py`:

```python
@pytest.mark.asyncio
async def test_escalates_after_threshold_misses_even_with_steps_left():
    ctx = _ctx()
    # 3 distinct steps already tried and failed (threshold default = 3),
    # but the article still has more steps available.
    ctx.record_suggested_steps(
        ["Check for physical obstructions", "Restart the laptop",
         "Test with the On-Screen Keyboard"]
    )
    ctx.mark_last_batch_failed()
    kb = _kb()
    kb[0]["resolution_steps"].append(
        {"step_number": 4, "instruction": "Check the keyboard language",
         "details": "Settings -> Time & Language."}
    )
    state = {"knowledge_results": kb, "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    # Routed to escalation: no steps presented, phase escalating.
    assert result["resolution_steps"] == []
    assert result["conversation_phase"] == "escalating"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_resolution_one_step.py::test_escalates_after_threshold_misses_even_with_steps_left -v`
Expected: FAIL — the node presents step 4 instead of escalating.

- [ ] **Step 3: Add the miss-threshold gate**

In `resolution.py::resolution_node`, immediately AFTER `ordered, remaining = _build_progression(knowledge_results, diag_ctx)` (line 267) and BEFORE the `if not remaining:` block (line 270), insert:

```python
    # ── Proactive escalation after N consecutive misses (B1) ──────────
    # Even if more grounded steps exist, don't drag the user through all of
    # them — offer a live specialist once enough steps have failed.
    miss_threshold = max(1, get_settings().RESOLUTION_MISS_ESCALATE_THRESHOLD)
    if remaining and len(diag_ctx.failed_steps) >= miss_threshold:
        diag_ctx.resolution_attempts += 1
        diag_ctx.resolution_confidence = 0.0
        diag_ctx.phase = DiagnosticPhase.ESCALATING
        diag_ctx.last_response_type = "escalate"
        subtype = diag_ctx.issue_subtype or diag_ctx.symptom or "this issue"
        diag_ctx.escalation_reason = (
            f"{len(diag_ctx.failed_steps)} troubleshooting steps for '{subtype}' were "
            f"attempted without resolving the issue."
        )
        logger.info(
            "resolution_miss_threshold_escalation",
            failed=len(diag_ctx.failed_steps),
            threshold=miss_threshold,
        )
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "escalation_reason": diag_ctx.escalation_reason,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "audit_trail": [
                {
                    "event": "resolution.miss_threshold_escalation",
                    "failed_steps": len(diag_ctx.failed_steps),
                    "threshold": miss_threshold,
                }
            ],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_resolution_one_step.py -v`
Expected: PASS (all, including Task 1's).

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uv run ruff check app/workflows/nodes/resolution.py tests/unit/test_resolution_one_step.py && uv run ruff format --check app/workflows/nodes/resolution.py
cd ..
git add backend/app/workflows/nodes/resolution.py backend/tests/unit/test_resolution_one_step.py
git commit -m "feat(chat): proactively offer a specialist after N consecutive misses"
```

---

### Task 3: LLM-phrase escalation messages

**Files:**
- Modify: `backend/app/services/agents/conversation_messages.py` (add two generators + fallbacks; export if there is an `__all__`)
- Modify: `backend/app/workflows/nodes/escalation.py` (call the generators in `escalation_node`, lines 58-66)
- Test: `backend/tests/unit/test_conversation_messages_ops.py` (create)

**Interfaces:**
- Consumes: `get_llm_service()`, `_PERSONA`, `DiagnosticContext`.
- Produces: `async generate_escalation_offer(diag_ctx, reason) -> str` and `async generate_escalation_confirmed(diag_ctx) -> str`, each returning LLM text when available else the deterministic fallback (byte-identical to today's wording).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_conversation_messages_ops.py`:

```python
"""B1: escalation + ticketing messages are LLM-phrased with deterministic fallbacks."""

import pytest

import app.services.agents.conversation_messages as CM
from app.services.agents.diagnostic_state import DiagnosticContext


class _FakeLLM:
    def __init__(self, available, text=""):
        self.is_available = available
        self._text = text

    async def complete(self, prompt, system_prompt=None, temperature=0.8, max_tokens=200):
        return self._text


@pytest.fixture
def ctx():
    c = DiagnosticContext()
    c.affected_system = "your laptop"
    return c


@pytest.mark.asyncio
async def test_escalation_offer_uses_llm(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service",
                        lambda: _FakeLLM(True, "I'll bring in our IT team to help you further."))
    msg = await CM.generate_escalation_offer(ctx, "steps exhausted")
    assert msg == "I'll bring in our IT team to help you further."


@pytest.mark.asyncio
async def test_escalation_offer_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_escalation_offer(ctx, "steps exhausted")
    assert "IT team" in msg and len(msg) > 20


@pytest.mark.asyncio
async def test_escalation_confirmed_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_escalation_confirmed(ctx)
    assert "connect" in msg.lower() and len(msg) > 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_conversation_messages_ops.py -v`
Expected: FAIL — `generate_escalation_offer`/`generate_escalation_confirmed` do not exist.

- [ ] **Step 3: Add the generators**

Append to `backend/app/services/agents/conversation_messages.py`:

```python
# ═══════════════════════════════════════════════════════════════════════════════
#  ESCALATION — offering / confirming a handoff to the IT team
# ═══════════════════════════════════════════════════════════════════════════════

_ESCALATION_OFFER_PROMPT = """You could not fully resolve the user's IT issue and want to
hand off to the human IT team. Warmly let them know you'll bring in the IT team and that
you'll pass along everything from the conversation so they don't have to repeat themselves.
Keep it to 1-2 sentences. Do not promise a specific time.

Context (for you — do NOT echo labels): system = {system}; why escalating = {reason}."""


async def generate_escalation_offer(diag_ctx: "DiagnosticContext", reason: str) -> str:
    """Natural escalation message. Falls back to a deterministic template."""
    llm = get_llm_service()
    system = diag_ctx.affected_system or diag_ctx.normalized_system or "your system"
    if llm.is_available:
        try:
            content = await llm.complete(
                _ESCALATION_OFFER_PROMPT.format(system=system, reason=reason),
                system_prompt=_PERSONA,
                temperature=0.8,
                max_tokens=140,
            )
            if content and len(content) > 20:
                return content.strip()
        except Exception as exc:
            logger.warning("escalation_offer_llm_error", error=str(exc))
    return _fallback_escalation_offer(system)


def _fallback_escalation_offer(system: str) -> str:
    return (
        f"I wasn't able to fully sort out your {system} issue on my own, but our IT team "
        f"can help from here. I'll include everything from our conversation so they can "
        f"pick up right where we left off."
    )


_ESCALATION_CONFIRMED_PROMPT = """The user just agreed to be connected to the IT team.
Reassure them warmly that you're connecting them now and have shared the full context.
Keep it to 1-2 sentences."""


async def generate_escalation_confirmed(diag_ctx: "DiagnosticContext") -> str:
    """Natural 'connecting you now' message. Falls back to a template."""
    llm = get_llm_service()
    if llm.is_available:
        try:
            content = await llm.complete(
                _ESCALATION_CONFIRMED_PROMPT,
                system_prompt=_PERSONA,
                temperature=0.7,
                max_tokens=100,
            )
            if content and len(content) > 20:
                return content.strip()
        except Exception as exc:
            logger.warning("escalation_confirmed_llm_error", error=str(exc))
    return _fallback_escalation_confirmed()


def _fallback_escalation_confirmed() -> str:
    return (
        "Perfect! I'm connecting you with our IT team now. I've included everything from "
        "our conversation so they can help you right away."
    )
```

Note: if the file defines `__all__`, add the four new public names (`generate_escalation_offer`, `generate_escalation_confirmed`, and the Task-4 ones) to it. If not, skip.

- [ ] **Step 4: Wire the escalation node**

In `backend/app/workflows/nodes/escalation.py`, add the import near the top:
```python
from app.services.agents.conversation_messages import (
    generate_escalation_confirmed,
    generate_escalation_offer,
)
```
Replace the confirmed-branch message (lines 58-61):
```python
        message = (
            "Perfect! I'm connecting you with our IT team now. "
            "I've included everything from our conversation so they can help you right away."
        )
```
with:
```python
        message = await generate_escalation_confirmed(diag_ctx)
```
Replace the else-branch message (line 66) `message = _build_escalation_message(diag_ctx, reason)` with:
```python
        if diag_ctx.live_agent_requested:
            message = _build_escalation_message(diag_ctx, reason)
        else:
            message = await generate_escalation_offer(diag_ctx, reason)
```
(Keep `_build_escalation_message` for the live-agent-requested wording; the generator covers the rest.)

- [ ] **Step 5: Run tests + regressions**

Run: `cd backend && uv run pytest tests/unit/test_conversation_messages_ops.py tests/unit/test_workflow_nodes.py -v`
Expected: PASS. If a workflow test asserts the old literal escalation string, update it to assert the fallback wording (do not weaken the assertion).

- [ ] **Step 6: Lint + commit**

```bash
cd backend && uv run ruff check app/services/agents/conversation_messages.py app/workflows/nodes/escalation.py tests/unit/test_conversation_messages_ops.py && uv run ruff format --check app/services/agents/conversation_messages.py app/workflows/nodes/escalation.py
cd ..
git add backend/app/services/agents/conversation_messages.py backend/app/workflows/nodes/escalation.py backend/tests/unit/test_conversation_messages_ops.py
git commit -m "feat(chat): LLM-phrase escalation messages with deterministic fallback"
```

---

### Task 4: LLM-phrase ticketing messages

**Files:**
- Modify: `backend/app/services/agents/conversation_messages.py` (add two generators + fallbacks)
- Modify: `backend/app/workflows/nodes/ticketing.py` (offer message, lines 60-73)
- Modify: `backend/app/services/agents/chat_service.py` (`_format_response` post-create confirmation, lines 324-332; and the async caller that passes `ticket_ref`)
- Test: `backend/tests/unit/test_conversation_messages_ops.py` (append)

**Interfaces:**
- Consumes: `get_llm_service()`, `_PERSONA`.
- Produces: `async generate_ticket_offer(diag_ctx, priority, category) -> str` and `async generate_ticket_created(ticket_number, diag_ctx) -> str`. The ticket-created generator MAY include the ticket number (override of the persona's usual "no ticket numbers" rule). `_format_response` gains an optional `ticket_created_message: str | None = None` param; when a ticket was created it uses that message if provided, else the existing f-string fallback.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_conversation_messages_ops.py`:

```python
@pytest.mark.asyncio
async def test_ticket_offer_falls_back(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_ticket_offer(ctx, "high", "hardware/laptop")
    assert "ticket" in msg.lower() and len(msg) > 20


@pytest.mark.asyncio
async def test_ticket_created_includes_number(monkeypatch, ctx):
    monkeypatch.setattr(CM, "get_llm_service", lambda: _FakeLLM(False))
    msg = await CM.generate_ticket_created("INC-1001", ctx)
    assert "INC-1001" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_conversation_messages_ops.py -k ticket -v`
Expected: FAIL — generators don't exist.

- [ ] **Step 3: Add the ticketing generators**

Append to `backend/app/services/agents/conversation_messages.py`:

```python
# ═══════════════════════════════════════════════════════════════════════════════
#  TICKETING — offering to raise a ticket / confirming it was created
# ═══════════════════════════════════════════════════════════════════════════════

_TICKET_OFFER_PROMPT = """You want to offer to raise a support ticket for the IT team and
connect the user with a specialist. Warmly explain you can raise a {priority}-priority
ticket capturing everything discussed, and ask them to confirm (they can click
"Connect with a specialist" or reply yes). Keep it to 2-3 sentences."""


async def generate_ticket_offer(diag_ctx: "DiagnosticContext", priority: str,
                                category: str) -> str:
    """Natural ticket-offer message. Falls back to a deterministic template."""
    llm = get_llm_service()
    if llm.is_available:
        try:
            content = await llm.complete(
                _TICKET_OFFER_PROMPT.format(priority=priority),
                system_prompt=_PERSONA,
                temperature=0.7,
                max_tokens=160,
            )
            if content and len(content) > 20:
                return content.strip()
        except Exception as exc:
            logger.warning("ticket_offer_llm_error", error=str(exc))
    return _fallback_ticket_offer(priority)


def _fallback_ticket_offer(priority: str) -> str:
    return (
        f"I wasn't able to fully resolve this one on my own, so the best next step is our "
        f"IT team. I can raise a {priority}-priority support ticket with everything we've "
        f"covered and connect you with a specialist — just click "
        f"'Connect with a specialist' below or reply yes."
    )


# The persona normally avoids ticket numbers; the created-confirmation is the one
# place we intentionally include it because the number is the point of the message.
_TICKET_CREATED_PROMPT = """A support ticket was just created for the user. Confirm warmly
that ticket {number} is created, that you've shared the full conversation with the
specialist so they won't have to repeat anything, and that they'll stay in this chat
until a specialist picks it up. You MUST include the ticket number {number}. 2-3
sentences."""


async def generate_ticket_created(ticket_number: str,
                                  diag_ctx: "DiagnosticContext") -> str:
    """Natural ticket-created confirmation (includes the number). Falls back."""
    llm = get_llm_service()
    if llm.is_available:
        try:
            content = await llm.complete(
                _TICKET_CREATED_PROMPT.format(number=ticket_number),
                system_prompt=_PERSONA,
                temperature=0.6,
                max_tokens=160,
            )
            if content and ticket_number in content:
                return content.strip()
        except Exception as exc:
            logger.warning("ticket_created_llm_error", error=str(exc))
    return _fallback_ticket_created(ticket_number)


def _fallback_ticket_created(ticket_number: str) -> str:
    return (
        f"✅ I've created support ticket {ticket_number} and I'm sharing our full "
        f"conversation with the IT specialist — including what you asked, what I "
        f"understood, and the steps we already tried — so they can continue without "
        f"asking you to repeat everything.\n\nYou'll stay in this chat; a specialist "
        f"will pick it up shortly. Is there anything else I can help you with in the "
        f"meantime?"
    )
```

- [ ] **Step 4: Wire the ticket offer in the ticketing node**

In `backend/app/workflows/nodes/ticketing.py`, add the import:
```python
from app.services.agents.conversation_messages import generate_ticket_offer
```
Replace the unconfirmed-branch `message = (...)` block (lines 65-73) with:
```python
        message = await generate_ticket_offer(
            diag_ctx, ticket_draft["priority"], ticket_draft["category"]
        )
```
Confirm `diag_ctx` is in scope in this node; if the node parses it as `DiagnosticContext.from_dict(state.get("diagnostic_context") or {})` elsewhere, reuse that variable — otherwise add that parse line above this block. (Read the node to confirm before editing.)

- [ ] **Step 5: Wire the created-confirmation in chat_service**

In `backend/app/services/agents/chat_service.py`:
- Add the import: `from app.services.agents.conversation_messages import generate_ticket_created`
- Change `_format_response` signature to accept `ticket_created_message: str | None = None`.
- Replace the ticket confirmation block (lines 324-332) with:
```python
        if ticket_ref is not None:
            content = ticket_created_message or (
                f"✅ I've created support ticket **{ticket_ref.ticket_number}** and I'm "
                f"sharing our full conversation with the IT specialist — including what you "
                f"asked, what I understood, and the steps we already tried — so they can "
                f"continue without asking you to repeat everything.\n\n"
                f"You'll stay in this chat; a specialist will pick it up shortly. Is there "
                f"anything else I can help you with in the meantime?"
            )
```
- In the async method that calls `_format_response(..., ticket_ref=...)` (search for `ticket_ref=` in this file — it's in the ticket-creation/confirm path), await the generator and pass it:
```python
            ticket_created_message = await generate_ticket_created(
                ticket_ref.ticket_number, diag_ctx
            )
            response = self._format_response(
                session_id, result, ticket_ref=ticket_ref,
                include_debug=include_debug,
                ticket_created_message=ticket_created_message,
            )
```
Read the surrounding code to get the exact variable names (`diag_ctx` may need to come from `result["diagnostic_context"]` — construct via `DiagnosticContext.from_dict(...)` if a context object isn't already at hand). Keep the fallback f-string intact so behavior is unchanged when the message isn't generated.

- [ ] **Step 6: Run tests + regressions**

Run: `cd backend && uv run pytest tests/unit/test_conversation_messages_ops.py tests/unit/test_chat_live_support_flow.py tests/unit/test_workflow_nodes.py -v`
Expected: PASS. Update any test asserting the old literal ticket-offer/created strings to assert the fallback wording (which is byte-identical), not weaker.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && uv run ruff check app/services/agents/conversation_messages.py app/workflows/nodes/ticketing.py app/services/agents/chat_service.py tests/unit/test_conversation_messages_ops.py && uv run ruff format --check app/services/agents/conversation_messages.py app/workflows/nodes/ticketing.py app/services/agents/chat_service.py
cd ..
git add backend/app/services/agents/conversation_messages.py backend/app/workflows/nodes/ticketing.py backend/app/services/agents/chat_service.py backend/tests/unit/test_conversation_messages_ops.py
git commit -m "feat(chat): LLM-phrase ticket offer + created confirmation with fallback"
```

---

### Task 5: Frontend single-step rendering

**Files:**
- Read then Modify: the **live** employee chat component that renders the steps card. Per the Task-1 review this is `frontend/src/pages/employee/SupportChatPage.tsx` (~lines 629-653, a bordered "Troubleshooting Steps" card rendered **unconditionally when `resolution_steps` is non-empty** — including for a single step). Also check `frontend/src/features/chat/ChatBubble.tsx` (`ProseContent`/`proseSingleStep`) since it renders steps too — fix whichever component(s) are actually mounted in the employee chat route.
- Test: a test co-located with the component you modify (create or extend — check if one exists first).

**IMPORTANT (corrected from original plan):** The original plan assumed the card was gated on `steps.length > 1` in `ChatBubble.tsx`. The live page renders it unconditionally in `SupportChatPage.tsx`. So the real change is: **for the one-step flow, do NOT render the duplicate "Troubleshooting Steps" card** (the click-path now lives in the prose). Decide the cleanest rule — e.g. suppress the card when there is exactly one step, OR remove the card from the employee-facing single-step flow entirely — and apply it to the live component. Confirm which component is mounted by tracing the employee chat route before editing.

**Interfaces:**
- Consumes: the `ChatMessage` type (`content`, `steps?`, `conversationPhase`) from `frontend/src/types`.
- Produces: a single-step bot message renders its `content` as plain conversational prose (no numbered-pill reformatting, no "Resolution Steps" timeline card). Confirm buttons still show when `conversationPhase === 'confirming'`.

- [ ] **Step 1: Inspect the component**

Run: `cd frontend && sed -n '1,120p' src/features/chat/ChatBubble.tsx` and note the `hasMultipleSteps` gate (`steps.length > 1`, keep it) and the `proseSingleStep`/`ProseContent` numbered-pill logic that reformats "1. …"/"Step 1:" lines — that reformatting must NOT turn conversational prose into pills for the one-step flow. Also confirm whether `ChatBubble.test.tsx` exists.

- [ ] **Step 2: Write the failing test**

Create/extend `frontend/src/features/chat/ChatBubble.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ChatBubble } from './ChatBubble';

describe('ChatBubble single-step reply', () => {
  it('renders one-step prose without a Resolution Steps card', () => {
    const message = {
      id: '1',
      role: 'assistant' as const,
      content:
        "Let's start simple — open Settings > Accessibility > Keyboard and turn on the " +
        'On-Screen Keyboard to check whether it types. Give that a try and tell me how it goes.',
      steps: [{ step_number: 1, instruction: 'Test with the On-Screen Keyboard', details: null }],
      conversationPhase: 'confirming',
    };
    render(<ChatBubble message={message as never} />);
    expect(screen.queryByText(/Resolution Steps/i)).toBeNull();
    expect(screen.getByText(/On-Screen Keyboard/i)).toBeInTheDocument();
  });
});
```

Adjust the `message` object and `ChatBubble` props to match the real `ChatMessage`/props shape found in Step 1 (import the type; don't invent fields).

- [ ] **Step 3: Run test to verify it fails or reveals the prop shape**

Run: `cd frontend && npx vitest run src/features/chat/ChatBubble.test.tsx`
Expected: FAIL (or a type/props error that tells you the exact shape to use). Fix the test's props to the real shape, then it should fail on the assertion if the card/pills render.

- [ ] **Step 4: Adjust the component**

In `ChatBubble.tsx`, ensure that for a single-step assistant message the `content` renders as plain prose (the `hasMultipleSteps` gate already hides the `StepTimeline` for one step). Remove or bypass the `proseSingleStep` numbered-pill reformatting so a one-step conversational reply is shown verbatim as prose. Do not change multi-step rendering.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/features/chat/ChatBubble.test.tsx`
Expected: PASS.

- [ ] **Step 6: Lint + typecheck + commit**

```bash
cd frontend && npm run lint && npm run typecheck
cd ..
git add frontend/src/features/chat/ChatBubble.tsx frontend/src/features/chat/ChatBubble.test.tsx
git commit -m "feat(chat): render single-step replies as conversational prose"
```

---

### Task 6: Regression sweep + full verification

**Files:**
- Modify (as needed): any golden-conversation / workflow test whose expectations assumed the 3-step batch or the old canned escalation/ticket strings.

- [ ] **Step 1: Run the chat/workflow regression suites**

Run: `cd backend && uv run pytest tests/unit/test_workflow_nodes.py tests/unit/test_diagnostic_conversation.py tests/unit/test_chat_live_support_flow.py tests/unit/test_conversation_behavior.py tests/unit/test_outlook_mailbox_full_flow.py -v`
Expected: PASS. For any failure caused by the intended B1 change (batch now 1, LLM-phrased strings), update the test's expectation to the new correct behavior/fallback wording — never weaken an assertion or delete a guardrail check. Report each such update.

- [ ] **Step 2: Full backend gate**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: lint clean, suite green (note any pre-existing unrelated failures explicitly).

- [ ] **Step 3: Full frontend gate**

Run: `cd frontend && npm run lint && npm run typecheck && npx vitest run`
Expected: clean + green.

- [ ] **Step 4: Manual end-to-end (if a dev stack is available)**

Seed + run; in chat, take a laptop issue: confirm one step per turn with the click-path in the prose (no steps card), say "still not working" three times and confirm the agent proactively offers a specialist, then confirm the escalation + ticket-created messages read naturally.

- [ ] **Step 5: Commit any test expectation updates**

```bash
git add backend/tests
git commit -m "test(chat): update expectations for one-step + LLM-phrased ops messages"
```

---

## Self-Review

**Spec coverage:**
- One step per turn (spec §1) → Task 1. ✓
- Click-path in prose (spec §1) → Task 1 Steps 5-6. ✓
- Escalate after N misses (spec §2) → Task 2. ✓
- LLM-phrased escalation (spec §3) → Task 3. ✓
- LLM-phrased ticketing (spec §4) → Task 4. ✓
- Frontend single-step render (spec §5) → Task 5. ✓
- Testing (spec) → Tasks 1-6; guardrail preservation asserted by keeping/adjusting (not deleting) regression tests → Task 6. ✓
- Acceptance criteria 1-5 → Tasks 1-6 + Task 6 gates. ✓

**Placeholder scan:** Tasks 4 Step 5 and Task 5 contain read-then-edit instructions (exact caller variable names / component prop shape) rather than guessed code — deliberate, because those exact identifiers were not read during planning and guessing them would be wrong. Every generator, prompt, config, and threshold has complete code. No TBD/TODO.

**Type consistency:** Generator names are consistent between definition (Task 3/4), tests, and wiring (`generate_escalation_offer`, `generate_escalation_confirmed`, `generate_ticket_offer`, `generate_ticket_created`). `RESOLUTION_STEP_BATCH_SIZE` / `RESOLUTION_MISS_ESCALATE_THRESHOLD` names match across config, resolution.py, and tests. `_format_response`'s new `ticket_created_message` param name is consistent between definition and caller.

**Note for implementer:** Tasks 4 and 5 require reading the exact caller/prop shapes before editing (called out in-step). The `DiagnosticContext` import in `conversation_messages.py` is under `TYPE_CHECKING`; the new generators reference it only in annotations (as string literals `"DiagnosticContext"`), so no runtime import is added.
