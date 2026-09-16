-- Metadata + summary counts for a matching run between two snapshots. The
-- actual per-feature change records (added/removed/modified_*/unchanged/
-- ambiguous, one GeoJSON feature each, carrying match method/score/reason
-- and metrics) live in object storage as one "change layer" FeatureCollection;
-- this table records which two snapshots were compared, with what algorithm
-- version, and where to find the results -- mirroring the split already used
-- for snapshots (001_create_snapshots.sql): bulk geodata in object storage,
-- small queryable metadata in Postgres.
--
-- Natural key = (snapshot_a_id, snapshot_b_id, algorithm_version).
-- created_time is recorded as an attribute, not part of the natural key, so
-- re-running a comparison with the same inputs and algorithm is a no-op
-- (idempotent), per CLAUDE.md's idempotency rules -- same pattern as
-- snapshots.ingestion_time.

CREATE TABLE IF NOT EXISTS changesets (
    id BIGSERIAL PRIMARY KEY,

    -- Natural key
    snapshot_a_id BIGINT NOT NULL REFERENCES snapshots (id),
    snapshot_b_id BIGINT NOT NULL REFERENCES snapshots (id),
    algorithm_version TEXT NOT NULL,

    -- Provenance
    created_time TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Where the per-feature change records actually live
    change_layer_object_uri TEXT NOT NULL,

    -- Summary counts, one per classification -- useful for quick sanity
    -- checks (and for reproducing docs/matching-behavior.md's acceptance
    -- table) without opening the object store file.
    unchanged_count INTEGER NOT NULL,
    modified_geometry_count INTEGER NOT NULL,
    modified_attributes_count INTEGER NOT NULL,
    modified_geometry_and_attributes_count INTEGER NOT NULL,
    added_count INTEGER NOT NULL,
    removed_count INTEGER NOT NULL,
    ambiguous_count INTEGER NOT NULL,

    CONSTRAINT changesets_natural_key UNIQUE (snapshot_a_id, snapshot_b_id, algorithm_version)
);

COMMENT ON TABLE changesets IS
    'One row per matching run between two snapshots. Per-feature change records live in object storage; this is metadata + summary counts.';
COMMENT ON COLUMN changesets.algorithm_version IS
    'Version of the matching algorithm + thresholds (src.matching.config.ALGORITHM_VERSION) that produced this comparison. A changed algorithm/threshold creates a new version rather than rewriting history, per CLAUDE.md.';
COMMENT ON COLUMN changesets.snapshot_a_id IS
    'The earlier ("before") snapshot in the comparison.';
COMMENT ON COLUMN changesets.snapshot_b_id IS
    'The later ("after") snapshot in the comparison.';
