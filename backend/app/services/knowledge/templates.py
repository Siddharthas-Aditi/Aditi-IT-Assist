"""Article templates for common IT issue categories.

Each template pre-fills fields for ``ArticleCreate`` so authors start with
a structured scaffold instead of a blank form.  The caller merges template
defaults with the author's title/category overrides and creates a draft.

Templates are chosen by ``key`` (URL-safe slug).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArticleTemplate:
    key: str  # URL-safe identifier
    label: str  # Display name
    category: str  # KB category slug
    subcategory: str
    product_or_system: str
    description: str  # Short human description shown in the picker
    icon: str  # Emoji for UI display
    defaults: dict[str, Any] = field(default_factory=dict)  # Pre-filled article fields


# ─────────────────────────────────────────────────────────────────────
# Template definitions
# ─────────────────────────────────────────────────────────────────────

ARTICLE_TEMPLATES: list[ArticleTemplate] = [
    # ── Outlook ──────────────────────────────────────────────────────
    ArticleTemplate(
        key="outlook-not-receiving-email",
        label="Outlook — Not Receiving Email",
        category="email/outlook",
        subcategory="email-delivery",
        product_or_system="Microsoft Outlook",
        description="For issues where a user stops receiving email in Outlook.",
        icon="📧",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["outlook", "email", "email-delivery", "inbox", "microsoft"],
            "keywords": [
                "not receiving email",
                "missing emails",
                "outlook inbox empty",
                "email not arriving",
            ],
            "symptoms": [
                "Emails not appearing in Inbox",
                "Outlook shows no new messages but colleagues are receiving email",
                "Email delivery delayed by hours",
            ],
            "probable_causes": [
                "Mailbox storage quota exceeded",
                "Clutter or Focused Inbox filtering misrouting messages",
                "Exchange sync issue / Outlook in offline mode",
                "Spam filter blocking legitimate email",
                "Forwarding rule redirecting all mail elsewhere",
            ],
            "prerequisites": [
                "Outlook is installed and you are signed in with your corporate account",
                "Check webmail (outlook.office.com) first to isolate client vs server issue",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Check webmail first",
                    "details": (
                        "Open outlook.office.com in a browser. "
                        "If emails appear there, the issue is with the Outlook client, "
                        "not Exchange."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Check Junk/Spam and Other folders",
                    "details": (
                        "Emails may have been filtered. "
                        "Right-click any misrouted message and choose 'Not Junk' to restore."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Verify Focused Inbox is not hiding messages",
                    "details": (
                        "In Outlook, click View > Show Focused Inbox. "
                        "Check the 'Other' tab for missing messages and move them."
                    ),
                },
                {
                    "step_number": 4,
                    "instruction": "Check mailbox quota",
                    "details": (
                        "Go to File > Info. "
                        "A full mailbox will reject new messages. Archive or delete older items."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Send/Receive All Folders",
                    "details": "Press F9 or click Send/Receive > Send/Receive All Folders.",
                },
                {
                    "step_number": 2,
                    "instruction": "Rebuild the Outlook profile",
                    "details": (
                        "Go to Control Panel > Mail > Show Profiles. "
                        "Remove the existing profile and re-add it using autodiscover "
                        "with your corporate email address."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Reset Focused Inbox",
                    "details": (
                        "View > Show Focused Inbox > Move All Messages from 'Other' "
                        "to Focused Inbox."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Ask a colleague to send a test email",
                    "details": (
                        "Confirm it arrives within 5 minutes. If not, escalate to Exchange admin."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if the issue persists after profile rebuild, "
                "or if multiple users in the same team are affected simultaneously."
            ),
            "escalation_target_team": "Exchange / M365 Admin Team",
            "review_interval_days": 180,
        },
    ),
    ArticleTemplate(
        key="outlook-sync-issue",
        label="Outlook — Calendar / Mail Not Syncing",
        category="email/outlook",
        subcategory="sync",
        product_or_system="Microsoft Outlook",
        description="Outlook calendar or email out of sync with Exchange.",
        icon="🔄",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["outlook", "sync", "calendar", "exchange", "microsoft"],
            "keywords": [
                "outlook not syncing",
                "calendar sync issue",
                "outlook offline",
                "exchange sync",
            ],
            "symptoms": [
                "Calendar events missing or showing outdated information",
                "Sent emails not appearing in Sent Items",
                "Outlook shows 'Working Offline' in the status bar",
                "Contacts not updating across devices",
            ],
            "probable_causes": [
                "Network connectivity issues blocking Exchange access",
                "Outlook profile corruption",
                "OST file corruption",
                "Exchange server blocked by firewall or proxy",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Verify network connectivity",
                    "details": "Ensure you are connected to the corporate network or VPN.",
                },
                {
                    "step_number": 2,
                    "instruction": "Toggle Work Offline mode",
                    "details": (
                        "Send/Receive tab > click 'Work Offline' to toggle back online. "
                        "The status bar should change from 'Working Offline' to 'Connected'."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Run Outlook in safe mode",
                    "details": (
                        "Press Win+R, type outlook.exe /safe, press Enter. "
                        "If sync works, a plugin is likely causing the issue — "
                        "disable add-ins one by one."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Recreate the OST file",
                    "details": (
                        "Close Outlook. Navigate to %LOCALAPPDATA%\\Microsoft\\Outlook. "
                        "Rename the .ost file to .ost.bak. "
                        "Reopen Outlook to let it rebuild from Exchange."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Create a test calendar event",
                    "details": (
                        "Check it appears in webmail (outlook.office.com) within 2 minutes."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if OST rebuild does not resolve the issue, "
                "or if the issue affects 5+ users in the same department."
            ),
            "escalation_target_team": "Exchange / M365 Admin Team",
            "review_interval_days": 180,
        },
    ),
    # ── Zoom ──────────────────────────────────────────────────────────
    ArticleTemplate(
        key="zoom-audio-issues",
        label="Zoom — Audio Not Working",
        category="video-conferencing/zoom",
        subcategory="audio",
        product_or_system="Zoom",
        description="Microphone or speaker not working in Zoom meetings.",
        icon="🎤",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["zoom", "audio", "microphone", "speaker", "meeting"],
            "keywords": [
                "zoom no audio",
                "microphone not working zoom",
                "can't hear in zoom",
                "zoom muted",
            ],
            "symptoms": [
                "Cannot hear other participants",
                "Other participants cannot hear you",
                "Audio cuts in and out during the meeting",
                "Echo or feedback during calls",
                "Microphone appears unmuted but no sound is transmitted",
            ],
            "probable_causes": [
                "Wrong audio device selected in Zoom settings",
                "OS-level audio permissions not granted to Zoom",
                "Physical mute button on headset activated",
                "Conflicting or outdated audio drivers",
                "Zoom audio settings reset after an update",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Check Zoom audio settings",
                    "details": (
                        "In Zoom, click the arrow next to the Mute button > Audio Settings. "
                        "Select the correct microphone and speaker from the dropdowns."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Check system audio permissions",
                    "details": (
                        "Windows: Settings > Privacy > Microphone — ensure Zoom is allowed. "
                        "Mac: System Settings > Privacy & Security > Microphone."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Test with Zoom audio test",
                    "details": "In Audio Settings, click 'Test Speaker' and 'Test Microphone'.",
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Leave and rejoin the meeting",
                    "details": "Sometimes re-joining resets the audio device selection.",
                },
                {
                    "step_number": 2,
                    "instruction": "Update Zoom",
                    "details": (
                        "Open Zoom > click your profile > Check for Updates. "
                        "Install the latest version."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Reinstall Zoom audio driver",
                    "details": (
                        "In Device Manager, uninstall the Zoom Virtual Audio device "
                        "and let Zoom reinstall it on next launch."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Join the Zoom audio test meeting",
                    "details": (
                        "Use zoom.us/test to confirm audio works before your next real meeting."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if the issue persists after reinstalling Zoom, "
                "or if audio works in all other applications but not Zoom."
            ),
            "escalation_target_team": "Desktop Support",
            "review_interval_days": 180,
        },
    ),
    ArticleTemplate(
        key="zoom-cannot-sign-in",
        label="Zoom — Cannot Sign In",
        category="video-conferencing/zoom",
        subcategory="authentication",
        product_or_system="Zoom",
        description="User cannot sign into Zoom using SSO or corporate credentials.",
        icon="🔐",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["zoom", "signin", "sso", "authentication", "login"],
            "keywords": [
                "zoom login error",
                "zoom sso failed",
                "cannot sign in zoom",
                "zoom licence",
            ],
            "symptoms": [
                "Zoom SSO login redirects to an error page",
                "Zoom displays 'Invalid credentials'",
                "Zoom licence not assigned after successful login",
            ],
            "probable_causes": [
                "SSO session expired",
                "Zoom licence not assigned in the admin portal",
                "Browser cookie conflict during SSO flow",
                "Corporate email address not matching the Zoom account",
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Use SSO sign-in",
                    "details": (
                        "Click 'Sign In with SSO' and enter the company domain. "
                        "Do not use email/password login."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Clear browser cache",
                    "details": ("If using the web client, clear cookies and retry the SSO login."),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Join a test meeting",
                    "details": (
                        "Confirm your name appears with the correct licence type (not Basic)."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if SSO consistently fails — may require licence assignment by IT admin."
            ),
            "escalation_target_team": "IT Admin — Zoom Licence Management",
            "review_interval_days": 180,
        },
    ),
    # ── Intune / Device Management ────────────────────────────────────
    ArticleTemplate(
        key="intune-device-not-compliant",
        label="Intune — Device Not Compliant",
        category="device-management/intune",
        subcategory="compliance",
        product_or_system="Microsoft Intune",
        description="Corporate device showing as non-compliant in Intune / Company Portal.",
        icon="🛡️",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["intune", "compliance", "mdm", "device-management", "company-portal"],
            "keywords": [
                "intune not compliant",
                "device compliance failed",
                "company portal compliance",
                "mdm compliance",
            ],
            "symptoms": [
                "Device shown as 'Not Compliant' in Company Portal",
                "Access to corporate resources blocked (M365, SharePoint, etc.)",
                "Conditional access policy blocking Microsoft 365 apps",
                "Email app shows authentication error",
            ],
            "probable_causes": [
                "OS is out of date and below the minimum required version",
                "BitLocker or FileVault encryption not enabled",
                "Antivirus not running or definitions out of date",
                "Screen lock PIN/password policy not configured",
                "Device certificate expired",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Open Company Portal and check compliance details",
                    "details": (
                        "The app lists each specific compliance failure. "
                        "Tap each one for resolution guidance."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Run Windows Update",
                    "details": (
                        "Settings > Windows Update > Check for updates. "
                        "Install all pending updates including optional ones."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Verify BitLocker is enabled",
                    "details": (
                        "Search 'Manage BitLocker' in the Start menu. "
                        "If not enabled, turn it on for the C: drive."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Sync device in Company Portal",
                    "details": (
                        "Open Company Portal > Devices > select your device > Sync. "
                        "Wait 15 minutes for policy refresh."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Re-enrol device if sync fails",
                    "details": (
                        "Settings > Accounts > Access work or school > Disconnect. "
                        "Re-add using your corporate email and re-enrol."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Re-open Company Portal after 30 minutes",
                    "details": (
                        "Status should change to 'Compliant'. Retry accessing corporate resources."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if compliance fails after OS update and re-enrolment, "
                "or if encryption cannot be enabled (possible hardware TPM issue)."
            ),
            "escalation_target_team": "Device Management / Intune Admin Team",
            "review_interval_days": 120,
        },
    ),
    # ── Camera ────────────────────────────────────────────────────────
    ArticleTemplate(
        key="camera-not-working",
        label="Camera — Black Screen or Not Detected",
        category="hardware/camera",
        subcategory="driver",
        product_or_system="Built-in / USB Webcam",
        description="Webcam shows black screen or is not detected by video conferencing apps.",
        icon="📷",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["camera", "webcam", "video", "driver", "hardware"],
            "keywords": [
                "camera not working",
                "black screen camera",
                "webcam not detected",
                "camera driver",
            ],
            "symptoms": [
                "Camera shows black screen in Zoom, Teams, or Meet",
                "Video app reports 'No camera found'",
                "Camera indicator light does not activate",
                "Camera works in one app but not another",
            ],
            "probable_causes": [
                "Privacy shutter physically closed over the lens",
                "OS-level camera permission denied for the app",
                "Another app is already using the camera (exclusive access)",
                "Outdated or corrupt camera driver",
                "USB camera not powered or connected properly",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Check the privacy shutter",
                    "details": (
                        "Many laptops have a physical privacy cover over the camera. "
                        "Ensure it is slid fully open."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Check OS camera permissions",
                    "details": (
                        "Windows: Settings > Privacy > Camera — enable for the affected app. "
                        "Mac: System Settings > Privacy & Security > Camera."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Close other apps using the camera",
                    "details": (
                        "Only one app can use the camera at a time. "
                        "Close Zoom, Teams, Skype, or any other video conferencing app."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Update camera driver",
                    "details": (
                        "Device Manager > Cameras > right-click > "
                        "Update driver > Search automatically."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Uninstall and reinstall camera driver",
                    "details": (
                        "Device Manager > Cameras > right-click > Uninstall device "
                        "(check 'Delete driver software'). Restart — Windows will reinstall."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Test with Windows Camera app",
                    "details": (
                        "Open the Camera app from Start menu. "
                        "If it shows your image, the hardware and driver are working correctly."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if driver reinstall fails or if the camera is not visible "
                "in Device Manager (possible hardware fault)."
            ),
            "escalation_target_team": "Hardware Support",
            "review_interval_days": 270,
        },
    ),
    # ── VPN ───────────────────────────────────────────────────────────
    ArticleTemplate(
        key="vpn-cannot-connect",
        label="VPN — Cannot Connect",
        category="network/connectivity",
        subcategory="vpn",
        product_or_system="Corporate VPN Client",
        description="User cannot establish a VPN connection to the corporate network.",
        icon="🔒",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["vpn", "network", "connectivity", "remote-access"],
            "keywords": [
                "vpn not connecting",
                "vpn error",
                "cannot connect vpn",
                "vpn failed",
            ],
            "symptoms": [
                "VPN client shows 'Connection failed' or 'Authentication failed'",
                "VPN connects but corporate resources are unreachable",
                "VPN disconnects repeatedly after a few minutes",
                "VPN client crashes on launch",
            ],
            "probable_causes": [
                "MFA token expired or not entered in time",
                "Incorrect VPN server address in client settings",
                "Local firewall or antivirus blocking VPN traffic",
                "VPN certificate expired",
                "ISP or local network blocking VPN protocol (common on hotel Wi-Fi)",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Verify VPN server address",
                    "details": (
                        "Confirm the VPN gateway address in the client settings matches "
                        "the one in the IT setup guide."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Check MFA prompt",
                    "details": (
                        "Some VPN clients require approving a push notification or "
                        "entering a TOTP code during connection. Check your authenticator app."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Temporarily disable local firewall",
                    "details": (
                        "Windows Defender Firewall > Turn off (for testing only). "
                        "Re-enable immediately after testing."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Reinstall VPN client",
                    "details": (
                        "Uninstall the VPN client via Control Panel, "
                        "download the latest version from the IT portal, and reinstall."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Try a different network",
                    "details": (
                        "If on hotel or café Wi-Fi, switch to a mobile hotspot. "
                        "Some networks block VPN protocols."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Access an internal resource after connecting",
                    "details": (
                        "Try accessing an intranet page or shared drive to confirm "
                        "the VPN tunnel is routing traffic correctly."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if the VPN certificate has expired, or if the issue is "
                "reproducible on multiple different networks."
            ),
            "escalation_target_team": "Network / Security Team",
            "review_interval_days": 180,
        },
    ),
    # ── Access / Permissions ──────────────────────────────────────────
    ArticleTemplate(
        key="access-denied-resource",
        label="Access — Permission Denied to Resource",
        category="access/permissions",
        subcategory="rbac",
        product_or_system="Active Directory / Azure AD",
        description=(
            "User receives 'Access Denied' when trying to access "
            "a file share, application, or system."
        ),
        icon="🚫",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["access", "permissions", "active-directory", "rbac", "authorization"],
            "keywords": [
                "access denied",
                "permission denied",
                "cannot access resource",
                "unauthorized",
            ],
            "symptoms": [
                "'Access Denied' or '403 Forbidden' error message",
                "File share appears in Explorer but cannot be opened",
                "Application login succeeds but features or data are unavailable",
            ],
            "probable_causes": [
                "User not added to the required security group",
                "Group Policy not yet applied to new user account",
                "MFA not completed — conditional access blocking",
                "Resource permissions changed by an admin",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Confirm you are signed in with the correct account",
                    "details": (
                        "Check the top-right corner of the app. "
                        "Ensure you are using your corporate email, not a personal account."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Sign out and sign back in",
                    "details": (
                        "Token caching can cause stale permission sets. "
                        "A fresh sign-in picks up updated group memberships."
                    ),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Request access via the IT Service Portal",
                    "details": (
                        "Submit an access request ticket specifying the resource and "
                        "business justification. Your manager will be asked to approve."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Retry after access is granted",
                    "details": (
                        "Wait for the confirmation email, then retry. "
                        "Group Policy propagation can take up to 1 hour."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate immediately if the denied resource is business-critical "
                "and blocking time-sensitive work."
            ),
            "escalation_target_team": "Identity & Access Management Team",
            "review_interval_days": 180,
        },
    ),
    # ── Device Performance ────────────────────────────────────────────
    ArticleTemplate(
        key="device-slow-performance",
        label="Device — Slow Performance / Freezing",
        category="hardware/other",
        subcategory="performance",
        product_or_system="Windows Laptop",
        description="Corporate laptop running slowly, freezing, or taking a long time to start.",
        icon="🐌",
        defaults={
            "article_type": "troubleshooting",
            "audience": "employee",
            "tags": ["performance", "slow", "laptop", "hardware", "windows"],
            "keywords": [
                "laptop slow",
                "computer freezing",
                "slow windows",
                "performance issue",
                "high cpu",
            ],
            "symptoms": [
                "Applications take more than 30 seconds to open",
                "System freezes or becomes unresponsive",
                "High CPU or RAM usage visible in Task Manager",
                "Fan running at maximum speed constantly",
                "Device takes over 5 minutes to boot",
            ],
            "probable_causes": [
                "Too many startup programmes launching at boot",
                "Low disk space (less than 10% free on C: drive)",
                "Malware or runaway background process",
                "Insufficient RAM for the current workload",
                "Overheating throttling the CPU",
            ],
            "troubleshooting_steps": [
                {
                    "step_number": 1,
                    "instruction": "Check Task Manager",
                    "details": (
                        "Press Ctrl+Shift+Esc. Sort by CPU then Memory. "
                        "Identify and close any process using more than 80%."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Check disk space",
                    "details": (
                        "Open File Explorer > This PC. "
                        "The C: drive should have at least 10 GB free."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Run Windows Defender scan",
                    "details": ("Windows Security > Virus & threat protection > Quick scan."),
                },
            ],
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Disable unnecessary startup programmes",
                    "details": (
                        "Task Manager > Startup tab. "
                        "Disable any non-essential apps (e.g., Spotify, OneDrive helper)."
                    ),
                },
                {
                    "step_number": 2,
                    "instruction": "Run Disk Cleanup",
                    "details": (
                        "Search 'Disk Cleanup' > run as Administrator > "
                        "Clean up system files > check all boxes."
                    ),
                },
                {
                    "step_number": 3,
                    "instruction": "Restart the device",
                    "details": (
                        "A clean restart clears memory leaks and applies pending Windows updates."
                    ),
                },
            ],
            "validation_steps": [
                {
                    "step_number": 1,
                    "instruction": "Monitor performance after restart",
                    "details": (
                        "Open Task Manager and confirm CPU and RAM settle below 50% "
                        "at idle within 5 minutes of boot."
                    ),
                },
            ],
            "escalation_criteria": (
                "Escalate if performance does not improve after cleanup and restart, "
                "or if the device is more than 4 years old."
            ),
            "escalation_target_team": "Desktop Support",
            "review_interval_days": 270,
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────
# Registry helpers
# ─────────────────────────────────────────────────────────────────────

TEMPLATES_BY_KEY: dict[str, ArticleTemplate] = {t.key: t for t in ARTICLE_TEMPLATES}


def get_template(key: str) -> ArticleTemplate | None:
    return TEMPLATES_BY_KEY.get(key)


def list_templates() -> list[ArticleTemplate]:
    return list(ARTICLE_TEMPLATES)


def templates_by_category() -> dict[str, list[ArticleTemplate]]:
    result: dict[str, list[ArticleTemplate]] = {}
    for t in ARTICLE_TEMPLATES:
        result.setdefault(t.category, []).append(t)
    return result
