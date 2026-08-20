# GIS Vector Map Changes

Educational vector-GIS data platform for detecting and explaining changes
between dated map snapshots of Tel Aviv-Yafo. See `CLAUDE.md` for full
project scope, working agreement, and architecture rules.

## Current milestone: ingestion

Fetches three dated Tel Aviv-Yafo building snapshots from OpenStreetMap (via
the [ohsome API](https://docs.ohsome.org/ohsome-api/v1/)), validates and
normalizes them, and persists them durably (MinIO object storage + Postgres
metadata). Matching/classification (added/removed/modified/unchanged/
ambiguous) is a separate, later milestone -- not implemented yet.

## Data source and licensing

Building geometry and tags come from [OpenStreetMap](https://www.openstreetmap.org/copyright),
via HeiGIT's [ohsome API](https://ohsome.org/copyrights), licensed under the
[Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/).

**Attribution required wherever this data (or anything derived from it) is
published:** `© OpenStreetMap contributors`

The area-of-interest polygon (`aoi/tel_aviv_yafo_v1.geojson`) is OpenStreetMap
relation [1382494](https://www.openstreetmap.org/relation/1382494) (Tel
Aviv-Yafo municipal boundary), itself a community-maintained copy of an
Israel Ministry of Interior boundary (per the relation's own `source` /
`source:date` tags) -- retrieved via the Nominatim lookup API on 2026-08-20.
Same ODbL/attribution terms apply.

## Setup

```bash
cp .env.example .env   # then fill in real values -- never commit .env
make install            # creates .venv, installs pinned deps
make up                  # Airflow (LocalExecutor) + Postgres/PostGIS + MinIO
make migrate             # applies sql/*.sql to the `gis` database
```

- Airflow UI: http://localhost:8080 (`_AIRFLOW_WWW_USER_USERNAME` / `_PASSWORD` from `.env`)
- MinIO console: http://localhost:9001 (`MINIO_ROOT_USER` / `_PASSWORD` from `.env`)

Trigger the `ingest_osm_building_snapshots` DAG manually from the UI (or
`airflow dags trigger ingest_osm_building_snapshots`) -- it's not scheduled;
see the DAG's docstring for why.

## Tests

```bash
make test              # fast, offline (fixtures/mocks only)
make test-db            # needs `make up && make migrate` (real local Postgres)
make test-integration    # hits the real ohsome API over the network
```

## Known limitations / things to verify on first real run

This project's ingestion code and tests were built and validated inside a
sandboxed dev environment without Docker access, so the full stack has not
been run end-to-end yet. Specifically still to verify on your machine:

1. **`docker compose up` itself** -- the compose file, Airflow 3.3.1 service
   topology (LocalExecutor, no Celery/Redis per project scope), and the two
   Airflow Connections (`minio_default`, `gis_postgres_default`) created by
   `airflow-init` have not been run for real.
2. **ohsome's `/elements/geometry` endpoint** -- confirmed working for
   `/metadata`, `/elements/count`, and `/elements/bbox` from the sandbox's
   network, but `/elements/geometry` (the endpoint this project actually
   uses, for real footprint geometry) and `/elements/centroid` returned
   HTTP 403 from that specific network -- most likely a WAF/anti-abuse rule
   on a shared sandbox egress IP, not a real API restriction. Worth a quick
   manual check (`make test-integration`, or a direct `curl`) before relying
   on it in a scheduled run.
3. **ohsome's tag-property response shape** -- `src/ingestion/snapshot.py`
   assumes `properties=tags` flattens OSM tags directly into each feature's
   `properties` object (alongside `@osmId`/`@snapshotTimestamp`), based on
   ohsome's documented conventions. This wasn't confirmed against a live
   `/elements/geometry` response (blocked, see above) -- only against
   `/elements/bbox`, which didn't have tags requested. Worth confirming on
   first real run and adjusting `normalize_feature()` if the actual shape
   differs.
4. **AOI boundary clipping semantics** -- whether ohsome's `bpolys` clips
   returned geometries to the boundary or only filters by intersection is
   still unconfirmed (needs a real `/elements/geometry` call near the AOI
   edge). This defines our actual behavior for the "features clipped by the
   AOI boundary" test case CLAUDE.md's testing section calls for.
5. **Snapshot dates**: ohsome's underlying data extent currently reaches
   only `2026-07-27T09:00Z` (confirmed via `GET /v1/metadata`), so the
   default `requested_times` are `2025-07-01` / `2026-06-01` / `2026-07-01`,
   not the `2025-08-01` / `2026-07-01` / `2026-08-01` originally discussed --
   shifted back one month to stay inside real coverage, same spacing.
