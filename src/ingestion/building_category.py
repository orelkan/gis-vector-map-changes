"""Maps OSM `building=*` tag values to a small set of documented broad
categories.

OSM has no built-in category field the way Overture has `subtype` -- this
mapping is our own, explicit, and tested (CLAUDE.md: "every metric and
threshold must have a documented interpretation"). It is a deliberately
small starting table, not an attempt to cover every value in
https://wiki.openstreetmap.org/wiki/Key:building -- extend it as real data
surfaces values worth distinguishing.
"""

from __future__ import annotations

CATEGORY_RESIDENTIAL = "residential"
CATEGORY_COMMERCIAL = "commercial"
CATEGORY_INDUSTRIAL = "industrial"
CATEGORY_RELIGIOUS = "religious"
CATEGORY_CIVIC = "civic"
CATEGORY_OTHER = "other"

ALL_CATEGORIES = frozenset(
    {
        CATEGORY_RESIDENTIAL,
        CATEGORY_COMMERCIAL,
        CATEGORY_INDUSTRIAL,
        CATEGORY_RELIGIOUS,
        CATEGORY_CIVIC,
        CATEGORY_OTHER,
    }
)

# building=* value -> category. Values not listed here (including the very
# common generic `building=yes`) fall back to CATEGORY_OTHER -- "other"
# means "we looked and it didn't fit our buckets", not "unknown".
_BUILDING_TAG_TO_CATEGORY: dict[str, str] = {
    # Residential
    "house": CATEGORY_RESIDENTIAL,
    "detached": CATEGORY_RESIDENTIAL,
    "semidetached_house": CATEGORY_RESIDENTIAL,
    "terrace": CATEGORY_RESIDENTIAL,
    "apartments": CATEGORY_RESIDENTIAL,
    "residential": CATEGORY_RESIDENTIAL,
    "dormitory": CATEGORY_RESIDENTIAL,
    "bungalow": CATEGORY_RESIDENTIAL,
    "static_caravan": CATEGORY_RESIDENTIAL,
    # Commercial
    "commercial": CATEGORY_COMMERCIAL,
    "retail": CATEGORY_COMMERCIAL,
    "office": CATEGORY_COMMERCIAL,
    "supermarket": CATEGORY_COMMERCIAL,
    "kiosk": CATEGORY_COMMERCIAL,
    "hotel": CATEGORY_COMMERCIAL,
    "restaurant": CATEGORY_COMMERCIAL,
    # Industrial
    "industrial": CATEGORY_INDUSTRIAL,
    "warehouse": CATEGORY_INDUSTRIAL,
    "manufacture": CATEGORY_INDUSTRIAL,
    "factory": CATEGORY_INDUSTRIAL,
    # Religious
    "church": CATEGORY_RELIGIOUS,
    "mosque": CATEGORY_RELIGIOUS,
    "synagogue": CATEGORY_RELIGIOUS,
    "temple": CATEGORY_RELIGIOUS,
    "cathedral": CATEGORY_RELIGIOUS,
    "chapel": CATEGORY_RELIGIOUS,
    "religious": CATEGORY_RELIGIOUS,
    # Civic
    "school": CATEGORY_CIVIC,
    "university": CATEGORY_CIVIC,
    "hospital": CATEGORY_CIVIC,
    "government": CATEGORY_CIVIC,
    "civic": CATEGORY_CIVIC,
    "public": CATEGORY_CIVIC,
    "kindergarten": CATEGORY_CIVIC,
    "train_station": CATEGORY_CIVIC,
    "fire_station": CATEGORY_CIVIC,
}


def categorize(building_tag_value: str | None) -> str:
    """Map a raw `building=*` tag value to a broad category.

    Unmapped or missing values fall back to CATEGORY_OTHER.
    """
    if building_tag_value is None:
        return CATEGORY_OTHER
    return _BUILDING_TAG_TO_CATEGORY.get(building_tag_value.lower(), CATEGORY_OTHER)
