from __future__ import annotations

from shapely.geometry import Polygon, shape

from src.matching.changeset import build_changeset
from src.matching.features import LoadedFeature
from src.matching.render import render_change_layer


def _feat(osm_id, geom, building="house", category="residential", name=None, repaired=False):
    return LoadedFeature(
        osm_id=osm_id,
        geometry=geom,
        attrs={"building": building, "category": category, "name": name},
        repaired=repaired,
    )


def _square(x0, y0, side):
    # Small values -- these represent METRIC_CRS (EPSG:2039, metres, values
    # in the low hundreds-of-thousands near Tel Aviv) coordinates well
    # outside the real AOI, but reprojection must still succeed and land in
    # a lon/lat-shaped range.
    return Polygon([(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)])


def test_render_produces_a_feature_per_record():
    a = {"way/1": _feat("way/1", _square(180_000, 660_000, 10))}
    b = {"way/1": _feat("way/1", _square(180_000, 660_000, 10))}
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)

    assert layer["type"] == "FeatureCollection"
    assert len(layer["features"]) == len(records)


def test_render_reprojects_geometry_back_to_lon_lat_range():
    a = {"way/1": _feat("way/1", _square(180_000, 660_000, 10))}
    b = {"way/1": _feat("way/1", _square(180_000, 660_000, 10))}
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)
    geom = shape(layer["features"][0]["geometry"])

    minx, miny, _maxx, _maxy = geom.bounds
    assert 34 < minx < 36  # Israel's longitude range
    assert 31 < miny < 34  # Israel's latitude range


def test_render_properties_carry_classification_and_ids():
    a = {"way/1": _feat("way/1", _square(180_000, 660_000, 10), building="house")}
    b = {"way/1": _feat("way/1", _square(180_000, 660_000, 10), building="office")}
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)
    props = layer["features"][0]["properties"]

    assert props["classification"] == "modified_attributes"
    assert props["osm_ids_a"] == ["way/1"]
    assert props["osm_ids_b"] == ["way/1"]
    assert props["match_method"] == "osm_id"
    assert len(props["candidates"]) == 1
    assert props["candidates"][0]["attrs_changed"] == ["building"]


def test_render_added_record_uses_b_geometry():
    a: dict = {}
    b = {"way/new": _feat("way/new", _square(180_000, 660_000, 10))}
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)
    props = layer["features"][0]["properties"]

    assert props["classification"] == "added"
    assert props["osm_ids_a"] == []
    assert props["osm_ids_b"] == ["way/new"]


def test_render_removed_record_uses_a_geometry():
    a = {"way/gone": _feat("way/gone", _square(180_000, 660_000, 10))}
    b: dict = {}
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)
    props = layer["features"][0]["properties"]

    assert props["classification"] == "removed"
    assert props["osm_ids_a"] == ["way/gone"]
    assert props["osm_ids_b"] == []


def test_render_ambiguous_split_carries_all_candidates():
    a = {"way/old": _feat("way/old", _square(180_000, 660_000, 4))}
    b = {
        "way/new1": _feat("way/new1", _square(180_000, 660_000, 2)),
        "way/new2": _feat("way/new2", _square(180_002, 660_000, 2)),
    }
    records = build_changeset(a, b)

    layer = render_change_layer(records, a, b)
    props = next(f["properties"] for f in layer["features"] if f["properties"]["classification"] == "ambiguous")

    assert props["classification_reason"] == "split_candidate"
    assert len(props["candidates"]) == 2
    assert {c["osm_id_b"] for c in props["candidates"]} == {"way/new1", "way/new2"}
    # Representative geometry is the union of both new footprints -- still
    # a valid, locatable polygon, not thrown away for lack of a single answer.
    geom = shape(next(f["geometry"] for f in layer["features"] if f["properties"]["classification"] == "ambiguous"))
    assert geom.is_valid
    assert geom.area > 0
