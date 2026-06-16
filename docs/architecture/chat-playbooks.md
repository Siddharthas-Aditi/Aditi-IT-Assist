# Chat Playbooks Architecture

> Playbook-guided diagnostic conversations for IT support.

---

## Overview

Playbooks define **what to ask** and **when to ask it** for each
product/issue category. They guide the triage agent without making it
rigid — the agent uses LLM for natural phrasing but follows the playbook's
diagnostic structure.

## Playbook Registry

Located in `backend/app/services/agents/playbooks.py`.

### Available Playbooks

| Category | Playbook | Entity | Key Subtypes |
|----------|----------|--------|-------------|
| `access/sixth_sense` | SIXTH_SENSE_PLAYBOOK | sixth_sense | login-failure, account-locked, unhandled-message, otp-issue |
| `email/outlook` | OUTLOOK_PLAYBOOK | outlook | not-receiving-emails, outlook-crash, calendar-sync |
| `video-conferencing/zoom` | ZOOM_PLAYBOOK | zoom | no-audio, no-video, cant-join-meeting |
| `device-management/intune` | INTUNE_PLAYBOOK | intune | non-compliant, enrollment-failure |
| `hardware/camera` | CAMERA_PLAYBOOK | — | camera-black-screen, camera-not-detected |
| `hardware/audio` | AUDIO_PLAYBOOK | — | no-audio-output, microphone-not-working |
| `network/connectivity` | NETWORK_PLAYBOOK | vpn | vpn-not-connecting, wifi-disconnecting |
| `access/permissions` | ACCESS_PLAYBOOK | — | account-locked, mfa-not-working |
| `software/other` | SOFTWARE_PLAYBOOK | — | app-crash, install-failure |
| `hardware/other` | HARDWARE_OTHER_PLAYBOOK | — | monitor, keyboard, docking-station |
| `other` | OTHER_PLAYBOOK | — | (generic) |

## Playbook Structure

```python
@dataclass
class IssuePlaybook:
    category: str                        # Issue category key
    display_name: str                    # Human-readable name
    required_slots: list[str]            # Slots needed before resolution
    questions: list[PlaybookQuestion]    # Ordered diagnostic questions
    retrieval_category_filter: str       # KB search filter
    retrieval_boost_terms: list[str]     # Terms to boost in search
    max_retrieval_results: int           # Limit for KB results
    escalation_triggers: list[...]       # When to force-escalate
    subtypes: list[str]                  # Known issue subtypes
```

### PlaybookQuestion

Each question targets a specific diagnostic slot:

```python
@dataclass
class PlaybookQuestion:
    slot: str               # DiagnosticContext field to fill
    question: str           # Natural language question
    priority: int           # Lower = ask first
    options: list[...]      # Quick-reply chips
    skip_if: list[str]      # Skip if these slots are already filled
    condition: str | None   # Only ask if a specific value is set
```

## Flow: How Playbooks Guide Conversation

1. **Entity recognized** → select entity-specific playbook
2. **Check filled slots** → compare against `required_slots`
3. **Get next question** → ordered by priority, skip filled slots
4. **Present with quick-reply options** → user can tap or type
5. **Extract slot value** → from user response or chip selection
6. **Repeat** until `has_enough_context()` returns True
7. **Proceed to retrieval** → using playbook's filter and boost terms

## Sixth Sense Playbook (Example)

The Sixth Sense playbook demonstrates entity-specific diagnostic flow:

**Turn 1**: User says "I am having issue with sixthsenses"
- Entity normalizer: `sixth_sense` (confidence 0.85)
- Playbook selected: `SIXTH_SENSE_PLAYBOOK`
- First question: "Can you tell me what's happening?"
- Quick replies: `Can't log in`, `Account locked`, `Unhandled Message`, `OTP issue`

**Turn 2**: User says "I am unable to login"
- Intent detected: `login-failure`
- Slots filled: `symptom=login-failure`, `login_issue_flag=True`
- Playbook: enough context → proceed to retrieval
- Retrieval query: "sixth sense login failure"
- KB returns: Sixth Sense login troubleshooting article
- Resolution: stepwise guidance (stop attempts → wait 1 hour → reset password)

## Adding a New Playbook

1. Define the `IssuePlaybook` in `playbooks.py`
2. Register it in `_PLAYBOOK_REGISTRY`
3. If entity-specific, add mapping in `get_playbook_for_entity()`
4. Create corresponding KB seed data in `knowledge_base/seed/`
5. Write tests for the diagnostic flow
6. Update this document

## Key Design Principles

- **Playbooks guide, not script** — the agent has discretion
- **Quick replies accelerate** — but users can always type freely
- **Progressive disclosure** — ask the most important question first
- **Max 3 clarifications** — then proceed with best-effort context
- **Playbook ≠ KB article** — playbooks define questions, KB has answers
