# GIS Vector Map Changes

Educational vector-GIS data platform for detecting and explaining changes
between dated map snapshots of Tel Aviv-Yafo. See `CLAUDE.md` for full
project scope, working agreement, and architecture rules.

## Milestones

**1. Ingestion** (`dags/ingest_osm_building_snapshots.py`, `src/ingestion/`):
fetches dated Tel Aviv-Yafo building snapshots from OpenStreetMap (via the
[ohsome API](https://docs.ohsome.org/ohsome-api/v1/)), validates and
normalizes them, and persists them durably (MinIO object storage + Postgres
metadata). Seven snapshots are currently ingested, annually from 2021-07-01
plus 2026-06-01 and 2026-07-01.

**2. Matching & classification** (`dags/build_changesets.py`,
`src/matching/`): compares pairs of snapshots and classifies every building
as `added`/`removed`/`modified_geometry`/`modified_attributes`/
`modified_geometry_and_attributes`/`unchanged`/`ambiguous`. Behavior was
specified *before* implementation, per CLAUDE.md's requirement -- see
[docs/matching-spec.md](docs/matching-spec.md), which derives every
threshold from measurement of the real ingested snapshots and records the
expected output as an acceptance test.

**3. Web UI** (`web/`, `api/`, `dags/publish_to_postgis.py`): a React +
TypeScript viewer whose MapLibre map is driven by vector tiles generated in
PostGIS (`ST_AsMVT`). Click a building to see what changed and how, filter
by change type, switch between computed intervals (1 month / 1 year /
5 years), and view any building's full history across all snapshots.

See [docs/architecture.md](docs/architecture.md) for accepted architecture
and the rationale behind key decisions (including why per-interval change
storage does **not** grow quadratically), and
[docs/progress.md](docs/progress.md) for current status and verification
results actually run against the live stack.

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

Trigger `ingest_osm_building_snapshots` first (neither DAG is scheduled --
see each DAG's docstring for why), then `build_changesets` once those
snapshots exist:

```bash
airflow dags trigger ingest_osm_building_snapshots
airflow dags trigger build_changesets     # needs the snapshots above
airflow dags trigger publish_to_postgis   # needs both of the above
```

Then start the web UI (the API runs in the stack; the UI runs on the host
for fast HMR):

```bash
make web-install   # once
make web           # http://localhost:5173
```

## Tests

```bash
make test              # fast, offline (fixtures/mocks only)
make test-db            # needs `make up && make migrate` (real local Postgres)
make test-integration    # hits the real ohsome API over the network
make test-web            # frontend (vitest + React Testing Library)
```

## Status and verification

All three milestones above are implemented and have been run for real
against the live Docker stack, not just designed against docs. Detailed
verification results (real run counts, cross-checks, idempotency checks,
and the one thing that isn't verifiable headlessly) are tracked in
[docs/progress.md](docs/progress.md), which is kept current as the project
evolves rather than duplicated here.
