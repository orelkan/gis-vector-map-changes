"""Publishes snapshot features and change records from their MinIO GeoJSON
into the PostGIS serving tables (see sql/003_create_feature_tables.sql).

Takes an already-connected DBAPI connection rather than owning connection
setup, matching src/db/*.py -- so this is testable against a real local
Postgres without Airflow.

Idempotent by atomic replacement: every publish deletes the rows scoped to
one snapshot_id / changeset_id and re-inserts, inside a single transaction
(CLAUDE.md: "if output is replaced, do so atomically where practical").

Ordering dependency: publish_change_features() derives each record's
before/after geometry by joining to snapshot_features, so **both** of a
changeset's snapshots must be published first. This is deliberate -- the
geometry already exists there, so deriving it avoids both duplicating it and
having to change the matching pipeline's output format. The function raises
if the prerequisite is missing rather than silently writing NULL geometry.
"""

from __future__ import annotations

import json
from typing import Any

from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

# Mirrors the geometry(MultiPolygon, ...) columns: a typed column must pick
# one type, and snapshots legitimately contain both Polygon and MultiPolygon.
POLYGONAL_TYPES = ("Polygon", "MultiPolygon")


def _as_multipolygon(geometry: BaseGeometry) -> MultiPolygon:
    """Normalize to MultiPolygon (PostGIS ST_Multi equivalent), done in
    Python so the WKB sent to the database already matches the column type.

    Raises on anything non-polygonal rather than coercing: the v2 ingestion
    fix guarantees Polygon/MultiPolygon only, so a GeometryCollection here
    would mean that invariant broke and must not pass silently.
    """
    if geometry.geom_type == "MultiPolygon":
        return geometry
    if geometry.geom_type == "Polygon":
        return MultiPolygon([geometry])
    raise ValueError(
        f"expected {POLYGONAL_TYPES}, got {geometry.geom_type!r} -- "
        "snapshots should contain only polygonal geometry (see "
        "src/ingestion/validate.py)"
    )


def _geom_hex(geojson_geometry: dict[str, Any]) -> str:
    return _as_multipolygon(shape(geojson_geometry)).wkb_hex


_STAGING_SNAPSHOT_DDL = """
    CREATE TEMP TABLE staging_snapshot_features (
        osm_id TEXT, osm_type TEXT, building TEXT, category TEXT, name TEXT,
        raw_tags TEXT, original_valid BOOLEAN, repair_method TEXT, geom_hex TEXT
    ) ON COMMIT DROP
"""

_INSERT_SNAPSHOT_FEATURES = """
    INSERT INTO snapshot_features (
        snapshot_id, osm_id, osm_type, building, category, name, raw_tags,
        original_valid, repair_method, geom, geom_3857
    )
    SELECT
        %(snapshot_id)s, osm_id, osm_type, building, category, name,
        raw_tags::jsonb, original_valid, repair_method,
        ST_SetSRID(geom_hex::geometry, 4326),
        ST_Transform(ST_SetSRID(geom_hex::geometry, 4326), 3857)
    FROM staging_snapshot_features
"""


def publish_snapshot_features(
    connection: Any, snapshot_id: int, processed_geojson: dict[str, Any]
) -> int:
    """Replace this snapshot's feature rows. Returns the row count written."""
    features = processed_geojson.get("features", [])
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM snapshot_features WHERE snapshot_id = %s", (snapshot_id,))
        cursor.execute(_STAGING_SNAPSHOT_DDL)
        with cursor.copy(
            "COPY staging_snapshot_features "
            "(osm_id, osm_type, building, category, name, raw_tags, "
            "original_valid, repair_method, geom_hex) FROM STDIN"
        ) as copy:
            for feature in features:
                props = feature["properties"]
                copy.write_row(
                    (
                        props["osm_id"],
                        props["osm_type"],
                        props.get("building"),
                        props.get("category"),
                        props.get("name"),
                        json.dumps(props.get("raw_tags", {})),
                        props["original_valid"],
                        props.get("repair_method"),
                        _geom_hex(feature["geometry"]),
                    )
                )
        cursor.execute(_INSERT_SNAPSHOT_FEATURES, {"snapshot_id": snapshot_id})
        written = cursor.rowcount
    connection.commit()
    return written


_STAGING_CHANGE_DDL = """
    CREATE TEMP TABLE staging_change_features (
        classification TEXT, match_method TEXT, match_score DOUBLE PRECISION,
        classification_reason TEXT, osm_ids_a TEXT[], osm_ids_b TEXT[],
        involves_repaired_geometry BOOLEAN, touches_aoi_boundary BOOLEAN,
        iou DOUBLE PRECISION, iou_centroid_aligned DOUBLE PRECISION,
        centroid_shift_m DOUBLE PRECISION, area_ratio DOUBLE PRECISION,
        hausdorff_m DOUBLE PRECISION, attrs_changed TEXT[], candidates TEXT,
        geom_hex TEXT
    ) ON COMMIT DROP
"""

# Before/after geometry is derived from the already-published snapshot rows
# *inside this INSERT*, not by a follow-up UPDATE: the
# change_features_added_has_b / _removed_has_a CHECK constraints are
# evaluated per row at insert time, and PostgreSQL cannot defer CHECK
# constraints (only FK/PK/UNIQUE/EXCLUDE), so the geometry has to be present
# immediately. ST_Union collapses a multi-candidate ambiguous group's
# footprints into one geometry and yields NULL over zero rows -- which is
# exactly what `added` (no A side) and `removed` (no B side) require.
_INSERT_CHANGE_FEATURES = """
    INSERT INTO change_features (
        changeset_id, classification, match_method, match_score,
        classification_reason, osm_ids_a, osm_ids_b,
        involves_repaired_geometry, touches_aoi_boundary,
        iou, iou_centroid_aligned, centroid_shift_m, area_ratio, hausdorff_m,
        attrs_changed, candidates, geom_a, geom_b, geom_render_3857
    )
    SELECT
        %(changeset_id)s, s.classification, s.match_method, s.match_score,
        s.classification_reason, s.osm_ids_a, s.osm_ids_b,
        s.involves_repaired_geometry, s.touches_aoi_boundary,
        s.iou, s.iou_centroid_aligned, s.centroid_shift_m, s.area_ratio, s.hausdorff_m,
        s.attrs_changed, s.candidates::jsonb,
        (SELECT ST_Multi(ST_Union(sf.geom)) FROM snapshot_features sf
          WHERE sf.snapshot_id = %(snapshot_a_id)s AND sf.osm_id = ANY (s.osm_ids_a)),
        (SELECT ST_Multi(ST_Union(sf.geom)) FROM snapshot_features sf
          WHERE sf.snapshot_id = %(snapshot_b_id)s AND sf.osm_id = ANY (s.osm_ids_b)),
        ST_Transform(ST_SetSRID(s.geom_hex::geometry, 4326), 3857)
    FROM staging_change_features s
"""


def _require_published_snapshot(cursor: Any, snapshot_id: int) -> None:
    cursor.execute(
        "SELECT 1 FROM snapshot_features WHERE snapshot_id = %s LIMIT 1", (snapshot_id,)
    )
    if cursor.fetchone() is None:
        raise ValueError(
            f"snapshot {snapshot_id} has no published features -- publish both of a "
            "changeset's snapshots before publishing the changeset itself "
            "(before/after geometry is derived from them)"
        )


def publish_change_features(
    connection: Any,
    changeset_id: int,
    snapshot_a_id: int,
    snapshot_b_id: int,
    change_layer_geojson: dict[str, Any],
) -> int:
    """Replace this changeset's change rows, skipping `unchanged` records.

    `unchanged` is derived from absence rather than stored (98-99% of a
    changeset would otherwise be no-op rows); the change_features_no_unchanged
    CHECK constraint enforces this independently. Returns rows written.
    """
    features = [
        f
        for f in change_layer_geojson.get("features", [])
        if f["properties"]["classification"] != "unchanged"
    ]

    with connection.cursor() as cursor:
        _require_published_snapshot(cursor, snapshot_a_id)
        _require_published_snapshot(cursor, snapshot_b_id)

        cursor.execute("DELETE FROM change_features WHERE changeset_id = %s", (changeset_id,))
        cursor.execute(_STAGING_CHANGE_DDL)
        with cursor.copy(
            "COPY staging_change_features "
            "(classification, match_method, match_score, classification_reason, "
            "osm_ids_a, osm_ids_b, involves_repaired_geometry, touches_aoi_boundary, "
            "iou, iou_centroid_aligned, centroid_shift_m, area_ratio, hausdorff_m, "
            "attrs_changed, candidates, geom_hex) FROM STDIN"
        ) as copy:
            for feature in features:
                props = feature["properties"]
                # A resolved 1:1 pair has exactly one candidate, whose metrics
                # are the record's metrics. Multi-candidate (ambiguous) groups
                # keep everything in `candidates` and leave these NULL rather
                # than picking one to promote.
                candidates = props.get("candidates", [])
                metrics = candidates[0] if len(candidates) == 1 else {}
                copy.write_row(
                    (
                        props["classification"],
                        props.get("match_method"),
                        props.get("match_score"),
                        props["classification_reason"],
                        props.get("osm_ids_a", []),
                        props.get("osm_ids_b", []),
                        props["involves_repaired_geometry"],
                        props["touches_aoi_boundary"],
                        metrics.get("iou"),
                        metrics.get("iou_centroid_aligned"),
                        metrics.get("centroid_shift_m"),
                        metrics.get("area_ratio"),
                        metrics.get("hausdorff_m"),
                        metrics.get("attrs_changed", []),
                        json.dumps(candidates),
                        _geom_hex(feature["geometry"]),
                    )
                )
        cursor.execute(
            _INSERT_CHANGE_FEATURES,
            {
                "changeset_id": changeset_id,
                "snapshot_a_id": snapshot_a_id,
                "snapshot_b_id": snapshot_b_id,
            },
        )
        written = cursor.rowcount

    connection.commit()
    return written
