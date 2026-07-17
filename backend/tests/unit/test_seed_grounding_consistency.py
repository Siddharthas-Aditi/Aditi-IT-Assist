"""New laptop KB articles must be subtype-consistent so grounding reranks them,
and a laptop query must rank the focused article above sibling hardware families."""

from app.knowledge_base.structured_seed import ARTICLES
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.grounding import ground_results
from app.services.agents.subtype_classifier import classify_subtype, known_subtypes

NEW_SLUGS = {
    "laptop-keyboard-not-working",
    "laptop-trackpad-not-working",
    "laptop-wont-power-on",
    "laptop-battery-not-charging",
    "laptop-external-monitor-not-detected",
    "laptop-slow-performance",
    "windows-update-failure",
}


def _by_slug(slug):
    return next(a for a in ARTICLES if a["slug"] == slug)


def test_new_articles_present():
    slugs = {a["slug"] for a in ARTICLES}
    assert NEW_SLUGS.issubset(slugs), NEW_SLUGS - slugs


def test_new_articles_subcategory_is_known_subtype():
    for slug in NEW_SLUGS:
        art = _by_slug(slug)
        subs = known_subtypes(art["category"])
        assert art["subcategory"] in subs, (slug, art["subcategory"], subs)


def test_camera_article_subcategory_fixed():
    # The pre-existing camera article used an invalid "camera-access" subtype.
    cam = next(a for a in ARTICLES if a["category"] == "hardware/camera")
    assert cam["subcategory"] in known_subtypes("hardware/camera"), cam["subcategory"]


def test_keyboard_query_grounds_to_keyboard_article():
    text = "my keyboard is not working"
    m = classify_subtype(text, "hardware/laptop")
    ctx = DiagnosticContext()
    ctx.issue_category = "hardware/laptop"
    ctx.issue_subtype = m.subtype
    ctx.symptom = text
    # Candidate set: the keyboard article + two sibling-family hardware articles.
    candidates = [
        _by_slug("laptop-battery-not-charging"),
        _by_slug("laptop-keyboard-not-working"),
    ]
    result = ground_results(candidates, ctx)
    assert result.kept, "keyboard article was rejected"
    assert result.kept[0].article["slug"] == "laptop-keyboard-not-working"
    assert result.kept[0].subtype_match is True
