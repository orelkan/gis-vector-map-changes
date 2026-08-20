from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ohsome_response_fixture() -> dict:
    """A hand-authored GeoJSON FeatureCollection shaped like a real ohsome
    /elements/geometry response (field names verified against a live
    /elements/bbox call to the same API -- see the plan doc). Covers: a
    valid simple polygon, a polygon with a hole, a self-intersecting
    (invalid) polygon, and a feature with no `building` tag value we
    recognize (falls back to category "other").
    """
    return json.loads((FIXTURES_DIR / "ohsome_response.json").read_text())


@pytest.fixture
def db_connection():
    """A real psycopg connection to the local `gis` database, per
    CLAUDE.md's rule to test SQL against the actual local database rather
    than mocks. Requires `make up` (and `make migrate`) to be running --
    skips (not fails) if it can't connect, so `make test` (which excludes
    the `db` marker) never depends on this.
    """
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(
            host=os.environ.get("GIS_DB_HOST", "localhost"),
            port=int(os.environ.get("GIS_DB_PORT", "5432")),
            dbname=os.environ.get("GIS_DB_NAME", "gis"),
            user=os.environ.get("GIS_DB_USER", "gis"),
            password=os.environ.get("GIS_DB_PASSWORD", "gis"),
            connect_timeout=3,
        )
    except Exception as exc:  # noqa: BLE001 -- any connection failure means "skip"
        pytest.skip(f"no local Postgres available: {exc}")
    yield conn
    conn.close()
