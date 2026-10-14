"""Meshing with another gear (DER-10, DER-11, VAL-16, VAL-18)."""

import math
import typing

from .derived import inv, tooth_count
from .params import GearParams
from .validation import ERROR, WARNING, Issue


def ideal_center_distance(module: float, pressure_angle: float, z1: int, z2: int,
                          x1: float, x2: float) -> typing.Optional[float]:
    """DER-10: the center distance at which two gears mesh without backlash.
    None if the profile shifts are so negative that no such distance exists."""
    target = inv(pressure_angle) + 2 * math.tan(pressure_angle) * (x1 + x2) / (z1 + z2)
    if target <= 0:
        return None
    lo, hi = 0.0, math.pi / 2 - 1e-9   # inv rises monotonically from 0 on this interval
    if inv(hi) < target:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if inv(mid) < target else (lo, mid)
    working = (lo + hi) / 2
    return module * (z1 + z2) / 2 * math.cos(pressure_angle) / math.cos(working)


def mesh_axis(direction: float, mate_axis: float, mate_teeth: int, teeth: int) -> float:
    """DER-11: angle of this gear's tooth 0 axis, in the mate's plane.

    direction: angle from the mate's center to this gear's center.
    mate_axis: angle of the axis of one of the mate's teeth.
    A tooth of one gear on the line of centers faces a gap of the other."""
    mate_pitch, pitch = 2 * math.pi / mate_teeth, 2 * math.pi / teeth
    u = ((direction - mate_axis) / mate_pitch) % 1.0
    return direction + math.pi - (0.5 - u) * pitch


def rotation_for_axis(angle: float, teeth: int) -> float:
    """Start rotation p (fraction of a pitch, GEO-9) that puts a tooth axis at the
    given angle from the reference direction."""
    p = (angle / (2 * math.pi / teeth)) % 1.0
    return 0.0 if p > 1 - 1e-12 else p


def mesh_issues(p: GearParams, mate: GearParams, distance: float) -> typing.List[Issue]:
    """VAL-16 and VAL-18 for a gear and its mate at the given center distance (mm)."""
    issues = []
    if not math.isclose(p.module, mate.module, rel_tol=1e-9):
        issues.append(Issue('VAL-16', ERROR, 'The module differs from that of the gear to mesh '
                            'with ({:g} mm).'.format(mate.module)))
    if not math.isclose(p.pressure_angle, mate.pressure_angle, rel_tol=1e-9):
        issues.append(Issue('VAL-16', ERROR, 'The pressure angle differs from that of the gear to '
                            'mesh with ({:g} deg).'.format(math.degrees(mate.pressure_angle))))
    if issues:
        return issues
    ideal = ideal_center_distance(p.module, p.pressure_angle, tooth_count(p), tooth_count(mate),
                                  p.profile_shift, mate.profile_shift)
    if ideal is None:
        issues.append(Issue('VAL-18', WARNING, 'These profile shifts give no center distance at '
                            'which the gears mesh.'))
    elif abs(distance - ideal) > 0.01 * p.module:
        issues.append(Issue('VAL-18', WARNING, 'The center distance is {:.3f} mm; the gears mesh '
                            'at {:.3f} mm.'.format(distance, ideal)))
    return issues
