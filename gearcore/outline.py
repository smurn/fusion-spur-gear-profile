"""The closed gear outline as exact arcs and fitted splines (ARC-1).

Gear frame: gear center at the origin, +X is the reference direction of GEO-9.
"""

import dataclasses
import math
import typing

from . import spline as spline_mod
from .params import GearError, GearParams
from .profile import ToothProfile
from .spline import Point, Spline
from .validation import errors


@dataclasses.dataclass(frozen=True)
class Arc:
    """Counter-clockwise circular arc about `center`."""
    center: Point
    radius: float
    start_angle: float
    sweep: float

    def _at(self, ang: float) -> Point:
        return (self.center[0] + self.radius * math.cos(ang),
                self.center[1] + self.radius * math.sin(ang))

    @property
    def start(self) -> Point:
        return self._at(self.start_angle)

    @property
    def end(self) -> Point:
        return self._at(self.start_angle + self.sweep)

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        return [self._at(self.start_angle + self.sweep * k / per_span) for k in range(per_span + 1)]


Segment = typing.Union[Arc, Spline]


@dataclasses.dataclass(frozen=True)
class Outline:
    """Closed outline, counter-clockwise. Each segment starts where the previous one ends."""
    segments: typing.Tuple[Segment, ...]
    teeth: int

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        pts = []
        for seg in self.segments:
            pts += seg.sample(per_span)[:-1]
        return pts

    def area(self, per_span: int = 64) -> float:
        pts = self.sample(per_span)
        return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2

    def max_gap(self) -> float:
        """Largest distance between the end of a segment and the start of the next (ACC-3)."""
        segs = self.segments
        return max(math.dist(a.end, b.start) for a, b in zip(segs, segs[1:] + segs[:1]))


def half_tooth_splines(tooth: ToothProfile, tolerance: float):
    """Flank (tip to join) and root curve (join to root circle) of the half-tooth."""
    flank = spline_mod.fit(tooth.involute, tooth.t_tip, tooth.t_join, tolerance,
                           tooth.involute_tangent(tooth.t_tip), tooth.involute_tangent(tooth.t_join))
    # Without undercut the root curve leaves the flank tangentially and meets the
    # root circle tangentially.
    a = tooth.root_angle
    root = spline_mod.fit(tooth.trochoid, tooth.phi_flank, tooth.phi_root, tolerance,
                          tooth.involute_tangent(tooth.t_join), (-math.sin(a), math.cos(a)))
    return flank, root


def gear_outline(p: GearParams) -> Outline:
    """The gear outline for the parameters (GEO-1 to GEO-9, full circle)."""
    problems = errors(p)
    if problems:
        raise GearError('; '.join('{}: {}'.format(i.id, i.message) for i in problems))
    if p.arc_span is not None:
        raise NotImplementedError('arc mode (GEO-10)')
    if p.print_offset != 0:
        raise NotImplementedError('print offset (GEO-7)')
    if p.bore != 0:
        raise NotImplementedError('bore (GEO-11)')
    tooth = ToothProfile(p)
    if tooth.undercut:
        raise NotImplementedError('undercut (GEO-4)')
    if tooth.r_join >= tooth.ra:
        raise GearError('The tip circle lies below the start of the flank: no involute remains.')

    flank, root = half_tooth_splines(tooth, p.tolerance)
    origin = (0.0, 0.0)
    tip, root_ang, tau = tooth.tip_angle, tooth.root_angle, tooth.tau
    segments = []
    for k in range(tooth.teeth):
        axis = (p.rotation + k) * tau   # GEO-9
        # GEO-8: the lower side of the tooth is the mirror image of the upper side.
        segments.append(root.transformed(axis, mirror=True).reversed())
        segments.append(flank.transformed(axis, mirror=True).reversed())
        segments.append(Arc(origin, tooth.ra, axis - tip, 2 * tip))             # GEO-5
        segments.append(flank.transformed(axis))
        segments.append(root.transformed(axis))
        if tooth.phi_root > 0:
            segments.append(Arc(origin, tooth.rf, axis + root_ang, 2 * tooth.phi_root))   # GEO-3
    return Outline(tuple(segments), tooth.teeth)
