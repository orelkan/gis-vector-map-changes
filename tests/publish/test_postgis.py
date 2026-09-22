"""Publisher tests against a real local Postgres, per CLAUDE.md's rule to
test SQL against the actual database rather than mocks.

Requires `make up && make migrate`. Run with `make test-db`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.db import changesets as changesets_db
from src.db import snapshots as snapshots_db
from src.publish import postgis

pytestmark = pytest.mark.db

TEST_SOURCE = "test-source-publish"

# Two 1m-ish squares near Tel Aviv, in EPSG:4326.
SQUARE_A = [[34.780, 32.080], [34.781, 32.080], [34.781, 32.081], [34.780, 32.081], [34.780, 32.080]]
SQUARE_B = [[34.790, 32.090], [34.791, 32.090], [34.791, 32.091], [34.790, 32.091], [34.790, 32.090]]


def _snapshot_params(**overrides) -> dict:
    base = {
        "source": TEST_SOURCE,
        "source_query_version": "v2",
        "layer": "building",
        "aoi_id": "test-aoi",
        "aoi_version": "v1",
        "requested_time": datetime(2026, 6, 1, tzinfo=UTC),
        "crs": "OGC:CRS84",
        "raw_object_uri": "s3://bucket/raw.geojson",
        "processed_object_uri": "s3://bucket/processed.geojson",
        "feature_count": 1,
        "invalid_geometry_count": 0,
        "repaired_geometry_count": 0,
    }
    base.update(overrides)
    return base


def _snapshot_feature(osm_id="way/1", coords=None, geom_type="Polygon", **prop_overrides):
    coords = coords or SQUARE_A
    geometry = (
        {"type": "Polygon", "coordinates": [coords]}
        if geom_type == "Polygon"
        else {"type": "MultiPolygon", "coordinates": [[coords]]}
    )
    props = {
        "osm_id": osm_id,
        "osm_type": osm_id.split("/")[0],
        "building": "house",
        "category": "residential",
        "name": None,
        "raw_tags": {"building": "house"},
        "original_valid": True,
        "repair_method": None,
    }
    props.update(prop_overrides)
    return {"type": "Feature", "geometry": geometry, "properties": props}


def _change_feature(classification="added", osm_ids_a=None, osm_ids_b=None, coords=None,
                    candidates=None, reason="no_spatial_counterpart"):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords or SQUARE_A]},
        "properties": {
            "classification": classification,
            "match_method": "osm_id" if classification.startswith("modified") else None,
            "match_score": 0.5 if classification.startswith("modified") else None,
            "classification_reason": reason,
            "osm_ids_a": osm_ids_a if osm_ids_a is not None else [],
            "osm_ids_b": osm_ids_b if osm_ids_b is not None else ["way/1"],
            "involves_repaired_geometry": False,
            "touches_aoi_boundary": False,
            "algorithm_version": "v1",
            "candidates": candidates if candidates is not None else [],
        },
    }


@pytest.fixture
def published_snapshots(db_connection):
    """Two snapshots with one feature each, already published."""
    a = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 6, 1, tzinfo=UTC))
    )
    b = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 7, 1, tzinfo=UTC))
    )
    postgis.publish_snapshot_features(
        db_connection, a.id,
        {"type": "FeatureCollection", "features": [_snapshot_feature("way/1", SQUARE_A)]},
    )
    postgis.publish_snapshot_features(
        db_connection, b.id,
        {"type": "FeatureCollection", "features": [_snapshot_feature("way/1", SQUARE_B)]},
    )
    return a.id, b.id


@pytest.fixture(autouse=True)
def _cleanup(db_connection):
    yield
    with db_connection.cursor() as cursor:
        # change_features / snapshot_features cascade from their parents.
        cursor.execute(
            "DELETE FROM changesets WHERE snapshot_a_id IN "
            "(SELECT id FROM snapshots WHERE source = %s)", (TEST_SOURCE,)
        )
        cursor.execute("DELETE FROM snapshots WHERE source = %s", (TEST_SOURCE,))
    db_connection.commit()


# --- snapshot features ----------------------------------------------------


def test_publish_snapshot_features_writes_rows(db_connection):
    snap = snapshots_db.upsert_snapshot(db_connection, _snapshot_params())
    fc = {"type": "FeatureCollection",
          "features": [_snapshot_feature("way/1"), _snapshot_feature("way/2", SQUARE_B)]}

    written = postgis.publish_snapshot_features(db_connection, snap.id, fc)

    assert written == 2
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM snapshot_features WHERE snapshot_id = %s", (snap.id,))
        assert cur.fetchone()[0] == 2


def test_publish_snapshot_features_is_idempotent(db_connection):
    snap = snapshots_db.upsert_snapshot(db_connection, _snapshot_params())
    fc = {"type": "FeatureCollection", "features": [_snapshot_feature("way/1")]}

    postgis.publish_snapshot_features(db_connection, snap.id, fc)
    postgis.publish_snapshot_features(db_connection, snap.id, fc)

    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM snapshot_features WHERE snapshot_id = %s", (snap.id,))
        assert cur.fetchone()[0] == 1


def test_publish_normalizes_polygon_to_multipolygon(db_connection):
    snap = snapshots_db.upsert_snapshot(db_connection, _snapshot_params())
    fc = {"type": "FeatureCollection", "features": [_snapshot_feature("way/1", geom_type="Polygon")]}

    postgis.publish_snapshot_features(db_connection, snap.id, fc)

    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT ST_GeometryType(geom), ST_SRID(geom), ST_SRID(geom_3857) "
            "FROM snapshot_features WHERE snapshot_id = %s", (snap.id,)
        )
        geom_type, srid, srid_3857 = cur.fetchone()
    assert geom_type == "ST_MultiPolygon"
    assert srid == 4326
    assert srid_3857 == 3857


def test_publish_geom_3857_matches_transform_of_geom(db_connection):
    snap = snapshots_db.upsert_snapshot(db_connection, _snapshot_params())
    postgis.publish_snapshot_features(
        db_connection, snap.id,
        {"type": "FeatureCollection", "features": [_snapshot_feature("way/1")]},
    )

    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT ST_Equals(geom_3857, ST_Transform(geom, 3857)) "
            "FROM snapshot_features WHERE snapshot_id = %s", (snap.id,)
        )
        assert cur.fetchone()[0] is True


def test_publish_rejects_non_polygonal_geometry(db_connection):
    snap = snapshots_db.upsert_snapshot(db_connection, _snapshot_params())
    bad = {"type": "Feature",
           "geometry": {"type": "LineString", "coordinates": [[34.78, 32.08], [34.79, 32.09]]},
           "properties": _snapshot_feature()["properties"]}

    with pytest.raises(ValueError, match="polygonal"):
        postgis.publish_snapshot_features(
            db_connection, snap.id, {"type": "FeatureCollection", "features": [bad]}
        )
    db_connection.rollback()


# --- change features ------------------------------------------------------


def _changeset(db_connection, a_id, b_id):
    return changesets_db.upsert_changeset(db_connection, {
        "snapshot_a_id": a_id, "snapshot_b_id": b_id, "algorithm_version": "v1",
        "change_layer_object_uri": "s3://bucket/change_layer.geojson",
        "unchanged_count": 1, "modified_geometry_count": 1,
        "modified_attributes_count": 0, "modified_geometry_and_attributes_count": 0,
        "added_count": 1, "removed_count": 0, "ambiguous_count": 0,
    })


def test_publish_change_features_skips_unchanged(db_connection, published_snapshots):
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)
    layer = {"type": "FeatureCollection", "features": [
        _change_feature("unchanged", ["way/1"], ["way/1"], reason="osm_id_match_unchanged"),
        _change_feature("added", [], ["way/1"]),
    ]}

    written = postgis.publish_change_features(db_connection, cs.id, a_id, b_id, layer)

    assert written == 1  # only the `added` row
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT classification FROM change_features WHERE changeset_id = %s", (cs.id,)
        )
        assert [r[0] for r in cur.fetchall()] == ["added"]


def test_change_features_check_constraint_rejects_unchanged(db_connection, published_snapshots):
    """The no-unchanged invariant is enforced by the database itself, not
    only by the loader -- a future loader bug cannot reintroduce the rows."""
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)

    with (
        pytest.raises(Exception, match="change_features_no_unchanged"),
        db_connection.cursor() as cur,
    ):
        cur.execute(
            "INSERT INTO change_features (changeset_id, classification, "
            "classification_reason, involves_repaired_geometry, touches_aoi_boundary, "
            "geom_render_3857) VALUES (%s, 'unchanged', 'x', false, false, "
            "ST_Transform(ST_SetSRID(ST_GeomFromText('MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))'), 4326), 3857))",
            (cs.id,),
        )
    db_connection.rollback()


def test_publish_change_features_is_idempotent(db_connection, published_snapshots):
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)
    layer = {"type": "FeatureCollection", "features": [_change_feature("added", [], ["way/1"])]}

    postgis.publish_change_features(db_connection, cs.id, a_id, b_id, layer)
    postgis.publish_change_features(db_connection, cs.id, a_id, b_id, layer)

    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM change_features WHERE changeset_id = %s", (cs.id,))
        assert cur.fetchone()[0] == 1


def test_publish_derives_before_and_after_geometry(db_connection, published_snapshots):
    """geom_a/geom_b are joined from the already-published snapshot rows --
    this is what makes the before/after overlay possible."""
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)
    layer = {"type": "FeatureCollection", "features": [
        _change_feature("modified_geometry", ["way/1"], ["way/1"], coords=SQUARE_B,
                        reason="osm_id_match_modified_geometry",
                        candidates=[{"osm_id_a": "way/1", "osm_id_b": "way/1", "iou": 0.0,
                                     "iou_centroid_aligned": 1.0, "centroid_shift_m": 1300.0,
                                     "area_ratio": 1.0, "hausdorff_m": 1400.0,
                                     "attrs_changed": []}]),
    ]}

    postgis.publish_change_features(db_connection, cs.id, a_id, b_id, layer)

    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT geom_a IS NOT NULL, geom_b IS NOT NULL, ST_Equals(geom_a, geom_b), "
            "iou, centroid_shift_m FROM change_features WHERE changeset_id = %s", (cs.id,)
        )
        has_a, has_b, equal, iou, shift = cur.fetchone()
    assert has_a and has_b
    assert equal is False  # SQUARE_A vs SQUARE_B are genuinely different
    assert iou == 0.0
    assert shift == pytest.approx(1300.0)


def test_added_record_has_no_before_geometry(db_connection, published_snapshots):
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)
    layer = {"type": "FeatureCollection", "features": [_change_feature("added", [], ["way/1"])]}

    postgis.publish_change_features(db_connection, cs.id, a_id, b_id, layer)

    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT geom_a IS NULL, geom_b IS NOT NULL FROM change_features "
            "WHERE changeset_id = %s", (cs.id,)
        )
        a_null, b_present = cur.fetchone()
    assert a_null and b_present


def test_publish_change_features_requires_published_snapshots(db_connection):
    """Fails loudly rather than writing NULL before/after geometry."""
    a = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 6, 1, tzinfo=UTC))
    )
    b = snapshots_db.upsert_snapshot(
        db_connection, _snapshot_params(requested_time=datetime(2026, 7, 1, tzinfo=UTC))
    )
    cs = _changeset(db_connection, a.id, b.id)

    with pytest.raises(ValueError, match="no published features"):
        postgis.publish_change_features(
            db_connection, cs.id, a.id, b.id,
            {"type": "FeatureCollection", "features": [_change_feature()]},
        )
    db_connection.rollback()


def test_unchanged_is_derivable_from_absence(db_connection, published_snapshots):
    """A building in both snapshots with no change_features row is unchanged
    -- the derivation the UI and API rely on (see docs/architecture.md)."""
    a_id, b_id = published_snapshots
    cs = _changeset(db_connection, a_id, b_id)
    postgis.publish_change_features(
        db_connection, cs.id, a_id, b_id, {"type": "FeatureCollection", "features": []}
    )

    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT sf.osm_id FROM snapshot_features sf
            WHERE sf.snapshot_id = %(b)s
              AND EXISTS (SELECT 1 FROM snapshot_features p
                          WHERE p.snapshot_id = %(a)s AND p.osm_id = sf.osm_id)
              AND NOT EXISTS (SELECT 1 FROM change_features cf
                              WHERE cf.changeset_id = %(cs)s
                                AND sf.osm_id = ANY (cf.osm_ids_b))
            """,
            {"a": a_id, "b": b_id, "cs": cs.id},
        )
        assert [r[0] for r in cur.fetchall()] == ["way/1"]
