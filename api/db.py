"""Database connection handling for the API.

Reads the same GIS_DB_* environment variables the rest of the project uses
(see .env.example) -- no new credentials are introduced for the web layer.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

_POOL: ConnectionPool | None = None


def _conninfo() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.environ.get("GIS_DB_HOST", "postgres"),
        port=int(os.environ.get("GIS_DB_PORT", "5432")),
        dbname=os.environ.get("GIS_DB_NAME", "gis"),
        user=os.environ.get("GIS_DB_USER", "gis"),
        password=os.environ.get("GIS_DB_PASSWORD", "gis"),
    )


def get_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(_conninfo(), min_size=1, max_size=8, open=True)
    return _POOL


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A pooled read connection. The API never writes -- publishing is
    Airflow's job -- so every caller gets a rolled-back, read-only unit of
    work rather than an implicit commit.
    """
    with get_pool().connection() as conn:
        conn.read_only = True
        yield conn
