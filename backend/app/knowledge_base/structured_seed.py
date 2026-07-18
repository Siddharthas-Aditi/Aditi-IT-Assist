"""Structured knowledge seed data + seeding routine."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    (
        "category",
        "device-management/intune",
        "Device Management - Intune",
        "device-management/intune",
    ),
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
        "subcategory": "not-receiving-emails",
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
            {
                "step_number": 1,
                "instruction": "Disable Work Offline",
                "details": "Send/Receive tab -> ensure Work Offline is not active.",
            },
            {
                "step_number": 2,
                "instruction": "Verify connectivity and VPN",
                "details": "Confirm internet access and that VPN is connected if required.",
            },
            {
                "step_number": 3,
                "instruction": "Disable non-essential add-ins",
                "details": "File -> Options -> Add-ins -> COM Add-ins -> uncheck non-essential ones, restart.",
            },
            {
                "step_number": 4,
                "instruction": "Repair the data file",
                "details": "File -> Account Settings -> Data Files -> run Inbox Repair if mailbox is large or corrupt.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Send a test email to yourself and confirm it arrives within a minute.",
            },
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
        "subcategory": "no-audio",
        "product_or_system": "zoom",
        "platform": "windows",
        "issue_type": "device_access",
        "severity_hint": "medium",
        "tags": ["zoom", "teams", "audio", "video", "camera", "microphone", "headset", "no sound"],
        "keywords": [
            "device permissions",
            "speaker test",
            "camera privacy",
            "audio driver",
            "headset not working",
        ],
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
            {
                "step_number": 1,
                "instruction": "Close unnecessary browser tabs and background apps",
                "details": "High CPU or RAM usage causes audio dropouts. Close all non-essential tabs and applications before joining the call.",
            },
            {
                "step_number": 2,
                "instruction": "Select the correct audio device",
                "details": "In Zoom: click the arrow next to Mute -> select your headset or speaker. In Teams: click the three dots -> Device settings -> select the correct mic and speaker.",
            },
            {
                "step_number": 3,
                "instruction": "Replug the headset and try a different USB port",
                "details": "Unplug your headset, wait 5 seconds, and plug it into a different USB port. Windows will re-detect the audio device.",
            },
            {
                "step_number": 4,
                "instruction": "Allow OS privacy access for Zoom and Teams",
                "details": "Windows Settings -> Privacy -> Microphone -> ensure Allow apps to access your microphone is ON and Zoom or Teams are listed. Same for Camera.",
            },
            {
                "step_number": 5,
                "instruction": "Update audio drivers",
                "details": "Device Manager (Win+X) -> Sound, video and game controllers -> right-click your audio device -> Update driver. Restart after updating.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Use Zoom Test Speaker and Microphone option and confirm the camera preview before joining the next call.",
            },
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
        "subcategory": "vpn-not-connecting",
        "product_or_system": "globalprotect",
        "platform": "windows",
        "issue_type": "connectivity_drop",
        "severity_hint": "high",
        "tags": ["vpn", "connectivity", "globalprotect", "disconnect", "remote work"],
        "keywords": ["wifi power management", "mtu", "split tunnel", "vpn drops"],
        "ownership_group": "network-access",
        "symptoms": ["VPN drops every 15-20 minutes", "Reconnect prompts repeatedly"],
        "probable_causes": [
            "Wi-Fi adapter power saving",
            "Unstable home network",
            "Outdated VPN client",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable Wi-Fi power saving",
                "details": "Device Manager -> network adapter -> Power Management -> uncheck allow the computer to turn off this device.",
            },
            {
                "step_number": 2,
                "instruction": "Update the VPN client",
                "details": "Install the latest approved GlobalProtect version from the Aditi IT portal.",
            },
            {
                "step_number": 3,
                "instruction": "Test on a wired connection",
                "details": "Connect via Ethernet to isolate Wi-Fi instability.",
            },
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
        "subcategory": "non-compliant",
        "product_or_system": "microsoft_intune",
        "platform": "windows",
        "issue_type": "compliance",
        "severity_hint": "high",
        "tags": [
            "intune",
            "compliance",
            "mdm",
            "conditional access",
            "company portal",
            "not compliant",
        ],
        "keywords": [
            "company portal",
            "sync",
            "encryption",
            "defender",
            "windows update",
            "firewall",
        ],
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
            {
                "step_number": 1,
                "instruction": "Run Windows Update",
                "details": "Settings -> Windows Update -> Check for updates -> install all pending updates. Restart the laptop. This resolves the majority of Intune compliance failures at Aditi.",
            },
            {
                "step_number": 2,
                "instruction": "Update Virus and Threat Protection",
                "details": "Windows Security -> Virus and threat protection -> Protection updates -> Check for updates. Ensure definitions are no more than 1 day old.",
            },
            {
                "step_number": 3,
                "instruction": "Enable Windows Firewall",
                "details": "Windows Security -> Firewall and network protection -> ensure Firewall is ON for Domain, Private, and Public networks. Intune policy requires all three to be active.",
            },
            {
                "step_number": 4,
                "instruction": "Force a Device Sync with Intune",
                "details": "Company Portal app -> Settings -> Sync device. Or: Settings -> Accounts -> Access work or school -> click your Aditi account -> Info -> Sync. Wait 5 minutes for the policy to re-evaluate.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Re-run Company Portal sync and confirm it reports Compliant. Then test opening Outlook or Teams.",
            },
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
        "subcategory": "account-locked",
        "product_or_system": "azure_ad",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "high",
        "tags": [
            "password",
            "account locked",
            "mfa",
            "login",
            "access denied",
            "reset",
            "entra id",
        ],
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
            {
                "step_number": 1,
                "instruction": "Wait 15 minutes for auto-unlock",
                "details": "Aditi AD policy auto-unlocks after 15 minutes. Do NOT keep retrying - each failed attempt resets the timer.",
            },
            {
                "step_number": 2,
                "instruction": "Use Self-Service Password Reset (SSPR)",
                "details": "Go to aka.ms/sspr, enter your Aditi email, verify via registered mobile number or backup email, then reset your password.",
            },
            {
                "step_number": 3,
                "instruction": "Re-register MFA authenticator",
                "details": "If your phone changed, go to aka.ms/mfasetup to add a new authenticator app. You will need IT to verify your identity first.",
            },
            {
                "step_number": 4,
                "instruction": "Use the QR Code method if available",
                "details": "On the SSPR page, select Use a verification code from my mobile app and scan the QR code with Microsoft Authenticator to regain access.",
            },
            {
                "step_number": 5,
                "instruction": "Contact IT if self-service fails",
                "details": "Raise a Freshservice ticket at aditi.freshservice.com with your Employee ID and manager name for manual unlock. Response SLA: 2 hours.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in at portal.office.com and confirm access to Outlook and Teams.",
            },
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
        "tags": [
            "keyboard",
            "mouse",
            "monitor",
            "docking station",
            "usb",
            "peripheral",
            "display",
            "hardware",
        ],
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
            {
                "step_number": 1,
                "instruction": "Check all physical connections",
                "details": "Unplug and firmly re-seat all USB, HDMI, DisplayPort, and power cables at both ends.",
            },
            {
                "step_number": 2,
                "instruction": "Try a different port or cable",
                "details": "Test with another USB port or a replacement cable to rule out a faulty connector.",
            },
            {
                "step_number": 3,
                "instruction": "Update or reinstall the device driver",
                "details": "Open Device Manager (Win+X) -> find the device -> right-click -> Update driver. For docking stations visit the manufacturer site for firmware.",
            },
            {
                "step_number": 4,
                "instruction": "Restart and re-dock",
                "details": "Shut down fully, disconnect from dock, restart, then reconnect. Windows re-enumerates all USB devices on boot.",
            },
            {
                "step_number": 5,
                "instruction": "Raise a Freshservice hardware ticket if fault persists",
                "details": "If the hardware is physically damaged or still fails after the above steps, raise a ticket at aditi.freshservice.com under Hardware -> Peripheral Issue. Include the asset tag number if visible on the device.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm all peripherals are detected in Device Manager with no yellow warning icons.",
            },
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
        "tags": [
            "install",
            "crash",
            "software",
            "application",
            "license",
            "keka",
            "freshservice",
            "error",
        ],
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
            {
                "step_number": 1,
                "instruction": "Restart the application and your computer",
                "details": "Close all instances, restart Windows, then try again. Resolves most temporary crashes.",
            },
            {
                "step_number": 2,
                "instruction": "Run as Administrator",
                "details": "Right-click the app shortcut -> Run as administrator. Some installers require elevated privileges.",
            },
            {
                "step_number": 3,
                "instruction": "Repair or reinstall via Company Portal",
                "details": "Open Intune Company Portal -> find the app -> click Repair or Reinstall. This re-downloads the approved version.",
            },
            {
                "step_number": 4,
                "instruction": "Check license assignment",
                "details": "For Microsoft 365 apps: go to portal.office.com -> settings -> verify your license. Contact IT if unassigned.",
            },
            {
                "step_number": 5,
                "instruction": "Check Windows Event Viewer for error codes",
                "details": "Win+X -> Event Viewer -> Windows Logs -> Application. Note the error source and Event ID for IT to investigate.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Launch the app, perform a basic action, and confirm it stays stable for 5 minutes.",
            },
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
        "tags": [
            "outlook",
            "email",
            "archive",
            "calendar",
            "quarantine",
            "mfa",
            "password",
            "sync",
            "missing emails",
        ],
        "keywords": [
            "empty folder",
            "archive folder",
            "calendar sync",
            "quarantine release",
            "sspr",
            "password reset",
        ],
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
            {
                "step_number": 1,
                "instruction": "Empty Deleted Items and Junk Email folders",
                "details": "Right-click Deleted Items -> Empty Folder. Right-click Junk Email -> Empty Folder. This frees mailbox space and often unblocks new mail delivery.",
            },
            {
                "step_number": 2,
                "instruction": "Check the Archive folder",
                "details": "In Outlook, look for Online Archive in the left panel. If missing, go to File -> Office Account -> verify your account has an archive licence, or raise a Freshservice ticket to enable it.",
            },
            {
                "step_number": 3,
                "instruction": "Fix Calendar sync",
                "details": "Open Outlook -> Calendar view -> right-click your calendar -> Properties -> Permissions. If sharing is broken, remove and re-share. On mobile, remove and re-add the Exchange account.",
            },
            {
                "step_number": 4,
                "instruction": "Release emails from Microsoft Quarantine",
                "details": "Go to security.microsoft.com -> Email and Collaboration -> Review -> Quarantine. Find the held email, select it, and click Release. If greyed out, raise a Freshservice ticket - admin must release it.",
            },
            {
                "step_number": 5,
                "instruction": "Reset password or re-register MFA via SSPR",
                "details": "If Outlook prompts for password or MFA fails: go to aka.ms/sspr to reset your password, or aka.ms/mfasetup to update your MFA device. Use your registered mobile number or backup email to verify.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Send a test email to yourself and confirm delivery. Open the calendar on your phone and desktop and verify events match.",
            },
        ],
        "escalation_criteria": "Mailbox over quota, archive not available after 1 business day, or quarantine release blocked by admin policy.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "outlook-mailbox-full",
        "title": "Outlook Mailbox Full / Storage Quota Exceeded",
        "short_summary": (
            "Mailbox is at/over its storage quota. Clear Deleted Items and Junk "
            "Email first, remove large attachments, then archive old mail to free space."
        ),
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "mailbox-full",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "storage_quota",
        "severity_hint": "medium",
        "tags": ["outlook", "mailbox", "inbox", "full", "storage", "quota", "space"],
        "keywords": [
            "inbox full",
            "mailbox full",
            "mailbox storage",
            "out of space",
            "over quota",
            "quota exceeded",
            "free up space",
            "reduce mailbox size",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Outlook says the mailbox is full or over quota",
            "Cannot send or receive because the mailbox is full",
            "Storage warning banner at the top of Outlook",
        ],
        "probable_causes": [
            "Mailbox has reached its storage quota",
            "Large attachments and old Sent/Deleted items consuming space",
            "Online Archive not enabled or not connected",
        ],
        "prerequisites": ["Outlook desktop or Outlook on the web access"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Check your current mailbox size and quota",
                "details": "Outlook: File -> Tools -> Mailbox Cleanup -> View Mailbox Size. Outlook on the web: Settings -> General -> Storage.",
            },
            {
                "step_number": 2,
                "instruction": "Empty the Deleted Items folder",
                "details": "Right-click 'Deleted Items' -> Empty Folder. Deleted mail still counts against your quota until this is emptied.",
            },
            {
                "step_number": 3,
                "instruction": "Empty the Junk Email folder",
                "details": "Right-click 'Junk Email' -> Empty Folder to remove spam consuming space.",
            },
            {
                "step_number": 4,
                "instruction": "Delete or clean up large attachments",
                "details": "File -> Tools -> Mailbox Cleanup -> Find items larger than 5 MB, then delete or save-and-remove the largest ones.",
            },
            {
                "step_number": 5,
                "instruction": "Empty the Sent Items folder of old large messages",
                "details": "Sort Sent Items by Size and remove large/old outgoing mail you no longer need.",
            },
            {
                "step_number": 6,
                "instruction": "Archive older email to free up live mailbox space",
                "details": "File -> Tools -> Clean Up Old Items (Archive), or enable Online Archive if your account has it.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Recheck mailbox size (step 1). Send a test email to yourself and confirm it sends and arrives.",
            },
        ],
        "escalation_criteria": "Mailbox still over quota after clearing Deleted/Junk/large items and archiving, or a quota increase is needed.",
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
        "tags": [
            "alias",
            "shared mailbox",
            "distribution list",
            "email address",
            "freshservice",
            "new mailbox",
        ],
        "keywords": [
            "shared email",
            "group mailbox",
            "team inbox",
            "email alias request",
            "distribution group",
        ],
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
            {
                "step_number": 1,
                "instruction": "Raise a Freshservice ticket for the new mailbox",
                "details": "Go to aditi.freshservice.com and raise a new ticket under Email and Outlook -> New Mailbox or Alias Request.",
            },
            {
                "step_number": 2,
                "instruction": "Provide the email address in Aditi standard format",
                "details": "Aditi email addresses follow the pattern: [Division]-[Zone]-[Description]@aditiconsulting.com. Example: hr-bengaluru-onboarding@aditiconsulting.com. Specify this exact address in the ticket.",
            },
            {
                "step_number": 3,
                "instruction": "List the members who need access",
                "details": "In the ticket, list all employees by Aditi email or Employee ID who should have send-as and read access to the shared mailbox.",
            },
            {
                "step_number": 4,
                "instruction": "Get manager approval",
                "details": "CC your reporting manager on the ticket. IT will not create shared mailboxes without manager sign-off.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Once provisioned, send a test email to the new alias and confirm it appears in the shared mailbox inbox.",
            },
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
        "subcategory": "new-joiner-setup",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "high",
        "tags": [
            "new joiner",
            "onboarding",
            "intune",
            "ruddr",
            "laptop",
            "account setup",
            "first day",
        ],
        "keywords": [
            "joining date",
            "enrol device",
            "microsoft 365 account",
            "company portal",
            "it setup",
        ],
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
            {
                "step_number": 1,
                "instruction": "Submit the IT onboarding form before the start date",
                "details": "The hiring manager must raise a Freshservice onboarding ticket at least 3 business days before the joining date. Include: full name, personal email, joining date, office location (Bengaluru, Hyderabad, Delhi, Chennai, Pune, or Mumbai), reporting manager, and role.",
            },
            {
                "step_number": 2,
                "instruction": "Receive Microsoft 365 credentials",
                "details": "IT will email the new joiner personal address with their Aditi email (firstname.lastname@aditiconsulting.com), temporary password, and MFA setup link. Complete MFA setup at aka.ms/mfasetup before day one.",
            },
            {
                "step_number": 3,
                "instruction": "Enrol the laptop in Intune on day one",
                "details": "On your Aditi laptop: Settings -> Accounts -> Access work or school -> Connect -> enter your Aditi email. Install Company Portal from the Microsoft Store and complete device enrolment. This is mandatory for Conditional Access to work.",
            },
            {
                "step_number": 4,
                "instruction": "Set up Ruddr Resource Management",
                "details": "Log in to Ruddr at app.ruddr.io using your Aditi Microsoft 365 account (SSO). If the account is not provisioned, raise a Freshservice ticket under Software -> Ruddr Access.",
            },
            {
                "step_number": 5,
                "instruction": "Raise a laptop ticket if hardware is not ready",
                "details": "If no laptop was issued before the joining date, raise a Freshservice ticket under Hardware -> New Laptop Request with your location and joining date. Standard SLA is 2 business days.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm you can log in to portal.office.com, access Outlook and Teams, and that Company Portal shows your device as Compliant.",
            },
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
        "subcategory": "access-denied-app",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "medium",
        "tags": [
            "ruddr",
            "resource management",
            "login",
            "access",
            "account",
            "project management",
            "timesheet",
        ],
        "keywords": [
            "ruddr login",
            "cannot access ruddr",
            "ruddr account",
            "SSO ruddr",
            "timesheet",
        ],
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
            {
                "step_number": 1,
                "instruction": "Try logging in via Microsoft SSO",
                "details": "Go to app.ruddr.io and click Sign in with Microsoft. Use your Aditi email. Do NOT use a separate Ruddr password.",
            },
            {
                "step_number": 2,
                "instruction": "Clear browser cache and retry",
                "details": "Press Ctrl+Shift+Delete -> clear cookies and cached data for the last 7 days -> close and reopen the browser -> try app.ruddr.io again.",
            },
            {
                "step_number": 3,
                "instruction": "Raise a Freshservice ticket if account is missing",
                "details": "Go to aditi.freshservice.com -> raise a ticket under Software -> Ruddr Access Request. Include your Employee ID, joining date, reporting manager name, and the project(s) you need access to. CC your reporting manager on the ticket.",
            },
            {
                "step_number": 4,
                "instruction": "SLA expectation",
                "details": "Ruddr account provisioning SLA is 1 business day from ticket creation. If not resolved within 1 business day, escalate by adding a note to your Freshservice ticket.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to app.ruddr.io, confirm your name and team appear, and verify you can see your assigned projects and submit a timesheet entry.",
            },
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
        "subcategory": "license-request",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "low",
        "tags": [
            "license",
            "tool access",
            "copilot",
            "github",
            "linkedin recruiter",
            "software request",
            "access request",
        ],
        "keywords": [
            "microsoft copilot",
            "github copilot",
            "linkedin recruiter",
            "tool request",
            "software licence",
            "access approval",
        ],
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
            {
                "step_number": 1,
                "instruction": "Get your reporting manager approval first",
                "details": "Before raising a ticket, confirm with your reporting manager that the tool is approved for your role and a license is available. This is mandatory - IT will not provision without manager sign-off.",
            },
            {
                "step_number": 2,
                "instruction": "Raise a Freshservice ticket for the license",
                "details": "Go to aditi.freshservice.com -> raise a ticket under Software -> License or Tool Access Request. Specify: tool name (e.g. GitHub Copilot), your Employee ID, your role or project, and the business justification.",
            },
            {
                "step_number": 3,
                "instruction": "CC your reporting manager on the ticket",
                "details": "In the Freshservice ticket, add your manager Aditi email in the CC field. IT requires manager approval on the ticket thread before provisioning.",
            },
            {
                "step_number": 4,
                "instruction": "Supported tools and request paths",
                "details": "Microsoft Copilot (M365): M365 admin assigns licence - appears in Office apps automatically. GitHub Copilot: assigned via GitHub org - must specify your GitHub username. LinkedIn Recruiter: requires HR or TA manager approval in addition to reporting manager.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open the requested application and confirm the licensed features are available (e.g. Copilot icon in Word or Teams, Copilot chat in VS Code, LinkedIn Recruiter seats in your LinkedIn account).",
            },
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
        "category": "access/sixth_sense",
        "subcategory": "login-failure",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "medium",
        "tags": [
            "sixth sense",
            "found it",
            "naukri",
            "cloudflare",
            "recruiting",
            "login",
            "plugin",
            "browser extension",
        ],
        "keywords": [
            "cloudflare one",
            "sixth sense login",
            "found it plugin",
            "naukri plugin",
            "resfind",
            "firefox",
        ],
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
            {
                "step_number": 1,
                "instruction": "Use Mozilla Firefox not Chrome",
                "details": "The Naukri or Found It plugin and Sixth Sense portal are only fully supported in Mozilla Firefox at Aditi. Uninstall the plugin from Chrome if installed and install it in Firefox instead.",
            },
            {
                "step_number": 2,
                "instruction": "Install the Naukri or Found It plugin in Firefox",
                "details": "In Firefox, go to the Firefox Add-ons store and search for Naukri RMS or Found It by Monster. Install the plugin and sign in with your Aditi Naukri recruiter credentials.",
            },
            {
                "step_number": 3,
                "instruction": "Access the Sixth Sense portal via the Cloudflare URL",
                "details": "Open Firefox and navigate to 10.2.5.9:9999/resfind - this is the internal Cloudflare One-protected URL for Sixth Sense at Aditi. Do NOT use the public URL.",
            },
            {
                "step_number": 4,
                "instruction": "Authenticate through Cloudflare One",
                "details": "If Cloudflare Access prompts for login, use your Aditi Microsoft 365 credentials (SSO). Click Sign in with Microsoft, complete MFA if prompted. You will be redirected to the Sixth Sense portal once authenticated.",
            },
            {
                "step_number": 5,
                "instruction": "Raise a ticket if access is still blocked",
                "details": "If you still cannot access the portal after following the above steps, raise a Freshservice ticket under Network or Access -> Cloudflare or VPN Access. Include a screenshot of the Cloudflare error page.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open Firefox, navigate to the Cloudflare URL, log in via Microsoft SSO, and confirm you can search and view candidate profiles in Sixth Sense.",
            },
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
    repo: KnowledgeRepository, term_type: str, key: str, label: str, mapping: str | None
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


# ─────────────────────────────────────────────────────────────────────
# YAML-parity articles (granular subtypes from the YAML fallback seed)
# ─────────────────────────────────────────────────────────────────────

_YAML_ARTICLES = [
    # ── Outlook granular subtypes ──────────────────────────────────
    {
        "slug": "outlook-not-receiving",
        "title": "Outlook Not Receiving Emails",
        "short_summary": "New mail is not arriving. Check Work Offline, force Send/Receive, and review Inbox rules.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "not-receiving-emails",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "sync_failure",
        "severity_hint": "medium",
        "tags": ["outlook", "email", "not receiving", "missing", "incoming", "sync"],
        "keywords": [
            "not receiving",
            "no new emails",
            "missing emails",
            "emails not arriving",
            "stopped receiving",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "New mail is not arriving in the inbox",
            "Mailbox appears frozen on old messages",
        ],
        "probable_causes": [
            "Work Offline mode is enabled",
            "Inbox rule moving or deleting mail",
            "Sync hiccup with Exchange",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Make sure Work Offline is turned off",
                "details": "Send/Receive tab — if 'Work Offline' is highlighted, click it to go back online.",
            },
            {
                "step_number": 2,
                "instruction": "Force a manual Send/Receive",
                "details": "Press F9 or click Send/Receive All Folders and watch for new mail.",
            },
            {
                "step_number": 3,
                "instruction": "Check Inbox rules aren't moving or deleting mail",
                "details": "File > Manage Rules & Alerts. Disable any rule that moves matching mail to another folder or deletes it.",
            },
            {
                "step_number": 4,
                "instruction": "Check the Junk Email and other folders",
                "details": "Incoming mail may be filtered into Junk Email. Mark legitimate senders as 'Not Junk'.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Ask a colleague to send a test email and confirm it arrives within 2 minutes.",
            }
        ],
        "escalation_criteria": "If mail still doesn't arrive after these steps, or others on your team also stopped receiving mail, escalate (possible Exchange/M365 issue).",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "outlook-sending-failure",
        "title": "Outlook Cannot Send Emails / Stuck in Outbox",
        "short_summary": "Outgoing messages stuck in Outbox. Confirm you are online, check for oversized attachments, force Send/Receive.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "sending-failure",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "sending_failure",
        "severity_hint": "medium",
        "tags": ["outlook", "email", "send", "outbox", "stuck", "sending"],
        "keywords": ["can't send", "cannot send", "stuck in outbox", "not sending", "send failed"],
        "ownership_group": "endpoint-productivity",
        "symptoms": ["Messages stay in Outbox and never send", "Send/Receive shows an error"],
        "probable_causes": [
            "Work Offline mode enabled",
            "Oversized attachment blocking the queue",
            "Network or Exchange connection issue",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm Outlook is online (Work Offline is off)",
                "details": "Send/Receive tab — ensure 'Work Offline' is not highlighted.",
            },
            {
                "step_number": 2,
                "instruction": "Open the Outbox and check for an oversized message",
                "details": "A message with a very large attachment can block the queue. Remove or shrink the attachment.",
            },
            {
                "step_number": 3,
                "instruction": "Force a Send/Receive",
                "details": "Press F9 to retry sending the queued messages.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Send a test message to yourself and verify it leaves the Outbox and arrives in your Inbox.",
            }
        ],
        "escalation_criteria": "If messages remain stuck after these steps, escalate to IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "outlook-slow-freezing",
        "title": "Outlook Running Slow or Freezing",
        "short_summary": "Outlook is sluggish or freezes. Disable add-ins, restart, apply Office updates.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "outlook-slow",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "performance",
        "severity_hint": "low",
        "tags": ["outlook", "slow", "freezing", "performance", "lagging", "hangs"],
        "keywords": ["slow", "freezing", "lagging", "not responding", "hangs"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Outlook freezes or becomes unresponsive",
            "Takes a long time to open or switch folders",
        ],
        "probable_causes": ["Heavy COM add-ins", "Large local data file", "Pending Office updates"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable non-essential COM add-ins",
                "details": "File > Options > Add-ins > Manage: COM Add-ins > Go. Untick add-ins you don't need, then restart Outlook.",
            },
            {
                "step_number": 2,
                "instruction": "Restart Outlook (and the PC if needed)",
                "details": "Fully close Outlook and reopen. A reboot clears background processes that can slow it down.",
            },
            {
                "step_number": 3,
                "instruction": "Apply pending Office updates",
                "details": "File > Office Account > Update Options > Update Now.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open a large folder and verify Outlook responds immediately without hanging.",
            }
        ],
        "escalation_criteria": "If Outlook stays slow after disabling add-ins and updating, escalate — the local data file may need a repair.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "outlook-offline-mode",
        "title": "Outlook Stuck in Offline Mode / Disconnected",
        "short_summary": "Outlook shows 'Working Offline'. Turn off Work Offline and confirm network/VPN.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "offline-mode",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "connectivity",
        "severity_hint": "medium",
        "tags": ["outlook", "offline", "disconnected", "work offline"],
        "keywords": ["work offline", "offline mode", "shows offline", "disconnected"],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Status bar shows 'Working Offline' or 'Disconnected'",
            "Outlook does not sync",
        ],
        "probable_causes": [
            "Work Offline mode accidentally enabled",
            "VPN not connected",
            "Network issue",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Turn off Work Offline",
                "details": "Send/Receive tab > click 'Work Offline' so it is no longer highlighted.",
            },
            {
                "step_number": 2,
                "instruction": "Confirm you have network connectivity",
                "details": "Open a browser and load any internal site. Connect VPN if your mail requires it.",
            },
            {
                "step_number": 3,
                "instruction": "Restart Outlook",
                "details": "Close and reopen Outlook; the status bar should show 'Connected'.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the status bar shows 'Connected' and a new email arrives within 2 minutes of sending yourself a test.",
            }
        ],
        "escalation_criteria": "If Outlook stays disconnected with working network/VPN, escalate to IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "outlook-general-troubleshooting",
        "title": "General Outlook Troubleshooting",
        "short_summary": "Generic Outlook checks when the specific issue is unclear — restart, connectivity, updates.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "other",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "general",
        "severity_hint": "low",
        "tags": ["outlook", "email", "general", "troubleshoot"],
        "keywords": ["outlook issue", "email issue", "outlook problem"],
        "ownership_group": "endpoint-productivity",
        "symptoms": ["Outlook is not working as expected"],
        "probable_causes": ["Temporary app glitch", "Pending update", "Connectivity issue"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Restart Outlook",
                "details": "Fully close and reopen the app.",
            },
            {
                "step_number": 2,
                "instruction": "Confirm you are online and connected to VPN if required",
                "details": "Check the status bar shows 'Connected'.",
            },
            {
                "step_number": 3,
                "instruction": "Apply pending Office updates",
                "details": "File > Office Account > Update Options > Update Now.",
            },
        ],
        "escalation_criteria": "If the issue is unclear or persists after basic checks, escalate for hands-on support.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # ── Email alias / shared mailbox ──────────────────────────────
    {
        "slug": "alias-shared-mailbox-access",
        "title": "Cannot Access Shared Mailbox / Alias Not Working",
        "short_summary": "Shared mailbox not showing or alias not working. Re-add the mailbox in Outlook or raise an IT ticket if access was never granted.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "shared-mailbox-access",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "medium",
        "tags": [
            "shared mailbox",
            "alias",
            "distribution list",
            "mailbox access",
            "delegate",
            "send as",
        ],
        "keywords": [
            "shared mailbox",
            "can't access shared mailbox",
            "alias not working",
            "distribution list",
            "send as",
            "mailbox not showing",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Shared mailbox not visible in Outlook",
            "Cannot send from an alias address",
            "Access Denied on shared inbox",
        ],
        "probable_causes": [
            "Permissions not yet propagated (can take up to 60 min)",
            "Access not yet granted — IT ticket required",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Close Outlook and reopen it to force a permissions refresh",
                "details": "M365 permissions can take up to 60 minutes to propagate after IT grants access.",
            },
            {
                "step_number": 2,
                "instruction": "Remove and re-add the shared mailbox in Outlook",
                "details": "Go to File > Account Settings > Account Settings > select your main account > Change > More Settings > Advanced tab. Remove the shared mailbox, click OK, reopen Outlook, then add it again using its full email address.",
            },
            {
                "step_number": 3,
                "instruction": "Open the shared mailbox via Outlook on the Web",
                "details": "At outlook.office.com, click your profile picture > Open another mailbox. Type the shared mailbox address. This confirms whether access has been granted at all.",
            },
            {
                "step_number": 4,
                "instruction": "If you do not have access, raise an IT ticket with manager approval",
                "details": "Raise a ticket: 'Shared Mailbox Access — [mailbox name] — [your name]' and CC your manager. IT will action within 1 business day.",
            },
        ],
        "escalation_criteria": "If Outlook on the Web also shows no access and manager has already approved, escalate the existing IT ticket.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "alias-update-add-remove",
        "title": "Alias / Email Alias Add, Remove or Create Request",
        "short_summary": "Alias changes must be raised as an IT ticket. They cannot be self-managed. IT implements within 1 business day.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "email/outlook",
        "subcategory": "alias-update",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "low",
        "tags": ["alias", "email alias", "add alias", "remove alias", "create alias", "smtp alias"],
        "keywords": [
            "alias",
            "email alias",
            "add alias",
            "create alias",
            "remove alias",
            "secondary email",
            "smtp",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Need a secondary email address added to my account",
            "Team needs a new alias created or an existing one removed",
        ],
        "probable_causes": ["Alias changes are IT-managed and require a ticket"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Raise an IT ticket for the alias change",
                "details": "In Freshservice raise a ticket titled: 'Alias Request — [Add/Remove/Create] — [your name]'. Include the exact alias email address required.",
            },
            {
                "step_number": 2,
                "instruction": "Specify the alias format: firstname.lastname@aditiconsulting.com",
                "details": "Non-standard aliases (team or role aliases) require business justification and manager approval in the ticket.",
            },
            {
                "step_number": 3,
                "instruction": "Wait up to 1 business day for IT to implement the change",
                "details": "IT processes alias changes within 1 business day. You will receive a confirmation email when done.",
            },
            {
                "step_number": 4,
                "instruction": "Test the new alias by sending a test email to it",
                "details": "After IT confirms, ask a colleague to send a test email to the alias. Mention 'Send As' permission in the original ticket if you also need to send from the alias.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Ask a colleague to send a test email to the new alias and confirm it arrives in your primary inbox.",
            }
        ],
        "escalation_criteria": "If the alias is not working 24 hours after IT confirmed the change, reply to the original ticket to escalate.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # ── Hardware audio ─────────────────────────────────────────────
    {
        "slug": "audio-voice-breaks-calls",
        "title": "Voice Breaks / Audio Cutting Out During Interview Calls",
        "short_summary": "Close unused apps, select correct headset in Teams/Zoom audio settings, unplug/replug the headset.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/audio",
        "subcategory": "voice-breaks-during-call",
        "platform": "windows",
        "issue_type": "audio_quality",
        "severity_hint": "high",
        "tags": [
            "audio",
            "voice breaks",
            "cutting out",
            "interview",
            "call quality",
            "teams",
            "zoom",
        ],
        "keywords": [
            "voice breaks",
            "audio cutting",
            "cutting out",
            "breaking up",
            "choppy audio",
            "robotic voice",
            "audio drops",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Voice breaking up or cutting out on calls",
            "Participants report choppy or robotic audio",
        ],
        "probable_causes": [
            "Too many open browser tabs consuming bandwidth/CPU",
            "Wrong audio device selected",
            "Loose headset connection",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Close all unused browser tabs and background applications",
                "details": "Each open tab and app consumes bandwidth and CPU. Close everything not needed for the call — this is the single most common fix for choppy audio.",
            },
            {
                "step_number": 2,
                "instruction": "In Teams/Zoom, go to Settings > Audio and select your headset as both mic and speaker",
                "details": "Teams: click '...' > Settings > Devices. Zoom: Settings > Audio. Explicitly select your headset from the dropdown — do not leave it on 'Default'.",
            },
            {
                "step_number": 3,
                "instruction": "Unplug and firmly replug your headset; try a different USB port",
                "details": "A loose connection causes intermittent audio. Unplug, wait 5 seconds, and reconnect. If USB, try a different port.",
            },
            {
                "step_number": 4,
                "instruction": "Mute and unmute yourself to reset the audio stream",
                "details": "Click the mute button in Teams/Zoom and wait 2 seconds, then unmute. This resets the audio capture pipeline.",
            },
            {
                "step_number": 5,
                "instruction": "Rejoin the call if the issue continues",
                "details": "Leave the meeting, close Teams/Zoom fully (system tray), reopen, and rejoin. A fresh session clears any corrupted audio state.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Ask the other participant to confirm they can hear you clearly with no breaks.",
            }
        ],
        "escalation_criteria": "If audio breaks on every call regardless of app or device, contact IT — the audio driver may need updating or the headset may need replacing.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "audio-candidate-cannot-hear",
        "title": "Candidate Cannot Hear Me / Microphone Not Detected",
        "short_summary": "Unmute yourself, select correct mic in Teams/Zoom, verify Windows microphone privacy allows the app.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/audio",
        "subcategory": "candidate-cannot-hear",
        "platform": "windows",
        "issue_type": "microphone",
        "severity_hint": "high",
        "tags": ["microphone", "mic", "cannot hear", "candidate", "no audio output", "interview"],
        "keywords": [
            "candidate cannot hear",
            "they can't hear me",
            "mic not working",
            "microphone not detected",
            "no microphone",
            "muted",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Other person on the call cannot hear me",
            "Microphone icon shows no activity in Teams/Zoom",
        ],
        "probable_causes": [
            "Microphone muted in app or on headset",
            "Wrong microphone device selected",
            "Windows microphone privacy blocking the app",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Check you are not muted in Teams/Zoom",
                "details": "Look for the microphone icon in the call toolbar — a red slash means you are muted. Click it to unmute. Also check the physical mute button on your headset.",
            },
            {
                "step_number": 2,
                "instruction": "Select the correct microphone in Teams/Zoom settings",
                "details": "Teams: '...' > Settings > Devices > Microphone — pick your headset microphone. Zoom: Settings > Audio > Microphone. Do not use 'Default' if multiple devices are listed.",
            },
            {
                "step_number": 3,
                "instruction": "Check Windows microphone privacy settings",
                "details": "Settings > Privacy & Security > Microphone. Ensure 'Microphone access' is ON and that the app (Teams, Zoom, Chrome) is allowed.",
            },
            {
                "step_number": 4,
                "instruction": "Close other apps that may have captured the microphone",
                "details": "If Zoom and Teams are both open, one may have locked the microphone. Close whichever app you are NOT using for this call.",
            },
            {
                "step_number": 5,
                "instruction": "Update audio drivers via Device Manager",
                "details": "Right-click Start > Device Manager > Sound, video and game controllers > right-click your audio device > Update driver > Search automatically. Restart after updating.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Ask the other participant to confirm they can hear you clearly.",
            }
        ],
        "escalation_criteria": "If the microphone is not listed at all in Device Manager, or after updating drivers the problem persists, contact IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "audio-no-sound-output",
        "title": "No Sound / Speakers Not Working on Laptop",
        "short_summary": "Check volume isn't muted, right-click speaker icon to select correct output device, run audio troubleshooter.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/audio",
        "subcategory": "no-audio-output",
        "platform": "windows",
        "issue_type": "audio_output",
        "severity_hint": "medium",
        "tags": ["no sound", "no audio", "speakers", "muted", "audio output", "volume"],
        "keywords": [
            "no sound",
            "no audio",
            "speakers not working",
            "can't hear anything",
            "sound not working",
            "muted",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "No sound from laptop speakers or headset",
            "Volume slider present but no audio plays",
        ],
        "probable_causes": [
            "Volume muted or at zero",
            "Wrong output device selected",
            "Audio driver issue",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Check volume level and ensure the laptop is not muted",
                "details": "Click the speaker icon in the taskbar. Make sure the slider is not at zero and the icon doesn't show a red X. Also check any physical volume/mute keys on your keyboard (Fn + mute key).",
            },
            {
                "step_number": 2,
                "instruction": "Right-click the speaker icon and select the correct output device",
                "details": "Right-click the speaker icon > Sound settings. Under Output, change the device to your speakers or headset. If a headset is plugged in, make sure Windows switched to it.",
            },
            {
                "step_number": 3,
                "instruction": "Run the Windows Audio Troubleshooter",
                "details": "Settings > System > Troubleshoot > Other troubleshooters > Playing Audio > Run. Apply any recommendations.",
            },
            {
                "step_number": 4,
                "instruction": "Restart the Windows Audio service",
                "details": "Press Win+R, type services.msc, find 'Windows Audio', right-click > Restart. Also restart 'Windows Audio Endpoint Builder'.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Play a short audio file or YouTube video and confirm sound comes through.",
            }
        ],
        "escalation_criteria": "If no audio device appears in Sound settings, or the audio troubleshooter reports a hardware fault, contact IT support.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # ── Hardware camera ────────────────────────────────────────────
    {
        "slug": "camera-not-working",
        "title": "Laptop Camera Not Working",
        "short_summary": "Check the physical privacy shutter, enable camera in Windows Privacy settings, and verify app permissions.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/camera",
        "subcategory": "camera-not-detected",
        "platform": "windows",
        "issue_type": "camera_fault",
        "severity_hint": "medium",
        "tags": ["camera", "webcam", "video", "not working", "permissions", "black screen"],
        "keywords": [
            "camera not working",
            "webcam not working",
            "black screen camera",
            "camera not detected",
            "no camera",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Camera shows black screen in Zoom or Teams",
            "Camera not detected or missing from device list",
        ],
        "probable_causes": [
            "Physical privacy shutter closed",
            "Windows camera privacy setting disabled",
            "Another app holding the camera",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Restart your laptop",
                "details": "A simple restart resolves many camera driver issues.",
            },
            {
                "step_number": 2,
                "instruction": "Check if camera is physically blocked",
                "details": "Many laptops have a physical privacy shutter. Ensure it is open/slid to reveal the camera lens.",
            },
            {
                "step_number": 3,
                "instruction": "Enable Camera Access in Privacy & Security settings",
                "details": "Go to Settings > Privacy & Security > Camera. Ensure 'Camera access' is turned ON.",
            },
            {
                "step_number": 4,
                "instruction": "Enable camera permissions for specific apps",
                "details": "In the same Camera settings, ensure the apps you need (Zoom, Teams) have camera permission enabled.",
            },
            {
                "step_number": 5,
                "instruction": "Close other applications using the camera",
                "details": "Only one app can use the camera at a time. Close Teams if using Zoom, and vice versa.",
            },
            {
                "step_number": 6,
                "instruction": "Test camera in the application's settings",
                "details": "Open Zoom/Teams Settings > Video/Camera and check if you see your preview.",
            },
            {
                "step_number": 7,
                "instruction": "Check Device Manager for camera driver",
                "details": "Right-click Start > Device Manager > Cameras. Check for warning icons. Right-click > Update driver if needed.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open Zoom or Teams settings and verify you see your own camera preview.",
            }
        ],
        "escalation_criteria": "If camera doesn't appear in Device Manager or driver update fails, contact IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # ── Network connectivity ───────────────────────────────────────
    {
        "slug": "network-vpn-not-connecting",
        "title": "VPN Not Connecting (GlobalProtect / Cisco)",
        "short_summary": "Disconnect VPN fully, restart the client, then reconnect and authenticate with Aditi credentials + MFA.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "network/connectivity",
        "subcategory": "vpn-not-connecting",
        "product_or_system": "globalprotect",
        "platform": "windows",
        "issue_type": "vpn",
        "severity_hint": "high",
        "tags": ["vpn", "globalprotect", "cisco", "not connecting", "network", "remote"],
        "keywords": [
            "vpn not connecting",
            "vpn won't connect",
            "can't connect to vpn",
            "vpn failed",
            "globalprotect",
            "cisco vpn",
        ],
        "ownership_group": "network-access",
        "symptoms": ["VPN client fails to connect", "Certificate error or 'Gateway unreachable'"],
        "probable_causes": ["Stale VPN session", "Network adapter issue", "Authentication failure"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disconnect from VPN completely and close the client",
                "details": "Right-click the VPN icon in the system tray and choose Disconnect. Then right-click again and Exit/Quit the application entirely.",
            },
            {
                "step_number": 2,
                "instruction": "Restart your Wi-Fi or switch to a wired connection",
                "details": "Turn Wi-Fi off and on again on your laptop, or plug in an Ethernet cable if available.",
            },
            {
                "step_number": 3,
                "instruction": "Reopen the VPN client and connect to the Aditi gateway",
                "details": "Open GlobalProtect or Cisco AnyConnect. Ensure the gateway address is set to the Aditi VPN endpoint. Click Connect.",
            },
            {
                "step_number": 4,
                "instruction": "Authenticate with your Aditi email and password + MFA",
                "details": "Enter your @aditiconsulting.com email and current password. Approve the MFA push notification or enter the 6-digit Authenticator code.",
            },
            {
                "step_number": 5,
                "instruction": "Restart your laptop if VPN still won't connect",
                "details": "A full restart clears stale network sessions. After reboot, try connecting to VPN before opening any other applications.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm VPN shows 'Connected' and access an internal resource (e.g. intranet page).",
            }
        ],
        "escalation_criteria": "If VPN fails after restart and reconnect, or you receive 'certificate error' or 'gateway unreachable', contact IT — your VPN profile may need re-provisioning.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "network-wifi-dropping",
        "title": "Wi-Fi Keeps Dropping / Slow Internet",
        "short_summary": "Disable Wi-Fi power management, forget and re-join the network, update the Wi-Fi driver.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "network/connectivity",
        "subcategory": "wifi-disconnecting",
        "platform": "windows",
        "issue_type": "wifi_instability",
        "severity_hint": "medium",
        "tags": ["wifi", "wi-fi", "dropping", "slow", "internet", "connectivity", "unstable"],
        "keywords": [
            "wifi keeps dropping",
            "wi-fi disconnecting",
            "slow internet",
            "keeps disconnecting",
            "unstable connection",
        ],
        "ownership_group": "network-access",
        "symptoms": ["Wi-Fi disconnects repeatedly", "Internet connection is slow or intermittent"],
        "probable_causes": [
            "Wi-Fi adapter power management switching off the adapter",
            "Too far from access point",
            "Outdated Wi-Fi driver",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable Wi-Fi adapter power management",
                "details": "Right-click Start > Device Manager > Network Adapters > right-click your Wi-Fi adapter > Properties > Power Management tab > uncheck 'Allow the computer to turn off this device to save power'.",
            },
            {
                "step_number": 2,
                "instruction": "Forget and rejoin the Wi-Fi network",
                "details": "Click the Wi-Fi icon in the taskbar > click the network name > Forget. Then reconnect and enter the password.",
            },
            {
                "step_number": 3,
                "instruction": "Run the Windows Network Troubleshooter",
                "details": "Settings > System > Troubleshoot > Other troubleshooters > Internet Connections > Run. Apply any fixes it suggests.",
            },
            {
                "step_number": 4,
                "instruction": "Update the Wi-Fi driver",
                "details": "Device Manager > Network Adapters > right-click Wi-Fi adapter > Update driver > Search automatically. Restart after updating.",
            },
            {
                "step_number": 5,
                "instruction": "Move closer to the Wi-Fi access point or switch to 5 GHz band",
                "details": "If the router broadcasts both 2.4 GHz and 5 GHz, connect to the 5 GHz network (usually labelled '_5G') for faster, more stable connection when in range.",
            },
        ],
        "validation_steps": [
            {"step_number": 1, "instruction": "Stay connected for 15 minutes and confirm no drops."}
        ],
        "escalation_criteria": "If the issue persists at the office (not a home network), contact IT — the access point or DHCP configuration may need attention.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "network-no-internet",
        "title": "No Internet Connection / Can't Connect to Internet",
        "short_summary": "Restart network adapter, check cables, try another network or wired connection, run Windows troubleshooter.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "network/connectivity",
        "subcategory": "internet",
        "platform": "windows",
        "issue_type": "connectivity",
        "severity_hint": "high",
        "tags": [
            "internet",
            "no internet",
            "can't connect",
            "connectivity",
            "offline",
            "disconnected",
        ],
        "keywords": [
            "can't connect to internet",
            "no internet",
            "internet not working",
            "no network",
            "offline",
            "disconnected from internet",
        ],
        "ownership_group": "network-access",
        "symptoms": ["No internet access on laptop", "All websites fail to load"],
        "probable_causes": [
            "Network adapter issue",
            "DHCP or DNS misconfiguration",
            "Router or gateway problem",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Check if you're connected to a network",
                "details": "Look at the Wi-Fi or Ethernet icon in the taskbar. If using a wired connection, make sure the Ethernet cable is plugged in.",
            },
            {
                "step_number": 2,
                "instruction": "Disconnect and reconnect your network adapter",
                "details": "Right-click the Wi-Fi icon > Wi-Fi > turn Off. Wait 5 seconds, then turn it On again. Or, if wired, unplug the Ethernet cable for 10 seconds and plug it back in.",
            },
            {
                "step_number": 3,
                "instruction": "Forget and rejoin the Wi-Fi network (if on Wi-Fi)",
                "details": "Click the Wi-Fi icon > click the network name > Forget. Then click the Wi-Fi icon again and select the same network.",
            },
            {
                "step_number": 4,
                "instruction": "Try a different network to isolate the issue",
                "details": "Connect to a phone hotspot to confirm if the issue is your network or your laptop.",
            },
            {
                "step_number": 5,
                "instruction": "Run the Windows Network Troubleshooter",
                "details": "Settings > System > Troubleshoot > Other troubleshooters > Internet Connections > Run.",
            },
            {
                "step_number": 6,
                "instruction": "Restart your laptop",
                "details": "A full reboot clears network adapter drivers and DHCP lease issues.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open a browser and confirm websites load after the fix.",
            }
        ],
        "escalation_criteria": "If internet is still unavailable after restarting, contact IT — the network adapter may need a driver update.",
        "escalation_target_team": "Network & Access",
    },
    # ── Access / permissions granular articles ─────────────────────
    {
        "slug": "access-account-locked",
        "title": "AD Account Locked / Unable to Login",
        "short_summary": "Account locked after failed attempts. Use SSPR at aka.ms/sspr to unlock and reset, or wait 30 min for auto-unlock.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "account-locked",
        "product_or_system": "azure_ad",
        "platform": "windows",
        "issue_type": "account_locked",
        "severity_hint": "high",
        "tags": ["account locked", "login", "password", "AD", "active directory", "locked out"],
        "keywords": [
            "account locked",
            "locked out",
            "can't login",
            "unable to login",
            "login failed",
            "too many attempts",
        ],
        "ownership_group": "network-access",
        "symptoms": [
            "Account is locked — cannot log in to Windows, VPN, or Office 365",
            "Message says 'Your account has been locked'",
        ],
        "probable_causes": [
            "Too many failed login attempts triggered lockout policy",
            "Saved password in an app retrying with an old password",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Stop all login attempts immediately",
                "details": "Each failed attempt resets the lockout timer. Do not try again until you follow the steps below.",
            },
            {
                "step_number": 2,
                "instruction": "Use Self-Service Password Reset (SSPR) to unlock your account",
                "details": "Go to https://aka.ms/sspr in a browser. Enter your Aditi email, verify via registered method, and reset your password. This unlocks and resets in one step.",
            },
            {
                "step_number": 3,
                "instruction": "Wait 30 minutes if SSPR is not available",
                "details": "If you cannot access SSPR, the account auto-unlocks after 30 minutes of no login attempts.",
            },
            {
                "step_number": 4,
                "instruction": "Update saved passwords everywhere",
                "details": "After resetting, update the saved password in your browser, VPN client, Outlook mobile app, and any other apps that may be retrying with the old password.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to portal.office.com and confirm access to Outlook and Teams.",
            }
        ],
        "escalation_criteria": "If SSPR fails, account is still locked after 30 minutes, or you believe your account may have been compromised, contact IT immediately.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "access-password-expired",
        "title": "Password Expired / Force Password Change",
        "short_summary": "Press Ctrl+Alt+Del to change password on your laptop, or use SSPR at aka.ms/sspr. Then update all apps.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "password-expired",
        "product_or_system": "azure_ad",
        "platform": "windows",
        "issue_type": "password_expired",
        "severity_hint": "medium",
        "tags": ["password expired", "change password", "reset password", "force change"],
        "keywords": [
            "password expired",
            "must change password",
            "change your password",
            "password reset",
            "force change password",
        ],
        "ownership_group": "network-access",
        "symptoms": [
            "Windows prompts for a password change on login",
            "Outlook or VPN stops working suddenly",
        ],
        "probable_causes": ["Aditi's 90-day password policy has expired"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Change your password using Ctrl+Alt+Del on your Windows laptop",
                "details": "Press Ctrl+Alt+Del and select 'Change a password'. Enter the old password and set a new one (12+ characters, uppercase, lowercase, number, symbol).",
            },
            {
                "step_number": 2,
                "instruction": "Alternatively, use SSPR at https://aka.ms/sspr",
                "details": "If you cannot log in at all, go to https://aka.ms/sspr, verify your identity, and set a new password remotely.",
            },
            {
                "step_number": 3,
                "instruction": "Update your password in all connected apps and devices",
                "details": "After changing: update Outlook mobile, VPN client (GlobalProtect/Cisco), Teams mobile, and any browser saved passwords. Old passwords stored in apps will re-lock your account.",
            },
            {
                "step_number": 4,
                "instruction": "Re-authenticate in Outlook and VPN",
                "details": "Open Outlook — it may prompt for your new credentials. Open your VPN client and sign in again with the new password.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in successfully and confirm VPN and Outlook are both working with the new password.",
            }
        ],
        "escalation_criteria": "If you are unable to change the password via Ctrl+Alt+Del or SSPR, contact IT support.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "access-mfa-not-working",
        "title": "MFA / Authenticator Not Working",
        "short_summary": "Check phone date/time is auto-set. Open Authenticator and refresh. Use 6-digit code if push not arriving.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "mfa-not-working",
        "product_or_system": "azure_ad",
        "platform": "windows",
        "issue_type": "mfa",
        "severity_hint": "high",
        "tags": ["mfa", "multi-factor", "authenticator", "microsoft authenticator", "2fa", "otp"],
        "keywords": [
            "mfa not working",
            "authenticator not working",
            "no code",
            "two factor",
            "2fa",
            "push notification not arriving",
        ],
        "ownership_group": "network-access",
        "symptoms": [
            "Microsoft Authenticator push notification not arriving",
            "6-digit codes not accepted",
            "Cannot complete MFA to sign in",
        ],
        "probable_causes": [
            "Phone time not set to automatic",
            "Authenticator app needs a refresh",
            "Phone changed — MFA not re-registered",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Ensure your phone's date and time are set to automatic",
                "details": "Go to Settings > General (iOS) or Settings > Date & Time (Android) and enable 'Set Automatically'. An incorrect clock causes TOTP codes to be invalid.",
            },
            {
                "step_number": 2,
                "instruction": "Open the Microsoft Authenticator app and pull down to refresh",
                "details": "Open Authenticator, find your Aditi account, and pull down to force a refresh.",
            },
            {
                "step_number": 3,
                "instruction": "Use the 6-digit code instead of waiting for the push notification",
                "details": "Tap your Aditi account in Authenticator to see the 6-digit TOTP code. Enter this manually on the sign-in page when prompted.",
            },
            {
                "step_number": 4,
                "instruction": "If you have lost your phone, use a backup method",
                "details": "On the Microsoft sign-in page, click 'Sign in another way' to use SMS, email, or a backup code.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Sign in to portal.office.com and confirm MFA completes successfully.",
            }
        ],
        "escalation_criteria": "If you have lost access to your phone and have no backup method, contact IT — they will verify your identity and reset your MFA registration.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "new-joiner-setup",
        "title": "New Joiner — Email, Laptop or Tool Access Not Provisioned",
        "short_summary": "Raise an urgent IT ticket with start date, location, manager name, and employee ID. IT will prioritise same-day provisioning.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "new-joiner-setup",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "high",
        "tags": [
            "new joiner",
            "onboarding",
            "email not created",
            "laptop",
            "tools",
            "provisioning",
            "access",
        ],
        "keywords": [
            "new joiner",
            "new employee",
            "just joined",
            "email not created",
            "account not set up",
            "laptop not received",
            "tools not provisioned",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "New employee does not have email or M365 access on day 1",
            "Laptop not received or not enrolled in Intune",
        ],
        "probable_causes": ["IT New Joiner Request Form not submitted before start date"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the New Joiner Request Form was submitted before your start date",
                "details": "Your manager or HR should have submitted the IT New Joiner Request Form at least 3 business days before your start date.",
            },
            {
                "step_number": 2,
                "instruction": "Raise an urgent IT ticket: 'New Joiner Access Missing — [Your Full Name]'",
                "details": "Include: full name, employee ID, start date, location, manager name and email, and the list of missing access. Mark the ticket as High priority.",
            },
            {
                "step_number": 3,
                "instruction": "Ask your manager to CC themselves on the ticket",
                "details": "Manager confirmation speeds up provisioning. Your manager should also follow up directly with IT if day-1 access is critically needed.",
            },
            {
                "step_number": 4,
                "instruction": "IT will provision email, Ruddr, and core tools within the agreed SLA",
                "details": "Once IT receives the complete ticket, email, Ruddr, and M365 access are provisioned within 1 business day. Laptop shipment follows a separate timeline.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to portal.office.com and confirm access to Outlook, Teams, and Company Portal.",
            }
        ],
        "escalation_criteria": "If email access is not provisioned within 1 business day, reply with URGENT. Ask your manager to escalate to IT leadership.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "ruddr-account-missing",
        "title": "Ruddr Account Missing / Not Created After Joining",
        "short_summary": "Raise an IT ticket with your full name, employee ID, manager, and start date. IT actions within 1 business day.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "ruddr-account-missing",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "medium",
        "tags": [
            "ruddr",
            "account missing",
            "not created",
            "new joiner",
            "timesheet",
            "project tracking",
        ],
        "keywords": [
            "ruddr",
            "ruddr account",
            "ruddr account missing",
            "ruddr not set up",
            "cannot access ruddr",
            "ruddr timesheet",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Cannot log in to Ruddr at app.ruddr.io",
            "Account not found or access denied",
        ],
        "probable_causes": [
            "Ruddr account not provisioned — onboarding ticket not raised",
            "New joiner form missing Ruddr in the request",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Raise an IT support ticket immediately",
                "details": "Go to Freshservice and raise a ticket titled: 'Ruddr Account Missing — [Your Full Name]'.",
            },
            {
                "step_number": 2,
                "instruction": "Include your full name, employee ID, manager name, and start date in the ticket",
                "details": "IT needs these details to locate your record and create or restore your Ruddr account.",
            },
            {
                "step_number": 3,
                "instruction": "CC your manager on the ticket",
                "details": "Ruddr access is linked to your project assignment. Your manager must confirm the project code.",
            },
            {
                "step_number": 4,
                "instruction": "Wait up to 1 business day for IT to action the ticket",
                "details": "Once IT receives the ticket with all required information, your Ruddr account will be created within 1 business day.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to app.ruddr.io and confirm your name, team, and assigned projects appear.",
            }
        ],
        "escalation_criteria": "If the account is still missing after 1 business day from ticket submission, reply to the ticket to escalate.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "ruddr-account-locked",
        "title": "Ruddr Account Disabled or Locked",
        "short_summary": "A disabled Ruddr account must be re-enabled by IT. Raise a ticket with your name, employee ID, and manager CC'd.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "ruddr-account-locked",
        "platform": "windows",
        "issue_type": "account_locked",
        "severity_hint": "medium",
        "tags": ["ruddr", "account locked", "account disabled", "blocked", "cannot login"],
        "keywords": [
            "ruddr account locked",
            "ruddr account disabled",
            "ruddr blocked",
            "ruddr access denied",
            "ruddr suspended",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": ["Ruddr login returns 'Account disabled' or 'Access denied'"],
        "probable_causes": [
            "Account disabled during extended leave or audit",
            "Account suspended by admin",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Do not attempt repeated logins — raise an IT ticket instead",
                "details": "Multiple failed login attempts will not help. This issue requires IT intervention.",
            },
            {
                "step_number": 2,
                "instruction": "Raise a ticket: 'Ruddr Account Disabled — [Your Full Name]'",
                "details": "Include your full name, employee ID, your manager's name, and the date you last had access.",
            },
            {
                "step_number": 3,
                "instruction": "CC your manager on the ticket",
                "details": "Your manager's confirmation is required before IT re-enables access — this is a security control.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to app.ruddr.io and confirm access is restored.",
            }
        ],
        "escalation_criteria": "If IT has not responded within 1 business day, reply with URGENT. For business-critical access, ask your manager to escalate to IT leadership.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "license-request",
        "title": "Software License / Tool Access Request (Copilot, GitHub, LinkedIn, Keeper)",
        "short_summary": "Get manager approval first, then raise an IT ticket. Provisioning takes 1–3 business days after approval.",
        "article_type": "how_to",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "license-request",
        "platform": "windows",
        "issue_type": "provisioning",
        "severity_hint": "low",
        "tags": [
            "license",
            "tool access",
            "copilot",
            "github",
            "linkedin recruiter",
            "keeper",
            "software",
        ],
        "keywords": [
            "license request",
            "software license",
            "tool access",
            "copilot license",
            "github access",
            "linkedin recruiter",
            "keeper",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Need access to Microsoft Copilot, GitHub Copilot, LinkedIn Recruiter, or Keeper",
            "License not assigned to my account",
        ],
        "probable_causes": [
            "License not yet assigned — requires manager approval before provisioning"
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Get verbal or written approval from your manager before raising a ticket",
                "details": "All tool licenses require manager sign-off. Confirm the business need before raising the IT ticket.",
            },
            {
                "step_number": 2,
                "instruction": "Raise an IT ticket: 'License Request — [Tool Name] — [Your Name]'",
                "details": "Include: tool/software name, business justification, project name (if applicable), manager name and approval confirmation.",
            },
            {
                "step_number": 3,
                "instruction": "IT will confirm with procurement and provision within 1–3 business days",
                "details": "Once approved, IT will provision access. You will receive an email with login instructions.",
            },
            {
                "step_number": 4,
                "instruction": "For GitHub access — include the repo or org name",
                "details": "If you need access to a specific Aditi GitHub organisation or repository, include the exact repo URL in the ticket.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open the requested application and confirm the licensed features are available (e.g. Copilot icon in Word, Copilot chat in VS Code).",
            }
        ],
        "escalation_criteria": "If no response after 3 business days, reply to the ticket and CC your manager.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "license-not-working",
        "title": "Licensed Tool Not Working / Access Denied After Provisioning",
        "short_summary": "Sign out and back in, clear browser cache, allow 1 hour for permission propagation. If still blocked, reply to your original IT ticket.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/permissions",
        "subcategory": "access-denied-app",
        "platform": "windows",
        "issue_type": "access_denied",
        "severity_hint": "medium",
        "tags": [
            "license not working",
            "access denied",
            "tool not working",
            "software error",
            "provisioned but blocked",
        ],
        "keywords": [
            "access denied",
            "license not working",
            "tool not working after provisioning",
            "not authorized",
            "licence expired",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Tool shows 'Access Denied' or 'Not Authorized' after IT provisioned the license"
        ],
        "probable_causes": [
            "Permissions not yet propagated (can take up to 60 min)",
            "Old browser session caching previous permissions",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Sign out of the tool completely and sign back in",
                "details": "Sign out from all instances (browser, desktop app, mobile) and sign back in with your Aditi SSO credentials.",
            },
            {
                "step_number": 2,
                "instruction": "Clear browser cache and cookies for the tool's domain",
                "details": "In Chrome: Ctrl+Shift+Delete > Cached images and files + Cookies > Clear data. Then reopen the tool's website and sign in fresh.",
            },
            {
                "step_number": 3,
                "instruction": "Wait up to 1 hour for the license assignment to propagate",
                "details": "M365 and most SaaS tools take up to 60 minutes for new license assignments to become active.",
            },
            {
                "step_number": 4,
                "instruction": "Try accessing from a private/incognito browser window",
                "details": "Open an incognito window (Ctrl+Shift+N) and visit the tool. If it works in incognito, the issue is a cached session — clearing cookies will fix it permanently.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the licensed features are accessible (e.g. Copilot icon appears, GitHub shows organisation membership).",
            }
        ],
        "escalation_criteria": "If access is still denied 2 hours after IT confirmed provisioning, reply to the original IT ticket with a screenshot of the error.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    # ── Sixth Sense / Naukri ───────────────────────────────────────
    {
        "slug": "sixth-sense-account-locked",
        "title": "Sixth Sense / Naukri Login Issues — Account Locked or Unhandled Message",
        "short_summary": "Account locks after 5+ wrong password attempts. Wait 1 hour for auto-unlock, then reset password at naukri.com.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/sixth_sense",
        "subcategory": "login-failure",
        "platform": "windows",
        "issue_type": "account_locked",
        "severity_hint": "medium",
        "tags": ["sixth sense", "naukri", "login", "account locked", "unhandled message", "otp"],
        "keywords": [
            "sixth sense login",
            "naukri login",
            "sixth sense blocked",
            "naukri account locked",
            "unhandled message",
        ],
        "ownership_group": "network-access",
        "symptoms": [
            "Cannot log in to Sixth Sense or Naukri",
            "Message says account is blocked after multiple failed attempts",
        ],
        "probable_causes": [
            "5+ incorrect password attempts triggered lockout",
            "Direct naukri.com login causing Unhandled Message error",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Stop all login attempts immediately",
                "details": "Each attempt resets the 1-hour lock timer. Do NOT try to log in again.",
            },
            {
                "step_number": 2,
                "instruction": "Wait for 1 hour for the account to auto-unlock",
                "details": "The Naukri system automatically unlocks your account after 1 hour of inactivity.",
            },
            {
                "step_number": 3,
                "instruction": "After 1 hour, reset your password at naukri.com",
                "details": "Visit naukri.com and click 'Forgot Password'. Follow the email/OTP verification to set a new password.",
            },
            {
                "step_number": 4,
                "instruction": "Update the new password in the Sixth Sense portal",
                "details": "Once your Naukri password is reset, open the Sixth Sense portal and update your credentials.",
            },
            {
                "step_number": 5,
                "instruction": "Always use the Sixth Sense portal URL, not naukri.com directly",
                "details": "Direct login via naukri.com can trigger the 'Unhandled Message' error. Use the portal URL provided by IT.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in to the Sixth Sense portal and confirm you can search and view candidate profiles.",
            }
        ],
        "escalation_criteria": "If the account remains locked after 1 hour, or if you cannot receive OTP/password reset emails, escalate to IT.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "sixth-sense-unhandled-message",
        "title": "Sixth Sense — 'Unhandled Message' Error on Direct Login",
        "short_summary": "Use the Sixth Sense portal URL instead of logging in directly on naukri.com. Clear browser cache if error persists.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/sixth_sense",
        "subcategory": "unhandled-message",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "low",
        "tags": ["sixth sense", "naukri", "unhandled message", "error", "direct login"],
        "keywords": [
            "unhandled message",
            "sixth sense error",
            "naukri error",
            "portal login",
            "sixth sense unhandled",
        ],
        "ownership_group": "network-access",
        "symptoms": ["'Unhandled Message' error when logging in to Naukri or Sixth Sense"],
        "probable_causes": [
            "User tried to log in directly via naukri.com instead of the Sixth Sense portal"
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Do not log in through naukri.com directly",
                "details": "Direct login via the Naukri website triggers the 'Unhandled Message' error due to SSO/integration configuration.",
            },
            {
                "step_number": 2,
                "instruction": "Use the Sixth Sense portal URL provided by IT",
                "details": "Always access Sixth Sense through the designated portal URL. This ensures proper authentication flow.",
            },
            {
                "step_number": 3,
                "instruction": "Clear browser cache and cookies if the error persists",
                "details": "Press Ctrl+Shift+Delete, clear cookies for naukri.com and the Sixth Sense portal domain, then try again.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Log in via the portal URL and confirm you reach the Sixth Sense dashboard.",
            }
        ],
        "escalation_criteria": "If the error persists after using the portal URL and clearing cache, escalate to IT.",
        "escalation_target_team": "Network & Access",
    },
    {
        "slug": "sixth-sense-otp-not-received",
        "title": "Sixth Sense — OTP Not Received After Account Recovery",
        "short_summary": "Wait for the full 1-hour lock period. Check spam folder. Request a new OTP after 2 minutes.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "access/sixth_sense",
        "subcategory": "otp-issue",
        "platform": "windows",
        "issue_type": "otp",
        "severity_hint": "low",
        "tags": ["sixth sense", "naukri", "otp", "verification", "password reset"],
        "keywords": [
            "otp not received",
            "sixth sense otp",
            "naukri otp",
            "no otp",
            "verification code not arriving",
        ],
        "ownership_group": "network-access",
        "symptoms": ["OTP email not arriving after requesting account recovery for Sixth Sense"],
        "probable_causes": ["OTP requested during active lock period", "OTP email in spam folder"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Ensure the 1-hour lock period has fully elapsed",
                "details": "OTP delivery may be blocked during the active lock period. Wait the full hour before requesting any OTP.",
            },
            {
                "step_number": 2,
                "instruction": "Check spam/junk folder in your registered email",
                "details": "OTP emails from Naukri sometimes land in spam. Search for emails from naukri.com in your junk folder.",
            },
            {
                "step_number": 3,
                "instruction": "Request a new OTP after a 2-minute wait",
                "details": "If the first OTP didn't arrive, wait at least 2 minutes before requesting a new one. Rapid requests may be rate-limited.",
            },
            {
                "step_number": 4,
                "instruction": "Verify your registered email/phone is correct",
                "details": "If you recently changed your email or phone, the OTP may be going to the old contact. Contact IT to update your registered details.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Enter the OTP successfully and confirm you can complete the password reset.",
            }
        ],
        "escalation_criteria": "If OTP is still not received after following all steps, escalate to IT to verify the registered contact information.",
        "escalation_target_team": "Network & Access",
    },
    # ── Zoom granular articles ─────────────────────────────────────
    {
        "slug": "zoom-sign-in-issues",
        "title": "Zoom Sign-In Issues",
        "short_summary": "Use 'Sign In with SSO' and enter 'aditiconsulting' as the company domain. Clear Zoom cache if SSO fails.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "video-conferencing/zoom",
        "subcategory": "sign-in-issue",
        "product_or_system": "zoom",
        "platform": "windows",
        "issue_type": "authentication",
        "severity_hint": "medium",
        "tags": ["zoom", "sign-in", "login", "SSO", "authentication"],
        "keywords": [
            "zoom sign in",
            "zoom login",
            "zoom SSO",
            "zoom not signing in",
            "zoom authentication",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": ["Cannot sign in to Zoom", "Zoom login fails or shows error"],
        "probable_causes": [
            "Using email/password instead of SSO",
            "Stale Zoom cache",
            "KYC not completed for India-based users",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Open Zoom and click 'Sign In with SSO'",
                "details": "Do NOT use regular email/password login. SSO is required for Aditi accounts.",
            },
            {
                "step_number": 2,
                "instruction": "Enter the company SSO domain: aditiconsulting",
                "details": "Type 'aditiconsulting' when prompted for the company domain, then complete authentication.",
            },
            {
                "step_number": 3,
                "instruction": "Complete authentication via the Aditi login page",
                "details": "Use your Aditi corporate credentials (email + MFA) to authenticate on the Microsoft login page.",
            },
            {
                "step_number": 4,
                "instruction": "For India-based users: complete KYC if prompted",
                "details": "Indian regulatory requirements may require KYC completion for Zoom access.",
            },
            {
                "step_number": 5,
                "instruction": "If SSO fails, clear Zoom cache",
                "details": "Close Zoom > Delete %AppData%/Zoom folder > Restart Zoom and try SSO login again.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm you reach the Zoom home screen with your Aditi name and email shown.",
            }
        ],
        "escalation_criteria": "If SSO authentication fails after clearing cache, contact IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "zoom-audio-issues",
        "title": "Zoom Audio Issues — Microphone or Speaker Not Working",
        "short_summary": "Go to Zoom Settings > Audio, verify correct devices are selected, and test speaker/mic before the call.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "video-conferencing/zoom",
        "subcategory": "no-audio",
        "product_or_system": "zoom",
        "platform": "windows",
        "issue_type": "audio_quality",
        "severity_hint": "medium",
        "tags": ["zoom", "audio", "microphone", "speaker", "no sound"],
        "keywords": [
            "zoom audio not working",
            "zoom microphone",
            "zoom speaker",
            "zoom no sound",
            "zoom echo",
        ],
        "ownership_group": "endpoint-productivity",
        "symptoms": [
            "Cannot hear others in Zoom",
            "Others cannot hear me in Zoom",
            "Echo in Zoom calls",
        ],
        "probable_causes": [
            "Wrong audio device selected in Zoom",
            "Another app locking the microphone or speaker",
        ],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Open Zoom Settings > Audio",
                "details": "Click your profile icon (top right) > Settings > Audio.",
            },
            {
                "step_number": 2,
                "instruction": "Verify correct speaker device is selected",
                "details": "Click 'Test Speaker' to confirm you can hear the test tone. Select the correct device from the dropdown.",
            },
            {
                "step_number": 3,
                "instruction": "Verify correct microphone device is selected",
                "details": "Click 'Test Mic' and speak — verify the input level bar moves. Select the correct device.",
            },
            {
                "step_number": 4,
                "instruction": "Check system audio settings",
                "details": "Open Windows Sound Settings and ensure correct default devices are set for both input and output.",
            },
            {
                "step_number": 5,
                "instruction": "Close other applications that may use audio",
                "details": "Close Teams, Discord, or other apps that might lock audio devices. Restart Zoom.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Use Zoom's Test Speaker and Test Microphone and confirm both work before joining the call.",
            }
        ],
        "escalation_criteria": "If audio issues persist after checking all device settings, contact IT.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-keyboard-not-working",
        "title": "Laptop Keyboard Not Working",
        "short_summary": "Fix a laptop keyboard that's unresponsive, wrong chars, or intermittent.",
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "keyboard-not-working",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["keyboard", "keys", "typing", "laptop", "hardware"],
        "keywords": [
            "keys not responding",
            "typing wrong characters",
            "on-screen keyboard",
            "keyboard layout",
        ],
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
            {
                "step_number": 1,
                "instruction": "Check for physical obstructions",
                "details": "Remove dust or debris and make sure no key is physically stuck.",
            },
            {
                "step_number": 2,
                "instruction": "Restart the laptop",
                "details": "Restart the device and test the keyboard again.",
            },
            {
                "step_number": 3,
                "instruction": "Test with the On-Screen Keyboard",
                "details": (
                    "Settings -> Accessibility -> Keyboard -> enable On-Screen "
                    "Keyboard to confirm whether the issue is hardware or software."
                ),
            },
            {
                "step_number": 4,
                "instruction": "Check the keyboard language/layout",
                "details": (
                    "Settings -> Time & Language -> Language & Region -> verify "
                    "the correct keyboard layout is selected."
                ),
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open Notepad and confirm every key types the expected character.",
            },
        ],
        "escalation_criteria": (
            "Keyboard still unresponsive after these steps (likely hardware fault "
            "needing diagnostics)."
        ),
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
        "keywords": [
            "touchpad disabled",
            "cursor jumping",
            "gestures not working",
            "external mouse",
        ],
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
            {
                "step_number": 1,
                "instruction": "Check touchpad settings",
                "details": (
                    "Settings -> Bluetooth & Devices -> Touchpad -> ensure the touchpad is enabled."
                ),
            },
            {
                "step_number": 2,
                "instruction": "Disconnect any external mouse",
                "details": "Remove external mice and test the touchpad on its own.",
            },
            {
                "step_number": 3,
                "instruction": "Restart the laptop",
                "details": "Restart the device and verify touchpad functionality.",
            },
            {
                "step_number": 4,
                "instruction": "Clean the touchpad",
                "details": ("Make sure the surface is clean and dry; remove any dirt or moisture."),
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": (
                    "Move the cursor and perform a two-finger scroll to confirm normal behaviour."
                ),
            },
        ],
        "escalation_criteria": "Touchpad still malfunctions after these steps.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-wont-power-on",
        "title": "Laptop Not Powering On",
        "short_summary": (
            "Recover a laptop that does not turn on, shows no display, or is "
            "unresponsive to the power button."
        ),
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
            {
                "step_number": 1,
                "instruction": "Check the power connection",
                "details": (
                    "Ensure the adapter is securely connected, the wall outlet "
                    "works, and the charging LED is on."
                ),
            },
            {
                "step_number": 2,
                "instruction": "Disconnect the charger and external devices",
                "details": (
                    "Remove the charger, all USB devices, docking stations, and "
                    "external monitors, then try again."
                ),
            },
            {
                "step_number": 3,
                "instruction": "Perform a power reset",
                "details": (
                    "Disconnect the charger, press and hold the power button for "
                    "15-20 seconds, then reconnect the charger and power on."
                ),
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the laptop boots to the Windows sign-in screen.",
            },
        ],
        "escalation_criteria": (
            "Laptop still does not power on after a power reset (hardware diagnostics required)."
        ),
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-battery-not-charging",
        "title": "Laptop Battery Not Charging",
        "short_summary": (
            "Fix a laptop that stays at the same battery percentage or shows "
            "'plugged in, not charging'."
        ),
        "article_type": "troubleshooting",
        "audience": "employee",
        "category": "hardware/laptop",
        "subcategory": "battery-not-charging",
        "product_or_system": "laptop",
        "platform": "windows",
        "issue_type": "hardware_fault",
        "severity_hint": "medium",
        "tags": ["battery", "charging", "power adapter", "laptop"],
        "keywords": [
            "plugged in not charging",
            "charging led",
            "charger damage",
            "battery status",
        ],
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
            {
                "step_number": 1,
                "instruction": "Verify the charger connection",
                "details": (
                    "Ensure the charger is securely connected and the charging indicator LED is on."
                ),
            },
            {
                "step_number": 2,
                "instruction": "Inspect the charger",
                "details": (
                    "Check the charger and cable for visible damage; try another "
                    "compatible charger if available."
                ),
            },
            {
                "step_number": 3,
                "instruction": "Restart the laptop",
                "details": "Restart while keeping the charger connected.",
            },
            {
                "step_number": 4,
                "instruction": "Check the battery status",
                "details": (
                    "If Windows shows 'Plugged in, Not Charging', note the exact "
                    "message before contacting IT."
                ),
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the battery percentage increases while plugged in.",
            },
        ],
        "escalation_criteria": (
            "Battery still does not charge (battery/charger replacement may be needed)."
        ),
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-external-monitor-not-detected",
        "title": "External Monitor Not Detected",
        "short_summary": (
            "Get Windows to detect and display on an external monitor connected to the laptop."
        ),
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
            {
                "step_number": 1,
                "instruction": "Check cable connections",
                "details": (
                    "Ensure HDMI/DisplayPort/USB-C cables are secure and the monitor is powered on."
                ),
            },
            {
                "step_number": 2,
                "instruction": "Select the correct input source",
                "details": (
                    "Use the monitor's menu buttons to select the matching input (HDMI, DP, USB-C)."
                ),
            },
            {
                "step_number": 3,
                "instruction": "Detect the display",
                "details": "Settings -> System -> Display -> click Detect under Multiple displays.",
            },
            {
                "step_number": 4,
                "instruction": "Use the display shortcut",
                "details": (
                    "Press Windows + P and choose Duplicate, Extend, or Second screen only."
                ),
            },
            {
                "step_number": 5,
                "instruction": "Restart both devices",
                "details": "Restart the laptop and the monitor and retry.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm the desktop appears on the external monitor.",
            },
        ],
        "escalation_criteria": "Monitor still not detected after these steps.",
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "laptop-slow-performance",
        "title": "Laptop Running Slow",
        "short_summary": "Speed up a laptop that is slow to open apps or do daily tasks.",
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
            {
                "step_number": 1,
                "instruction": "Restart the laptop",
                "details": "Restart to clear temporary memory usage.",
            },
            {
                "step_number": 2,
                "instruction": "Free up disk space",
                "details": (
                    "Delete unnecessary files, empty the Recycle Bin, and remove "
                    "unused applications if permitted."
                ),
            },
            {
                "step_number": 3,
                "instruction": "Install Windows updates",
                "details": "Settings -> Windows Update -> install pending updates and restart.",
            },
            {
                "step_number": 4,
                "instruction": "Restart periodically",
                "details": (
                    "If the laptop has run for several days, restart it to restore performance."
                ),
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Open a few applications and confirm they respond promptly.",
            },
        ],
        "escalation_criteria": (
            "Performance remains slow after these steps (further diagnostics needed)."
        ),
        "escalation_target_team": "Endpoint & Productivity",
    },
    {
        "slug": "windows-update-failure",
        "title": "Windows Update Fails or Gets Stuck",
        "short_summary": "Resolve Windows updates that fail, get stuck, or show error codes.",
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
            {
                "step_number": 1,
                "instruction": "Check the internet connection",
                "details": "Ensure the laptop has a stable internet connection.",
            },
            {
                "step_number": 2,
                "instruction": "Restart the laptop",
                "details": "Restart and try checking for updates again.",
            },
            {
                "step_number": 3,
                "instruction": "Check for updates",
                "details": "Settings -> Windows Update -> Check for updates.",
            },
            {
                "step_number": 4,
                "instruction": "Run the Windows Update troubleshooter",
                "details": (
                    "Settings -> System -> Troubleshoot -> Other troubleshooters "
                    "-> run Windows Update."
                ),
            },
            {
                "step_number": 5,
                "instruction": "Free up disk space",
                "details": "Ensure there is sufficient free disk space before installing updates.",
            },
        ],
        "validation_steps": [
            {
                "step_number": 1,
                "instruction": "Confirm Windows Update reports the device is up to date.",
            },
        ],
        "escalation_criteria": (
            "Updates continue to fail or show an error code (contact IT with a "
            "screenshot of the error)."
        ),
        "escalation_target_team": "Endpoint & Productivity",
    },
]

# Extend ARTICLES with the YAML-parity entries (slug uniqueness enforced by seeder)
ARTICLES.extend(_YAML_ARTICLES)

# Add newer categories to taxonomy if not present
TAXONOMY_TERMS = list(TAXONOMY_TERMS) + [
    ("category", "hardware/audio", "Hardware - Audio", "hardware/audio"),
    ("category", "hardware/laptop", "Hardware - Laptop", "hardware/laptop"),
    ("category", "system/performance", "System - Performance", "system/performance"),
    ("category", "software/windows-update", "Software - Windows Update", "software/windows-update"),
    ("product", "laptop", "Laptop", None),
]
