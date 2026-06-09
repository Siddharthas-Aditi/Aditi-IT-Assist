# Support Domain Knowledge

## Issue Categories
- `email/outlook` — Email delivery, sync, performance
- `video-conferencing/zoom` — Sign-in (SSO), audio, video
- `device-management/intune` — Compliance, device sync
- `hardware/camera` — Camera access, permissions, drivers
- `network/connectivity` — VPN, WiFi, internet
- `access/permissions` — Login failures, access denied

## Escalation Rules
- Confidence < 0.5 → automatic escalation
- Confidence 0.5-0.8 → offer escalation
- User explicitly requests human → always escalate
- 3+ failed resolution attempts → escalate
- Hardware failure suspected → escalate

## Resolution Confidence Bands
- `>= 0.8` HIGH: Present resolution directly
- `0.5 - 0.8` MEDIUM: Present with disclaimer
- `< 0.5` LOW: Escalate immediately
