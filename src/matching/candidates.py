"""Spatial candidate generation for features whose osm_id does not persist
across snapshots (the remainder after Stage 1 ID matching).

Boundary semantics (explicit, per CLAUDE.md, see docs/matching-behavior.md
section 4): candidacy requires positive *overlapping area*, not the
`intersects` predicate. Tel Aviv terraced housing shares walls, so
`intersects` would generate many spurious candidates from mere edge
contact; a shared boundary with zero overlap area is not a candidate.
"""

from __future__ import annotations

from shapely.strtree import STRtree

from src.matching.features import LoadedFeature


def generate_candidates(
    only_in_a: dict[str, LoadedFeature],
    only_in_b: dict[str, LoadedFeature],
) -> dict[str, list[str]]:
    """Returns {osm_id_in_a: [osm_id_in_b, ...]} for every pair with
    positive intersection area. An A-id with no entry (or an empty list)
    has no spatial candidate at all.
    """
    if not only_in_a or not only_in_b:
        return {}

    b_ids = list(only_in_b)
    b_geoms = [only_in_b[b_id].geometry for b_id in b_ids]
    tree = STRtree(b_geoms)

    result: dict[str, list[str]] = {}
    for a_id, a_feature in only_in_a.items():
        matches = []
        for idx in tree.query(a_feature.geometry):
            b_id = b_ids[idx]
            if a_feature.geometry.intersection(only_in_b[b_id].geometry).area > 0:
                matches.append(b_id)
        if matches:
            result[a_id] = matches
    return result
