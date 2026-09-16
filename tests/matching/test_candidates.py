from __future__ import annotations

from shapely.geometry import Polygon

from src.matching.candidates import generate_candidates
from src.matching.features import LoadedFeature


def _feat(osm_id, geom):
    return LoadedFeature(osm_id=osm_id, geometry=geom, attrs={}, repaired=False)


def _square(x0, y0, side):
    return Polygon([(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)])


def test_no_candidate_when_nothing_overlaps():
    a = {"way/1": _feat("way/1", _square(0, 0, 1))}
    b = {"way/2": _feat("way/2", _square(100, 100, 1))}

    assert generate_candidates(a, b) == {}


def test_one_to_one_overlap():
    a = {"way/1": _feat("way/1", _square(0, 0, 2))}
    b = {"way/2": _feat("way/2", _square(1, 1, 2))}  # overlaps way/1's corner

    assert generate_candidates(a, b) == {"way/1": ["way/2"]}


def test_one_to_many_split_candidate():
    # one old building overlapping two new, smaller ones
    a = {"way/old": _feat("way/old", _square(0, 0, 4))}
    b = {
        "way/new1": _feat("way/new1", _square(0, 0, 2)),
        "way/new2": _feat("way/new2", _square(2, 0, 2)),
    }

    result = generate_candidates(a, b)

    assert set(result.keys()) == {"way/old"}
    assert set(result["way/old"]) == {"way/new1", "way/new2"}


def test_many_to_one_merge_candidate():
    a = {
        "way/old1": _feat("way/old1", _square(0, 0, 2)),
        "way/old2": _feat("way/old2", _square(2, 0, 2)),
    }
    b = {"way/new": _feat("way/new", _square(0, 0, 4))}

    result = generate_candidates(a, b)

    assert result == {"way/old1": ["way/new"], "way/old2": ["way/new"]}


def test_touching_only_is_not_a_candidate():
    # Shares an edge (touches) but zero overlapping area -- exactly the Tel
    # Aviv terraced-housing case the boundary semantics doc calls out.
    a = {"way/1": _feat("way/1", _square(0, 0, 1))}
    b = {"way/2": _feat("way/2", _square(1, 0, 1))}  # shares the x=1 edge only

    assert a["way/1"].geometry.intersects(b["way/2"].geometry)  # sanity: they DO touch
    assert generate_candidates(a, b) == {}


def test_empty_inputs_give_empty_result():
    assert generate_candidates({}, {}) == {}
    assert generate_candidates({"way/1": _feat("way/1", _square(0, 0, 1))}, {}) == {}
