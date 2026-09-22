"""FastAPI application: vector tiles generated in PostGIS, plus the JSON
endpoints the web UI needs.

Serving both from one service is deliberate -- a detail API is needed
regardless, so a dedicated tile server would mean two services for no gain
at this data scale (see the milestone plan).

Read-only: publishing is Airflow's job. The API never writes.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from api import queries
from api.db import connection

MVT_CONTENT_TYPE = "application/vnd.mapbox-vector-tile"
MAX_ZOOM = 22
DEFAULT_SOURCE_QUERY_VERSION = os.environ.get("GIS_SOURCE_QUERY_VERSION", "v2")

app = FastAPI(
    title="GIS Vector Map Changes API",
    description=(
        "Vector tiles and change data for dated OpenStreetMap building "
        "snapshots of Tel Aviv-Yafo. Data © OpenStreetMap contributors, ODbL."
    ),
)

# The Vite dev server runs on a different port; in production the UI is
# served from the same origin and this is a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("API_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
# HTTP header values must be latin-1; "©" (0xa9) is not encodable, so the
# header carries an ASCII form while JSON bodies keep the real glyph.
ATTRIBUTION_HEADER = "(c) OpenStreetMap contributors (ODbL)"


def _rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def _one(sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    result = _rows(sql, params)
    return result[0] if result else None


def _validate_tile(z: int, x: int, y: int) -> None:
    """Reject out-of-range tile coordinates with 4xx rather than letting
    PostGIS raise and surface as a 500."""
    if not 0 <= z <= MAX_ZOOM:
        raise HTTPException(400, f"zoom must be between 0 and {MAX_ZOOM}, got {z}")
    limit = 1 << z
    if not (0 <= x < limit and 0 <= y < limit):
        raise HTTPException(400, f"x and y must be within [0, {limit}) at zoom {z}")


def _mvt_response(mvt: bytes | None, cache_key: str) -> Response:
    # An empty tile is a legitimate answer (nothing here), not an error --
    # MapLibre expects 204/empty rather than a 404 for sparse layers.
    return Response(
        content=bytes(mvt) if mvt else b"",
        media_type=MVT_CONTENT_TYPE,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Data-Version": cache_key,
            "X-Attribution": ATTRIBUTION_HEADER,
        },
    )


def _span_label(time_a: datetime, time_b: datetime) -> str:
    """Human label for an interval, e.g. '1 month' / '1 year' / '5 years'."""
    days = (time_b - time_a).days
    years = days / 365.25
    if years >= 0.9:
        n = round(years)
        return f"{n} year{'s' if n != 1 else ''}"
    months = days / 30.44
    if months >= 0.9:
        n = round(months)
        return f"{n} month{'s' if n != 1 else ''}"
    return f"{max(days, 1)} days"


@app.get("/api/health")
def health() -> dict[str, Any]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    return {"status": "ok", "attribution": ATTRIBUTION}


@app.get("/api/snapshots")
def list_snapshots(
    source_query_version: str = DEFAULT_SOURCE_QUERY_VERSION,
) -> list[dict[str, Any]]:
    return _rows(
        queries.LIST_SNAPSHOTS, {"source_query_version": source_query_version}
    )


def _changeset_payload(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["span_label"] = _span_label(row["time_a"], row["time_b"])
    # `unchanged` has no rows in change_features by design; the count comes
    # from the changesets metadata table.
    row["changed_count"] = (
        row["modified_geometry_count"]
        + row["modified_attributes_count"]
        + row["modified_geometry_and_attributes_count"]
        + row["added_count"]
        + row["removed_count"]
        + row["ambiguous_count"]
    )
    return row


@app.get("/api/changesets")
def list_changesets() -> list[dict[str, Any]]:
    return [_changeset_payload(r) for r in _rows(queries.LIST_CHANGESETS)]


@app.get("/api/changesets/{changeset_id}")
def get_changeset(changeset_id: int) -> dict[str, Any]:
    row = _one(queries.GET_CHANGESET, {"changeset_id": changeset_id})
    if row is None:
        raise HTTPException(404, f"no changeset with id {changeset_id}")
    return _changeset_payload(row)


@app.get("/api/changes/{change_feature_id}")
def get_change_feature(change_feature_id: int) -> dict[str, Any]:
    """Full change record including before/after geometry as GeoJSON --
    what the detail panel overlays to show *how* a geometry changed."""
    row = _one(queries.GET_CHANGE_FEATURE, {"change_feature_id": change_feature_id})
    if row is None:
        raise HTTPException(404, f"no change feature with id {change_feature_id}")
    return row


@app.get("/api/features/{snapshot_id}/{osm_id:path}")
def get_snapshot_feature(snapshot_id: int, osm_id: str) -> dict[str, Any]:
    row = _one(
        queries.GET_SNAPSHOT_FEATURE, {"snapshot_id": snapshot_id, "osm_id": osm_id}
    )
    if row is None:
        raise HTTPException(404, f"no feature {osm_id!r} in snapshot {snapshot_id}")
    return row


@app.get("/api/history/{osm_id:path}")
def get_feature_history(
    osm_id: str, source_query_version: str = DEFAULT_SOURCE_QUERY_VERSION
) -> dict[str, Any]:
    """One building across every snapshot held, plus the changesets it
    appears as a change in.

    This is what makes "many different timestamps" answerable: before/after
    is always relative to one interval, but this shows the whole trajectory.
    """
    history = _rows(
        queries.GET_FEATURE_HISTORY,
        {"osm_id": osm_id, "source_query_version": source_query_version},
    )
    if not history:
        raise HTTPException(404, f"no snapshot contains feature {osm_id!r}")
    changes = _rows(queries.GET_FEATURE_CHANGE_PARTICIPATION, {"osm_id": osm_id})
    return {"osm_id": osm_id, "history": history, "changes": changes}


@app.get("/tiles/changes/{changeset_id}/{z}/{x}/{y}.mvt")
def change_tile(
    changeset_id: int,
    z: Annotated[int, Path()],
    x: Annotated[int, Path()],
    y: Annotated[int, Path()],
    classifications: Annotated[str | None, Query()] = None,
) -> Response:
    """The small coloured change layer for one interval."""
    _validate_tile(z, x, y)

    if classifications is None:
        requested = sorted(queries.VALID_CLASSIFICATIONS)
    else:
        requested = [c.strip() for c in classifications.split(",") if c.strip()]
        unknown = set(requested) - queries.VALID_CLASSIFICATIONS
        if unknown:
            raise HTTPException(
                400,
                f"unknown classification(s): {sorted(unknown)}. "
                f"Valid: {sorted(queries.VALID_CLASSIFICATIONS)}. Note that "
                "'unchanged' is derived from absence and never stored.",
            )

    row = _one(
        queries.CHANGE_TILE,
        {
            "changeset_id": changeset_id,
            "z": z,
            "x": x,
            "y": y,
            "classifications": requested,
        },
    )
    return _mvt_response(row["mvt"] if row else None, f"changeset-{changeset_id}")


@app.get("/tiles/buildings/{snapshot_id}/{z}/{x}/{y}.mvt")
def building_tile(
    snapshot_id: int,
    z: Annotated[int, Path()],
    x: Annotated[int, Path()],
    y: Annotated[int, Path()],
) -> Response:
    """The shared grey context layer: all buildings of one snapshot."""
    _validate_tile(z, x, y)
    # Web Mercator metres per pixel at this zoom, scaled so lower zooms drop
    # proportionally more vertex detail.
    tolerance = 40075016.686 / (256 * (1 << z)) * 2
    row = _one(
        queries.BUILDING_TILE,
        {"snapshot_id": snapshot_id, "z": z, "x": x, "y": y, "tolerance": tolerance},
    )
    return _mvt_response(row["mvt"] if row else None, f"snapshot-{snapshot_id}")
