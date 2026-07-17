"""Triage must emit the new laptop/performance/windows-update categories on the
deterministic (no-LLM) keyword path, or the subtype classifier never runs."""

import pytest

from app.workflows.nodes.triage import ISSUE_CATEGORIES, _keyword_classify


def test_new_categories_registered():
    for cat in ("hardware/laptop", "system/performance", "software/windows-update"):
        assert cat in ISSUE_CATEGORIES, cat


@pytest.mark.parametrize(
    "message,expected",
    [
        ("my keyboard is not working", "hardware/laptop"),
        ("the touchpad is not responding", "hardware/laptop"),
        ("laptop won't turn on", "hardware/laptop"),
        ("battery is not charging", "hardware/laptop"),
        ("external monitor not detected", "hardware/laptop"),
        ("my laptop is really slow", "system/performance"),
        ("windows update is stuck", "software/windows-update"),
    ],
)
def test_keyword_classify_new_categories(message, expected):
    result = _keyword_classify(message)
    assert result["category"] == expected, (message, result["category"])


def test_password_update_still_access_not_windows_update():
    # "update my password" must stay access/permissions (access branch runs first).
    result = _keyword_classify("I need to update my password")
    assert result["category"] == "access/permissions", result["category"]


def test_outlook_slow_stays_outlook():
    # Product-specific branch wins over the generic performance branch.
    result = _keyword_classify("outlook is really slow")
    assert result["category"] == "email/outlook", result["category"]
