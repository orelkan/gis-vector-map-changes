# GIS Vector Map Changes

## Project purpose

GIS Vector Map Changes is an educational vector-GIS data platform for detecting
and explaining changes between dated map snapshots of Tel Aviv-Yafo.

Use **GIS Vector Map Changes** as the project name in documentation, prompts,
reports, UI text, and explanatory material. Use `gis-vector-map-changes` when a
lowercase repository or package slug is needed. Do not introduce an alternative
brand name or abbreviation unless explicitly requested.

The first complete vertical slice compares two Overture Maps building extracts
for the same area and produces:

- added buildings;
- removed buildings;
- modified buildings;
- unchanged buildings;
- ambiguous matches requiring review;
- summary statistics and GeoJSON change layers.

Later milestones may add road-network changes, topology validation, multiple
data sources, canonical feature identities, vector tiles, and a web map. Do not
implement later milestones unless explicitly requested.

## Learning goals

This project exists primarily to learn and practise:

- Apache Airflow 3.x DAG and task design;
- scheduling, data intervals, backfills, retries, and observability;
- asset-based dependencies and dynamic task mapping;
- idempotent and reproducible geospatial pipelines;
- Python vector-GIS processing;
- PostGIS data modelling and spatial queries;
- testing geospatial algorithms and Airflow DAGs;
- effective pair programming with Claude Code.

## Working agreement

- Act as a senior Airflow and vector-GIS engineer who is also a mentor.
- Explain important Airflow and GIS decisions before implementing them.
- Work on one approved milestone at a time.
- Do not build the entire project from a broad request.
- For substantial changes, inspect the repository and propose a plan first.
- Identify decisions that I should make instead of silently choosing everything.
- Prefer a small working vertical slice over speculative abstractions.
- When I am learning a concept, give me a focused exercise and let me attempt it
  before providing the full implementation.
- Review my code concretely: describe the failure scenario, not only the style
  preference.
- Never suppress, weaken, or delete a failing check merely to make CI green.
- Do not introduce infrastructure without explaining the immediate benefit.

## Initial scope

### Geographic scope

- Tel Aviv-Yafo, Israel.
- Store the authoritative area of interest as a versioned GeoJSON polygon.
- Do not treat a casually typed bounding box as the permanent AOI.
- All input snapshots must be clipped or filtered to the same AOI before
  comparison.

### Data scope

- Start with Overture Maps building footprints.
- A snapshot is immutable and identified by source, source release, layer, AOI,
  and ingestion time.
- Preserve source identifiers and source attributes.
- Preserve raw input or enough provenance to reproduce every processed record.

### MVP output

Given snapshots A and B, generate a versioned change set containing:

- `added`;
- `removed`;
- `modified_geometry`;
- `modified_attributes`;
- `modified_geometry_and_attributes`;
- `unchanged`;
- `ambiguous`.

Each matched or ambiguous record must include the relevant source identifiers,
the algorithm version, match score, classification reason, and useful geometry
comparison metrics.

## Intended technical stack

- Python, using a currently supported version for the selected Airflow release;
- Apache Airflow 3.x with the TaskFlow API;
- Docker Compose for local development;
- PostgreSQL with PostGIS;
- GeoPandas, Shapely, PyProj, GDAL-compatible tooling, and SQLAlchemy or psycopg;
- pytest;
- Ruff;
- mypy only if it adds useful feedback without dominating the learning project.

Pin important dependency versions. Verify Airflow and provider compatibility
against official documentation before selecting versions.

## Architecture rules

- DAG files describe orchestration, dependencies, schedules, and operational
  policy. They must not contain substantial geospatial business logic.
- Put reusable domain logic in importable modules under `src/`.
- Keep network access, storage access, normalization, matching,
  classification, and publication behind explicit interfaces or functions.
- Business-logic functions should be runnable and testable without Airflow.
- Avoid expensive I/O, database connections, downloads, and substantial
  computation during DAG parsing.
- Tasks exchange references and small metadata, not GeoDataFrames, GeoJSON
  documents, or large lists through XCom.
- Store large intermediate datasets in durable storage and pass their URI,
  snapshot ID, partition ID, or database key.
- Prefer explicit data contracts between pipeline stages.
- All outputs must record input snapshot IDs and algorithm version.

## Airflow rules

- Use Airflow logical dates and data intervals where temporal partitioning is
  relevant; do not derive partitions from `datetime.now()`.
- Make every task safe to retry.
- Make scheduled and backfilled runs deterministic where the source permits it.
- Set retries only for plausibly transient failures.
- Use timeouts for network and long-running operations.
- Do not use Airflow Variables as a general application database.
- Store credentials in Airflow Connections or environment-backed secrets, never
  in source control.
- Use Params for validated per-run choices such as source releases, AOI, or
  comparison mode when appropriate.
- Explain catchup and backfill consequences before enabling them.
- Use dynamic task mapping only when the runtime fan-out is data-dependent and
  task-level visibility or retry isolation is valuable.
- Avoid generating an unbounded number of mapped tasks. Partition deliberately.
- Use Assets when they express real dataset readiness between independently
  operated DAGs; do not split one workflow into many DAGs only to demonstrate
  Assets.

## Geospatial correctness rules

- Never calculate metric distance or area directly in EPSG:4326.
- Keep source geometries in their original CRS when useful, but transform to an
  explicitly selected local projected CRS for metric comparison.
- Record CRS metadata at dataset boundaries and assert compatible CRSs before
  spatial operations.
- Validate geometries and report invalid input rates.
- Do not silently repair or discard geometries. Record repair method, original
  validity, and outcome.
- Use spatial indexes or spatial candidate generation before pairwise geometry
  comparison. Avoid unconstrained all-to-all matching.
- Define boundary semantics explicitly for predicates such as intersects,
  touches, within, and contains.
- Treat numerical tolerances as named, documented configuration with tests.
- Preserve original geometries separately from normalized or repaired
  geometries.
- Make deterministic output ordering part of exported artifacts and tests.

## Change matching principles

Use source IDs as strong evidence when they are stable, but do not assume IDs
alone fully express real-world identity.

The initial matching pipeline should be explainable:

1. normalize and validate both snapshots;
2. generate spatially plausible candidate pairs;
3. calculate geometry and attribute similarity metrics;
4. resolve clear one-to-one matches;
5. identify additions and removals;
6. classify matched changes;
7. preserve ambiguous one-to-many and many-to-one cases for review.

Do not hide ambiguous matches by arbitrarily selecting the highest score.
Possible metrics include intersection-over-union, overlap ratios, centroid
distance, area change, Hausdorff distance, and selected attribute similarity.
Every metric and threshold must have a documented interpretation.

Before implementing matching, define expected behavior for:

- stable IDs with changed geometry;
- different IDs with nearly identical geometry;
- one old building split into several new buildings;
- several old buildings merged into one;
- small coordinate shifts;
- geometry repairs that alter comparison metrics;
- features clipped by the AOI boundary.

## Idempotency and versioning

- Treat source snapshots as immutable.
- Use stable natural or generated keys for snapshots, partitions, change sets,
  and algorithm versions.
- Enforce uniqueness in the database rather than relying only on application
  checks.
- Rerunning the same inputs with the same algorithm version must not create
  duplicate logical results.
- If output is replaced, do so atomically where practical.
- A new matching algorithm or threshold configuration creates a new versioned
  result rather than silently rewriting history.

## Testing expectations

Maintain a small, hand-authored geospatial fixture set that covers:

- unchanged polygon;
- added and removed polygons;
- small geometry modification;
- large geometry modification;
- attribute-only modification;
- invalid polygon;
- polygon with a hole;
- multipolygon;
- split case;
- merge case;
- AOI boundary case;
- no-candidate case;
- equally plausible ambiguous candidates.

Tests should cover:

- pure geometry metrics;
- candidate generation;
- match resolution and classification;
- CRS failures;
- idempotent database loading;
- DAG import/parsing;
- task dependency structure;
- representative failure and retry behavior.

Avoid tests that assert only row counts. Assert source IDs, classifications,
reasons, match scores or ranges, and geometries where appropriate.

## Commands and validation

- Prefer project-standard commands exposed through a `Makefile` or equivalent.
- After changing Python code, run the smallest relevant tests first, followed by
  the full test and lint suites when practical.
- After changing DAGs, run DAG import/parsing validation in addition to unit
  tests.
- After changing SQL migrations or PostGIS logic, test against the actual local
  database rather than relying exclusively on mocks.
- Report the exact checks run and any remaining failures.

## Security and repository hygiene

- Never commit secrets, API keys, passwords, connection URIs, or private data.
- Provide `.env.example` with placeholders only.
- Do not print secrets in commands, logs, examples, or test output.
- Do not commit large downloaded map snapshots or generated outputs unless a
  deliberately tiny fixture is required for tests.
- Record dataset attribution and licensing requirements in the README.

## Scope control

Unless explicitly requested, do not add:

- Kubernetes;
- CeleryExecutor or distributed workers;
- Spark;
- Kafka;
- dbt;
- a production cloud deployment;
- machine-learning-based matching;
- a complex frontend;
- road-network processing before the building MVP works end to end.

When suggesting one of these, explain which existing limitation it solves and
what additional operational burden it introduces.
