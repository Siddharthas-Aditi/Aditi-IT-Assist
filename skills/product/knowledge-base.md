# Skill: Knowledge Base Authoring

> Standards for creating and maintaining the IT knowledge base.

---

## Article Structure

Every knowledge base article follows this format:

```yaml
# backend/app/knowledge_base/seed/outlook-not-receiving.yml
id: "550e8400-e29b-41d4-a716-446655440000"
title: "Outlook Not Receiving Emails"
category: "email/outlook"
subcategory: "email-delivery"
tags: ["email", "outlook", "delivery", "receive", "inbox"]
severity_hint: "medium"
last_updated: "2024-03-15"

content: |
  ## Problem
  User reports not receiving emails in Outlook.

  ## Troubleshooting Steps
  1. Check the Junk/Spam folder for misrouted emails
  2. Verify mail flow rules haven't redirected messages
  3. Check if Focused Inbox is filtering messages
  4. Verify the mailbox isn't full (quota check)
  5. Test by sending a message from another account
  6. Check Outlook sync status (bottom status bar)

  ## If Steps Don't Work
  - Check mail flow in Exchange Admin Center
  - Verify no transport rules are blocking
  - Check message trace for the missing emails

  ## Resolution Verification
  Ask user to send themselves a test email and confirm receipt.

  ## Related Issues
  - Outlook sync delays (different from not receiving)
  - Calendar invites not arriving (subset of this issue)
```

---

## Authoring Rules

1. **Be specific** — Include exact menu paths, button names, UI locations
2. **Be ordered** — Steps from easiest/most-common to hardest/rare
3. **Be complete** — Include "if this doesn't work" fallback
4. **Be testable** — Include verification step at end
5. **Be tagged** — Multiple relevant keywords for search
6. **Be dated** — `last_updated` for freshness tracking

---

## Category Standards

| Category | Subcategory Pattern | Example |
|----------|-------------------|---------|
| `email/outlook` | `email-{problem}` | `email-delivery`, `email-sync` |
| `network/connectivity` | `network-{type}` | `network-vpn`, `network-wifi` |
| `hardware/camera` | `camera-{problem}` | `camera-permissions`, `camera-driver` |
| `access/permissions` | `access-{type}` | `access-mfa`, `access-password` |

---

## Embedding Strategy

Articles are embedded for vector search:
- **Embedding input**: `{title} {category} {tags} {first 500 chars of content}`
- **Model**: `text-embedding-3-small` (1536 dimensions)
- **Re-embed on**: Any content update

---

## Quality Checklist

- [ ] Title clearly describes the problem (user's words)
- [ ] Steps are numbered and actionable
- [ ] Category and subcategory match taxonomy
- [ ] Tags include synonyms users might search
- [ ] Includes escalation guidance ("if steps don't work")
- [ ] Includes verification step
- [ ] Last updated date is current
