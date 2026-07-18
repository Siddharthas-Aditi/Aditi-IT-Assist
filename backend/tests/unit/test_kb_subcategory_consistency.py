"""D: every seeded article's subcategory is a known subtype for its category,
except a small documented set of intentionally-generic/fallback articles."""

from app.knowledge_base.structured_seed import ARTICLES
from app.services.agents.subtype_classifier import known_subtypes

# Intentionally-generic / monolithic / cross-category fallback articles that
# should NOT force a (wrong) subtype match — documented exemptions.
GENERIC_EXEMPT = {
    "aditi-email-outlook-issues",
    "outlook-general-troubleshooting",
    "email-alias-shared-mailbox",
    "alias-shared-mailbox-access",
    "alias-update-add-remove",
    "network-no-internet",
    "hardware-peripheral-not-working",
    "software-installation-or-crash",
}


def test_article_subcategories_are_known_subtypes_or_exempt():
    bad = []
    for art in ARTICLES:
        cat = art.get("category")
        sub = art.get("subcategory")
        subs = known_subtypes(cat)
        if not subs:  # category has no classifier rules → nothing to enforce
            continue
        if art["slug"] in GENERIC_EXEMPT:
            continue
        if sub not in subs:
            bad.append((art["slug"], cat, sub))
    assert not bad, f"articles with unknown subcategory: {bad}"
