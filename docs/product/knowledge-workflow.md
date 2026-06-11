# Knowledge Workflow & Authoring Standards

> Last updated: 2026-06-11 · Audience: IT Leads, IT Admins, Knowledge Stewards

## Article lifecycle

```
 draft ──submit_for_review──> in_review ──approve──> approved ──publish──> published
   ▲          │                    │                    │                    │
   │          │ request_changes    │ reject             │ reject             │ archive
   └──────────┴────────────────────┴────────────────────┘                    ▼
        create_revision (from published) ─────────────────────────────> archived
                                                  restore ◄──────────────────┘
```

- The chat agent uses **published** articles only (by default).
- Editing a **published** article is blocked in place — use **New Revision**
  (`create_revision`), which forks a fresh draft and bumps the version.
- A new immutable **version snapshot** is captured on publish, archive, and
  revision.
- Every transition is recorded in the **audit trail** and (optionally) carries a
  reviewer **note**.

## Publish-readiness checklist (enforced)

An article cannot be published until it has:

1. Title, short summary, category, audience, and a citation label
2. At least some actionable body — resolution steps, troubleshooting steps, or
   overview content
3. At least one tag (for retrieval filtering)
4. An assigned ownership group

The editor surfaces these as live **content quality suggestions**; the backend
enforces them at the `publish` transition.

## Role responsibilities

| Role | Can do |
|------|--------|
| **Employee** | Read published, cited answers; submit article feedback |
| **IT Agent** | View internal/published; create drafts; submit for review; suggest improvements |
| **IT Lead** | Edit drafts; review; approve/reject; **publish**; archive; view analytics |
| **IT Admin** | Everything + taxonomy, ownership groups, reindex, delete |
| **Security/Auditor** | Read-only access to content, version history, audit trail |

## Stale-content governance

- Each article has a `next_review_due_at` (default 180 days; configurable per
  article via *review interval*).
- Published articles past their review date are flagged **stale** with a "needs
  review" badge in the list, detail, and a dedicated **Stale** queue.
- Stale articles can be bulk-reindexed and should be re-reviewed by their owning
  group.

## Authoring standards

- **Be retrieval-aware**: write a crisp `short_summary` (it becomes the citation
  snippet) and tag generously but precisely.
- **Structure over prose**: prefer symptoms / causes / steps fields over one big
  body so chunks are clean and answers are actionable.
- **Classify with the taxonomy**: pick managed categories/products/platforms so
  classification is standardized and aligned with ticket categories.
- **Set escalation guidance**: when self-service fails, the article should say who
  to escalate to.
- **Own it**: assign an ownership group so review reminders have a target.

## Admin operating workflow

1. **Author** a draft (or accept an agent's draft suggestion).
2. **Submit for review** → appears in the **Review Queue**.
3. **Reviewer** approves (or requests changes/rejects with a note).
4. **Publish** (confirmation modal explains it becomes agent-retrievable + indexed).
5. Monitor **Analytics** for effectiveness; act on **low performers** and **stale**
   content; **reindex** after bulk changes.

## Current limitations

- Draft *suggestions* from agents use the same create/review flow (no separate
  suggestion inbox yet).
- No scheduled job auto-emails stale-review reminders; the **Stale** queue + badges
  are the current mechanism.
