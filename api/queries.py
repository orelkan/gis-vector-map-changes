"""SQL for the API. Kept in one module so every query is visible together
and reviewable as a unit, separate from HTTP concerns.

All tile SQL follows the pattern validated against the live database:
ST_TileEnvelope -> filter on the indexed 3857 column -> ST_AsMVTGeom ->
ST_AsMVT. Everything is parameterized; the only value ever interpolated is
the classification list, which is validated against a fixed allow-list
first (see api/main.py).
"""

from __future__ import annotations

# Classifications a change_features row may legitimately carry. `unchanged`
# is deliberately absent -- it is derived from absence, never stored
# (sql/003_create_feature_tables.sql).
VALID_CLASSIFICATIONS = frozenset(
    {
        "added",
        "removed",
        "modified_geometry",
        "modified_attributes",
        "modified_geometry_and_attributes",
        "ambiguous",
    }
)

LIST_SNAPSHOTS = """
    SELECT s.id, s.requested_time, s.source_query_version, s.feature_count,
           s.invalid_geometry_count, s.repaired_geometry_count,
           count(sf.id) AS published_feature_count
    FROM snapshots s
    LEFT JOIN snapshot_features sf ON sf.snapshot_id = s.id
    WHERE s.source_query_version = %(source_query_version)s
    GROUP BY s.id
    ORDER BY s.requested_time
"""

LIST_CHANGESETS = """
    SELECT c.id, c.algorithm_version,
           sa.id AS snapshot_a_id, sb.id AS snapshot_b_id,
           sa.requested_time AS time_a, sb.requested_time AS time_b,
           c.unchanged_count, c.modified_geometry_count, c.modified_attributes_count,
           c.modified_geometry_and_attributes_count, c.added_count,
           c.removed_count, c.ambiguous_count
    FROM changesets c
    JOIN snapshots sa ON sa.id = c.snapshot_a_id
    JOIN snapshots sb ON sb.id = c.snapshot_b_id
    ORDER BY (sb.requested_time - sa.requested_time), sa.requested_time
"""

GET_CHANGESET = LIST_CHANGESETS.replace(
    "ORDER BY (sb.requested_time - sa.requested_time), sa.requested_time",
    "WHERE c.id = %(changeset_id)s",
)

# Change-layer tile. Carries just enough to style and popup without a
# round-trip; the detail endpoint supplies everything else.
CHANGE_TILE = """
    WITH tile AS (SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS env)
    SELECT ST_AsMVT(t.*, 'changes', 4096, 'geom') AS mvt
    FROM (
        SELECT cf.id AS change_feature_id,
               cf.classification,
               cf.classification_reason,
               cf.iou,
               cf.centroid_shift_m,
               ST_AsMVTGeom(cf.geom_render_3857, tile.env, 4096, 64, true) AS geom
        FROM change_features cf, tile
        WHERE cf.changeset_id = %(changeset_id)s
          AND cf.geom_render_3857 && tile.env
          AND cf.classification = ANY(%(classifications)s)
    ) t
"""

# Context layer: the ~27k buildings of one snapshot, shared by every
# interval. Deliberately minimal properties to keep this large layer light;
# clicking fetches detail separately. Simplified by zoom so low-zoom tiles
# don't carry full vertex detail.
BUILDING_TILE = """
    WITH tile AS (SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS env)
    SELECT ST_AsMVT(t.*, 'buildings', 4096, 'geom') AS mvt
    FROM (
        SELECT sf.osm_id,
               ST_AsMVTGeom(
                   CASE WHEN %(z)s >= 16 THEN sf.geom_3857
                        ELSE ST_SimplifyPreserveTopology(sf.geom_3857, %(tolerance)s)
                   END,
                   tile.env, 4096, 64, true) AS geom
        FROM snapshot_features sf, tile
        WHERE sf.snapshot_id = %(snapshot_id)s
          AND sf.geom_3857 && tile.env
    ) t
"""

GET_CHANGE_FEATURE = """
    SELECT cf.id, cf.changeset_id, cf.classification, cf.match_method, cf.match_score,
           cf.classification_reason, cf.osm_ids_a, cf.osm_ids_b,
           cf.involves_repaired_geometry, cf.touches_aoi_boundary,
           cf.iou, cf.iou_centroid_aligned, cf.centroid_shift_m, cf.area_ratio,
           cf.hausdorff_m, cf.attrs_changed, cf.candidates,
           ST_AsGeoJSON(cf.geom_a)::jsonb AS geom_a,
           ST_AsGeoJSON(cf.geom_b)::jsonb AS geom_b,
           sa.requested_time AS time_a, sb.requested_time AS time_b
    FROM change_features cf
    JOIN changesets c ON c.id = cf.changeset_id
    JOIN snapshots sa ON sa.id = c.snapshot_a_id
    JOIN snapshots sb ON sb.id = c.snapshot_b_id
    WHERE cf.id = %(change_feature_id)s
"""

GET_SNAPSHOT_FEATURE = """
    SELECT sf.id, sf.snapshot_id, sf.osm_id, sf.osm_type, sf.building, sf.category,
           sf.name, sf.raw_tags, sf.original_valid, sf.repair_method,
           ST_AsGeoJSON(sf.geom)::jsonb AS geometry,
           s.requested_time
    FROM snapshot_features sf
    JOIN snapshots s ON s.id = sf.snapshot_id
    WHERE sf.snapshot_id = %(snapshot_id)s AND sf.osm_id = %(osm_id)s
"""

# Per-building timeline: one building across every snapshot held. Answers
# "many different timestamps" without needing a changeset per pair.
# Served by the dedicated snapshot_features(osm_id) index.
GET_FEATURE_HISTORY = """
    SELECT s.id AS snapshot_id, s.requested_time,
           sf.building, sf.category, sf.name, sf.raw_tags,
           sf.original_valid, sf.repair_method,
           ST_AsGeoJSON(sf.geom)::jsonb AS geometry,
           ST_Area(ST_Transform(sf.geom, 2039)) AS area_m2
    FROM snapshot_features sf
    JOIN snapshots s ON s.id = sf.snapshot_id
    WHERE sf.osm_id = %(osm_id)s
      AND s.source_query_version = %(source_query_version)s
    ORDER BY s.requested_time
"""

# Which changesets this building appears as a change in, so the timeline can
# link a geometry jump to the interval that classified it.
GET_FEATURE_CHANGE_PARTICIPATION = """
    SELECT cf.id AS change_feature_id, cf.changeset_id, cf.classification,
           sa.requested_time AS time_a, sb.requested_time AS time_b
    FROM change_features cf
    JOIN changesets c ON c.id = cf.changeset_id
    JOIN snapshots sa ON sa.id = c.snapshot_a_id
    JOIN snapshots sb ON sb.id = c.snapshot_b_id
    WHERE %(osm_id)s = ANY(cf.osm_ids_a) OR %(osm_id)s = ANY(cf.osm_ids_b)
    ORDER BY sa.requested_time, sb.requested_time
"""
