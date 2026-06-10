# Skill: IT Support Workflows

> Domain knowledge for IT support at Aditi Consulting.

---

## Support Tiers

| Tier | Handler | SLA | Scope |
|------|---------|-----|-------|
| L0 | AI Agent | Instant | Self-service KB, guided troubleshooting |
| L1 | Help Desk | 15 min | Common issues, password resets, basic config |
| L2 | IT Specialist | 4 hours | Complex issues, system access, escalations |
| L3 | Engineering | 8 hours | Infrastructure, security, custom development |

---

## Escalation Matrix

| Condition | Escalates To | Priority |
|-----------|-------------|----------|
| AI confidence < 0.5 | L1 Help Desk | P3 |
| User requests human | L1 Help Desk | P2 |
| Security incident | L2 Security | P1 |
| System-wide outage | L3 Engineering | P1 |
| Executive impacted | L1 (fast-track) | P1 |
| Data loss/corruption | L2 Specialist | P1 |

---

## Common Issue Patterns

### Email/Outlook (35% of tickets)
- Not receiving emails → Check junk, rules, quota
- Outlook crashes → Safe mode, repair, profile rebuild
- Calendar sync issues → Remove/re-add calendar
- Shared mailbox access → Permissions in Exchange

### Network/VPN (20% of tickets)
- VPN won't connect → Check credentials, restart client, certificate
- WiFi drops → Forget/rejoin network, driver update
- Slow internet → Speed test, DNS check, proxy settings

### Access/Permissions (15% of tickets)
- Locked out → Account unlock, MFA reset
- Can't access resource → Permission request workflow
- Password expired → Self-service portal, IT reset

### Hardware (15% of tickets)
- Camera not working → Permissions, driver, restart
- Monitor not detected → Cable, display settings, driver
- Docking station → Firmware, driver, try different port

### Software (15% of tickets)
- App won't install → Admin rights, company portal
- App crashing → Clear cache, repair, reinstall
- License expired → Check assignment, request renewal

---

## Severity Definitions

| Severity | Definition | Example |
|----------|-----------|---------|
| Critical | Complete work stoppage, data loss risk | "All email is down for the department" |
| High | Significant impact, workaround difficult | "I can't access any shared drives" |
| Medium | Moderate impact, workaround exists | "Outlook is slow but working" |
| Low | Minor inconvenience | "My desktop wallpaper reset" |

---

## Urgency Factors

| Factor | Increases Urgency |
|--------|-------------------|
| Customer-facing deadline | ↑ High |
| Meeting in progress | ↑ High |
| Executive impacted | ↑ High |
| Multiple users affected | ↑ High |
| Security concern | ↑ Critical |
| End of day/week | ↑ Medium |
| Nice-to-have request | → Low |
