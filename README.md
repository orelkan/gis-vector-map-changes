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
make up                  # builds the Airflow image (Dockerfile) + brings up
                          # Airflow (LocalExecutor) + Postgres/PostGIS + MinIO
make migrate             # applies sql/*.sql to the `gis` database
```

Needs a `docker` group membership (`sudo usermod -aG docker "$USER"`, then a
fresh login) and Docker Compose v2 (`docker compose ...`, not the old
standalone `docker-compose` v1 binary -- v1 predates the
`service_completed_successfully` `depends_on` condition this compose file
relies on for `airflow-init` sequencing).

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

## Verified end-to-end (2026-08-20)

The full stack has been run for real (Docker, not just designed against
docs) and the four things flagged as unverified in earlier drafts of this
README are now resolved:

1. **`docker compose up` works** -- with one fix beyond what's described
   above: the stock `apache/airflow:3.3.1` image doesn't include this
   project's business-logic dependencies (geopandas/shapely/pyproj/
   requests/psycopg), so `x-airflow-common` now builds a local `Dockerfile`
   that extends the official image with them, rather than using the bare
   image directly. `_PIP_ADDITIONAL_REQUIREMENTS` was deliberately not used
   for this -- Airflow's own docs describe it as "ONLY for quick checks."
2. **ohsome's `POST /elements/geometry` is genuinely blocked (HTTP 403),
   confirmed from two independent real networks**, not a sandbox-specific
   fluke -- same for `/elements/centroid`. `/elements/bbox`,
   `/elements/count`, and `/elementsFullHistory/geometry` all work fine.
   No public explanation was found. The fix: `src/ingestion/ohsome_client.py`
   now queries `POST /elementsFullHistory/geometry` with a minimal
   (1-second) time *range* starting at the target instant; ohsome clips
   each returned version's `@validFrom`/`@validTo` to the query bounds, so
   filtering the response to `@validFrom == <requested instant>` (done in
   `src/ingestion/snapshot.py`) reconstructs the same point-in-time result
   the blocked endpoint would have given. Cross-checked live against
   `/elements/count` for the same instant/bbox -- feature counts matched
   exactly.
3. **ohsome's tag shape, confirmed**: `properties=tags` flattens OSM tags
   directly into each feature's `properties` object, alongside `@`-prefixed
   metadata (`@osmId`, `@validFrom`, `@validTo`) -- exactly what
   `normalize_feature()` assumed.
4. **AOI boundary clipping, confirmed**: ohsome's `bpolys` *clips*
   geometries to the AOI polygon, not just filters by intersection --
   verified by downloading a real snapshot and checking every feature that
   isn't fully `.contains()`-ed by the AOI polygon: the area outside the
   AOI is on the order of 1e-11 to 1e-14 square degrees (floating-point
   boundary noise, not real overhang) for all such features.

A real end-to-end run against Tel Aviv-Yafo produced (feature counts /
invalid-then-repaired geometries out of that count):

| requested_time | feature_count | invalid_geometry_count |
|---|---|---|
| 2025-07-01 | 27013 | 3 |
| 2026-06-01 | 26996 | 4 |
| 2026-07-01 | 26982 | 4 |

Idempotency was also verified for real: re-triggering the DAG with the same
`requested_times` left the `snapshots` table at 3 rows (no duplicates).

Snapshot dates default to `2025-07-01` / `2026-06-01` / `2026-07-01`, not
the `2025-08-01` / `2026-07-01` / `2026-08-01` originally discussed --
shifted back one month after `GET /v1/metadata` showed ohsome's data extent
only reaches `2026-07-27T09:00Z`, keeping the same 1-month/1-year spacing.
