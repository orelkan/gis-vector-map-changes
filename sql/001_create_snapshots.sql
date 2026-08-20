-- Metadata for immutable ingested snapshots. The actual building features
-- (raw + validated/normalized GeoJSON) live in object storage (MinIO); this
-- table records what was fetched, when, from where, and where to find it.
--
-- Natural key = (source, source_query_version, layer, aoi_id, aoi_version,
-- requested_time). ingestion_time is recorded as an attribute, not part of
-- the natural key, so re-running an ingestion for the same logical inputs
-- is a no-op (idempotent), per CLAUDE.md's idempotency rules.

CREATE TABLE IF NOT EXISTS snapshots (
    id BIGSERIAL PRIMARY KEY,

    -- Natural key
    source TEXT NOT NULL,
    source_query_version TEXT NOT NULL,
    layer TEXT NOT NULL,
    aoi_id TEXT NOT NULL,
    aoi_version TEXT NOT NULL,
    requested_time TIMESTAMPTZ NOT NULL,

    -- Provenance
    ingestion_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    crs TEXT NOT NULL,

    -- Where the actual data lives
    raw_object_uri TEXT NOT NULL,
    processed_object_uri TEXT NOT NULL,

    -- Summary stats, useful for quick sanity checks without opening the
    -- object store files
    feature_count INTEGER NOT NULL,
    invalid_geometry_count INTEGER NOT NULL,
    repaired_geometry_count INTEGER NOT NULL,

    CONSTRAINT snapshots_natural_key UNIQUE (
        source, source_query_version, layer, aoi_id, aoi_version, requested_time
    )
);

COMMENT ON TABLE snapshots IS
    'One row per immutable ingested snapshot. Feature data lives in object storage; this is metadata + provenance.';
COMMENT ON COLUMN snapshots.source_query_version IS
    'Version of our extraction definition (ohsome filter + extracted tags) -- our analog of a named upstream release, since OSM has none.';
COMMENT ON COLUMN snapshots.requested_time IS
    'The OSM-data-as-of instant this snapshot represents (the actual temporal partition of the source).';
