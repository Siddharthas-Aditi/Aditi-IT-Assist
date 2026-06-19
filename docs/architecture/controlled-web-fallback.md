# Controlled Web Fallback

> When the internal KB is silent and policy allows, the assistant may consult
> trusted external sources. This document is the governance contract that
> keeps that path safe.

---

## 1. Why "controlled" matters

A naïve web-search fallback would let the assistant pull arbitrary content
into a user-facing reply. That's unacceptable for an enterprise IT
assistant: it leaks brand voice, surfaces wrong or outdated guidance, and
provides no audit trail. The controlled fallback adds five layers of
defense between an unmet KB need and any external content the user sees.

---

## 2. Five gates

### Gate 1: Per-specialist opt-in (registry)

`SpecialistAgentSpec.web_fallback_allowed` is `False` by default. Only
specialists whose domains genuinely benefit from external sources (currently
`zoom_meetings`, `network_vpn`) declare `True`. Adding a new specialist with
web fallback is a deliberate, reviewable change to the registry.

### Gate 2: Supervisor policy

The supervisor (`supervisor.decide`) only proposes `WEB_FALLBACK` when:

1. The active specialist's `web_fallback_allowed` is `True`, AND
2. The per-specialist soft cap is hit (`_PER_SPECIALIST_CAP=3`
   delegations), AND
3. The web_research agent hasn't already been invoked this session.

Outside those conditions, the supervisor escalates instead.

### Gate 3: Trust-tier filter

`ControlledWebResearchAgent` rejects results below the allowed tier set.

| Tier | Examples | Default | Specialist opt-in |
|---|---|---|---|
| `OFFICIAL` | microsoft.com, apple.com, docs.zoom.us | ✓ | — |
| `VENDOR` | dell.com, hp.com, lenovo.com | ✓ | — |
| `TRUSTED_COMMUNITY` | community.zoom.us, support forums | ✗ | `zoom_meetings`, `network_vpn` |
| `GENERAL_BLOG` | Medium, personal blogs | ✗ | (never allowed) |

The tier of a domain is classified by `WebSearchService` based on a curated
allow-list — adding domains is a registry-style change reviewed in PRs.

### Gate 4: Mandatory candidate creation

Every accepted external result becomes a `KnowledgeCandidate` (source
`web_fallback`, confidence `0.45`) — never a direct user-facing answer.
SMEs review the candidate before any of that content can land in the
published KB.

### Gate 5: Audit logging

Every call writes a structured log:

- `web_research_completed` — specialist, raw_count, accepted_count, tiers.
- `web_research_blocked` — specialist, reason, attempted query
  (truncated).

These flow into the `security_auditor` dashboard so a Security/Compliance
review can answer "what external content has the assistant seen?" at any
time.

---

## 3. Where in the flow

```
supervisor.decide()
  └─▶ NextAction.WEB_FALLBACK (only past gates 1+2)
        │
        ▼
ControlledWebResearchAgent.research()
  ├─ Re-check gate 1 (defense-in-depth)
  ├─ Call WebSearchService.search()
  ├─ Filter to allowed_tiers  (gate 3)
  ├─ For each kept result:
  │     KnowledgeImprovementService.record_web_fallback_used()  (gate 4)
  └─ Emit web_research_completed log  (gate 5)
```

The response agent then renders the kept results inside a user-facing
message *labeled* as external (the message header includes
`"External sources you might find useful"` and trust badges per item — see
the Phase 2 frontend spec).

---

## 4. What this service does NOT do

- **Pick when to call.** The supervisor decides; the service only enforces
  policy on the call it receives.
- **Write to production KB.** Only candidates; SMEs promote separately.
- **Trust new domains automatically.** Tier classification is curated.
- **Bypass the offer/escalate flow.** A successful web fallback that
  returns nothing still escalates to a human; we don't pretend external
  content magically resolves issues.

---

## 5. Related docs

- [`multi-agent-support-architecture.md`](./multi-agent-support-architecture.md)
- [`knowledge-improvement-loop.md`](./knowledge-improvement-loop.md)
- [`retrieval-and-indexing.md`](./retrieval-and-indexing.md)
