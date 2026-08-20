from __future__ import annotations

import pytest

from src.ingestion import building_category as bc


@pytest.mark.parametrize(
    ("tag_value", "expected_category"),
    [
        ("house", bc.CATEGORY_RESIDENTIAL),
        ("apartments", bc.CATEGORY_RESIDENTIAL),
        ("retail", bc.CATEGORY_COMMERCIAL),
        ("office", bc.CATEGORY_COMMERCIAL),
        ("warehouse", bc.CATEGORY_INDUSTRIAL),
        ("synagogue", bc.CATEGORY_RELIGIOUS),
        ("mosque", bc.CATEGORY_RELIGIOUS),
        ("school", bc.CATEGORY_CIVIC),
        ("hospital", bc.CATEGORY_CIVIC),
    ],
)
def test_categorize_known_values(tag_value, expected_category):
    assert bc.categorize(tag_value) == expected_category


def test_categorize_is_case_insensitive():
    assert bc.categorize("House") == bc.CATEGORY_RESIDENTIAL
    assert bc.categorize("HOUSE") == bc.CATEGORY_RESIDENTIAL


def test_categorize_generic_yes_falls_back_to_other():
    # `building=yes` is the most common OSM building tag value and
    # deliberately carries no category information.
    assert bc.categorize("yes") == bc.CATEGORY_OTHER


def test_categorize_unmapped_value_falls_back_to_other():
    assert bc.categorize("some_value_not_in_the_table") == bc.CATEGORY_OTHER


def test_categorize_missing_tag_falls_back_to_other():
    assert bc.categorize(None) == bc.CATEGORY_OTHER


def test_every_mapped_category_is_in_all_categories():
    # Table-coverage check: every category the mapping table can produce is
    # a documented category, and every fallback lands in CATEGORY_OTHER.
    mapped_categories = set(bc._BUILDING_TAG_TO_CATEGORY.values())
    assert mapped_categories <= bc.ALL_CATEGORIES
    assert bc.CATEGORY_OTHER in bc.ALL_CATEGORIES
