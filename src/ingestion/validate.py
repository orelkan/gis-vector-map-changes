"""Geometry validation and repair.

Per CLAUDE.md's geospatial correctness rules: never silently repair or
discard invalid geometries. Every feature's original validity, repair
method (if any), and outcome must be recorded, and the original geometry
preserved separately from the repaired one.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

REPAIR_METHOD_MAKE_VALID = "make_valid"
REPAIR_METHOD_MAKE_VALID_EXTRACT = "make_valid+extract_polygons"

POLYGONAL_TYPES = ("Polygon", "MultiPolygon")


@dataclass(frozen=True)
class ValidationResult:
    geometry: BaseGeometry  # geometry to use downstream (repaired, if repair was needed)
    original_geometry: BaseGeometry  # always preserved, untouched
    original_valid: bool
    repair_method: str | None
    repaired_valid: bool


def _extract_polygonal(geometry: BaseGeometry) -> BaseGeometry | None:
    """Return the polygonal content of a geometry, or None if there is none.

    make_valid on a self-touching building footprint frequently returns a
    GeometryCollection: the recovered Polygon plus zero-area LineString
    "spikes" along the degenerate edges. Those spikes carry no area, but
    they make the geometry type GeometryCollection, which breaks the
    "snapshots contain Polygon/MultiPolygon" invariant that downstream
    matching (and a PostGIS geometry(MultiPolygon) column) depends on.
    """
    if geometry.geom_type in POLYGONAL_TYPES:
        return geometry
    if geometry.geom_type == "GeometryCollection":
        parts = [part for part in geometry.geoms if part.geom_type in POLYGONAL_TYPES]
        if parts:
            return unary_union(parts)
    return None


def validate_and_repair(geometry: BaseGeometry) -> ValidationResult:
    """Check validity; if invalid, repair via shapely's make_valid, then keep
    only the polygonal content of the repair.

    Repair is never silent: original validity, the repair method used, and
    whether the result ended up valid are all recorded, and the original
    geometry is preserved untouched alongside the repaired one.

    Note that repair can still change topology in ways callers must expect
    (a self-intersecting Polygon may legitimately become a MultiPolygon).
    What it will not do is hand back a non-polygonal type when polygonal
    content exists.
    """
    original_valid = geometry.is_valid
    if original_valid:
        return ValidationResult(
            geometry=geometry,
            original_geometry=geometry,
            original_valid=True,
            repair_method=None,
            repaired_valid=True,
        )

    repaired = make_valid(geometry)
    polygonal = _extract_polygonal(repaired)

    if polygonal is None:
        # Repair produced no polygonal content at all (a fully degenerate
        # footprint). Keep the raw make_valid output rather than inventing
        # a geometry, and let repaired_valid/geom_type tell the caller.
        return ValidationResult(
            geometry=repaired,
            original_geometry=geometry,
            original_valid=False,
            repair_method=REPAIR_METHOD_MAKE_VALID,
            repaired_valid=repaired.is_valid,
        )

    extracted = polygonal.geom_type != repaired.geom_type
    return ValidationResult(
        geometry=polygonal,
        original_geometry=geometry,
        original_valid=False,
        repair_method=(
            REPAIR_METHOD_MAKE_VALID_EXTRACT if extracted else REPAIR_METHOD_MAKE_VALID
        ),
        repaired_valid=polygonal.is_valid,
    )
