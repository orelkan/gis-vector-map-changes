-- Feature-level serving tables for the web UI (milestone 3).
--
-- Until now, feature geometry lived only in MinIO as GeoJSON, and PostGIS
-- held just metadata (snapshots, changesets). These two tables are the
-- *serving layer*: derived from the MinIO objects, rebuildable at any time,
-- and indexed for vector-tile generation via ST_AsMVT.
--
-- Storage model (see docs/web-ui.md and docs/matching-behavior.md):
--   * snapshot_features grows LINEARLY -- one row per building per snapshot,
--     shared by every comparison that involves that snapshot.
--   * change_features stores ONLY records that actually changed. In the real
--     data 98.3-99.8% of a fully-materialized changeset would be `unchanged`
--     rows carrying no information, so `unchanged` is derived instead: a
--     building present in both snapshots with no change_features row for a
--     changeset is unchanged. The CHECK constraint below enforces that
--     invariant at the database level.

CREATE TABLE IF NOT EXISTS snapshot_features (
    id BIGSERIAL PRIMARY KEY,

    snapshot_id BIGINT NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    osm_id TEXT NOT NULL,
    osm_type TEXT NOT NULL,

    -- Significant attributes (see src/matching/config.py SIGNIFICANT_TAGS)
    building TEXT,
    category TEXT,
    name TEXT,
    -- Full source tags preserved for provenance / the detail panel
    raw_tags JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Ingestion-time geometry provenance (see src/ingestion/validate.py)
    original_valid BOOLEAN NOT NULL,
    repair_method TEXT,

    -- Authoritative source CRS; what GeoJSON responses are built from
    -- (RFC 7946 requires WGS84), avoiding a lossy 3857 round-trip.
    geom geometry(MultiPolygon, 4326) NOT NULL,
    -- Web Mercator copy for MVT. Materialized rather than indexed via a
    -- functional index because ST_Transform is STABLE, not IMMUTABLE, so
    -- PostgreSQL rejects it in an index expression -- and this also avoids
    -- reprojecting every geometry on every tile request.
    geom_3857 geometry(MultiPolygon, 3857) NOT NULL,

    CONSTRAINT snapshot_features_natural_key UNIQUE (snapshot_id, osm_id)
);

CREATE INDEX IF NOT EXISTS snapshot_features_geom_3857_idx
    ON snapshot_features USING GIST (geom_3857);
CREATE INDEX IF NOT EXISTS snapshot_features_snapshot_id_idx
    ON snapshot_features (snapshot_id);
-- Serves the per-building timeline (one building across ALL snapshots).
-- The composite natural key above cannot satisfy a query filtered by
-- osm_id alone, since snapshot_id is its leading column.
CREATE INDEX IF NOT EXISTS snapshot_features_osm_id_idx
    ON snapshot_features (osm_id);


CREATE TABLE IF NOT EXISTS change_features (
    id BIGSERIAL PRIMARY KEY,

    changeset_id BIGINT NOT NULL REFERENCES changesets (id) ON DELETE CASCADE,

    classification TEXT NOT NULL,
    match_method TEXT,
    match_score DOUBLE PRECISION,
    classification_reason TEXT NOT NULL,
    osm_ids_a TEXT[] NOT NULL DEFAULT '{}',
    osm_ids_b TEXT[] NOT NULL DEFAULT '{}',
    involves_repaired_geometry BOOLEAN NOT NULL,
    touches_aoi_boundary BOOLEAN NOT NULL,

    -- Metrics for a resolved 1:1 pair; NULL for added/removed and for
    -- multi-candidate ambiguous groups (which keep everything in candidates).
    iou DOUBLE PRECISION,
    iou_centroid_aligned DOUBLE PRECISION,
    centroid_shift_m DOUBLE PRECISION,
    area_ratio DOUBLE PRECISION,
    hausdorff_m DOUBLE PRECISION,
    attrs_changed TEXT[] NOT NULL DEFAULT '{}',
    -- Every candidate pair considered, with its own metrics. Ambiguous
    -- records keep all of them rather than silently picking a winner.
    candidates JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Before/after, for "what changed and how". Served as GeoJSON by the
    -- detail endpoint for one selected feature rather than baked into
    -- every tile.
    geom_a geometry(MultiPolygon, 4326),
    geom_b geometry(MultiPolygon, 4326),
    -- What the change-layer tiles actually draw.
    geom_render_3857 geometry(MultiPolygon, 3857) NOT NULL,

    -- `unchanged` is derived (absence of a row), never stored -- see the
    -- header comment. Enforced here so a future loader bug cannot quietly
    -- reintroduce ~27k no-op rows per changeset.
    CONSTRAINT change_features_no_unchanged CHECK (classification <> 'unchanged'),
    CONSTRAINT change_features_added_has_b CHECK (
        classification <> 'added' OR geom_b IS NOT NULL
    ),
    CONSTRAINT change_features_removed_has_a CHECK (
        classification <> 'removed' OR geom_a IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS change_features_geom_render_3857_idx
    ON change_features USING GIST (geom_render_3857);
CREATE INDEX IF NOT EXISTS change_features_changeset_id_idx
    ON change_features (changeset_id);
-- The primary filter in the UI (show only added/removed/modified/...).
CREATE INDEX IF NOT EXISTS change_features_classification_idx
    ON change_features (changeset_id, classification);


COMMENT ON TABLE snapshot_features IS
    'One row per building per snapshot. Grows linearly with snapshots and is shared by every comparison involving that snapshot; never duplicated per changeset.';
COMMENT ON COLUMN snapshot_features.geom_3857 IS
    'Web Mercator copy of geom, materialized for MVT generation because ST_Transform is STABLE and therefore cannot be used in a functional index.';
COMMENT ON TABLE change_features IS
    'One row per NON-unchanged change record. `unchanged` is derived from absence (present in both snapshots, no row here) -- storing it would be 98-99% waste. Enforced by change_features_no_unchanged.';
COMMENT ON COLUMN change_features.geom_render_3857 IS
    'The geometry the change-layer vector tiles draw: the after-geometry where one exists, the before-geometry for removals, or the union of all involved footprints for a multi-candidate ambiguous group.';
COMMENT ON COLUMN change_features.candidates IS
    'Every candidate pair considered for this record with its metrics; ambiguous records retain all of them rather than silently resolving to the highest score.';
