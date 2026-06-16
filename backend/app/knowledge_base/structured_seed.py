"""Structured knowledge seed data + seeding routine."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.knowledge import (
    KnowledgeArticle,
    KnowledgeOwnershipGroup,
    KnowledgeTaxonomyTerm,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge.indexing import KnowledgeIndexingService
from app.services.knowledge.management import KnowledgeManagementService

if TYPE_CHECKING:
    from app.models.auth import User

logger = get_logger(__name__)

OWNERSHIP_GROUPS = [
    {
        "name": "endpoint-productivity",
        "display_name": "Endpoint & Productivity",
        "description": "Owns Outlook, Teams, Office, and device-related articles.",
    },
    {
        "name": "network-access",
        "display_name": "Network & Access",
        "description": "Owns VPN, connectivity, SSO, and access-permission articles.",
    },
]

TAXONOMY_TERMS = [
    ("category", "email/outlook", "Email - Outlook", "email/outlook"),
    ("category", "video-conferencing/zoom", "Video Conferencing - Zoom", "video-conferencing/zoom"),
    ("category", "hardware/camera", "Hardware - Camera", "hardware/camera"),
    ("category", "device-management/intune", "Device Management - Intune", "device-management/intune"),
    ("category", "network/connectivity", "Network - Connectivity", "network/connectivity"),
    ("category", "access/permissions", "Access - Permissions", "access/permissions"),
    ("category", "hardware/other", "Hardware - Other", "hardware/other"),
    ("category", "software/other", "Software - Other", "software/other"),
    ("platform", "windows", "Windows", None),
    ("platform", "macos", "macOS", None),
    ("product", "microsoft_outlook", "Microsoft Outlook", None),
    ("product", "zoom", "Zoom", None),
    ("product", "microsoft_intune", "Microsoft Intune", None),
]


ARTICLES = [
    {
        "slug": "outlook-not-receiving-or-slow",
        "title": "Outlook Not Receiving Email or Running Slow",
        "short_summary": "Resolve Outlook desktop issues where mail stops syncing or the app is slow.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "email-delivery",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "sync_failure",
        "severity_hint": "medium",
        "tags": ["outlook", "email", "sync", "slow", "not receiving"],
        "keywords": ["work offline", "send receive", "ost", "add-ins"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "New emails are not arriving in the desktop app",
            "Outlook is slow to open or freezes",
            "Web mail works but desktop does not",
        ],
        "probable_causes": [
            "Work Offline mode is enabled",
            "Corrupted OST/data file or oversized mailbox",
            "A misbehaving COM add-in",
        ],
        "prerequisites": ["Outlook desktop installed", "Corporate network or VPN access"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Disable Work Offline", "details": "Send/Receive tab -> ensure Work Offline is not active."},
            {"step_number": 2, "instruction": "Verify connectivity and VPN", "details": "Confirm internet access and that VPN is connected if required."},
            {"step_number": 3, "instruction": "Disable non-essential add-ins", "details": "File -> Options -> Add-ins -> COM Add-ins -> uncheck non-essential ones, restart."},
            {"step_number": 4, "instruction": "Repair the data file", "details": "File -> Account Settings -> Data Files -> run Inbox Repair if mailbox is large or corrupt."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Send a test email to yourself and confirm it arrives within a minute."},
        ],
        "escalation_criteria": "Steps do not restore sync, or the mailbox is over quota.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "zoom-no-audio-or-video",
        "title": "Zoom or Teams Meeting Has No Audio or Video",
        "short_summary": "Fix Zoom or Teams calls where the mic, speaker, or camera is not working at Aditi.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "video-conferencing/zoom",
        "subcategory": "av-devices",
        "product_or_system": "zoom",
        "platform": "windows",
        "issue_type": "device_access",
        "severity_hint": "medium",
        "tags": ["zoom", "teams", "audio", "video", "camera", "microphone", "headset", "no sound"],
        "keywords": ["device permissions", "speaker test", "camera privacy", "audio driver", "headset not working"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Others cannot hear you in a Zoom or Teams call",
            "Your camera shows a black screen",
            "Echo or background noise in meetings",
        ],
        "probable_causes": [
            "Wrong audio device selected in Zoom or Teams",
            "Too many browser tabs causing audio lag",
            "Headset not properly plugged in or using wrong USB port",
            "Audio driver out of date",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Close unnecessary browser tabs and background apps", "details": "High CPU or RAM usage causes audio dropouts. Close all non-essential tabs and applications before joining the call."},
            {"step_number": 2, "instruction": "Select the correct audio device", "details": "In Zoom: click the arrow next to Mute -> select your headset or speaker. In Teams: click the three dots -> Device settings -> select the correct mic and speaker."},
            {"step_number": 3, "instruction": "Replug the headset and try a different USB port", "details": "Unplug your headset, wait 5 seconds, and plug it into a different USB port. Windows will re-detect the audio device."},
            {"step_number": 4, "instruction": "Allow OS privacy access for Zoom and Teams", "details": "Windows Settings -> Privacy -> Microphone -> ensure Allow apps to access your microphone is ON and Zoom or Teams are listed. Same for Camera."},
            {"step_number": 5, "instruction": "Update audio drivers", "details": "Device Manager (Win+X) -> Sound, video and game controllers -> right-click your audio device -> Update driver. Restart after updating."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Use Zoom Test Speaker and Microphone option and confirm the camera preview before joining the next call."},
        ],
        "escalation_criteria": "Devices still fail after selecting correct device and granting access, or audio driver update fails.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "vpn-disconnects-frequently",
        "title": "VPN Disconnects Frequently When Working Remotely",
        "short_summary": "Stabilize a corporate VPN connection that drops every few minutes.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "network/connectivity",
        "subcategory": "vpn",
        "product_or_system": "globalprotect",
        "platform": "windows",
        "issue_type": "connectivity_drop",
        "severity_hint": "high",
        "tags": ["vpn", "connectivity", "globalprotect", "disconnect", "remote work"],
        "keywords": ["wifi power management", "mtu", "split tunnel", "vpn drops"],
        "ownership_group": "network-access",
        "symptoms": ["VPN drops every 15-20 minutes", "Reconnect prompts repeatedly"],
        "probable_causes": ["Wi-Fi adapter power saving", "Unstable home network", "Outdated VPN client"],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Disable Wi-Fi power saving", "details": "Device Manager -> network adapter -> Power Management -> uncheck allow the computer to turn off this device."},
            {"step_number": 2, "instruction": "Update the VPN client", "details": "Install the latest approved GlobalProtect version from the Aditi IT portal."},
            {"step_number": 3, "instruction": "Test on a wired connection", "details": "Connect via Ethernet to isolate Wi-Fi instability."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Stay connected for 30 minutes without a drop."},
        ],
        "escalation_criteria": "Drops persist on a wired connection with the latest client.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "intune-device-not-compliant",
        "title": "Device Shows Not Compliant in Intune",
        "short_summary": "Bring a managed Aditi laptop back into Intune compliance to restore access to corporate apps.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "device-management/intune",
        "subcategory": "compliance",
        "product_or_system": "microsoft_intune",
        "platform": "windows",
        "issue_type": "compliance",
        "severity_hint": "high",
        "tags": ["intune", "compliance", "mdm", "conditional access", "company portal", "not compliant"],
        "keywords": ["company portal", "sync", "encryption", "defender", "windows update", "firewall"],
        "ownership_group": "network-access",
        "symptoms": [
            "Conditional Access blocks Office 365 apps",
            "Company Portal shows Not compliant",
            "Cannot access corporate resources after laptop restart",
        ],
        "probable_causes": [
            "Pending Windows Update",
            "Virus and Threat Protection out of date",
            "Windows Firewall disabled",
            "Device not synced with Intune policy",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Run Windows Update", "details": "Settings -> Windows Update -> Check for updates -> install all pending updates. Restart the laptop. This resolves the majority of Intune compliance failures at Aditi."},
            {"step_number": 2, "instruction": "Update Virus and Threat Protection", "details": "Windows Security -> Virus and threat protection -> Protection updates -> Check for updates. Ensure definitions are no more than 1 day old."},
            {"step_number": 3, "instruction": "Enable Windows Firewall", "details": "Windows Security -> Firewall and network protection -> ensure Firewall is ON for Domain, Private, and Public networks. Intune policy requires all three to be active."},
            {"step_number": 4, "instruction": "Force a Device Sync with Intune", "details": "Company Portal app -> Settings -> Sync device. Or: Settings -> Accounts -> Access work or school -> click your Aditi account -> Info -> Sync. Wait 5 minutes for the policy to re-evaluate."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Re-run Company Portal sync and confirm it reports Compliant. Then test opening Outlook or Teams."},
        ],
        "escalation_criteria": "Device stays non-compliant after all remediation steps and sync - raise a Freshservice ticket.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "account-locked-or-password-reset",
        "title": "Account Locked, Password Reset, or MFA Issues",
        "short_summary": "Resolve locked accounts, forgotten passwords, and MFA access problems at Aditi.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "account-lockout",
        "product_or_system": "azure_ad",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "high",
        "tags": ["password", "account locked", "mfa", "login", "access denied", "reset", "entra id"],
        "keywords": ["lockout", "authenticator", "sspr", "self service password reset", "qr code"],
        "ownership_group": "network-access",
        "symptoms": [
            "Unable to log in - account locked message",
            "MFA code not working or phone lost",
            "Password expired or forgotten",
            "Access denied to corporate resources",
        ],
        "probable_causes": [
            "Multiple failed login attempts triggering lockout policy",
            "MFA device changed or authenticator app not synced",
            "Password expired per Aditi policy (90-day cycle)",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Wait 15 minutes for auto-unlock", "details": "Aditi AD policy auto-unlocks after 15 minutes. Do NOT keep retrying - each failed attempt resets the timer."},
            {"step_number": 2, "instruction": "Use Self-Service Password Reset (SSPR)", "details": "Go to aka.ms/sspr, enter your Aditi email, verify via registered mobile number or backup email, then reset your password."},
            {"step_number": 3, "instruction": "Re-register MFA authenticator", "details": "If your phone changed, go to aka.ms/mfasetup to add a new authenticator app. You will need IT to verify your identity first."},
            {"step_number": 4, "instruction": "Use the QR Code method if available", "details": "On the SSPR page, select Use a verification code from my mobile app and scan the QR code with Microsoft Authenticator to regain access."},
            {"step_number": 5, "instruction": "Contact IT if self-service fails", "details": "Raise a Freshservice ticket at aditi.freshservice.com with your Employee ID and manager name for manual unlock. Response SLA: 2 hours."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Log in at portal.office.com and confirm access to Outlook and Teams."},
        ],
        "escalation_criteria": "SSPR fails, MFA device is lost and cannot be recovered, or the account is suspended by security policy.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "hardware-peripheral-not-working",
        "title": "Keyboard, Mouse, Monitor or Peripheral Not Working",
        "short_summary": "Troubleshoot common hardware issues with peripherals and docking stations at Aditi.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/other",
        "subcategory": "peripheral",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["keyboard", "mouse", "monitor", "docking station", "usb", "peripheral", "display", "hardware"],
        "keywords": ["not detected", "driver", "device manager", "dual screen", "hardware fault"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Keyboard or mouse unresponsive",
            "Second monitor not detected or showing wrong resolution",
            "Docking station not charging laptop",
        ],
        "probable_causes": [
            "Loose or faulty USB or display connection",
            "Missing or outdated driver",
            "Docking station firmware out of date",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Check all physical connections", "details": "Unplug and firmly re-seat all USB, HDMI, DisplayPort, and power cables at both ends."},
            {"step_number": 2, "instruction": "Try a different port or cable", "details": "Test with another USB port or a replacement cable to rule out a faulty connector."},
            {"step_number": 3, "instruction": "Update or reinstall the device driver", "details": "Open Device Manager (Win+X) -> find the device -> right-click -> Update driver. For docking stations visit the manufacturer site for firmware."},
            {"step_number": 4, "instruction": "Restart and re-dock", "details": "Shut down fully, disconnect from dock, restart, then reconnect. Windows re-enumerates all USB devices on boot."},
            {"step_number": 5, "instruction": "Raise a Freshservice hardware ticket if fault persists", "details": "If the hardware is physically damaged or still fails after the above steps, raise a ticket at aditi.freshservice.com under Hardware -> Peripheral Issue. Include the asset tag number if visible on the device."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm all peripherals are detected in Device Manager with no yellow warning icons."},
        ],
        "escalation_criteria": "Hardware is physically damaged or the device still fails after driver reinstall.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "software-installation-or-crash",
        "title": "Software Installation Failed, Crashes, or Won't Open",
        "short_summary": "Resolve application install failures, crashes, and licensing issues for Aditi-approved software.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "software/other",
        "subcategory": "app-crash",
        "platform": "windows",
        "issue_type": "software_fault",
        "severity_hint": "medium",
        "tags": ["install", "crash", "software", "application", "license", "keka", "freshservice", "error"],
        "keywords": ["not launching", "keeps crashing", "corrupted", "uninstall reinstall"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Application crashes immediately on launch",
            "Software installation fails with an error code",
            "License expired or not activated",
            "App missing from Intune Company Portal",
        ],
        "probable_causes": [
            "Corrupted installation files",
            "Conflicting software or outdated dependencies",
            "License not assigned in Azure AD",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Restart the application and your computer", "details": "Close all instances, restart Windows, then try again. Resolves most temporary crashes."},
            {"step_number": 2, "instruction": "Run as Administrator", "details": "Right-click the app shortcut -> Run as administrator. Some installers require elevated privileges."},
            {"step_number": 3, "instruction": "Repair or reinstall via Company Portal", "details": "Open Intune Company Portal -> find the app -> click Repair or Reinstall. This re-downloads the approved version."},
            {"step_number": 4, "instruction": "Check license assignment", "details": "For Microsoft 365 apps: go to portal.office.com -> settings -> verify your license. Contact IT if unassigned."},
            {"step_number": 5, "instruction": "Check Windows Event Viewer for error codes", "details": "Win+X -> Event Viewer -> Windows Logs -> Application. Note the error source and Event ID for IT to investigate."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Launch the app, perform a basic action, and confirm it stays stable for 5 minutes."},
        ],
        "escalation_criteria": "Issue persists after reinstall, or the application is a business-critical tool such as Keka, Freshservice, or Outlook.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # -- Aditi-specific articles from COMMON TICKET SUBJECTS document
    {
        "slug": "aditi-email-outlook-issues",
        "title": "Email and Outlook Issues at Aditi",
        "short_summary": "Fix common Outlook problems at Aditi: missing emails, archive sync, calendar issues, quarantine, and password or MFA resets.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "email-delivery",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "sync_failure",
        "severity_hint": "medium",
        "tags": ["outlook", "email", "archive", "calendar", "quarantine", "mfa", "password", "sync", "missing emails"],
        "keywords": ["empty folder", "archive folder", "calendar sync", "quarantine release", "sspr", "password reset"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Emails are missing or not arriving in Outlook",
            "Archive folder is not showing up",
            "Calendar is not syncing across devices",
            "Emails are stuck in quarantine",
            "Cannot log in to Outlook - password or MFA issue",
        ],
        "probable_causes": [
            "Outlook data file is full or mailbox is near quota",
            "Archive mailbox not enabled or not connected",
            "Calendar permissions misconfigured",
            "Emails flagged and held in Microsoft quarantine",
            "Expired password or MFA device changed",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Empty Deleted Items and Junk Email folders", "details": "Right-click Deleted Items -> Empty Folder. Right-click Junk Email -> Empty Folder. This frees mailbox space and often unblocks new mail delivery."},
            {"step_number": 2, "instruction": "Check the Archive folder", "details": "In Outlook, look for Online Archive in the left panel. If missing, go to File -> Office Account -> verify your account has an archive licence, or raise a Freshservice ticket to enable it."},
            {"step_number": 3, "instruction": "Fix Calendar sync", "details": "Open Outlook -> Calendar view -> right-click your calendar -> Properties -> Permissions. If sharing is broken, remove and re-share. On mobile, remove and re-add the Exchange account."},
            {"step_number": 4, "instruction": "Release emails from Microsoft Quarantine", "details": "Go to security.microsoft.com -> Email and Collaboration -> Review -> Quarantine. Find the held email, select it, and click Release. If greyed out, raise a Freshservice ticket - admin must release it."},
            {"step_number": 5, "instruction": "Reset password or re-register MFA via SSPR", "details": "If Outlook prompts for password or MFA fails: go to aka.ms/sspr to reset your password, or aka.ms/mfasetup to update your MFA device. Use your registered mobile number or backup email to verify."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Send a test email to yourself and confirm delivery. Open the calendar on your phone and desktop and verify events match."},
        ],
        "escalation_criteria": "Mailbox over quota, archive not available after 1 business day, or quarantine release blocked by admin policy.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "email-alias-shared-mailbox",
        "title": "Request an Email Alias or Shared Mailbox at Aditi",
        "short_summary": "How to raise a Freshservice ticket to get a new email alias or shared mailbox created for your team.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "mailbox-provisioning",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "low",
        "tags": ["alias", "shared mailbox", "distribution list", "email address", "freshservice", "new mailbox"],
        "keywords": ["shared email", "group mailbox", "team inbox", "email alias request", "distribution group"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Team needs a shared inbox",
            "Need to send emails as a department alias",
            "New project or team requires a dedicated email address",
        ],
        "probable_causes": [
            "New team or project created without a corresponding mailbox",
            "Business process requires a shared or role-based email address",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Raise a Freshservice ticket for the new mailbox", "details": "Go to aditi.freshservice.com and raise a new ticket under Email and Outlook -> New Mailbox or Alias Request."},
            {"step_number": 2, "instruction": "Provide the email address in Aditi standard format", "details": "Aditi email addresses follow the pattern: [Division]-[Zone]-[Description]@aditiconsulting.com. Example: hr-bengaluru-onboarding@aditiconsulting.com. Specify this exact address in the ticket."},
            {"step_number": 3, "instruction": "List the members who need access", "details": "In the ticket, list all employees by Aditi email or Employee ID who should have send-as and read access to the shared mailbox."},
            {"step_number": 4, "instruction": "Get manager approval", "details": "CC your reporting manager on the ticket. IT will not create shared mailboxes without manager sign-off."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Once provisioned, send a test email to the new alias and confirm it appears in the shared mailbox inbox."},
        ],
        "escalation_criteria": "Ticket not resolved within 2 business days - follow up on the Freshservice ticket thread.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "new-joiner-onboarding-it",
        "title": "New Joiner IT Onboarding and Account Setup",
        "short_summary": "IT checklist for new joiners at Aditi: account access, Intune enrolment, Ruddr, laptop, and first-day setup.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "software/other",
        "subcategory": "onboarding",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "high",
        "tags": ["new joiner", "onboarding", "intune", "ruddr", "laptop", "account setup", "first day"],
        "keywords": ["joining date", "enrol device", "microsoft 365 account", "company portal", "it setup"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "New employee does not have Microsoft 365 account access",
            "Laptop not yet enrolled in Intune or Company Portal",
            "Ruddr account not created",
            "New joiner does not know what to do on day one",
        ],
        "probable_causes": [
            "Onboarding form not submitted before joining date",
            "Device not yet enrolled in Intune MDM",
            "HR system not yet synced to provision Azure AD account",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Submit the IT onboarding form before the start date", "details": "The hiring manager must raise a Freshservice onboarding ticket at least 3 business days before the joining date. Include: full name, personal email, joining date, office location (Bengaluru, Hyderabad, Delhi, Chennai, Pune, or Mumbai), reporting manager, and role."},
            {"step_number": 2, "instruction": "Receive Microsoft 365 credentials", "details": "IT will email the new joiner personal address with their Aditi email (firstname.lastname@aditiconsulting.com), temporary password, and MFA setup link. Complete MFA setup at aka.ms/mfasetup before day one."},
            {"step_number": 3, "instruction": "Enrol the laptop in Intune on day one", "details": "On your Aditi laptop: Settings -> Accounts -> Access work or school -> Connect -> enter your Aditi email. Install Company Portal from the Microsoft Store and complete device enrolment. This is mandatory for Conditional Access to work."},
            {"step_number": 4, "instruction": "Set up Ruddr Resource Management", "details": "Log in to Ruddr at app.ruddr.io using your Aditi Microsoft 365 account (SSO). If the account is not provisioned, raise a Freshservice ticket under Software -> Ruddr Access."},
            {"step_number": 5, "instruction": "Raise a laptop ticket if hardware is not ready", "details": "If no laptop was issued before the joining date, raise a Freshservice ticket under Hardware -> New Laptop Request with your location and joining date. Standard SLA is 2 business days."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Confirm you can log in to portal.office.com, access Outlook and Teams, and that Company Portal shows your device as Compliant."},
        ],
        "escalation_criteria": "Microsoft 365 account not created 1 day before joining date, or Intune enrolment blocked after following steps.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "ruddr-account-access-issues",
        "title": "Ruddr Account Access or Login Issues",
        "short_summary": "Resolve problems logging in to Ruddr (resource and project management tool) at Aditi.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "software/other",
        "subcategory": "app-access",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "medium",
        "tags": ["ruddr", "resource management", "login", "access", "account", "project management", "timesheet"],
        "keywords": ["ruddr login", "cannot access ruddr", "ruddr account", "SSO ruddr", "timesheet"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Cannot log in to Ruddr at app.ruddr.io",
            "Ruddr account not found or shows an error",
            "Projects or timesheets not visible in Ruddr",
            "New employee does not have Ruddr access after joining",
        ],
        "probable_causes": [
            "Ruddr account not provisioned (onboarding ticket not raised)",
            "Microsoft 365 SSO session expired",
            "Employee role or project not yet configured in Ruddr by manager",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Try logging in via Microsoft SSO", "details": "Go to app.ruddr.io and click Sign in with Microsoft. Use your Aditi email. Do NOT use a separate Ruddr password."},
            {"step_number": 2, "instruction": "Clear browser cache and retry", "details": "Press Ctrl+Shift+Delete -> clear cookies and cached data for the last 7 days -> close and reopen the browser -> try app.ruddr.io again."},
            {"step_number": 3, "instruction": "Raise a Freshservice ticket if account is missing", "details": "Go to aditi.freshservice.com -> raise a ticket under Software -> Ruddr Access Request. Include your Employee ID, joining date, reporting manager name, and the project(s) you need access to. CC your reporting manager on the ticket."},
            {"step_number": 4, "instruction": "SLA expectation", "details": "Ruddr account provisioning SLA is 1 business day from ticket creation. If not resolved within 1 business day, escalate by adding a note to your Freshservice ticket."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Log in to app.ruddr.io, confirm your name and team appear, and verify you can see your assigned projects and submit a timesheet entry."},
        ],
        "escalation_criteria": "Account not provisioned after 1 business day, or projects not visible after manager confirmation that access was granted.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "license-tool-access-request",
        "title": "Request a Software License or Tool Access at Aditi",
        "short_summary": "How to request access to licensed tools at Aditi: Microsoft Copilot, GitHub Copilot, LinkedIn Recruiter, and other approved software.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "software/other",
        "subcategory": "license-provisioning",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "low",
        "tags": ["license", "tool access", "copilot", "github", "linkedin recruiter", "software request", "access request"],
        "keywords": ["microsoft copilot", "github copilot", "linkedin recruiter", "tool request", "software licence", "access approval"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Need access to Microsoft Copilot, GitHub Copilot, or LinkedIn Recruiter",
            "Software license expired or not assigned to my account",
            "New tool required for a project that is not currently installed",
        ],
        "probable_causes": [
            "License not yet assigned - requires manager approval before provisioning",
            "Limited license pool - allocation is role-based and budget-approved",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Get your reporting manager approval first", "details": "Before raising a ticket, confirm with your reporting manager that the tool is approved for your role and a license is available. This is mandatory - IT will not provision without manager sign-off."},
            {"step_number": 2, "instruction": "Raise a Freshservice ticket for the license", "details": "Go to aditi.freshservice.com -> raise a ticket under Software -> License or Tool Access Request. Specify: tool name (e.g. GitHub Copilot), your Employee ID, your role or project, and the business justification."},
            {"step_number": 3, "instruction": "CC your reporting manager on the ticket", "details": "In the Freshservice ticket, add your manager Aditi email in the CC field. IT requires manager approval on the ticket thread before provisioning."},
            {"step_number": 4, "instruction": "Supported tools and request paths", "details": "Microsoft Copilot (M365): M365 admin assigns licence - appears in Office apps automatically. GitHub Copilot: assigned via GitHub org - must specify your GitHub username. LinkedIn Recruiter: requires HR or TA manager approval in addition to reporting manager."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Open the requested application and confirm the licensed features are available (e.g. Copilot icon in Word or Teams, Copilot chat in VS Code, LinkedIn Recruiter seats in your LinkedIn account)."},
        ],
        "escalation_criteria": "License not provisioned within 2 business days of manager approval confirmation.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "sixth-sense-cloudflare-login",
        "title": "Sixth Sense or Naukri Plugin Login Issue via Cloudflare",
        "short_summary": "Fix login failures for Sixth Sense (Found It) recruiting tool that routes through Cloudflare One at Aditi.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "software/other",
        "subcategory": "app-access",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "medium",
        "tags": ["sixth sense", "found it", "naukri", "cloudflare", "recruiting", "login", "plugin", "browser extension"],
        "keywords": ["cloudflare one", "sixth sense login", "found it plugin", "naukri plugin", "resfind", "firefox"],
        "ownership_group": "network-access",
        "symptoms": [
            "Cannot log in to Sixth Sense or Found It recruiting tool",
            "Naukri or Found It browser plugin shows authentication error",
            "Cloudflare Access page blocking the Sixth Sense portal",
            "Login page not loading for the recruiting platform",
        ],
        "probable_causes": [
            "Cloudflare One ZTNA policy requires Firefox - Chrome is not supported",
            "Browser extension not installed in Firefox",
            "Session token expired and Cloudflare is blocking re-authentication",
        ],
        "resolution_steps": [
            {"step_number": 1, "instruction": "Use Mozilla Firefox not Chrome", "details": "The Naukri or Found It plugin and Sixth Sense portal are only fully supported in Mozilla Firefox at Aditi. Uninstall the plugin from Chrome if installed and install it in Firefox instead."},
            {"step_number": 2, "instruction": "Install the Naukri or Found It plugin in Firefox", "details": "In Firefox, go to the Firefox Add-ons store and search for Naukri RMS or Found It by Monster. Install the plugin and sign in with your Aditi Naukri recruiter credentials."},
            {"step_number": 3, "instruction": "Access the Sixth Sense portal via the Cloudflare URL", "details": "Open Firefox and navigate to 10.2.5.9:9999/resfind - this is the internal Cloudflare One-protected URL for Sixth Sense at Aditi. Do NOT use the public URL."},
            {"step_number": 4, "instruction": "Authenticate through Cloudflare One", "details": "If Cloudflare Access prompts for login, use your Aditi Microsoft 365 credentials (SSO). Click Sign in with Microsoft, complete MFA if prompted. You will be redirected to the Sixth Sense portal once authenticated."},
            {"step_number": 5, "instruction": "Raise a ticket if access is still blocked", "details": "If you still cannot access the portal after following the above steps, raise a Freshservice ticket under Network or Access -> Cloudflare or VPN Access. Include a screenshot of the Cloudflare error page."},
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Open Firefox, navigate to the Cloudflare URL, log in via Microsoft SSO, and confirm you can search and view candidate profiles in Sixth Sense."},
        ],
        "escalation_criteria": "Cloudflare Access policy blocking after successful Microsoft SSO - requires network team to whitelist the device.",
        "escalation_target_team": "Network & Access",
    },
]


async def _get_or_create_group(repo: KnowledgeRepository, db, spec: dict, owner):
    existing = (
        await db.execute(
            select(KnowledgeOwnershipGroup).where(KnowledgeOwnershipGroup.name == spec["name"])
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    group = KnowledgeOwnershipGroup(
        name=spec["name"],
        display_name=spec["display_name"],
        description=spec.get("description"),
        owner_id=owner.id if owner else None,
    )
    await repo.add_ownership_group(group)
    return group


async def _ensure_taxonomy(
    repo: KnowledgeRepository, term_type: str, key: str, label: str, mapping: "str | None"
) -> None:
    existing = await repo.get_taxonomy_by_key(term_type, key)
    if existing:
        return
    await repo.add_taxonomy_term(
        KnowledgeTaxonomyTerm(
            term_type=term_type,
            key=key,
            label=label,
            ticket_category_mapping=mapping,
        )
    )


async def seed_knowledge(db, users: dict) -> int:
    """Seed ownership groups, taxonomy, and published structured articles."""
    repo = KnowledgeRepository(db)
    indexing = KnowledgeIndexingService(repo)

    lead = users.get("edward.lead@aditi.com")
    admin = users.get("admin@aditi.com")
    now = datetime.now(UTC)

    # Ownership groups
    groups: dict[str, KnowledgeOwnershipGroup] = {}
    for spec in OWNERSHIP_GROUPS:
        group = await _get_or_create_group(repo, db, spec, lead)
        groups[spec["name"]] = group

    # Taxonomy
    for term_type, key, label, mapping in TAXONOMY_TERMS:
        await _ensure_taxonomy(repo, term_type, key, label, mapping)
    await db.flush()

    seeded = 0
    for spec in ARTICLES:
        existing = await repo.get_by_slug(spec["slug"])
        if existing:
            # Update category in case it changed (taxonomy alignment fix)
            if existing.category != spec["category"]:
                existing.category = spec["category"]
                await db.flush()
            continue
        group = groups.get(spec.get("ownership_group", ""))
        article = KnowledgeArticle(
            slug=spec["slug"],
            title=spec["title"],
            short_summary=spec.get("short_summary"),
            article_type=spec.get("article_type", "troubleshooting"),
            status="published",
            version=1,
            audience=spec.get("audience", "employee"),
            visibility_scope=spec.get("visibility_scope", "public_internal"),
            category=spec["category"],
            subcategory=spec.get("subcategory"),
            product_or_system=spec.get("product_or_system"),
            platform=spec.get("platform"),
            issue_type=spec.get("issue_type"),
            severity_hint=spec.get("severity_hint"),
            tags=spec.get("tags", []),
            keywords=spec.get("keywords", []),
            ownership_group_id=group.id if group else None,
            symptoms=spec.get("symptoms", []),
            probable_causes=spec.get("probable_causes", []),
            prerequisites=spec.get("prerequisites", []),
            troubleshooting_steps=spec.get("troubleshooting_steps", []),
            resolution_steps=spec.get("resolution_steps", []),
            validation_steps=spec.get("validation_steps", []),
            escalation_criteria=spec.get("escalation_criteria"),
            escalation_target_team=spec.get("escalation_target_team"),
            references=spec.get("references", []),
            citation_label=spec["title"],
            source_type="seed",
            author_id=lead.id if lead else None,
            reviewer_id=lead.id if lead else None,
            approver_id=admin.id if admin else None,
            approved_by=admin.id if admin else None,
            is_published=True,
            is_approved=True,
            published_at=now,
            last_reviewed_at=now,
            next_review_due_at=now + timedelta(days=180),
        )
        KnowledgeManagementService._recompute_quality(article)
        await repo.add(article)
        await indexing.index_article(article)
        seeded += 1

    logger.info("knowledge_seeded", articles=seeded, groups=len(groups))
    return seeded
