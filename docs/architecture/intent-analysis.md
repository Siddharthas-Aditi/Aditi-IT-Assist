# Intent Analysis Architecture

> How Aditi IT Assist understands what the user is asking for.

---

## Overview

The intent analysis system runs on every user message and extracts two
orthogonal signals:

1. **Entity Normalization** — *which* product/system the user is talking about
2. **Intent Detection** — *what kind* of problem they're experiencing

These two signals combine to route the conversation to the correct
playbook and retrieval strategy.

## Why the Old Behavior Failed

The previous triage relied solely on keyword matching against broad
categories (e.g. "email/outlook", "access/permissions"). When a user
mentioned "sixthsenses" or "sixth sense":

- No keyword matched any known category
- The system classified the issue as `"other"` (confidence 0.3)
- Low confidence → immediate escalation → generic ticket draft
- The known Sixth Sense login playbook was never consulted

## Current Architecture

```
User Message
    │
    ├──→ Entity Normalizer (entity_normalizer.py)
    │        │
    │        ├── Exact alias match (conf=1.0)
    │        ├── Substring alias match (conf=0.9)
    │        └── Fuzzy match for typos (conf=0.6–0.85)
    │        │
    │        └──→ EntityMatch {canonical, category, display_name}
    │
    ├──→ Intent Detector (entity_normalizer.detect_issue_intent)
    │        │
    │        ├── Login/access intent
    │        ├── Account locked intent
    │        ├── OTP intent
    │        ├── Unhandled message intent
    │        ├── Error/crash/performance intents
    │        │
    │        └──→ intent flags dict
    │
    └──→ Triage Node combines both signals
             │
             ├── Sets issue_category from entity's known category
             ├── Sets diagnostic flags (login_issue, blocked_account, etc.)
             ├── Looks up entity-specific playbook
             └── Asks playbook-guided clarification questions
```

## Entity Registry

Located in `backend/app/services/agents/entity_normalizer.py`.

Each entity defines:
- `canonical_name` — stable ID (e.g. `"sixth_sense"`)
- `aliases` — all known spellings, abbreviations, typos
- `category` — maps to an issue category for playbook routing
- `common_issues` — known issue subtypes for this product

### Supported Entities

| Entity | Canonical | Category | Aliases |
|--------|-----------|----------|---------|
| Sixth Sense | `sixth_sense` | `access/sixth_sense` | sixth sense, sixthsense, sixthsenses, naukri, ... |
| Outlook | `outlook` | `email/outlook` | outlook, ms outlook, exchange, ... |
| Zoom | `zoom` | `video-conferencing/zoom` | zoom, zoom meeting, ... |
| Teams | `teams` | `video-conferencing/zoom` | teams, ms teams, ... |
| Intune | `intune` | `device-management/intune` | intune, company portal, mdm, ... |
| VPN | `vpn` | `network/connectivity` | vpn, globalprotect, anyconnect, ... |
| Keka | `keka` | `software/other` | keka, keka hr, ... |
| FreshService | `freshservice` | `software/other` | freshservice, freshdesk, ... |
| 3CX | `3cx` | `network/connectivity` | 3cx, voip, softphone, ... |

## Intent Detection

The intent detector analyzes the message text for common IT support
patterns and returns boolean flags:

| Flag | Triggers |
|------|----------|
| `is_login_issue` | "login", "sign in", "unable to access", ... |
| `is_account_locked` | "locked", "blocked", "too many attempts", ... |
| `has_otp_mention` | "otp", "verification code", "2fa", ... |
| `has_unhandled_message` | "unhandled", "unhandled message" |
| `has_error_message` | "error", "failed", "not working", ... |

## Adding New Entities

1. Add a `SystemEntity` entry to `_SYSTEM_REGISTRY` in `entity_normalizer.py`
2. Include all known aliases (check support tickets for common typos)
3. If the entity needs its own playbook, add one to `playbooks.py`
4. Map it in `get_playbook_for_entity()`
5. Add KB seed data in `knowledge_base/seed/`
6. Write tests for entity recognition

## Confidence Scoring

| Method | Confidence |
|--------|-----------|
| Exact alias match | 1.0 |
| Substring match in sentence | 0.9 |
| Fuzzy match (SequenceMatcher > 0.75) | 0.6–0.85 |

The confidence propagates into the diagnostic context and influences
whether the system asks clarifying questions or proceeds directly.
