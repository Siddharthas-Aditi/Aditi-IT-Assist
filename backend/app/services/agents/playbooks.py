"""Issue-specific diagnostic playbooks — guided troubleshooting flows.

Each playbook defines:
- Required context fields for the issue category
- Disambiguation questions (in priority order)
- Retrieval filter hints
- Escalation triggers

Playbooks guide the agent without making it rigid — they define WHAT to ask,
not the exact script. The agent uses LLM for natural phrasing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClarificationOption:
    """A disambiguation option presented to the user."""

    label: str  # Short label for quick-reply chips
    value: str  # The subcategory/symptom value this maps to
    follow_up: str | None = None  # Optional next question if this is chosen


@dataclass
class PlaybookQuestion:
    """A diagnostic question the agent should ask."""

    slot: str  # Which DiagnosticContext field this fills
    question: str  # Natural language question text
    priority: int = 1  # Lower = ask first
    options: list[ClarificationOption] = field(default_factory=list)
    skip_if: list[str] = field(default_factory=list)  # Skip if these slots are filled
    condition: str | None = None  # Only ask if this slot has a specific value


@dataclass
class PlaybookEscalationTrigger:
    """Condition under which this issue should escalate."""

    condition: str
    reason: str
    priority: str = "P2"


@dataclass
class IssuePlaybook:
    """Diagnostic playbook for an issue category."""

    category: str
    display_name: str
    description: str

    # Required context before attempting resolution
    required_slots: list[str] = field(default_factory=list)

    # Questions to ask (in priority order)
    questions: list[PlaybookQuestion] = field(default_factory=list)

    # Retrieval configuration
    retrieval_category_filter: str | None = None
    retrieval_boost_terms: list[str] = field(default_factory=list)
    max_retrieval_results: int = 3

    # Escalation configuration
    escalation_triggers: list[PlaybookEscalationTrigger] = field(default_factory=list)

    # Common subtypes for this category
    subtypes: list[str] = field(default_factory=list)

    def get_next_question(
        self, filled_slots: dict[str, str], asked_count: int
    ) -> PlaybookQuestion | None:
        """Get the next most important question to ask.

        Returns None if all required context is gathered.
        """
        for q in sorted(self.questions, key=lambda x: x.priority):
            # Skip if the target slot is already filled
            if q.slot in filled_slots and filled_slots[q.slot]:
                continue
            # Skip if prerequisite slots aren't met
            if q.condition and q.condition not in filled_slots:
                continue
            # Skip if dependent slots are already filled (making this redundant)
            if q.skip_if and any(s in filled_slots for s in q.skip_if):
                continue
            return q
        return None

    def has_enough_context(self, filled_slots: dict[str, str]) -> bool:
        """Check if all required slots are filled."""
        return all(s in filled_slots and filled_slots[s] for s in self.required_slots)


# ══════════════════════════════════════════════════════════════════════
#  PLAYBOOK DEFINITIONS
# ══════════════════════════════════════════════════════════════════════

OUTLOOK_PLAYBOOK = IssuePlaybook(
    category="email/outlook",
    display_name="Outlook / Email",
    description="Microsoft Outlook and email-related issues",
    required_slots=["symptom"],
    subtypes=[
        "not-receiving-emails",
        "sending-failure",
        "outlook-slow",
        "outlook-crash",
        "calendar-sync",
        "search-not-working",
        "attachment-issue",
        "sign-in-problem",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question=(
                "I can see this is an Outlook/email issue. "
                "Could you tell me what's specifically happening?"
            ),
            priority=1,
            options=[
                ClarificationOption("Not receiving emails", "not-receiving-emails"),
                ClarificationOption("Can't send emails", "sending-failure"),
                ClarificationOption("Outlook is slow", "outlook-slow"),
                ClarificationOption("Outlook keeps crashing", "outlook-crash"),
                ClarificationOption("Calendar not syncing", "calendar-sync"),
                ClarificationOption("Search not working", "search-not-working"),
                ClarificationOption("Sign-in issue", "sign-in-problem"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="error_message",
            question="Are you seeing any specific error message? If so, what does it say?",
            priority=2,
            skip_if=["exact_problem_statement"],
        ),
        PlaybookQuestion(
            slot="duration",
            question="When did this start? Has it been happening consistently or intermittently?",
            priority=3,
        ),
        PlaybookQuestion(
            slot="platform_os",
            question="Are you using Outlook on Windows, Mac, or the web (outlook.office.com)?",
            priority=4,
            skip_if=["device_type"],
        ),
    ],
    retrieval_category_filter="email/outlook",
    retrieval_boost_terms=["outlook", "email", "microsoft 365", "exchange"],
    escalation_triggers=[
        PlaybookEscalationTrigger(
            condition="all_users_affected",
            reason="Possible Exchange/M365 service outage — requires IT team investigation",
            priority="P1",
        ),
        PlaybookEscalationTrigger(
            condition="data_loss",
            reason="Potential email data loss — immediate IT intervention required",
            priority="P1",
        ),
    ],
)

ZOOM_PLAYBOOK = IssuePlaybook(
    category="video-conferencing/zoom",
    display_name="Zoom / Video Conferencing",
    description="Zoom meetings, audio, video, and connectivity issues",
    required_slots=["symptom"],
    subtypes=[
        "no-audio",
        "no-video",
        "cant-join-meeting",
        "sign-in-issue",
        "screen-share-issue",
        "poor-quality",
        "zoom-crash",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question=(
                "I can see this is a Zoom/video conferencing issue. "
                "What exactly is going wrong?"
            ),
            priority=1,
            options=[
                ClarificationOption("No audio / can't hear", "no-audio"),
                ClarificationOption("Camera not working", "no-video"),
                ClarificationOption("Can't join meeting", "cant-join-meeting"),
                ClarificationOption("Sign-in problem", "sign-in-issue"),
                ClarificationOption("Screen sharing issue", "screen-share-issue"),
                ClarificationOption("Poor call quality", "poor-quality"),
                ClarificationOption("Zoom crashing", "zoom-crash"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="device_type",
            question="Are you using Zoom on a laptop, desktop, or mobile device?",
            priority=2,
        ),
        PlaybookQuestion(
            slot="network_type",
            question="Are you on office Wi-Fi, home network, or VPN?",
            priority=3,
            condition="poor-quality",
        ),
    ],
    retrieval_category_filter="video-conferencing/zoom",
    retrieval_boost_terms=["zoom", "audio", "video", "meeting", "teams"],
    escalation_triggers=[
        PlaybookEscalationTrigger(
            condition="account_blocked",
            reason="Zoom account appears blocked — admin intervention needed",
            priority="P2",
        ),
    ],
)

INTUNE_PLAYBOOK = IssuePlaybook(
    category="device-management/intune",
    display_name="Intune / Device Compliance",
    description="Device management, compliance, and enrollment issues",
    required_slots=["symptom"],
    subtypes=[
        "non-compliant",
        "enrollment-failure",
        "sync-issue",
        "app-deployment",
        "policy-conflict",
        "conditional-access-blocked",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question=(
                "I can see this is a device management/Intune issue. "
                "What's the device showing?"
            ),
            priority=1,
            options=[
                ClarificationOption("Device is non-compliant", "non-compliant"),
                ClarificationOption("Can't enroll device", "enrollment-failure"),
                ClarificationOption("Intune not syncing", "sync-issue"),
                ClarificationOption("App won't install", "app-deployment"),
                ClarificationOption("Blocked from Office apps", "conditional-access-blocked"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="device_type",
            question="What type of device is this — Windows laptop, Mac, or mobile (iOS/Android)?",
            priority=2,
        ),
        PlaybookQuestion(
            slot="error_message",
            question="Does Company Portal show a specific compliance issue or error code?",
            priority=3,
        ),
    ],
    retrieval_category_filter="device-management/intune",
    retrieval_boost_terms=["intune", "compliance", "company portal", "enrollment", "MDM"],
    escalation_triggers=[
        PlaybookEscalationTrigger(
            condition="enrollment_blocker",
            reason="Device enrollment blocked — requires IT admin policy review",
            priority="P2",
        ),
    ],
)

CAMERA_PLAYBOOK = IssuePlaybook(
    category="hardware/camera",
    display_name="Camera / Webcam",
    description="Camera, webcam, and video device issues",
    required_slots=["symptom"],
    subtypes=[
        "camera-black-screen",
        "camera-not-detected",
        "camera-permission-denied",
        "camera-poor-quality",
        "camera-in-use-by-another-app",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question="What's happening with your camera?",
            priority=1,
            options=[
                ClarificationOption("Black screen / no image", "camera-black-screen"),
                ClarificationOption("Camera not detected", "camera-not-detected"),
                ClarificationOption("Permission denied", "camera-permission-denied"),
                ClarificationOption("Poor quality / blurry", "camera-poor-quality"),
                ClarificationOption("Says 'in use by another app'", "camera-in-use-by-another-app"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="affected_system",
            question="Which application are you trying to use the camera with (Zoom, Teams, other)?",
            priority=2,
        ),
        PlaybookQuestion(
            slot="platform_os",
            question="Is this on Windows or Mac?",
            priority=3,
        ),
    ],
    retrieval_category_filter="hardware/camera",
    retrieval_boost_terms=["camera", "webcam", "video", "permissions"],
)

NETWORK_PLAYBOOK = IssuePlaybook(
    category="network/connectivity",
    display_name="Network / VPN / Connectivity",
    description="VPN, Wi-Fi, internet, and network connectivity issues",
    required_slots=["symptom"],
    subtypes=[
        "vpn-not-connecting",
        "wifi-disconnecting",
        "internet-slow",
        "specific-site-unreachable",
        "dns-issue",
        "3cx-voip-issue",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question="What connectivity issue are you experiencing?",
            priority=1,
            options=[
                ClarificationOption("VPN won't connect", "vpn-not-connecting"),
                ClarificationOption("Wi-Fi keeps dropping", "wifi-disconnecting"),
                ClarificationOption("Internet is slow", "internet-slow"),
                ClarificationOption("Can't reach a specific site/app", "specific-site-unreachable"),
                ClarificationOption("VoIP/3CX issue", "3cx-voip-issue"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="network_type",
            question="Are you on office Wi-Fi, home network, or using a mobile hotspot?",
            priority=2,
        ),
        PlaybookQuestion(
            slot="error_message",
            question="Do you see any specific error when trying to connect (e.g., 'connection timed out', 'authentication failed')?",
            priority=3,
        ),
    ],
    retrieval_category_filter="network/connectivity",
    retrieval_boost_terms=["vpn", "wifi", "network", "connectivity", "DNS"],
    escalation_triggers=[
        PlaybookEscalationTrigger(
            condition="office_wide_outage",
            reason="Appears to be an office-wide connectivity outage — escalating to network team",
            priority="P1",
        ),
    ],
)

ACCESS_PLAYBOOK = IssuePlaybook(
    category="access/permissions",
    display_name="Access / Login / Permissions",
    description="Account lockouts, MFA, password, and access control issues",
    required_slots=["symptom"],
    subtypes=[
        "account-locked",
        "password-expired",
        "mfa-not-working",
        "access-denied-app",
        "new-access-request",
        "sso-failure",
    ],
    questions=[
        PlaybookQuestion(
            slot="symptom",
            question="What access issue are you experiencing?",
            priority=1,
            options=[
                ClarificationOption("Account is locked", "account-locked"),
                ClarificationOption("Password expired / reset needed", "password-expired"),
                ClarificationOption("MFA not working", "mfa-not-working"),
                ClarificationOption("Access denied to an app", "access-denied-app"),
                ClarificationOption("Need access to something new", "new-access-request"),
                ClarificationOption("SSO / single sign-on issue", "sso-failure"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="affected_system",
            question="Which system or application are you trying to access?",
            priority=2,
            skip_if=["exact_problem_statement"],
        ),
        PlaybookQuestion(
            slot="error_message",
            question="What error message or page do you see when trying to log in?",
            priority=3,
        ),
    ],
    retrieval_category_filter="access/permissions",
    retrieval_boost_terms=["login", "password", "MFA", "locked", "access", "Azure AD"],
    escalation_triggers=[
        PlaybookEscalationTrigger(
            condition="security_incident",
            reason="Possible unauthorized access — escalating to security team",
            priority="P1",
        ),
    ],
)

SOFTWARE_PLAYBOOK = IssuePlaybook(
    category="software/other",
    display_name="Software / Applications",
    description="Application installs, crashes, licensing, and configuration",
    required_slots=["symptom", "affected_system"],
    subtypes=[
        "app-crash",
        "install-failure",
        "license-issue",
        "update-problem",
        "performance-issue",
    ],
    questions=[
        PlaybookQuestion(
            slot="affected_system",
            question="Which application or software is this about?",
            priority=1,
        ),
        PlaybookQuestion(
            slot="symptom",
            question="What's happening with the application?",
            priority=2,
            options=[
                ClarificationOption("Keeps crashing", "app-crash"),
                ClarificationOption("Won't install", "install-failure"),
                ClarificationOption("License / activation error", "license-issue"),
                ClarificationOption("Won't update", "update-problem"),
                ClarificationOption("Running very slow", "performance-issue"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="error_message",
            question="Is there a specific error message when it fails?",
            priority=3,
        ),
    ],
    retrieval_category_filter="software/other",
    retrieval_boost_terms=["software", "application", "install", "crash"],
)

HARDWARE_OTHER_PLAYBOOK = IssuePlaybook(
    category="hardware/other",
    display_name="Hardware / Peripherals",
    description="Monitors, keyboards, docking stations, and other hardware",
    required_slots=["symptom", "affected_system"],
    questions=[
        PlaybookQuestion(
            slot="affected_system",
            question="Which hardware device is having the issue?",
            priority=1,
            options=[
                ClarificationOption("Monitor / display", "monitor"),
                ClarificationOption("Keyboard", "keyboard"),
                ClarificationOption("Docking station", "docking-station"),
                ClarificationOption("Mouse / trackpad", "mouse"),
                ClarificationOption("Headset / speakers", "headset"),
                ClarificationOption("Printer", "printer"),
                ClarificationOption("Something else", "other"),
            ],
        ),
        PlaybookQuestion(
            slot="symptom",
            question="What's happening with the device — not detected, not working properly, or something else?",
            priority=2,
        ),
    ],
    retrieval_category_filter="hardware/other",
    retrieval_boost_terms=["hardware", "peripheral", "device", "driver"],
)

OTHER_PLAYBOOK = IssuePlaybook(
    category="other",
    display_name="Other IT Issues",
    description="Issues that don't fit standard categories",
    required_slots=["symptom", "affected_system"],
    questions=[
        PlaybookQuestion(
            slot="affected_system",
            question="Which system, application, or device is affected?",
            priority=1,
        ),
        PlaybookQuestion(
            slot="symptom",
            question="Could you describe what's happening in a bit more detail?",
            priority=2,
        ),
    ],
)

# ══════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════

_PLAYBOOK_REGISTRY: dict[str, IssuePlaybook] = {
    "email/outlook": OUTLOOK_PLAYBOOK,
    "video-conferencing/zoom": ZOOM_PLAYBOOK,
    "device-management/intune": INTUNE_PLAYBOOK,
    "hardware/camera": CAMERA_PLAYBOOK,
    "hardware/other": HARDWARE_OTHER_PLAYBOOK,
    "software/other": SOFTWARE_PLAYBOOK,
    "network/connectivity": NETWORK_PLAYBOOK,
    "access/permissions": ACCESS_PLAYBOOK,
    "other": OTHER_PLAYBOOK,
}


def get_playbook(category: str) -> IssuePlaybook:
    """Get the playbook for a given issue category."""
    return _PLAYBOOK_REGISTRY.get(category, OTHER_PLAYBOOK)


def get_all_playbooks() -> dict[str, IssuePlaybook]:
    """Get all registered playbooks."""
    return _PLAYBOOK_REGISTRY.copy()
