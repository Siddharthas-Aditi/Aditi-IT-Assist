# Laptop KB Import + Classifier Correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 11 laptop-issue KB guides retrievable and correctly grounded in employee chat by adding 7 new issue subtypes + 3 categories, fixing the `hardware/other`→audio classifier bug, and seeding 7 new published articles.

**Architecture:** The deterministic subtype classifier gains new rule tables + categories; the triage node learns the new categories (LLM prompt + keyword fallback); `structured_seed.py` gains 7 article dicts + taxonomy terms. Grounding rejects on category *family* (`hardware`, `system`, `software`) and reranks by *subtype match*, so each new article's `subcategory` must equal a newly-registered subtype to win its rerank. No schema migration — KB is data.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy, Ruff. Backend only.

## Global Constraints

- Line length: 100 chars max. Linter/formatter: Ruff (`uv run ruff check . && uv run ruff format --check .` must be clean).
- Deterministic path must work with NO LLM configured (keyword classifier is the floor).
- An article's `subcategory` must equal a value returned by `known_subtypes(category)` for its category, so grounding's subtype rerank fires (grounding rejects only on family mismatch, but the rerank needs the subtype equality — see `backend/app/services/agents/grounding.py:196-205`).
- Re-running the seeder must stay idempotent (dedup by unique `slug`).
- New categories/subtypes are additive; do NOT rename or remove existing subtypes (regression risk — `memory/known-risks.md` #1).
- Run backend commands from `backend/` via `uv run` (e.g. `cd backend && uv run pytest ...`).

---

### Task 1: New subtype rule tables + categories + fix `hardware/other` alias

**Files:**
- Modify: `backend/app/services/agents/subtype_classifier.py` (add rule tables after `_AUDIO_RULES` ~line 517; edit `_CATEGORY_RULES` ~line 520-533)
- Test: `backend/tests/unit/test_subtype_classifier.py` (append new test classes)

**Interfaces:**
- Consumes: `SubtypeRule` dataclass (`subtype: str`, `keywords: tuple[str,...]`, `anti_keywords: tuple[str,...]=()`, `base_weight: float=1.0`), `classify_subtype(text, category) -> SubtypeMatch | None`, `known_subtypes(category) -> list[str]` (all already defined in the module).
- Produces: new categories usable by `classify_subtype`: `hardware/laptop`, `system/performance`, `software/windows-update`; new subtypes `keyboard-not-working`, `trackpad-not-working`, `laptop-wont-power-on`, `battery-not-charging`, `external-monitor-not-detected`, `slow-performance`, `windows-update-failure`; `hardware/other` remapped to `_HARDWARE_OTHER_RULES`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_subtype_classifier.py`:

```python
class TestLaptopSubtypes:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("my keyboard is not working", "keyboard-not-working"),
            ("keys are typing wrong characters", "keyboard-not-working"),
            ("the touchpad is not responding", "trackpad-not-working"),
            ("my trackpad cursor keeps jumping", "trackpad-not-working"),
            ("laptop won't turn on at all", "laptop-wont-power-on"),
            ("my laptop is not powering on, no display", "laptop-wont-power-on"),
            ("battery is not charging when plugged in", "battery-not-charging"),
            ("plugged in but not charging", "battery-not-charging"),
            ("external monitor not detected", "external-monitor-not-detected"),
            ("my second screen won't display anything", "external-monitor-not-detected"),
        ],
    )
    def test_laptop_subtypes(self, text, expected):
        m = classify_subtype(text, "hardware/laptop")
        assert m is not None and m.subtype == expected, (text, m and m.subtype)

    def test_known_subtypes_laptop(self):
        subs = known_subtypes("hardware/laptop")
        assert set(subs) == {
            "keyboard-not-working",
            "trackpad-not-working",
            "laptop-wont-power-on",
            "battery-not-charging",
            "external-monitor-not-detected",
        }


class TestPerformanceSubtype:
    @pytest.mark.parametrize(
        "text",
        ["my laptop is really slow", "everything is lagging and freezing", "very sluggish today"],
    )
    def test_slow_performance(self, text):
        m = classify_subtype(text, "system/performance")
        assert m is not None and m.subtype == "slow-performance", (text, m and m.subtype)


class TestWindowsUpdateSubtype:
    @pytest.mark.parametrize(
        "text",
        ["windows update is stuck", "windows update failed to install", "update error on windows"],
    )
    def test_windows_update(self, text):
        m = classify_subtype(text, "software/windows-update")
        assert m is not None and m.subtype == "windows-update-failure", (text, m and m.subtype)


class TestHardwareOtherNoLongerAudioAlias:
    def test_hardware_other_keyboard_not_audio(self):
        # Regression: hardware/other used to alias _AUDIO_RULES, so "keyboard"
        # text scored against audio subtypes. It must now reach a hardware subtype.
        m = classify_subtype("my keyboard is not working", "hardware/other")
        assert m is not None
        assert m.subtype == "keyboard-not-working", m.subtype

    def test_hardware_other_still_matches_audio(self):
        # hardware/other must still cover audio (combined table), not lose it.
        m = classify_subtype("no sound from my speakers", "hardware/other")
        assert m is not None and m.subtype == "no-audio-output", m and m.subtype
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_subtype_classifier.py -k "Laptop or Performance or WindowsUpdate or HardwareOther" -v`
Expected: FAIL — `classify_subtype("...", "hardware/laptop")` returns `None` (no rules for the category yet).

- [ ] **Step 3: Add the rule tables**

In `backend/app/services/agents/subtype_classifier.py`, immediately after the `_AUDIO_RULES` definition (ends ~line 517) and before the `_CATEGORY_RULES` dict, add:

```python
_LAPTOP_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="battery-not-charging",
        keywords=(
            "not charging",
            "won't charge",
            "wont charge",
            "battery not charging",
            "plugged in not charging",
            "not charging when plugged",
            "battery stuck",
            "battery percentage not",
        ),
    ),
    SubtypeRule(
        subtype="laptop-wont-power-on",
        keywords=(
            "won't turn on",
            "wont turn on",
            "not turning on",
            "won't power on",
            "wont power on",
            "not powering on",
            "won't boot",
            "wont boot",
            "no display",
            "does not turn on",
            "doesn't turn on",
            "dead laptop",
            "power button",
        ),
        anti_keywords=("monitor", "external"),
    ),
    SubtypeRule(
        subtype="external-monitor-not-detected",
        keywords=(
            "external monitor",
            "second monitor",
            "second screen",
            "monitor not detected",
            "monitor not detecting",
            "display not detected",
            "dual monitor",
            "extend display",
            "hdmi not",
            "docking station monitor",
        ),
    ),
    SubtypeRule(
        subtype="keyboard-not-working",
        keywords=(
            "keyboard not working",
            "keyboard is not working",
            "keyboard not responding",
            "keys not responding",
            "keys not working",
            "typing wrong",
            "wrong characters",
            "keyboard stopped",
            "keys stuck",
            "keyboard isn't",
        ),
        anti_keywords=("on-screen keyboard works",),
    ),
    SubtypeRule(
        subtype="trackpad-not-working",
        keywords=(
            "trackpad",
            "track pad",
            "touchpad",
            "cursor moving",
            "cursor jumping",
            "cursor keeps jumping",
            "gestures not",
            "pad not responding",
        ),
    ),
)

_PERFORMANCE_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="slow-performance",
        keywords=(
            "slow",
            "very slow",
            "running slow",
            "laggy",
            "lagging",
            "freezing",
            "freezes",
            "hangs",
            "sluggish",
            "takes forever",
            "poor performance",
        ),
    ),
)

_WINDOWS_UPDATE_RULES: tuple[SubtypeRule, ...] = (
    SubtypeRule(
        subtype="windows-update-failure",
        keywords=(
            "windows update",
            "update failed",
            "update stuck",
            "update error",
            "won't update",
            "update not installing",
            "stuck installing update",
            "check for updates",
            "install updates",
            "update loop",
        ),
    ),
)

# Combined catch-all for the generic "hardware/other" bucket so it no longer
# aliases audio-only rules (the old cross-family misclassification bug).
_HARDWARE_OTHER_RULES: tuple[SubtypeRule, ...] = _LAPTOP_RULES + _AUDIO_RULES + _CAMERA_RULES
```

Note: `_CAMERA_RULES` is defined above `_AUDIO_RULES` (~line 434) so it is in scope here.

- [ ] **Step 4: Register the categories and fix the alias**

Edit the `_CATEGORY_RULES` dict (~line 520-533). Change the `"hardware/other"` entry and add three new entries:

```python
_CATEGORY_RULES: dict[str, tuple[SubtypeRule, ...]] = {
    "email/outlook": _OUTLOOK_RULES,
    "access/permissions": _ACCESS_RULES,
    "access/sixth_sense": _ACCESS_RULES,
    "access/ruddr": _ACCESS_RULES,
    "video-conferencing/zoom": _ZOOM_RULES,
    "video-conferencing/teams": _ZOOM_RULES,
    "device-management/intune": _INTUNE_RULES,
    "hardware/camera": _CAMERA_RULES,
    "hardware/audio": _AUDIO_RULES,
    "hardware/laptop": _LAPTOP_RULES,
    "hardware/other": _HARDWARE_OTHER_RULES,
    "system/performance": _PERFORMANCE_RULES,
    "software/windows-update": _WINDOWS_UPDATE_RULES,
    "network/connectivity": _NETWORK_RULES,
    "software/other": _ACCESS_RULES,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_subtype_classifier.py -v`
Expected: PASS (new classes + all pre-existing tests still green).

- [ ] **Step 6: Lint**

Run: `cd backend && uv run ruff check app/services/agents/subtype_classifier.py tests/unit/test_subtype_classifier.py && uv run ruff format --check app/services/agents/subtype_classifier.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agents/subtype_classifier.py backend/tests/unit/test_subtype_classifier.py
git commit -m "feat(kb): add laptop/performance/windows-update subtypes; fix hardware/other audio-alias bug"
```

---

### Task 2: Triage learns the new categories (LLM prompt + keyword fallback)

**Files:**
- Modify: `backend/app/workflows/nodes/triage.py` (`ISSUE_CATEGORIES` ~line 442; `CLASSIFICATION_PROMPT` category list ~line 460-462; `_keyword_classify` ~line 1374-1492)
- Test: `backend/tests/unit/test_subtype_classifier.py` is the wrong home; create `backend/tests/unit/test_triage_categories.py`

**Interfaces:**
- Consumes: `_keyword_classify(message: str, diag_ctx=None) -> dict` (returns a dict with a `"category"` key), `ISSUE_CATEGORIES: list[str]`.
- Produces: `_keyword_classify` returns `category="hardware/laptop"` for laptop-hardware phrases, `"system/performance"` for slow phrases, `"software/windows-update"` for update phrases; `ISSUE_CATEGORIES` contains the three new categories.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_triage_categories.py`:

```python
"""Triage must emit the new laptop/performance/windows-update categories on the
deterministic (no-LLM) keyword path, or the subtype classifier never runs."""

import pytest

from app.workflows.nodes.triage import ISSUE_CATEGORIES, _keyword_classify


def test_new_categories_registered():
    for cat in ("hardware/laptop", "system/performance", "software/windows-update"):
        assert cat in ISSUE_CATEGORIES, cat


@pytest.mark.parametrize(
    "message,expected",
    [
        ("my keyboard is not working", "hardware/laptop"),
        ("the touchpad is not responding", "hardware/laptop"),
        ("laptop won't turn on", "hardware/laptop"),
        ("battery is not charging", "hardware/laptop"),
        ("external monitor not detected", "hardware/laptop"),
        ("my laptop is really slow", "system/performance"),
        ("windows update is stuck", "software/windows-update"),
    ],
)
def test_keyword_classify_new_categories(message, expected):
    result = _keyword_classify(message)
    assert result["category"] == expected, (message, result["category"])


def test_password_update_still_access_not_windows_update():
    # "update my password" must stay access/permissions (access branch runs first).
    result = _keyword_classify("I need to update my password")
    assert result["category"] == "access/permissions", result["category"]


def test_outlook_slow_stays_outlook():
    # Product-specific branch wins over the generic performance branch.
    result = _keyword_classify("outlook is really slow")
    assert result["category"] == "email/outlook", result["category"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_triage_categories.py -v`
Expected: FAIL — new categories absent from `ISSUE_CATEGORIES`; laptop/slow/update messages fall through to `"other"`.

- [ ] **Step 3: Add the new categories to the vocabulary + prompt**

In `backend/app/workflows/nodes/triage.py`, edit `ISSUE_CATEGORIES` (~line 442) to add three entries before `"other"`:

```python
ISSUE_CATEGORIES = [
    "email/outlook",
    "video-conferencing/zoom",
    "device-management/intune",
    "hardware/camera",
    "hardware/audio",
    "hardware/laptop",
    "hardware/other",
    "system/performance",
    "software/windows-update",
    "software/other",
    "network/connectivity",
    "access/permissions",
    "access/sixth_sense",
    "other",
]
```

And update the `CLASSIFICATION_PROMPT` category list (~line 460-462) so the LLM can emit them:

```python
Categories:
- email/outlook, video-conferencing/zoom, device-management/intune
- hardware/camera, hardware/audio, hardware/laptop, hardware/other
- system/performance, software/windows-update, software/other
- network/connectivity, access/permissions, access/sixth_sense, other
```

- [ ] **Step 4: Add keyword branches to `_keyword_classify`**

In `_keyword_classify`, insert these three branches **after** the `access/permissions` branch (the one matching `["password", "login", "mfa", "locked", "access denied"]`, ~line 1460-1470) and **before** the `software/other` branch (~line 1471). Order matters: windows-update before laptop before performance; all after network/access so `wifi`/`password` win first.

```python
    elif any(
        w in message_lower
        for w in ["windows update", "update failed", "update stuck", "update error",
                  "check for updates", "install updates"]
    ):
        return {
            "category": "software/windows-update",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(
        w in message_lower
        for w in ["keyboard", "touchpad", "trackpad", "track pad", "won't turn on",
                  "wont turn on", "not turning on", "won't power on", "not powering on",
                  "won't charge", "not charging", "battery", "external monitor",
                  "second monitor", "second screen", "won't boot", "hdmi"]
    ):
        return {
            "category": "hardware/laptop",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.85 if has_symptom else 0.6,
            "_method": "keyword",
        }
    elif any(
        w in message_lower
        for w in ["slow", "laggy", "lagging", "freezing", "freezes", "hangs",
                  "sluggish", "takes forever"]
    ):
        return {
            "category": "system/performance",
            "subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "has_specific_symptom": has_symptom,
            "symptom": message if has_symptom else None,
            "confidence": 0.8 if has_symptom else 0.55,
            "_method": "keyword",
        }
```

Note: the `normalize_entity` path runs before these branches (~line 1387). Laptop-hardware phrases are not known entities, so they fall through to these branches. Verify no entity named "monitor"/"battery" exists (Step 5 tests cover this — if one fails, add the term to the entity exclusion or reorder).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_triage_categories.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full triage/classifier test set for regressions**

Run: `cd backend && uv run pytest tests/unit/test_subtype_classifier.py tests/unit/test_triage_categories.py tests/unit/test_intent_classifier.py -v`
Expected: PASS.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && uv run ruff check app/workflows/nodes/triage.py tests/unit/test_triage_categories.py && uv run ruff format --check app/workflows/nodes/triage.py
cd ..
git add backend/app/workflows/nodes/triage.py backend/tests/unit/test_triage_categories.py
git commit -m "feat(kb): triage emits hardware/laptop, system/performance, software/windows-update"
```

---

### Task 3: Seed 7 new articles + taxonomy terms + fix camera subcategory

**Files:**
- Modify: `backend/app/knowledge_base/structured_seed.py` (append to `_YAML_ARTICLES` before line 2783 `]`; add taxonomy terms in the block at ~line 2789; fix the camera article's `subcategory`)
- Test: `backend/tests/unit/test_seed_grounding_consistency.py` (create)

**Interfaces:**
- Consumes: `ARTICLES` / `_YAML_ARTICLES` lists (dicts with the article schema); `known_subtypes(category)`; `classify_subtype`.
- Produces: 7 new published article dicts (unique slugs listed below); a regression test asserting new articles' subtype consistency + a laptop grounding smoke test.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_seed_grounding_consistency.py`:

```python
"""New laptop KB articles must be subtype-consistent so grounding reranks them,
and a laptop query must rank the focused article above sibling hardware families."""

from app.knowledge_base.structured_seed import ARTICLES
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.grounding import ground_results
from app.services.agents.subtype_classifier import classify_subtype, known_subtypes

NEW_SLUGS = {
    "laptop-keyboard-not-working",
    "laptop-trackpad-not-working",
    "laptop-wont-power-on",
    "laptop-battery-not-charging",
    "laptop-external-monitor-not-detected",
    "laptop-slow-performance",
    "windows-update-failure",
}


def _by_slug(slug):
    return next(a for a in ARTICLES if a["slug"] == slug)


def test_new_articles_present():
    slugs = {a["slug"] for a in ARTICLES}
    assert NEW_SLUGS.issubset(slugs), NEW_SLUGS - slugs


def test_new_articles_subcategory_is_known_subtype():
    for slug in NEW_SLUGS:
        art = _by_slug(slug)
        subs = known_subtypes(art["category"])
        assert art["subcategory"] in subs, (slug, art["subcategory"], subs)


def test_camera_article_subcategory_fixed():
    # The pre-existing camera article used an invalid "camera-access" subtype.
    cam = next(a for a in ARTICLES if a["category"] == "hardware/camera")
    assert cam["subcategory"] in known_subtypes("hardware/camera"), cam["subcategory"]


def test_keyboard_query_grounds_to_keyboard_article():
    text = "my keyboard is not working"
    m = classify_subtype(text, "hardware/laptop")
    ctx = DiagnosticContext()
    ctx.issue_category = "hardware/laptop"
    ctx.issue_subtype = m.subtype
    ctx.symptom = text
    # Candidate set: the keyboard article + two sibling-family hardware articles.
    candidates = [
        _by_slug("laptop-battery-not-charging"),
        _by_slug("laptop-keyboard-not-working"),
    ]
    result = ground_results(candidates, ctx)
    assert result.kept, "keyboard article was rejected"
    assert result.kept[0].article["slug"] == "laptop-keyboard-not-working"
    assert result.kept[0].subtype_match is True
```

Note: confirm `DiagnosticContext` has attributes `issue_category`, `issue_subtype`, `symptom` (grounding reads these — see `grounding.py:159-169`). If the constructor requires args, adjust instantiation to match `backend/app/services/agents/diagnostic_state.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_seed_grounding_consistency.py -v`
Expected: FAIL — new slugs absent; camera subcategory still `camera-access`.

- [ ] **Step 3: Append the 7 article dicts**

In `backend/app/knowledge_base/structured_seed.py`, insert these 7 dicts into the `_YAML_ARTICLES` list, immediately before its closing `]` (line 2783):

```python
    {
        "slug": "laptop-keyboard-not-working",
        "title": "Laptop Keyboard Not Working",
        "short_summary": "Fix a laptop keyboard that is unresponsive, typing wrong characters, or intermittent.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "keyboard-not-working",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["keyboard", "keys", "typing", "laptop", "hardware"],
        "keywords": ["keys not responding", "typing wrong characters", "on-screen keyboard", "keyboard layout"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Keyboard keys are not responding",
            "Typing produces incorrect characters",
            "Keys work only intermittently",
        ],
        "probable_causes": [
            "Physical dust or debris under the keys",
            "Temporary driver/state glitch",
            "Wrong keyboard language/layout selected",
        ],
        "prerequisites": ["Aditi laptop", "Ability to open Windows Settings"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check for physical obstructions", "details": "Remove dust or debris and make sure no key is physically stuck."},
            {"step_number": 2, "instruction": "Restart the laptop", "details": "Restart the device and test the keyboard again."},
            {"step_number": 3, "instruction": "Test with the On-Screen Keyboard", "details": "Settings -> Accessibility -> Keyboard -> enable On-Screen Keyboard to confirm whether the issue is hardware or software."},
            {"step_number": 4, "instruction": "Check the keyboard language/layout", "details": "Settings -> Time & Language -> Language & Region -> verify the correct keyboard layout is selected."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Open Notepad and confirm every key types the expected character."},
        ],
        "escalation_criteria": "Keyboard still unresponsive after these steps (likely hardware fault needing diagnostics).",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-trackpad-not-working",
        "title": "Laptop Touchpad / Trackpad Not Working",
        "short_summary": "Fix a laptop touchpad that is unresponsive, jumpy, or ignoring gestures.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "trackpad-not-working",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["trackpad", "touchpad", "cursor", "gestures", "laptop"],
        "keywords": ["touchpad disabled", "cursor jumping", "gestures not working", "external mouse"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Touchpad is not responding",
            "Cursor moves unexpectedly",
            "Gestures are not working",
        ],
        "probable_causes": [
            "Touchpad disabled in settings",
            "Conflict with a connected external mouse",
            "Dirt or moisture on the touchpad surface",
        ],
        "prerequisites": ["Aditi laptop", "Ability to open Windows Settings"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check touchpad settings", "details": "Settings -> Bluetooth & Devices -> Touchpad -> ensure the touchpad is enabled."},
            {"step_number": 2, "instruction": "Disconnect any external mouse", "details": "Remove external mice and test the touchpad on its own."},
            {"step_number": 3, "instruction": "Restart the laptop", "details": "Restart the device and verify touchpad functionality."},
            {"step_number": 4, "instruction": "Clean the touchpad", "details": "Make sure the surface is clean and dry; remove any dirt or moisture."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Move the cursor and perform a two-finger scroll to confirm normal behaviour."},
        ],
        "escalation_criteria": "Touchpad still malfunctions after these steps.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-wont-power-on",
        "title": "Laptop Not Powering On",
        "short_summary": "Recover a laptop that does not turn on, shows no display, or is unresponsive to the power button.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "laptop-wont-power-on",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "high",
        "tags": ["power", "won't turn on", "no display", "dead", "laptop"],
        "keywords": ["charging led", "power reset", "hold power button", "no display"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Laptop does not turn on",
            "No display when powered",
            "No response when the power button is pressed",
        ],
        "probable_causes": [
            "No power reaching the laptop (adapter/outlet)",
            "External device interfering with boot",
            "Residual power state needing a hard reset",
        ],
        "prerequisites": ["Power adapter", "A known-working wall outlet"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check the power connection", "details": "Ensure the adapter is securely connected, the wall outlet works, and the charging LED is on."},
            {"step_number": 2, "instruction": "Disconnect the charger and external devices", "details": "Remove the charger, all USB devices, docking stations, and external monitors, then try again."},
            {"step_number": 3, "instruction": "Perform a power reset", "details": "Disconnect the charger, press and hold the power button for 15-20 seconds, then reconnect the charger and power on."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm the laptop boots to the Windows sign-in screen."},
        ],
        "escalation_criteria": "Laptop still does not power on after a power reset (hardware diagnostics required).",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-battery-not-charging",
        "title": "Laptop Battery Not Charging",
        "short_summary": "Fix a laptop that stays at the same battery percentage or shows 'plugged in, not charging'.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "battery-not-charging",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["battery", "charging", "power adapter", "laptop"],
        "keywords": ["plugged in not charging", "charging led", "charger damage", "battery status"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Battery does not charge when plugged in",
            "Battery percentage stays the same",
            "Windows shows 'Plugged in, Not Charging'",
        ],
        "probable_causes": [
            "Loose or faulty charger connection",
            "Damaged charger or cable",
            "Battery firmware/state glitch",
        ],
        "prerequisites": ["Original or compatible charger"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Verify the charger connection", "details": "Ensure the charger is securely connected and the charging indicator LED is on."},
            {"step_number": 2, "instruction": "Inspect the charger", "details": "Check the charger and cable for visible damage; try another compatible charger if available."},
            {"step_number": 3, "instruction": "Restart the laptop", "details": "Restart while keeping the charger connected."},
            {"step_number": 4, "instruction": "Check the battery status", "details": "If Windows shows 'Plugged in, Not Charging', note the exact message before contacting IT."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm the battery percentage increases while plugged in."},
        ],
        "escalation_criteria": "Battery still does not charge (battery/charger replacement may be needed).",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-external-monitor-not-detected",
        "title": "External Monitor Not Detected",
        "short_summary": "Get Windows to detect and display on an external monitor connected to the laptop.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "external-monitor-not-detected",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "display_issue",
        "severity_hint": "medium",
        "tags": ["monitor", "external display", "hdmi", "displayport", "usb-c", "laptop"],
        "keywords": ["detect displays", "windows + p", "input source", "second screen"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Laptop does not detect an external monitor",
            "External monitor shows no content",
        ],
        "probable_causes": [
            "Loose or wrong cable / port",
            "Monitor on the wrong input source",
            "Windows not projecting to the second display",
        ],
        "prerequisites": ["External monitor + video cable (HDMI/DisplayPort/USB-C)"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check cable connections", "details": "Ensure HDMI/DisplayPort/USB-C cables are secure and the monitor is powered on."},
            {"step_number": 2, "instruction": "Select the correct input source", "details": "Use the monitor's menu buttons to select the matching input (HDMI, DP, USB-C)."},
            {"step_number": 3, "instruction": "Detect the display", "details": "Settings -> System -> Display -> click Detect under Multiple displays."},
            {"step_number": 4, "instruction": "Use the display shortcut", "details": "Press Windows + P and choose Duplicate, Extend, or Second screen only."},
            {"step_number": 5, "instruction": "Restart both devices", "details": "Restart the laptop and the monitor and retry."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm the desktop appears on the external monitor."},
        ],
        "escalation_criteria": "Monitor still not detected after these steps.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-slow-performance",
        "title": "Laptop Running Slow",
        "short_summary": "Speed up a laptop that is slow to open apps, browse, or perform daily tasks.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "system/performance",
        "subcategory": "slow-performance",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "performance",
        "severity_hint": "medium",
        "tags": ["slow", "performance", "lag", "freezing", "laptop"],
        "keywords": ["free up disk space", "recycle bin", "pending updates", "restart"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Applications are slow to open",
            "Browsing and daily tasks lag",
            "The laptop freezes intermittently",
        ],
        "probable_causes": [
            "Accumulated temporary memory usage",
            "Low free disk space",
            "Pending Windows updates",
            "Device running for many days without a restart",
        ],
        "prerequisites": ["Aditi laptop"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Restart the laptop", "details": "Restart to clear temporary memory usage."},
            {"step_number": 2, "instruction": "Free up disk space", "details": "Delete unnecessary files, empty the Recycle Bin, and remove unused applications if permitted."},
            {"step_number": 3, "instruction": "Install Windows updates", "details": "Settings -> Windows Update -> install pending updates and restart."},
            {"step_number": 4, "instruction": "Restart periodically", "details": "If the laptop has run for several days, restart it to restore performance."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Open a few applications and confirm they respond promptly."},
        ],
        "escalation_criteria": "Performance remains slow after these steps (further diagnostics needed).",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "windows-update-failure",
        "title": "Windows Update Fails or Gets Stuck",
        "short_summary": "Resolve Windows updates that fail to install, get stuck, or show error codes.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "software/windows-update",
        "subcategory": "windows-update-failure",
        "product_or_system": "windows",
        "platform": "windows",
        "issue_type": "update_failure",
        "severity_hint": "medium",
        "tags": ["windows update", "update stuck", "update error", "patching"],
        "keywords": ["check for updates", "update troubleshooter", "disk space", "error code"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Windows updates fail to install",
            "Updates remain stuck",
            "Update error codes are displayed",
        ],
        "probable_causes": [
            "Unstable internet connection",
            "Transient update-service state",
            "Insufficient free disk space",
        ],
        "prerequisites": ["Stable internet connection"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check the internet connection", "details": "Ensure the laptop has a stable internet connection."},
            {"step_number": 2, "instruction": "Restart the laptop", "details": "Restart and try checking for updates again."},
            {"step_number": 3, "instruction": "Check for updates", "details": "Settings -> Windows Update -> Check for updates."},
            {"step_number": 4, "instruction": "Run the Windows Update troubleshooter", "details": "Settings -> System -> Troubleshoot -> Other troubleshooters -> run Windows Update."},
            {"step_number": 5, "instruction": "Free up disk space", "details": "Ensure there is sufficient free disk space before installing updates."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm Windows Update reports the device is up to date."},
        ],
        "escalation_criteria": "Updates continue to fail or show an error code (contact IT with a screenshot of the error).",
        "escalation_target_team": "Endpoint & Productivity",
    },
```

- [ ] **Step 4: Fix the camera article's invalid subcategory**

Find the existing camera article in `structured_seed.py` (grep for `"category": "hardware/camera"`). Change its `subcategory` from `"camera-access"` to `"camera-not-detected"`. If it has no `subcategory` key or a different invalid value, set it to `"camera-not-detected"`.

Run to locate: `cd backend && grep -n "camera-access\|hardware/camera" app/knowledge_base/structured_seed.py`

- [ ] **Step 5: Add taxonomy terms**

Edit the taxonomy-extension block at the end of the file (~line 2789):

```python
# Add newer categories to taxonomy if not present
TAXONOMY_TERMS = list(TAXONOMY_TERMS) + [
    ("category", "hardware/audio", "Hardware - Audio", "hardware/audio"),
    ("category", "hardware/laptop", "Hardware - Laptop", "hardware/laptop"),
    ("category", "system/performance", "System - Performance", "system/performance"),
    ("category", "software/windows-update", "Software - Windows Update", "software/windows-update"),
    ("product", "laptop", "Laptop", None),
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_seed_grounding_consistency.py -v`
Expected: PASS.

- [ ] **Step 7: Verify the seed module imports and slugs are unique**

Run: `cd backend && uv run python -c "from app.knowledge_base.structured_seed import ARTICLES; s=[a['slug'] for a in ARTICLES]; assert len(s)==len(set(s)), 'duplicate slugs'; print('articles:', len(s), 'ok')"`
Expected: prints article count, no assertion error.

- [ ] **Step 8: Lint + commit**

```bash
cd backend && uv run ruff check app/knowledge_base/structured_seed.py tests/unit/test_seed_grounding_consistency.py && uv run ruff format --check app/knowledge_base/structured_seed.py
cd ..
git add backend/app/knowledge_base/structured_seed.py backend/tests/unit/test_seed_grounding_consistency.py
git commit -m "feat(kb): seed 7 laptop/performance/windows-update articles; fix camera subcategory + taxonomy"
```

---

### Task 4: Retrieval eval coverage + full-suite verification

**Files:**
- Modify: `backend/tests/data/retrieval_eval.yaml` (add corpus entries + labelled queries; bump `version`)
- Test: `backend/tests/unit/test_retrieval_eval.py` (existing harness — no code change; it reads the yaml)

**Interfaces:**
- Consumes: the eval yaml schema — `corpus: [{key, text, tags, embedding}]`, labelled `queries` (inspect the file's existing `queries:` block for the exact key names, e.g. `query`/`relevant`/`expected`).
- Produces: laptop queries whose relevant corpus entry is retrieved within `recall_k`, keeping keyword recall ≥ target and hybrid ≥ keyword.

- [ ] **Step 1: Inspect the eval file's query schema**

Run: `cd backend && sed -n '40,140p' tests/data/retrieval_eval.yaml`
Note the exact shape of the `queries:` list and the `embedding` dimensionality (4-dim in the corpus sample).

- [ ] **Step 2: Add corpus entries + queries**

Append to the `corpus:` list (use a 4-dim embedding pointing in a fresh direction so it doesn't collide with existing clusters):

```yaml
  - key: laptop-keyboard-not-working
    text: "Laptop keyboard keys are not responding or typing wrong characters; test with the on-screen keyboard and check the layout."
    tags: ["keyboard", "keys", "typing", "laptop"]
    embedding: [0.0, 0.0, 0.0, 1.0]
  - key: laptop-wont-power-on
    text: "Laptop will not turn on and shows no display; check power, remove external devices, and perform a power reset."
    tags: ["power", "won't turn on", "no display", "laptop"]
    embedding: [0.2, 0.0, 0.0, 0.9]
  - key: laptop-slow-performance
    text: "Laptop is slow opening applications; restart, free up disk space, and install pending Windows updates."
    tags: ["slow", "performance", "disk space", "laptop"]
    embedding: [0.0, 0.2, 0.0, 0.9]
```

Append to the `queries:` list, **matching the exact keys the existing entries use** (adapt `query`/`relevant`/`expected` names to what Step 1 showed):

```yaml
  - query: "my keyboard is not working and typing wrong letters"
    relevant: ["laptop-keyboard-not-working"]
  - query: "laptop won't turn on no display"
    relevant: ["laptop-wont-power-on"]
  - query: "my laptop is really slow"
    relevant: ["laptop-slow-performance"]
```

- [ ] **Step 3: Bump the eval version**

Change `version: "1.0.0"` to `version: "1.1.0"` at the top of the yaml.

- [ ] **Step 4: Run the eval to verify it passes**

Run: `cd backend && uv run pytest tests/unit/test_retrieval_eval.py -v`
Expected: PASS — keyword recall meets target and hybrid ≥ keyword with the new laptop queries included.

- [ ] **Step 5: Run the full grounding + retrieval + workflow suites for regressions**

Run: `cd backend && uv run pytest tests/unit/test_grounding.py tests/unit/test_knowledge_retrieval.py tests/unit/test_retrieval_node.py tests/unit/test_subtype_classifier.py tests/unit/test_triage_categories.py tests/unit/test_seed_grounding_consistency.py tests/unit/test_retrieval_eval.py -v`
Expected: PASS.

- [ ] **Step 6: Full backend lint + test gate**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: lint clean; test suite green.

- [ ] **Step 7: Manual end-to-end verification (seeded dev DB)**

If a dev DB is available:
```bash
docker compose up -d postgres redis backend
docker compose exec backend uv run python -m scripts.seed_enterprise
```
Then in the chat UI (or via the chat API), ask each of the 11 issues (e.g. "my keyboard isn't working", "laptop won't turn on", "battery not charging", "external monitor not detected", "laptop is slow", "windows update is stuck", plus audio/camera/network/password/wifi) and confirm: the correct steps come back, and no cross-family content leaks (e.g. keyboard never returns audio/password steps). Check the IT/admin `debug` trace shows the expected `subtype match`.

- [ ] **Step 8: Commit**

```bash
git add backend/tests/data/retrieval_eval.yaml
git commit -m "test(kb): retrieval-eval coverage for laptop keyboard/power/slow queries"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (new subtypes + classifier rules) → Task 1. ✓
- Spec §2 (triage category vocabulary, LLM + keyword) → Task 2. ✓
- Spec §3 (7 new articles, reconcile-not-duplicate, camera fix, taxonomy) → Task 3. Audio/network/password guides are already covered by existing articles; no new article needed (reconcile = no-op beyond camera fix, per spec). ✓
- Spec §1 fix `hardware/other` alias → Task 1 Step 3-4 (`_HARDWARE_OTHER_RULES`). ✓
- Spec "retrieval eval addition" → Task 4. ✓
- Spec testing (classifier unit, seed consistency, retrieval eval) → Tasks 1/3/4. ✓
- Acceptance criteria 1-5 → covered by Tasks 1-4 + Task 4 Step 6 (ruff) and Step 7 (manual). ✓

**Placeholder scan:** No TBD/TODO; all code blocks are concrete; article dicts are complete. Task 4 Step 2 intentionally instructs adapting yaml key names to the file's actual schema (verified in Step 1) rather than guessing — this is a read-then-write instruction, not a placeholder.

**Type consistency:** `classify_subtype`/`known_subtypes` signatures match the module; `SubtypeRule` field names match; article dict keys match the existing schema (`slug`, `title`, `short_summary`, `article_type`, `audience`, `category`, `subcategory`, `product_or_system`, `platform`, `issue_type`, `severity_hint`, `tags`, `keywords`, `ownership_group`, `symptoms`, `probable_causes`, `prerequisites`, `resolution_steps`, `validation_steps`, `escalation_criteria`, `escalation_target_team`); grounding attributes (`issue_category`, `issue_subtype`, `symptom`) match `grounding.py` reads. New slugs are consistent between Task 3's dicts and its test's `NEW_SLUGS`.

**Note for implementer:** `DiagnosticContext` construction in Task 3 Step 1 must match its actual definition in `backend/app/services/agents/diagnostic_state.py`; if fields are constructor args rather than settable attributes, adapt the test setup accordingly (behavior asserted is unchanged).
