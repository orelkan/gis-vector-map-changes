"""Geometry validation and repair.

Per CLAUDE.md's geospatial correctness rules: never silently repair or
discard invalid geometries. Every feature's original validity, repair
method (if any), and outcome must be recorded, and the original geometry
preserved separately from the repaired one.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

REPAIR_METHOD_MAKE_VALID = "make_valid"


@dataclass(frozen=True)
class ValidationResult:
    geometry: BaseGeometry  # geometry to use downstream (repaired, if repair was needed)
    original_geometry: BaseGeometry  # always preserved, untouched
    original_valid: bool
    repair_method: str | None
    repaired_valid: bool


def validate_and_repair(geometry: BaseGeometry) -> ValidationResult:
    """Check validity; if invalid, repair via shapely's make_valid.

    make_valid can change topology (e.g. a self-intersecting polygon may
    become a MultiPolygon) -- callers that need a specific geometry type
    downstream must check repaired_valid and the resulting geometry's type
    themselves rather than assuming repair always yields the same shape
    class.
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
    return ValidationResult(
        geometry=repaired,
        original_geometry=geometry,
        original_valid=False,
        repair_method=REPAIR_METHOD_MAKE_VALID,
        repaired_valid=repaired.is_valid,
    )
