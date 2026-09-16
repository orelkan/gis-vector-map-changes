"""Orchestrates the full matching pipeline: Stage 1 ID matching, Stage 2
spatial candidates for the remainder, Stage 3 scoring, Stage 4 resolution,
Stage 5 classification. See docs/matching-behavior.md section 4 for the
full specification this implements.

Deliberately Airflow-independent and I/O-free: callers load features via
src.matching.features and pass the resulting dicts in directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shapely.geometry.base import BaseGeometry

from src.matching.candidates import generate_candidates
from src.matching.config import AOI_BOUNDARY_DISTANCE_M, T_CROSS_ID_MATCH, T_UNCHANGED_IOU
from src.matching.features import LoadedFeature
from src.matching.metrics import MatchMetrics, compute_metrics

Classification = Literal[
    "unchanged",
    "modified_geometry",
    "modified_attributes",
    "modified_geometry_and_attributes",
    "added",
    "removed",
    "ambiguous",
]


@dataclass(frozen=True)
class ChangeRecord:
    classification: Classification
    match_method: str | None  # "osm_id" | "geometry" | None
    match_score: float | None  # iou, only set for a resolved 1:1 match
    osm_ids_a: tuple[str, ...]  # empty for `added`
    osm_ids_b: tuple[str, ...]  # empty for `removed`
    classification_reason: str
    # Every candidate pair actually considered for this record, keyed by
    # (osm_id_a, osm_id_b). Exactly one entry for a resolved match; several
    # for a split/merge/complex ambiguous group; empty for added/removed.
    # Per CLAUDE.md, ambiguous records keep every candidate's score rather
    # than silently picking the highest.
    pair_metrics: dict[tuple[str, str], MatchMetrics]
    involves_repaired_geometry: bool
    touches_aoi_boundary: bool


def _involves_repaired(feats: list[LoadedFeature]) -> bool:
    return any(f.repaired for f in feats)


def _touches_aoi_boundary(feats: list[LoadedFeature], aoi_boundary: BaseGeometry | None) -> bool:
    if aoi_boundary is None:
        return False
    return any(f.geometry.distance(aoi_boundary) < AOI_BOUNDARY_DISTANCE_M for f in feats)


def _classify_matched(
    *,
    osm_id_a: str,
    osm_id_b: str,
    match_method: str,
    metrics: MatchMetrics,
    feature_a: LoadedFeature,
    feature_b: LoadedFeature,
    aoi_boundary: BaseGeometry | None,
) -> ChangeRecord:
    """Stage 5: classify a resolved 1:1 match (ID- or geometry-matched)."""
    geometry_changed = metrics.iou < T_UNCHANGED_IOU
    attrs_changed = bool(metrics.attrs_changed)

    if geometry_changed and attrs_changed:
        classification: Classification = "modified_geometry_and_attributes"
    elif geometry_changed:
        classification = "modified_geometry"
    elif attrs_changed:
        classification = "modified_attributes"
    else:
        classification = "unchanged"

    return ChangeRecord(
        classification=classification,
        match_method=match_method,
        match_score=metrics.iou,
        osm_ids_a=(osm_id_a,),
        osm_ids_b=(osm_id_b,),
        classification_reason=f"{match_method}_match_{classification}",
        pair_metrics={(osm_id_a, osm_id_b): metrics},
        involves_repaired_geometry=_involves_repaired([feature_a, feature_b]),
        touches_aoi_boundary=_touches_aoi_boundary([feature_a, feature_b], aoi_boundary),
    )


def _ambiguous(
    a_ids: frozenset[str],
    b_ids: frozenset[str],
    pair_metrics: dict[tuple[str, str], MatchMetrics],
    reason: str,
    feats: list[LoadedFeature],
    aoi_boundary: BaseGeometry | None,
) -> ChangeRecord:
    return ChangeRecord(
        classification="ambiguous",
        match_method=None,
        match_score=None,
        osm_ids_a=tuple(sorted(a_ids)),
        osm_ids_b=tuple(sorted(b_ids)),
        classification_reason=reason,
        pair_metrics=pair_metrics,
        involves_repaired_geometry=_involves_repaired(feats),
        touches_aoi_boundary=_touches_aoi_boundary(feats, aoi_boundary),
    )


def _added_or_removed(
    classification: Literal["added", "removed"],
    feature: LoadedFeature,
    aoi_boundary: BaseGeometry | None,
) -> ChangeRecord:
    return ChangeRecord(
        classification=classification,
        match_method=None,
        match_score=None,
        osm_ids_a=(feature.osm_id,) if classification == "removed" else (),
        osm_ids_b=(feature.osm_id,) if classification == "added" else (),
        classification_reason="no_spatial_counterpart",
        pair_metrics={},
        involves_repaired_geometry=_involves_repaired([feature]),
        touches_aoi_boundary=_touches_aoi_boundary([feature], aoi_boundary),
    )


def _connected_components(
    candidates: dict[str, list[str]],
) -> list[tuple[frozenset[str], frozenset[str]]]:
    """Groups the bipartite candidate graph into connected components.

    A component of shape (1,1) is a plain 1:1 candidate pair; (1,N) is a
    split candidate; (N,1) a merge candidate; (N,M), N,M>1 a "complex
    cluster" -- CLAUDE.md names split/merge explicitly but a general
    bipartite graph can produce larger tangles (e.g. two old buildings each
    overlapping two new ones), and those are no less ambiguous.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    a_side: set[str] = set()
    b_side: set[str] = set()
    for a_id, b_ids in candidates.items():
        a_side.add(a_id)
        parent.setdefault(a_id, a_id)
        for b_id in b_ids:
            b_side.add(b_id)
            parent.setdefault(b_id, b_id)
            union(a_id, b_id)

    groups: dict[str, set[str]] = {}
    for node in parent:
        groups.setdefault(find(node), set()).add(node)

    return [
        (frozenset(m for m in members if m in a_side), frozenset(m for m in members if m in b_side))
        for members in groups.values()
    ]


def build_changeset(
    features_a: dict[str, LoadedFeature],
    features_b: dict[str, LoadedFeature],
    aoi_boundary: BaseGeometry | None = None,
) -> list[ChangeRecord]:
    """Runs the full 5-stage pipeline and returns one ChangeRecord per
    feature involved -- every feature in A and B appears in exactly one
    record. Output is deterministically ordered.

    `aoi_boundary`, if given, is the AOI polygon's boundary in the same CRS
    as the loaded features (METRIC_CRS) -- used only to set
    touches_aoi_boundary; omit it and that flag is always False.
    """
    records: list[ChangeRecord] = []

    # Stage 1: ID matching.
    shared_ids = set(features_a) & set(features_b)
    only_in_a = {k: v for k, v in features_a.items() if k not in shared_ids}
    only_in_b = {k: v for k, v in features_b.items() if k not in shared_ids}

    for osm_id in shared_ids:
        a, b = features_a[osm_id], features_b[osm_id]
        metrics = compute_metrics(a, b)
        records.append(
            _classify_matched(
                osm_id_a=osm_id,
                osm_id_b=osm_id,
                match_method="osm_id",
                metrics=metrics,
                feature_a=a,
                feature_b=b,
                aoi_boundary=aoi_boundary,
            )
        )

    # Stage 2: spatial candidates for the remainder only.
    candidates = generate_candidates(only_in_a, only_in_b)
    groups = _connected_components(candidates)

    matched_a: set[str] = set()
    matched_b: set[str] = set()

    for a_ids, b_ids in groups:
        pair_metrics = {
            (a_id, b_id): compute_metrics(only_in_a[a_id], only_in_b[b_id])
            for a_id in a_ids
            for b_id in b_ids
            if b_id in candidates.get(a_id, [])
        }
        matched_a.update(a_ids)
        matched_b.update(b_ids)
        feats = [only_in_a[a_id] for a_id in a_ids] + [only_in_b[b_id] for b_id in b_ids]

        # Stage 4: resolve.
        if len(a_ids) == 1 and len(b_ids) == 1:
            (a_id,), (b_id,) = a_ids, b_ids
            metrics = pair_metrics[(a_id, b_id)]
            if metrics.iou >= T_CROSS_ID_MATCH:
                records.append(
                    _classify_matched(
                        osm_id_a=a_id,
                        osm_id_b=b_id,
                        match_method="geometry",
                        metrics=metrics,
                        feature_a=only_in_a[a_id],
                        feature_b=only_in_b[b_id],
                        aoi_boundary=aoi_boundary,
                    )
                )
            else:
                records.append(
                    _ambiguous(a_ids, b_ids, pair_metrics, "partial_overlap", feats, aoi_boundary)
                )
        else:
            if len(a_ids) == 1:
                reason = "split_candidate"
            elif len(b_ids) == 1:
                reason = "merge_candidate"
            else:
                reason = "complex_cluster"
            records.append(_ambiguous(a_ids, b_ids, pair_metrics, reason, feats, aoi_boundary))

    # Whatever's left had no spatial candidate at all.
    for a_id in set(only_in_a) - matched_a:
        records.append(_added_or_removed("removed", only_in_a[a_id], aoi_boundary))
    for b_id in set(only_in_b) - matched_b:
        records.append(_added_or_removed("added", only_in_b[b_id], aoi_boundary))

    return sorted(records, key=lambda r: (r.osm_ids_a, r.osm_ids_b))
