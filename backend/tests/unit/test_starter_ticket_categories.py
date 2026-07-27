"""Pure data assertions for the starter ticket category tree."""

from scripts.seed_ticket_categories import STARTER_TREE


def test_starter_tree_has_no_empty_l2_item_lists() -> None:
    assert STARTER_TREE, "STARTER_TREE must not be empty"
    for l1_name, subs in STARTER_TREE.items():
        assert subs, f"L1 '{l1_name}' must have at least one L2 sub-category"
        for l2_name, items in subs.items():
            assert items, f"L2 '{l1_name}/{l2_name}' must have at least one L3 item"
