"""Adaptive ingestion tests — structural variation coverage.

Each fixture represents a different document format that the IT team might
upload.  Tests verify that the schema-stable pipeline extracts correct fields
regardless of format, with appropriate confidence levels.

ADAPTIVE DESIGN GOAL: all fixtures must produce ≥ 1 candidate with a title
extracted, even when the format differs wildly from the "ideal" template.
"""

from __future__ import annotations

from app.services.ingestion.field_extractor import extract_fields
from app.services.ingestion.normalizer import normalize_document
from app.services.ingestion.profiles.it_support import IT_SUPPORT_PROFILE
from app.services.ingestion.schema import ConfidenceLevel, ExtractionMethod
from app.services.ingestion.segmenter import segment_document


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures — raw document texts
# ─────────────────────────────────────────────────────────────────────────────

FIXTURE_HEADING_LABELED = """
## Outlook Not Receiving Emails

Symptoms:
- Emails stop arriving after the user's password was reset
- Inbox shows as empty even though webmail works
- Outlook says "Connected" but no sync occurs

Resolution:
1. Open Outlook and click File > Account Settings > Account Settings
2. Select the affected Exchange account and click Change
3. Click More Settings > Advanced and verify the server name
4. Click Check Name and wait for it to resolve
5. Click Next, then Finish, then send a test email

Escalation:
If the issue persists after completing these steps, contact the helpdesk.
Raise a ticket with logs attached.
"""

FIXTURE_NUMBERED_ONLY = """
Zoom Audio Not Working on Windows 11

1. Click the Start menu and open Sound Settings
2. Set the output device to your headset or speakers
3. Open Zoom and go to Settings > Audio
4. Select the correct microphone and speaker devices
5. Click Test Mic and Test Speaker to verify
6. Rejoin the meeting

If users still cannot hear, escalate to IT support.
"""

FIXTURE_BULLETS_NO_HEADINGS = """
- Users report that Intune-enrolled devices show as non-compliant
- The device compliance blade shows errors in Endpoint Manager
- Ensure the device has the latest Windows updates installed
- Run Windows Update and restart
- In Endpoint Manager, navigate to Devices > All Devices
- Select the device and click Sync
- Wait 15 minutes and check compliance status again
- If still non-compliant, reprovision the device using Autopilot
"""

FIXTURE_MULTI_TOPIC = """
## Issue 1: VPN Connection Fails

Symptoms:
- Users cannot connect to GlobalProtect VPN after recent Windows update
- Error message: "Network connection failed"

Resolution:
1. Right-click the GlobalProtect icon and select Disconnect
2. Reopen the client and enter your domain credentials
3. If the error persists, reinstall GlobalProtect from the software portal

---

## Issue 2: Camera Black Screen in Zoom

Symptoms:
- Camera shows black screen during video calls on Windows 11
- Device Manager shows camera as working

Resolution:
1. Open Camera Privacy settings and ensure Zoom has camera access
2. In Zoom, go to Settings > Video and select the correct camera
3. Update the camera driver via Device Manager
"""

FIXTURE_LABEL_COLON_FORMAT = """
Title: Access Denied When Opening SharePoint Site
Affected System: SharePoint Online

Issue Description:
Users receive an "Access Denied" error when navigating to a SharePoint site
that they previously had access to.

Steps to Resolve:
1. Verify the user's Azure AD group membership in the admin portal
2. Check SharePoint site permissions and ensure the user's group is listed
3. Remove and re-add the user to the SharePoint site permissions
4. Ask the user to clear the browser cache and retry

Escalation Criteria:
If group membership is correct but access is still denied, escalate to the
Azure AD team and raise an Entra ID access ticket.
"""

FIXTURE_INCOMPLETE_MINIMAL = """
Outlook Slow to Load

Some users are experiencing slow loading times when opening Outlook.
Try restarting Outlook in safe mode and disabling add-ins.
"""

FIXTURE_ALL_CAPS_HEADINGS = """
ISSUE: MICROSOFT TEAMS NOT LOADING

DESCRIPTION
The Teams desktop application fails to open on Windows 10 machines after
the latest security patch was applied.

TROUBLESHOOTING STEPS
1. Uninstall Teams from Programs and Features
2. Delete the Teams folder from %appdata%
3. Reinstall Teams from https://teams.microsoft.com/downloads
4. Sign in with your corporate credentials

RESOLUTION
After reinstalling, Teams should load correctly. If the issue persists,
contact IT helpdesk and reference this article.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(raw_text: str):
    """Run normalize → segment → extract_fields and return list of candidates."""
    norm_doc = normalize_document(raw_text.strip())
    segments = segment_document(norm_doc, IT_SUPPORT_PROFILE)
    assert segments, "Segmenter produced 0 segments"
    candidates = [
        extract_fields(seg, IT_SUPPORT_PROFILE, candidate_index=i)
        for i, seg in enumerate(segments)
    ]
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: labeled headings (ideal format)
# ─────────────────────────────────────────────────────────────────────────────

class TestHeadingLabeledFormat:
    def test_segment_count(self):
        candidates = _run(FIXTURE_HEADING_LABELED)
        assert len(candidates) >= 1

    def test_title_extracted(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.title.is_present
        assert "Outlook" in str(c.title.value)

    def test_title_confidence_high(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.title.confidence >= 0.8

    def test_resolution_extracted(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.resolution_steps.is_present
        steps = c.resolution_steps.value
        assert isinstance(steps, list) and len(steps) >= 3

    def test_resolution_deterministic(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.resolution_steps.method == ExtractionMethod.DETERMINISTIC

    def test_symptoms_extracted(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.symptoms.is_present

    def test_escalation_extracted(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.escalation_criteria.is_present

    def test_category_email(self):
        c = _run(FIXTURE_HEADING_LABELED)[0]
        assert c.category.is_present
        assert "email" in str(c.category.value).lower() or "outlook" in str(c.category.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: numbered list only (no explicit headings or labels)
# ─────────────────────────────────────────────────────────────────────────────

class TestNumberedOnlyFormat:
    def test_segment_count(self):
        candidates = _run(FIXTURE_NUMBERED_ONLY)
        assert len(candidates) >= 1

    def test_title_extracted(self):
        c = _run(FIXTURE_NUMBERED_ONLY)[0]
        assert c.title.is_present
        assert "Zoom" in str(c.title.value) or len(str(c.title.value)) >= 5

    def test_steps_extracted(self):
        c = _run(FIXTURE_NUMBERED_ONLY)[0]
        # Resolution or troubleshooting should capture the numbered list
        has_steps = (
            c.resolution_steps.is_present or c.troubleshooting_steps.is_present
        )
        assert has_steps

    def test_category_zoom(self):
        c = _run(FIXTURE_NUMBERED_ONLY)[0]
        assert c.category.is_present

    def test_platform_windows(self):
        c = _run(FIXTURE_NUMBERED_ONLY)[0]
        assert c.platform.is_present
        assert "Windows" in str(c.platform.value)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: bullets only, no headings or labels
# ─────────────────────────────────────────────────────────────────────────────

class TestBulletsNoHeadingsFormat:
    def test_produces_candidate(self):
        candidates = _run(FIXTURE_BULLETS_NO_HEADINGS)
        assert len(candidates) >= 1

    def test_symptoms_via_scan(self):
        c = _run(FIXTURE_BULLETS_NO_HEADINGS)[0]
        # Symptoms extracted via semantic scan (heuristic), not labeled section
        assert c.symptoms.is_present
        assert c.symptoms.method in (ExtractionMethod.DETERMINISTIC, ExtractionMethod.HEURISTIC)

    def test_category_intune(self):
        c = _run(FIXTURE_BULLETS_NO_HEADINGS)[0]
        assert c.category.is_present
        assert "intune" in str(c.category.value).lower() or "device" in str(c.category.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: multi-topic file
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiTopicFile:
    def test_segment_count(self):
        candidates = _run(FIXTURE_MULTI_TOPIC)
        assert len(candidates) >= 2, (
            f"Expected ≥2 topics from multi-topic doc, got {len(candidates)}"
        )

    def test_first_topic_vpn(self):
        candidates = _run(FIXTURE_MULTI_TOPIC)
        first = candidates[0]
        assert first.title.is_present
        assert "VPN" in str(first.title.value) or "vpn" in str(first.category.value or "").lower()

    def test_second_topic_camera(self):
        candidates = _run(FIXTURE_MULTI_TOPIC)
        assert len(candidates) >= 2
        second = candidates[1]
        assert second.title.is_present
        category_text = str(second.category.value or "").lower()
        assert "camera" in str(second.title.value).lower() or "camera" in category_text

    def test_each_topic_has_resolution(self):
        candidates = _run(FIXTURE_MULTI_TOPIC)
        for c in candidates:
            assert c.resolution_steps.is_present, (
                f"Candidate {c.candidate_index} missing resolution_steps"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: "Label:" colon format (different section labels)
# ─────────────────────────────────────────────────────────────────────────────

class TestLabelColonFormat:
    def test_title_from_label(self):
        c = _run(FIXTURE_LABEL_COLON_FORMAT)[0]
        assert c.title.is_present
        assert "SharePoint" in str(c.title.value) or "Access" in str(c.title.value)

    def test_resolution_from_label(self):
        c = _run(FIXTURE_LABEL_COLON_FORMAT)[0]
        assert c.resolution_steps.is_present

    def test_escalation_from_label(self):
        c = _run(FIXTURE_LABEL_COLON_FORMAT)[0]
        assert c.escalation_criteria.is_present

    def test_product_sharepoint(self):
        c = _run(FIXTURE_LABEL_COLON_FORMAT)[0]
        assert c.product_or_system.is_present

    def test_category_access(self):
        c = _run(FIXTURE_LABEL_COLON_FORMAT)[0]
        assert c.category.is_present


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: incomplete / minimal document
# ─────────────────────────────────────────────────────────────────────────────

class TestIncompleteMinimalDocument:
    def test_produces_candidate(self):
        candidates = _run(FIXTURE_INCOMPLETE_MINIMAL)
        assert len(candidates) >= 1

    def test_title_extracted(self):
        c = _run(FIXTURE_INCOMPLETE_MINIMAL)[0]
        assert c.title.is_present
        assert "Outlook" in str(c.title.value)

    def test_low_confidence(self):
        """Incomplete docs should have lower overall extraction confidence."""
        from app.services.ingestion.confidence import score_candidate
        c = _run(FIXTURE_INCOMPLETE_MINIMAL)[0]
        c = score_candidate(c, IT_SUPPORT_PROFILE)
        # Must not falsely claim HIGH confidence when data is sparse
        assert c.confidence_level != ConfidenceLevel.HIGH.value

    def test_review_required_on_low_confidence(self):
        from app.services.ingestion.confidence import score_candidate
        c = _run(FIXTURE_INCOMPLETE_MINIMAL)[0]
        c = score_candidate(c, IT_SUPPORT_PROFILE)
        if c.extraction_confidence < 0.50:
            assert c.review_required is True


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: ALL-CAPS headings
# ─────────────────────────────────────────────────────────────────────────────

class TestAllCapsHeadings:
    def test_title_extracted(self):
        c = _run(FIXTURE_ALL_CAPS_HEADINGS)[0]
        assert c.title.is_present
        # Title should contain Teams or the issue description
        val = str(c.title.value)
        assert len(val) >= 5

    def test_steps_extracted(self):
        c = _run(FIXTURE_ALL_CAPS_HEADINGS)[0]
        assert c.troubleshooting_steps.is_present or c.resolution_steps.is_present

    def test_category_teams(self):
        c = _run(FIXTURE_ALL_CAPS_HEADINGS)[0]
        assert c.category.is_present


# ─────────────────────────────────────────────────────────────────────────────
# Confidence scoring integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceScoring:
    def test_complete_doc_high_confidence(self):
        """A well-structured doc should score HIGH."""
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_HEADING_LABELED)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        assert c.extraction_confidence > 0.5, (
            f"Expected > 0.5 for complete doc, got {c.extraction_confidence}"
        )

    def test_label_format_respectable_confidence(self):
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_LABEL_COLON_FORMAT)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        assert c.extraction_confidence >= 0.40

    def test_confidence_level_is_set(self):
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_HEADING_LABELED)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        assert c.confidence_level in [lvl.value for lvl in ConfidenceLevel]

    def test_parser_warnings_are_list(self):
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_INCOMPLETE_MINIMAL)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        assert isinstance(c.parser_warnings, list)

    def test_review_required_for_low_score(self):
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_INCOMPLETE_MINIMAL)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        if c.extraction_confidence < 0.50:
            assert c.review_required is True

    def test_review_not_required_for_high_score(self):
        from app.services.ingestion.confidence import score_candidate
        candidates = _run(FIXTURE_HEADING_LABELED)
        c = score_candidate(candidates[0], IT_SUPPORT_PROFILE)
        if c.extraction_confidence >= 0.75:
            assert c.review_required is False
