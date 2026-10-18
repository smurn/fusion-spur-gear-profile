"""The pair rule for two touching gears (TRN-6)."""

import math


def mesh_axis(direction: float, mate_axis: float, mate_teeth: int, teeth: int) -> float:
    """TRN-6: angle of the axis of one of this gear's teeth, given one of the mate's.

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
