"""Orchestrates one full changeset run from two already-fetched snapshots:
validates they're comparable, loads features, runs the matching pipeline,
renders the change layer, and summarizes counts.

Deliberately I/O-free (CLAUDE.md: business logic testable without Airflow)
-- callers (the DAG task) fetch the snapshot rows and their processed
GeoJSON, pass them in here, and persist whatever comes back. See
src.ingestion.snapshot for the same fetch/business-logic split used there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

from src.matching.changeset import ChangeRecord, build_changeset
from src.matching.config import ALGORITHM_VERSION, METRIC_CRS
from src.matching.features import load_features
from src.matching.render import render_change_layer

_TO_METRIC_CRS = Transformer.from_crs("OGC:CRS84", METRIC_CRS, always_xy=True)

_COMPARABLE_FIELDS = ("source", "layer", "aoi_id", "aoi_version", "source_query_version")

CLASSIFICATIONS = (
    "unchanged",
    "modified_geometry",
    "modified_attributes",
    "modified_geometry_and_attributes",
    "added",
    "removed",
    "ambiguous",
)


@dataclass(frozen=True)
class SnapshotRef:
    """The subset of a `snapshots` table row this pipeline needs -- callers
    build one of these from whatever DB row shape they fetched with.
    """

    id: int
    source: str
    layer: str
    aoi_id: str
    aoi_version: str
    source_query_version: str
    requested_time: datetime


@dataclass(frozen=True)
class ChangesetResult:
    algorithm_version: str
    records: list[ChangeRecord]
    counts: dict[str, int]  # one entry per CLASSIFICATIONS value
    change_layer_geojson: dict[str, Any]


def validate_comparable(snapshot_a: SnapshotRef, snapshot_b: SnapshotRef) -> None:
    """Docs/matching-behavior.md section 2: both snapshots must share
    source, layer, aoi_id, aoi_version, and source_query_version. This is
    what makes AOI-boundary clipping safe to compare (section 6g) -- a hard
    error, not a warning, since comparing across a changed AOI or
    extraction definition would silently misattribute clipping artifacts
    (or a changed repair strategy, see the v1->v2 fix) as real change.
    """
    mismatches = [f for f in _COMPARABLE_FIELDS if getattr(snapshot_a, f) != getattr(snapshot_b, f)]
    if mismatches:
        raise ValueError(
            f"snapshots are not comparable -- differ in {mismatches}: "
            f"a=(id={snapshot_a.id}, {[(f, getattr(snapshot_a, f)) for f in mismatches]}) "
            f"b=(id={snapshot_b.id}, {[(f, getattr(snapshot_b, f)) for f in mismatches]})"
        )


def _aoi_boundary_in_metric_crs(aoi_geometry: dict[str, Any] | None):
    if aoi_geometry is None:
        return None
    return shapely_transform(_TO_METRIC_CRS.transform, shape(aoi_geometry)).boundary


def build_changeset_result(
    snapshot_a: SnapshotRef,
    snapshot_b: SnapshotRef,
    processed_geojson_a: dict[str, Any],
    processed_geojson_b: dict[str, Any],
    aoi_geometry: dict[str, Any] | None = None,
) -> ChangesetResult:
    """Runs the full pipeline: validate -> load -> match -> render -> summarize."""
    validate_comparable(snapshot_a, snapshot_b)

    features_a = load_features(processed_geojson_a)
    features_b = load_features(processed_geojson_b)
    aoi_boundary = _aoi_boundary_in_metric_crs(aoi_geometry)

    records = build_changeset(features_a, features_b, aoi_boundary=aoi_boundary)

    counts = dict.fromkeys(CLASSIFICATIONS, 0)
    for record in records:
        counts[record.classification] += 1

    change_layer_geojson = render_change_layer(records, features_a, features_b)

    return ChangesetResult(
        algorithm_version=ALGORITHM_VERSION,
        records=records,
        counts=counts,
        change_layer_geojson=change_layer_geojson,
    )
