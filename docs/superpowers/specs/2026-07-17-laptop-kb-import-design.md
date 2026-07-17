# Sub-project A — Laptop KB Import + Classifier Correctness

**Date:** 2026-07-17
**Status:** Approved design (pending user spec review)
**Owner:** IT Assist engineering

## Problem

Aditi IT delivered 11 new laptop-issue troubleshooting guides (`Laptop_issues/*.docx`).
The chat agent cannot help employees with most of them because:

1. **6–7 issue subtypes do not exist** in the deterministic subtype classifier
   (`keyboard`, `trackpad`, `laptop-wont-power-on`, `battery-not-charging`,
   `external-monitor-not-detected`, `slow-performance`, `windows-update-failure`).
   Per the grounding contract, an article whose `subcategory` is not a known subtype
   for its category is rejected by `grounding.py::ground_results`, so simply seeding
   the articles is not enough.
2. **`hardware/other` is aliased to `_AUDIO_RULES`** in
   `subtype_classifier.py::_CATEGORY_RULES` (line 530). Any keyboard/monitor/power
   text landing in `hardware/other` is scored against *audio* rules — a latent
   cross-family misclassification bug.
3. **Triage cannot emit the new categories.** `triage.py::ISSUE_CATEGORIES` (line 442)
   and `CLASSIFICATION_PROMPT` (line 456) list only the current categories, and the
   `_keyword_classify` fallback has no laptop-hardware/performance/windows-update
   keywords — so even a correct subtype table never runs for these issues.
4. One **pre-existing data bug**: the seeded camera article uses
   `subcategory="camera-access"`, which is **not** a known subtype
   (`_CAMERA_RULES` has `camera-not-detected`, `camera-black-screen`, …), so it
   fails the same grounding guardrail.

## Goal

Employees can describe any of the 11 laptop issues in natural language and the chat
agent retrieves **only** the correct, subtype-scoped article and never mixes
unrelated KB families. All work is deterministic-path safe (works without an LLM)
and idempotent to re-seed.

## Non-goals

- No docx auto-importer. 11 files are hand-authored as structured dicts (full control
  over subtype/keyword/step quality; a lossy extractor would risk misclassification).
- No changes to the resolution/escalation phrasing (that is sub-project B).
- No new UI. This is backend KB + classifier only.

## Taxonomy (approved: consolidated)

Three new categories; the physical-laptop subtypes share one category because the
*subtype* — not the category — is what grounding matches on.

| Guide (`Laptop_issues/`) | Category | Subtype (`subcategory`) | New? |
|---|---|---|---|
| KB-012-Audio | `hardware/audio` | `no-audio-output` | reuse existing subtype |
| KB-013-Camera | `hardware/camera` | `camera-not-detected` | reuse (also fixes bad seed) |
| KB-013-Network | `network/connectivity` | `wifi-disconnecting` | reuse existing subtype |
| KB-016-Passwordreset | `access/permissions` | `password-expired` | reuse existing subtype |
| KB-014-Keyboard | `hardware/laptop` | `keyboard-not-working` | **new** |
| KB-015-TrackPad | `hardware/laptop` | `trackpad-not-working` | **new** |
| KB-17-Power_Issues | `hardware/laptop` | `laptop-wont-power-on` | **new** |
| KB-019-Not_Charging | `hardware/laptop` | `battery-not-charging` | **new** |
| KB-020-Monitor_issues | `hardware/laptop` | `external-monitor-not-detected` | **new** |
| KB-018-Slow | `system/performance` | `slow-performance` | **new** |
| KB-021-Update_issues | `software/windows-update` | `windows-update-failure` | **new** |

New categories: `hardware/laptop`, `system/performance`, `software/windows-update`.
New subtypes: 7 (listed above).

## Design / units of work

### 1. Subtype classifier (`backend/app/services/agents/subtype_classifier.py`)
- Add three new `SubtypeRule` tables:
  - `_LAPTOP_RULES` — `keyboard-not-working`, `trackpad-not-working`,
    `laptop-wont-power-on`, `battery-not-charging`, `external-monitor-not-detected`.
    Multi-word, high-signal keywords first; anti-keywords to prevent cross-matches
    (e.g. `battery-not-charging` should not swallow generic "not working").
  - `_PERFORMANCE_RULES` — `slow-performance`.
  - `_WINDOWS_UPDATE_RULES` — `windows-update-failure`.
- Register them in `_CATEGORY_RULES`: `hardware/laptop`, `system/performance`,
  `software/windows-update`.
- **Fix the alias bug:** repoint `"hardware/other"` from `_AUDIO_RULES` to a new
  combined `_HARDWARE_OTHER_RULES` table that concatenates the laptop + audio +
  camera rules, so no single hardware family is privileged. `hardware/other` must
  never score against audio-only rules.
- Ensure `known_subtypes(category)` returns the new subtypes for each new category
  (this is what the grounding guardrail and the seed-consistency test check).

### 2. Triage category vocabulary (`backend/app/workflows/nodes/triage.py`)
- Add `hardware/laptop`, `system/performance`, `software/windows-update` to
  `ISSUE_CATEGORIES` and to the `CLASSIFICATION_PROMPT` category list (so the LLM
  path can emit them).
- Extend `_keyword_classify` with laptop-hardware / performance / windows-update
  keyword branches so the **no-LLM path** also routes correctly. This is the floor
  that guarantees deterministic correctness.

### 3. KB articles (`backend/app/knowledge_base/structured_seed.py`)

**7 genuinely new articles** (one per new subtype): `keyboard-not-working`,
`trackpad-not-working`, `laptop-wont-power-on`, `battery-not-charging`,
`external-monitor-not-detected`, `slow-performance`, `windows-update-failure`.

**4 guides whose subtype already exists** (audio, camera, network, password) are
**reconciled into the existing seed articles**, not added as duplicates (two articles
sharing one subtype adds retrieval noise): merge any net-new steps/keywords from the
docx into the existing article, and **fix the camera article's `subcategory`**
(`camera-access` → `camera-not-detected`). If an existing article already fully
covers the guide, no change beyond the camera fix is required.

- Append the 7 new article dicts to `_YAML_ARTICLES` following the exact existing schema:
  `slug` (unique), `title`, `short_summary`, `article_type="troubleshooting"`,
  `audience="employee"`, `category`, `subcategory` (== a known subtype),
  `product_or_system`, `platform`, `issue_type`, `severity_hint`, `tags`, `keywords`,
  `ownership_group`, `symptoms`, `probable_causes`, `prerequisites`,
  `troubleshooting_steps`, `resolution_steps` (`{step_number,instruction,details}`),
  `validation_steps`, `escalation_criteria`, `escalation_target_team`, `references`.
- Content is transcribed faithfully from the docx (Method-1..N → ordered
  `resolution_steps`); steps stay scoped to the single subtype (no monolithic
  "all laptop issues" article).
- **Fix the existing camera seed** `subcategory` from `camera-access` →
  `camera-not-detected`.
- Add `TAXONOMY_TERMS` entries for the three new categories.
- Confirm `ownership_group` values resolve (reuse `endpoint-productivity`; add a
  group only if none fits).
- Re-seeding stays idempotent (dedup by `slug`).

### 4. Taxonomy terms
- Add `("category", "hardware/laptop", "Hardware - Laptop", "hardware/laptop")` and
  equivalents for `system/performance`, `software/windows-update`.

## Data flow (unchanged contract)

```
employee msg → triage._classify_issue (LLM or _keyword_classify)
             → category ∈ ISSUE_CATEGORIES
subtype_classifier.classify(category, text) → subcategory ∈ known_subtypes(category)
retrieval.search → grounding.ground_results (subtype rerank; reject cross-family)
resolution._build_progression → subtype-scoped steps
```

The whole point: `category` and `subcategory` are now defined end-to-end for laptop
issues, so grounding keeps and reranks the right article instead of rejecting it.

## Error handling / safety

- Grounding guardrail is unchanged and remains the safety net: any article whose
  `subcategory` is not in `known_subtypes(category)` is still rejected. We satisfy it
  by construction (every new article's subcategory is a newly-registered subtype).
- No behavioral change when the LLM is off — `_keyword_classify` covers the new
  categories deterministically.
- Re-running `seed_enterprise` is idempotent; existing slugs skipped.

## Testing

- **Unit — classifier:** for each new subtype, a representative user phrase classifies
  to the expected `(category, subtype)`; anti-keyword cases don't false-match; and
  `hardware/other` text no longer maps to an audio subtype (regression for the bug).
- **Unit — seed consistency:** extend/verify the existing invariant test that every
  seeded article's `subcategory ∈ known_subtypes(category)` (now includes the 9 new
  + fixed camera article).
- **Retrieval eval:** add laptop queries to `backend/tests/data/retrieval_eval.yaml`
  ("my keyboard isn't typing", "laptop won't turn on", "screen not detected on
  second monitor", "windows update stuck", "laptop is really slow") asserting the
  correct article is retrieved top-k and cross-family articles are not. Existing
  gate (`test_retrieval_eval.py`, hybrid ≥ keyword recall) must still pass.
- **Manual:** re-seed a dev DB, ask each of the 11 issues in chat, confirm the right
  steps come back and no family mixing.

## Acceptance criteria

1. All 11 guides are retrievable as published articles with a valid subtype.
2. `known_subtypes()` includes the 7 new subtypes; `hardware/other` no longer aliases
   audio rules; the camera seed subcategory is valid.
3. Triage (LLM and keyword paths) emits the 3 new categories.
4. New classifier + seed-consistency + retrieval-eval tests pass; existing eval gate
   still green.
5. `uv run ruff check . && uv run ruff format --check .` clean.

## Risks (see `memory/known-risks.md` #1, #7, #8)

- Cross-family mixing: mitigated by subtype scoping + retrieval eval.
- Contract stability: new categories/subtypes are additive; no version bump needed
  for existing contracts.
- Migrations: none — KB seeding is data, not schema.
