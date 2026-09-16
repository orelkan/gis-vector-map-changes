from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon

from src.matching.changeset import build_changeset
from src.matching.config import T_CROSS_ID_MATCH, T_UNCHANGED_IOU
from src.matching.features import LoadedFeature


def _feat(osm_id, geom, building="house", category="residential", name=None, repaired=False):
    return LoadedFeature(
        osm_id=osm_id,
        geometry=geom,
        attrs={"building": building, "category": category, "name": name},
        repaired=repaired,
    )


def _square(x0, y0, side):
    return Polygon([(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)])


def _rect(x0, y0, w, h):
    return Polygon([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)])


def _one(records, **where):
    matches = [r for r in records if all(getattr(r, k) == v for k, v in where.items())]
    assert len(matches) == 1, f"expected exactly one record matching {where}, got {len(matches)}: {records}"
    return matches[0]


# --- unchanged / added / removed --------------------------------------------


def test_unchanged_same_id_same_geometry_same_attrs():
    sq = _square(0, 0, 10)
    a = {"way/1": _feat("way/1", sq)}
    b = {"way/1": _feat("way/1", sq)}

    records = build_changeset(a, b)

    r = _one(records, osm_ids_a=("way/1",))
    assert r.classification == "unchanged"
    assert r.match_method == "osm_id"
    assert r.match_score == 1.0


def test_added_no_spatial_counterpart():
    a = {"way/old": _feat("way/old", _square(0, 0, 5))}
    b = {"way/old": _feat("way/old", _square(0, 0, 5)), "way/new": _feat("way/new", _square(500, 500, 5))}

    records = build_changeset(a, b)

    r = _one(records, osm_ids_b=("way/new",))
    assert r.classification == "added"
    assert r.osm_ids_a == ()
    assert r.classification_reason == "no_spatial_counterpart"


def test_removed_no_spatial_counterpart():
    a = {"way/old": _feat("way/old", _square(0, 0, 5)), "way/gone": _feat("way/gone", _square(500, 500, 5))}
    b = {"way/old": _feat("way/old", _square(0, 0, 5))}

    records = build_changeset(a, b)

    r = _one(records, osm_ids_a=("way/gone",))
    assert r.classification == "removed"
    assert r.osm_ids_b == ()


def test_no_candidate_case_both_directions_in_one_run():
    # CLAUDE.md's "no-candidate case": features with zero spatial overlap on
    # either side, resolved independently as removed/added, not paired.
    a = {"way/gone": _feat("way/gone", _square(0, 0, 5))}
    b = {"way/new": _feat("way/new", _square(1000, 1000, 5))}

    records = build_changeset(a, b)

    assert {r.classification for r in records} == {"removed", "added"}
    assert len(records) == 2


# --- geometry / attribute modification --------------------------------------


def test_small_geometry_modification_stays_unchanged():
    # Concentric squares, IoU = 10000/10040.04 = 0.996 -- comfortably above
    # T_UNCHANGED_IOU, representing vertex noise / a minor re-trace.
    a = {"way/1": _feat("way/1", _square(0, 0, 100))}
    b = {"way/1": _feat("way/1", _square(0, 0, 100.2))}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "unchanged"
    assert r.pair_metrics[("way/1", "way/1")].iou > T_UNCHANGED_IOU


def test_large_geometry_modification_is_modified_geometry():
    a = {"way/1": _feat("way/1", _square(0, 0, 10))}
    b = {"way/1": _feat("way/1", _square(50, 50, 10))}  # essentially disjoint

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "modified_geometry"
    assert r.match_method == "osm_id"


def test_attribute_only_modification():
    sq = _square(0, 0, 10)
    a = {"way/1": _feat("way/1", sq, building="house")}
    b = {"way/1": _feat("way/1", sq, building="office")}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "modified_attributes"
    assert r.pair_metrics[("way/1", "way/1")].attrs_changed == ("building",)


def test_modified_geometry_and_attributes():
    a = {"way/1": _feat("way/1", _square(0, 0, 10), building="house")}
    b = {"way/1": _feat("way/1", _square(50, 50, 10), building="office")}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "modified_geometry_and_attributes"


# --- geometry types ----------------------------------------------------------


def test_polygon_with_hole_round_trips_as_unchanged():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]
    with_hole = Polygon(outer, [hole])
    a = {"way/1": _feat("way/1", with_hole)}
    b = {"way/1": _feat("way/1", with_hole)}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "unchanged"


def test_multipolygon_round_trips_as_unchanged():
    multi = MultiPolygon([_square(0, 0, 5), _square(20, 0, 5)])
    a = {"way/1": _feat("way/1", multi)}
    b = {"way/1": _feat("way/1", multi)}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.classification == "unchanged"


# --- ambiguous: split / merge / complex --------------------------------------


def test_split_candidate():
    a = {"way/old": _feat("way/old", _square(0, 0, 4))}
    b = {
        "way/new1": _feat("way/new1", _square(0, 0, 2)),
        "way/new2": _feat("way/new2", _square(2, 0, 2)),
    }

    r = _one(build_changeset(a, b), classification_reason="split_candidate")

    assert r.classification == "ambiguous"
    assert r.osm_ids_a == ("way/old",)
    assert r.osm_ids_b == ("way/new1", "way/new2")
    assert set(r.pair_metrics.keys()) == {("way/old", "way/new1"), ("way/old", "way/new2")}


def test_merge_candidate():
    a = {
        "way/old1": _feat("way/old1", _square(0, 0, 2)),
        "way/old2": _feat("way/old2", _square(2, 0, 2)),
    }
    b = {"way/new": _feat("way/new", _square(0, 0, 4))}

    r = _one(build_changeset(a, b), classification_reason="merge_candidate")

    assert r.classification == "ambiguous"
    assert r.osm_ids_a == ("way/old1", "way/old2")
    assert r.osm_ids_b == ("way/new",)


def test_equally_plausible_ambiguous_candidates_complex_cluster():
    # Two old buildings, each overlapping both of two new buildings roughly
    # equally -- CLAUDE.md's "equally plausible ambiguous candidates" case.
    # Neither a 1:many split nor a many:1 merge; must not silently pick a
    # highest-scoring pair.
    a = {
        "way/old1": _feat("way/old1", _square(0, 0, 3)),
        "way/old2": _feat("way/old2", _square(1, 0, 3)),
    }
    b = {
        "way/new1": _feat("way/new1", _square(0, 1, 3)),
        "way/new2": _feat("way/new2", _square(1, 1, 3)),
    }

    r = _one(build_changeset(a, b), classification_reason="complex_cluster")

    assert r.classification == "ambiguous"
    assert set(r.osm_ids_a) == {"way/old1", "way/old2"}
    assert set(r.osm_ids_b) == {"way/new1", "way/new2"}
    # All four candidate pairs preserved -- nothing silently discarded.
    assert len(r.pair_metrics) == 4


def test_one_to_one_below_cross_id_threshold_is_ambiguous_not_matched():
    a = {"way/old": _feat("way/old", _square(0, 0, 100))}
    b = {"way/new": _feat("way/new", _rect(0, 0, 100, 49.99))}  # IoU = 0.4999

    r = _one(build_changeset(a, b), osm_ids_a=("way/old",))

    assert r.classification == "ambiguous"
    assert r.classification_reason == "partial_overlap"
    assert r.pair_metrics[("way/old", "way/new")].iou < T_CROSS_ID_MATCH


def test_one_to_one_at_or_above_cross_id_threshold_is_matched():
    a = {"way/old": _feat("way/old", _square(0, 0, 100))}
    b = {"way/new": _feat("way/new", _rect(0, 0, 100, 50))}  # IoU = 0.5 exactly

    r = _one(build_changeset(a, b), osm_ids_a=("way/old",))

    assert r.classification != "ambiguous"
    assert r.match_method == "geometry"
    assert r.pair_metrics[("way/old", "way/new")].iou == 0.5


# --- exact threshold boundaries -----------------------------------------------


def test_unchanged_iou_boundary_is_inclusive():
    # Nested rectangles: intersection=9900, union=10000 -> IoU exactly 0.99.
    a = {"way/1": _feat("way/1", _rect(0, 0, 100, 100))}
    b = {"way/1": _feat("way/1", _rect(0, 0, 100, 99))}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.pair_metrics[("way/1", "way/1")].iou == T_UNCHANGED_IOU
    assert r.classification == "unchanged"


def test_unchanged_iou_boundary_just_below_is_modified():
    a = {"way/1": _feat("way/1", _rect(0, 0, 100, 100))}
    b = {"way/1": _feat("way/1", _rect(0, 0, 100, 98.9))}  # IoU = 0.989

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.pair_metrics[("way/1", "way/1")].iou < T_UNCHANGED_IOU
    assert r.classification == "modified_geometry"


# --- AOI boundary --------------------------------------------------------------


def test_touches_aoi_boundary_flag():
    from shapely.geometry import LineString

    aoi_edge = LineString([(0, 100), (100, 100)])
    near = {"way/near": _feat("way/near", _square(0, 0, 10))}  # touches y=100 edge closely? adjust
    # Put "near" right against the boundary line, "far" well away from it.
    near_b = {"way/near": _feat("way/near", _square(0, 95, 10))}
    far = {"way/far": _feat("way/far", _square(0, 0, 10))}
    far_b = {"way/far": _feat("way/far", _square(0, 0, 10))}

    near_records = build_changeset(near, near_b, aoi_boundary=aoi_edge)
    far_records = build_changeset(far, far_b, aoi_boundary=aoi_edge)

    assert _one(near_records, osm_ids_a=("way/near",)).touches_aoi_boundary is True
    assert _one(far_records, osm_ids_a=("way/far",)).touches_aoi_boundary is False


def test_touches_aoi_boundary_defaults_false_when_not_given():
    a = {"way/1": _feat("way/1", _square(0, 0, 10))}
    b = {"way/1": _feat("way/1", _square(0, 0, 10))}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.touches_aoi_boundary is False


# --- repaired geometry provenance ---------------------------------------------


def test_involves_repaired_geometry_flag():
    sq = _square(0, 0, 10)
    a = {"way/1": _feat("way/1", sq, repaired=True)}
    b = {"way/1": _feat("way/1", sq, repaired=False)}

    r = _one(build_changeset(a, b), osm_ids_a=("way/1",))

    assert r.involves_repaired_geometry is True


# --- structural invariants ------------------------------------------------------


def test_every_input_feature_appears_in_exactly_one_record():
    a = {
        "way/unchanged": _feat("way/unchanged", _square(0, 0, 5)),
        "way/gone": _feat("way/gone", _square(500, 500, 5)),
        "way/old": _feat("way/old", _square(0, 100, 4)),
    }
    b = {
        "way/unchanged": _feat("way/unchanged", _square(0, 0, 5)),
        "way/new": _feat("way/new", _square(500, 0, 5)),
        "way/new1": _feat("way/new1", _square(0, 100, 2)),
        "way/new2": _feat("way/new2", _square(2, 100, 2)),
    }

    records = build_changeset(a, b)

    seen_a = [oid for r in records for oid in r.osm_ids_a]
    seen_b = [oid for r in records for oid in r.osm_ids_b]
    assert sorted(seen_a) == sorted(a.keys())
    assert sorted(seen_b) == sorted(b.keys())


def test_output_ordering_is_deterministic():
    a = {"way/2": _feat("way/2", _square(0, 0, 5)), "way/1": _feat("way/1", _square(20, 0, 5))}
    b = {"way/2": _feat("way/2", _square(0, 0, 5)), "way/1": _feat("way/1", _square(20, 0, 5))}

    first = build_changeset(a, b)
    second = build_changeset(a, b)

    assert [(r.osm_ids_a, r.osm_ids_b) for r in first] == [(r.osm_ids_a, r.osm_ids_b) for r in second]
    keys = [(r.osm_ids_a, r.osm_ids_b) for r in first]
    assert keys == sorted(keys)
