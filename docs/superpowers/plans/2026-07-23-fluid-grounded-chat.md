# Fluid, Grounded Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the employee AI chat converse like a real IT specialist — drop the forced "confirm understanding" round-trip, stop repeating clarifying questions, deliver the relevant grounded steps together, and hand off honestly when the KB genuinely lacks an answer — without loosening grounding.

**Architecture:** All new behavior is gated behind a single flag `FEATURE_FLUID_CHAT` (default off). Flag-off = exactly today's behavior (existing tests stay green). Flag-on = the fluid flow. Changes are confined to `triage.py`, `resolution.py`, `diagnostic_engine.py`/`playbooks.py`, `diagnostic_state.py`, prompts, and config. The grounding spine (`grounding.py`, `confidence.py`, `subtype_classifier.py`, escalation/ticketing, session store) is untouched.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph. Tests: pytest (async, mocked LLM). Frontend already tolerates the resulting change (no structural frontend work).

## Global Constraints

- New behavior MUST be gated by `settings.FEATURE_FLUID_CHAT` (default `False`). Flag-off path must be byte-for-byte today's behavior so existing tests pass unchanged.
- Grounding is never loosened: factual steps still come only from the KB via `_build_progression` (subtype-filtered). No LLM-authored fixes.
- Services/nodes don't change their return-dict contracts except as specified; `conversation_phase` values stay within `DiagnosticPhase`.
- Line length ≤100; Ruff `check` + `format` clean. Run backend tests in Docker: `docker compose exec -T backend uv run pytest <path> -q`.
- New tests assert fluid behavior by monkeypatching `settings.FEATURE_FLUID_CHAT = True` (mirror how existing tests set settings attrs). LLM stays mocked (`is_available=False`) unless a test explicitly needs the humanizer.
- Thresholds are config-driven (no magic numbers inline).

---

## File Structure

**Modify:**
- `backend/app/core/config.py` — `FEATURE_FLUID_CHAT` + two thresholds.
- `backend/app/services/agents/diagnostic_state.py` — `asked_questions` field + record/seen helpers; clear in `reset_issue_context`.
- `backend/app/services/agents/diagnostic_engine.py` — `evaluate_clarify_or_answer`: skip already-asked questions.
- `backend/app/services/agents/playbooks.py` — `get_next_question`: accept an "already asked" set to skip.
- `backend/app/workflows/nodes/triage.py` — skip forced confirm gate when confident; record asked questions.
- `backend/app/workflows/nodes/resolution.py` — group steps flag-on; weak-match honest escalation; feed conversation context to the humanizer.
- `backend/app/workflows/nodes/resolution.py` prompts (`RESOLUTION_SYSTEM_PROMPT`, `RESOLUTION_PROMPT`) — remove single-step wording flag-on.
- `backend/.env.example` — document `FEATURE_FLUID_CHAT`.

**Test files (extend):**
- `backend/tests/unit/test_diagnostic_conversation.py` (asked-questions + de-dup)
- `backend/tests/unit/test_conversation_behavior.py` (skip-confirm-when-confident, flag on/off)
- `backend/tests/unit/test_resolution_node.py` (grouped steps, weak-match escalation, flag on/off)
- `backend/tests/unit/test_chat_golden_conversations.py` (Docker scenario + structural fluid assertions)
- New: `backend/tests/unit/test_fluid_chat_config.py`

---

## Task 1: Config flag + thresholds

**Files:**
- Modify: `backend/app/core/config.py` (near the other `FEATURE_*` flags, ~line 234-298; thresholds near `RESOLUTION_STEP_BATCH_SIZE` ~245)
- Modify: `backend/.env.example`
- Test: `backend/tests/unit/test_fluid_chat_config.py`

**Interfaces produced:**
- `settings.FEATURE_FLUID_CHAT: bool` (default `False`)
- `settings.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE: float` (default `0.6`) — skip the confirm gate only when the classified subtype is at least this confident.
- `settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE: float` (default `0.35`) — below this composite resolution confidence, hand off honestly instead of presenting steps.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_fluid_chat_config.py
from __future__ import annotations

from app.core.config import Settings


def test_fluid_chat_flag_defaults_off():
    s = Settings()
    assert s.FEATURE_FLUID_CHAT is False


def test_fluid_chat_thresholds():
    s = Settings()
    assert s.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE == 0.6
    assert s.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE == 0.35
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_fluid_chat_config.py -q`
Expected: FAIL — attributes missing.

- [ ] **Step 3: Add the settings**

In `config.py`, in the `FEATURE_*` block:
```python
    # Fluid, grounded chat — natural IT-specialist conversation flow (sub-project A).
    # Off = today's scripted flow (confirm gate + one step at a time). See
    # docs/superpowers/specs/2026-07-23-fluid-grounded-chat-design.md.
    FEATURE_FLUID_CHAT: bool = False
    # Skip the "confirm understanding" gate only when the subtype is at least this
    # confident; below it, still ask to confirm (genuine ambiguity).
    FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE: float = 0.6
    # Below this composite resolution confidence, hand off honestly instead of
    # presenting (likely-generic) steps — the anti-fabrication guard.
    FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE: float = 0.35
```

In `.env.example`, near the other feature flags, add:
```
# Natural IT-specialist chat flow (drops forced confirm + one-step-at-a-time).
FEATURE_FLUID_CHAT=false
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_fluid_chat_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/.env.example backend/tests/unit/test_fluid_chat_config.py
git commit -m "feat(chat): add FEATURE_FLUID_CHAT flag + thresholds (default off)"
```

---

## Task 2: `DiagnosticContext.asked_questions` tracking

**Files:**
- Modify: `backend/app/services/agents/diagnostic_state.py`
- Test: `backend/tests/unit/test_diagnostic_conversation.py`

**Interfaces produced (on `DiagnosticContext`):**
- field `asked_questions: list[str]` (default empty) — normalized question texts already asked.
- `record_asked_question(self, question: str) -> None` — append normalized (reuse `_norm_step`); no-op on empty.
- `was_question_asked(self, question: str) -> bool` — normalized membership test.
- `reset_issue_context` also clears `asked_questions`.
- Serialized in `to_dict`/`from_dict` (follow the existing list-field pattern).

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/unit/test_diagnostic_conversation.py (TestDiagnosticContext)
def test_asked_questions_record_and_seen():
    from app.services.agents.diagnostic_state import DiagnosticContext

    ctx = DiagnosticContext()
    assert ctx.was_question_asked("What's happening with the application?") is False
    ctx.record_asked_question("What's happening with the application?")
    # normalized (case/whitespace-insensitive) match
    assert ctx.was_question_asked("what's happening   with the application?") is True
    # survives serialization
    ctx2 = DiagnosticContext.from_dict(ctx.to_dict())
    assert ctx2.was_question_asked("What's happening with the application?") is True
    # cleared on reset
    ctx2.reset_issue_context()
    assert ctx2.was_question_asked("What's happening with the application?") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_diagnostic_conversation.py -k asked_questions -q`
Expected: FAIL — no `record_asked_question`.

- [ ] **Step 3: Implement**

In `diagnostic_state.py` `DiagnosticContext`, add the field alongside the other troubleshooting-memory lists (near `suggested_steps`, ~line 101):
```python
    asked_questions: list[str] = field(default_factory=list)
```
Add methods (near `is_step_exhausted_or_seen`, reusing the existing `_norm_step` staticmethod):
```python
    def record_asked_question(self, question: str) -> None:
        norm = self._norm_step(question)
        if norm and norm not in self.asked_questions:
            self.asked_questions.append(norm)

    def was_question_asked(self, question: str) -> bool:
        return self._norm_step(question) in self.asked_questions
```
In `reset_issue_context`, add `self.asked_questions = []` alongside the other resets.
Ensure `to_dict`/`from_dict` round-trip `asked_questions` (mirror how `suggested_steps` is handled — if those use `asdict`/explicit dict, follow the same mechanism).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_diagnostic_conversation.py -k asked_questions -q`
Expected: PASS. Also run the whole file to confirm no serialization regression: `docker compose exec -T backend uv run pytest tests/unit/test_diagnostic_conversation.py -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/diagnostic_state.py backend/tests/unit/test_diagnostic_conversation.py
git commit -m "feat(chat): track asked clarifying questions on DiagnosticContext"
```

---

## Task 3: Never repeat a clarifying question (de-dup)

**Files:**
- Modify: `backend/app/services/agents/playbooks.py` (`IssuePlaybook.get_next_question`, ~73-91)
- Modify: `backend/app/services/agents/diagnostic_engine.py` (`evaluate_clarify_or_answer`, ~196-244)
- Modify: `backend/app/workflows/nodes/triage.py` (record the asked question when a clarify/confirm question is emitted)
- Test: `backend/tests/unit/test_diagnostic_conversation.py`

**Interfaces:**
- Consumes: `DiagnosticContext.was_question_asked` / `record_asked_question` (Task 2), `settings.FEATURE_FLUID_CHAT` (Task 1).
- Changes: `get_next_question(self, filled_slots, clarification_count, *, asked: set[str] | None = None)` — when `asked` is given, skip any candidate question whose normalized text is in `asked`; if all remaining candidates were asked, return `None` (→ caller proceeds instead of re-asking). Default `asked=None` preserves today's behavior.
- `evaluate_clarify_or_answer(context)` — flag-on: pass `asked={norm of each in context.asked_questions}` into `get_next_question`; if it returns `None`, set `decision.should_clarify=False` (proceed).

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/unit/test_diagnostic_conversation.py
def test_clarify_does_not_repeat_asked_question(monkeypatch):
    from app.core.config import settings
    from app.services.agents.diagnostic_state import DiagnosticContext
    from app.services.agents.diagnostic_engine import evaluate_clarify_or_answer

    monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
    ctx = DiagnosticContext(issue_category="software")
    first = evaluate_clarify_or_answer(ctx)
    assert first.should_clarify and first.question
    ctx.record_asked_question(first.question)
    # Same unchanged context: must NOT return the identical question again.
    second = evaluate_clarify_or_answer(ctx)
    assert not (second.should_clarify and second.question == first.question)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_diagnostic_conversation.py -k repeat -q`
Expected: FAIL — the same question is returned twice.

- [ ] **Step 3: Implement**

`playbooks.py` `get_next_question` — add the keyword-only `asked` param and skip:
```python
    def get_next_question(self, filled_slots, clarification_count, *, asked=None):
        asked = asked or set()
        for q in sorted(self.questions, key=lambda x: x.priority):
            # ... existing skip conditions (slot filled / condition / skip_if) ...
            norm = " ".join((q.question or "").lower().split())
            if norm in asked:
                continue
            return q
        return None
```
(Keep the existing skip logic exactly; only add the `asked` skip + the keyword-only param.)

`diagnostic_engine.py` `evaluate_clarify_or_answer` — flag-on, thread asked-set and handle `None`:
```python
    from app.core.config import settings
    asked = None
    if settings.FEATURE_FLUID_CHAT:
        asked = {" ".join(q.lower().split()) for q in context.asked_questions}
    next_q = playbook.get_next_question(filled, context.clarification_count, asked=asked)
    if next_q is None:
        return ClarifyOrAnswerDecision(should_clarify=False, question=None, options=[], reason="...")
    # ... unchanged ...
```

`triage.py` — when the clarify branch (798-835) and the confirm branch (841-870) emit a question, record it (flag-on):
```python
    if settings.FEATURE_FLUID_CHAT:
        diag_ctx.record_asked_question(question_text)  # the exact text sent to the user
```
(Do this for both `decision.question` in the clarify branch and the confirm `question` — so a re-entry never repeats.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_diagnostic_conversation.py -q`
Expected: PASS. Then confirm flag-off unchanged: `docker compose exec -T backend uv run pytest tests/unit/test_triage.py tests/unit/test_conversation_behavior.py -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/playbooks.py backend/app/services/agents/diagnostic_engine.py backend/app/workflows/nodes/triage.py backend/tests/unit/test_diagnostic_conversation.py
git commit -m "feat(chat): never repeat a clarifying question (flag-gated)"
```

---

## Task 4: Skip the forced confirm gate when confident

**Files:**
- Modify: `backend/app/workflows/nodes/triage.py` (confirm gate ~837-870)
- Test: `backend/tests/unit/test_conversation_behavior.py`

**Interfaces:**
- Consumes: `settings.FEATURE_FLUID_CHAT`, `settings.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE` (Task 1).
- New helper in triage.py: `_confident_understanding(diag_ctx: DiagnosticContext) -> bool` — `True` when `diag_ctx.issue_category` and `diag_ctx.issue_subtype` are set and `diag_ctx.subtype_confidence >= settings.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE`.
- Behavior: flag-on AND `_confident_understanding` → **do not** set `awaiting_confirmation`; fall through to the proceed/diagnosing return (so the graph routes to retrieval and the reply is the actual help). Flag-off OR ambiguous → unchanged confirm gate.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/unit/test_conversation_behavior.py
import pytest
from app.core.config import settings
from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes.triage import triage_node
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_confident_issue_skips_confirm_when_fluid(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
    # A confidently-classified issue (subtype set, high confidence).
    ctx = DiagnosticContext(
        issue_category="email/outlook", issue_subtype="mailbox-full",
        subtype_confidence=0.9, symptom="mailbox full",
    )
    state = {
        "messages": [HumanMessage(content="my outlook mailbox is full")],
        "diagnostic_context": ctx.to_dict(),
    }
    out = await triage_node(state)
    # No forced confirm turn: it proceeds to diagnosing, not a "confirm" clarify.
    assert out.get("conversation_phase") == "diagnosing"
    assert out.get("needs_clarification") in (False, None)

@pytest.mark.asyncio
async def test_ambiguous_issue_still_confirms_when_fluid(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
    ctx = DiagnosticContext(issue_category="software", subtype_confidence=0.2)
    state = {
        "messages": [HumanMessage(content="something is wrong")],
        "diagnostic_context": ctx.to_dict(),
    }
    out = await triage_node(state)
    assert out.get("needs_clarification") is True
```

> Use `_no_llm()` from test_conversation_behavior.py if present so the keyword path runs. Adjust the exact `DiagnosticContext` fields to whatever `_confident_understanding` reads. The assertion targets behavior (phase/needs_clarification), not wording.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_conversation_behavior.py -k "skips_confirm or still_confirms" -q`
Expected: FAIL — confident issue still hits the confirm gate (`needs_clarification=True`, phase clarifying).

- [ ] **Step 3: Implement**

In triage.py add the helper (near the other `_is_*` helpers):
```python
def _confident_understanding(diag_ctx: DiagnosticContext) -> bool:
    return bool(
        diag_ctx.issue_category
        and diag_ctx.issue_subtype
        and diag_ctx.subtype_confidence >= settings.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE
    )
```
At the confirm gate (~841), guard it:
```python
    skip_confirm = settings.FEATURE_FLUID_CHAT and _confident_understanding(diag_ctx)
    if not skip_confirm and not diag_ctx.understanding_confirmed and not diag_ctx.last_resolution_failed:
        diag_ctx.awaiting_confirmation = True
        # ... unchanged confirm return ...
```
When `skip_confirm` is True, control falls through to the existing proceed/diagnosing return (894-908) — no confirm turn. (`understanding_confirmed` stays False but is no longer required on the confident path; verify no downstream code hard-requires it when flag-on — resolution keys off knowledge_results, not this flag.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_conversation_behavior.py -q`
Expected: PASS, including the existing `TestConfirmUnderstanding` (flag-off, unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/workflows/nodes/triage.py backend/tests/unit/test_conversation_behavior.py
git commit -m "feat(chat): skip confirm gate for confident issues (flag-gated)"
```

---

## Task 5: Deliver grounded steps together + context carry-over

**Files:**
- Modify: `backend/app/workflows/nodes/resolution.py` (prompts 22-60; batch logic ~267-315; `_llm_resolution` ~360-422)
- Test: `backend/tests/unit/test_resolution_node.py`

**Interfaces:**
- Consumes: `settings.FEATURE_FLUID_CHAT`.
- Behavior flag-on: present ALL currently-`remaining` steps for the matched subtype in one reply (capped at a small max, e.g. 5, to avoid a wall), instead of `RESOLUTION_STEP_BATCH_SIZE` (=1). Keep recording every presented step in `suggested_steps` so a later "still not working" advances correctly. The humanizer prompt no longer says "SINGLE next step"; it's told to give the relevant steps together, conversationally, and to reference the recent conversation.
- The batch selection is the only behavior change; grounding (`_build_progression` subtype filter) is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/unit/test_resolution_node.py
@pytest.mark.asyncio
async def test_fluid_groups_multiple_steps(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
    # knowledge_results with a subtype-matching article that has 3 short steps;
    # LLM mocked unavailable so the deterministic renderer returns all steps.
    state = _state_with_article(  # existing helper in the test file
        subtype="mailbox-full",
        steps=["Check mailbox size", "Empty Deleted Items", "Archive old mail"],
    )
    out = await resolution_node(state)
    assert len(out["resolution_steps"]) >= 3  # grouped, not 1-at-a-time
```

> Reuse the file's existing state/article builders and its `is_available=False` LLM mock. If no builder exists, construct `state["knowledge_results"]` as the list-of-dicts shape `_build_progression` consumes (inspect an existing resolution test for the exact shape).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_resolution_node.py -k groups_multiple -q`
Expected: FAIL — only 1 step returned (batch size 1).

- [ ] **Step 3: Implement**

In `resolution_node` where `batch` is chosen (~batch = remaining[:batch_size]):
```python
    if settings.FEATURE_FLUID_CHAT:
        batch = remaining[: max(1, settings.RESOLUTION_FLUID_STEP_CAP)]
    else:
        batch = remaining[: settings.RESOLUTION_STEP_BATCH_SIZE]
```
Add `RESOLUTION_FLUID_STEP_CAP: int = 5` to config.py (Task 1 file; if adding here, include a one-line test). In `RESOLUTION_SYSTEM_PROMPT`, when flag-on use a variant without the "Focus on the SINGLE next step" line and with "Give the relevant steps together, in a natural short paragraph or tight list." Simplest: keep the constant but build the system prompt in `_llm_resolution` conditionally:
```python
    system = RESOLUTION_SYSTEM_PROMPT
    if settings.FEATURE_FLUID_CHAT:
        system = RESOLUTION_SYSTEM_PROMPT_FLUID  # same, minus the single-step line, plus grouping + context guidance
```
Add `RESOLUTION_SYSTEM_PROMPT_FLUID` next to the existing constant. In `_llm_resolution`, include the last few conversation turns in the user prompt (context carry-over) when flag-on — read `state`/`diag_ctx` for recent messages already available to the node (pass them into `_render_resolution`/`_llm_resolution`); keep the "use ONLY these approved steps" constraint verbatim.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_resolution_node.py tests/unit/test_resolution_one_step.py -q`
Expected: new test PASS; flag-off one-step tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workflows/nodes/resolution.py backend/app/core/config.py backend/tests/unit/test_resolution_node.py
git commit -m "feat(chat): deliver grounded steps together + context carry-over (flag-gated)"
```

---

## Task 6: Honest hand-off on weak grounding (anti-fabrication)

**Files:**
- Modify: `backend/app/workflows/nodes/resolution.py` (after `_score_confidence`, before presenting steps)
- Test: `backend/tests/unit/test_resolution_node.py`

**Interfaces:**
- Consumes: `settings.FEATURE_FLUID_CHAT`, `settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE`, the existing `ConfidenceBreakdown.final` from `_score_confidence`.
- Behavior flag-on: if the composite confidence for the batch is `< FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE` (i.e. the grounding is weak/generic — the Docker case), do **not** present the steps. Instead set `phase = ESCALATING`, `escalation_reason = "no confident grounded guidance"`, return empty `resolution_steps` (the escalation node then offers a specialist honestly). Flag-off OR confident → present steps as today.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/unit/test_resolution_node.py
@pytest.mark.asyncio
async def test_fluid_weak_match_hands_off_not_fabricates(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
    # A generic, non-subtype article (weak grounding → low composite confidence).
    state = _state_with_generic_article(  # build a state whose _score_confidence < 0.35
        category="software", subtype="other",
        steps=["Restart the app", "Run as administrator"],
    )
    out = await resolution_node(state)
    assert out["resolution_steps"] == []
    assert out["conversation_phase"] == "escalating"
```

> Construct the state so `_score_confidence` yields < 0.35 — a generic article that is not a subtype match (so `has_subtype_article` is false → grounding gate caps final low). Verify against `confidence.py` (grounding 0.0/0.3 → final capped ≤0.25) by inspecting the article/trace shape a matching resolution test uses.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_resolution_node.py -k weak_match -q`
Expected: FAIL — generic steps are presented (non-empty `resolution_steps`, phase confirming).

- [ ] **Step 3: Implement**

In `resolution_node`, right after computing the batch confidence (`_score_confidence` → `breakdown`), before rendering/returning steps:
```python
    if (
        settings.FEATURE_FLUID_CHAT
        and breakdown.final < settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE
    ):
        diag_ctx.phase = DiagnosticPhase.ESCALATING
        diag_ctx.escalation_reason = "no confident grounded guidance"
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": breakdown.final,
            "confidence_breakdown": breakdown.to_dict(),
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": "escalating",
            "escalation_reason": "no confident grounded guidance",
            "audit_trail": [ {"node": "resolve", "action": "honest_handoff_low_confidence"} ],
        }
```
(Match the exact escalation return shape already used at resolution.py:216-230 / 250-265 — copy its keys so the graph's `route_after_resolution` routes to escalate.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_resolution_node.py -q`
Expected: PASS; flag-off behavior unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workflows/nodes/resolution.py backend/tests/unit/test_resolution_node.py
git commit -m "feat(chat): honest hand-off on weak grounding instead of generic steps (flag-gated)"
```

---

## Task 7: Golden conversations + structural fluid assertions

**Files:**
- Modify: `backend/tests/unit/test_chat_golden_conversations.py`
- Modify: `docs/development/golden-conversations.md` (document the new scenarios)
- Test: the above.

**Interfaces:** consumes the whole flag-on pipeline via in-memory `ChatService` (existing harness: mocked `TicketService`, `InMemorySessionStore`, keyword classification).

- [ ] **Step 1: Write the failing tests** (flag-on, end-to-end)

```python
# add to backend/tests/unit/test_chat_golden_conversations.py
class TestFluidChat:
    async def test_confident_issue_no_confirm_turn(self, monkeypatch):
        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        svc = _make_chat_service()  # existing helper
        r1 = await svc.process_message(_msg("my outlook mailbox is full"))
        # First reply already helps — it is NOT a bare "is that right?" confirm.
        assert "is that what you're experiencing" not in r1.content.lower()

    async def test_no_repeated_question(self, monkeypatch):
        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        svc = _make_chat_service()
        sid = None
        seen: list[str] = []
        for msg in ["I need software installed", "docker desktop", "for development"]:
            r = await svc.process_message(_msg(msg, session_id=sid))
            sid = r.session_id
            if r.follow_up_question or "?" in r.content:
                q = r.content.strip().lower()
                assert q not in seen, f"repeated question: {q}"
                seen.append(q)

    async def test_docker_install_no_fabricated_generic_steps(self, monkeypatch):
        monkeypatch.setattr(settings, "FEATURE_FLUID_CHAT", True)
        svc = _make_chat_service()  # KB has no Docker-install article
        sid = None
        for msg in ["I need to install docker desktop", "to develop my application", "yes"]:
            r = await svc.process_message(_msg(msg, session_id=sid)); sid = r.session_id
        # Must NOT dispense the generic troubleshooting ladder; should offer a human.
        text = r.content.lower()
        assert "run as administrator" not in text
        assert "restart your computer" not in text
        assert r.requires_escalation or r.escalation_offered or "specialist" in text
```

> Use the file's existing `ChatService` construction + `_msg` helpers (read the top of the file). Adjust assertion strings to the actual generated copy if the deterministic (no-LLM) renderer differs; the intent is: no confirm-only turn, no repeated question, no generic-step fabrication for an unknown install request.

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec -T backend uv run pytest tests/unit/test_chat_golden_conversations.py -k Fluid -q`
Expected: FAIL initially where behavior isn't yet exercised end-to-end (or reveals wiring gaps — fix in the relevant node, not the test).

- [ ] **Step 3: Make them pass**

These should pass given Tasks 3–6 if the flag is threaded through every node. If a test fails, the gap is a missing flag-check on one path — fix in the node (do not weaken the assertion). Document the three scenarios in `docs/development/golden-conversations.md`.

- [ ] **Step 4: Verify + grounding non-regression**

Run:
```bash
docker compose exec -T backend uv run pytest tests/unit/test_chat_golden_conversations.py -q
docker compose exec -T backend uv run pytest tests/unit/test_grounding.py tests/unit/test_confidence.py tests/unit/test_retrieval_eval.py -q
```
Expected: all PASS (grounding/confidence/retrieval unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/test_chat_golden_conversations.py docs/development/golden-conversations.md
git commit -m "test(chat): golden fluid conversations + no-repeat/no-fabrication assertions"
```

---

## Task 8: Enable in dev + end-to-end verification

**Files:** `backend/.env` (local, gitignored — set the flag); verification only otherwise.

- [ ] **Step 1: Enable the flag in dev**

Set `FEATURE_FLUID_CHAT=true` in `backend/.env` (or root `.env` used by compose), then `docker compose restart backend` (or recreate) and confirm `docker compose exec -T backend printenv FEATURE_FLUID_CHAT` → `true`.

- [ ] **Step 2: Full backend suite + lint**

```bash
docker compose exec -T backend uv run pytest tests/unit tests/api -q
docker compose exec -T backend uv run ruff check . && docker compose exec -T backend uv run ruff format --check .
```
Expected: green (pre-existing unrelated failures, if any, noted — this plan adds none).

- [ ] **Step 3: Drive the real chat (browser or curl) with the flag on**

Reproduce the original failure scenarios and confirm the fluid behavior:
1. "my outlook mailbox is full" → **one** natural helpful reply, no "is that right?" confirm turn, relevant steps together.
2. "I need to install docker desktop" → after minimal clarification, an **honest** "I don't have a specific guide — let me get a specialist" (no restart/run-as-admin/Intune ladder), no repeated questions.
3. A known KB issue with a follow-up "still not working" → advances to genuinely new steps, never repeats a failed batch.

- [ ] **Step 4: Confirm grounding intact**

Spot-check that a well-covered issue still returns KB-grounded steps (retrieval_source `db_hybrid`/`db_keyword`, citations present) — fluidity didn't bypass grounding.

- [ ] **Step 5: Finish** per superpowers:finishing-a-development-branch.

---

## Self-Review Notes (author checklist — completed)

- **Spec coverage:** §2A confirm gate → Task 4. §2B non-repeating clarify → Tasks 2–3. §2C group steps + §2E context → Task 5. §2D honest weak-match → Task 6. §2F frontend → achieved by Task 4 (no forced yes/no chips emitted); the frontend already tolerates `null` quick_replies (no frontend code task needed — verified in the reference map). §4 validation → Task 7. §5 feature-flag rollout → Task 1 (+ Task 8 enable). §6 success criteria → Task 7 + Task 8.
- **Type/name consistency:** `FEATURE_FLUID_CHAT`, `FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE`, `FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE`, `RESOLUTION_FLUID_STEP_CAP` used consistently across tasks; `asked_questions` / `record_asked_question` / `was_question_asked` consistent between Tasks 2 and 3; `_confident_understanding` defined and used in Task 4; escalation return shape in Task 6 mirrors resolution.py:216-230.
- **Flag-off invariance:** every task's change is behind `settings.FEATURE_FLUID_CHAT`; existing tests (`TestConfirmUnderstanding`, one-step resolution) run flag-off and must stay green — asserted in each task's Step 4.
- **Implementer verify-points flagged inline (`>` notes):** exact `to_dict`/`from_dict` mechanism for `asked_questions`; the `_no_llm()` helper name; the resolution test's article/state builder shape; and the exact generated copy strings for golden assertions — verify against real code, don't guess.
