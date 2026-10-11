"""The closed gear outline as exact arcs, lines and fitted splines (ARC-1).

Gear frame: gear center at the origin, +X is the reference direction of GEO-9.
"""

import dataclasses
import math
import typing

from . import spline as spline_mod
from .derived import tooth_axes
from .params import GearError, GearParams
from .profile import ToothProfile
from .spline import Point, Spline
from .validation import errors

ORIGIN = (0.0, 0.0)


@dataclasses.dataclass(frozen=True)
class Arc:
    """Circular arc about `center`. A positive sweep is counter-clockwise."""
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


@dataclasses.dataclass(frozen=True)
class Line:
    start: Point
    end: Point

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        return [self.start, self.end]


@dataclasses.dataclass(frozen=True)
class Circle:
    """A full circle; used for the bore of a full gear (GEO-11)."""
    center: Point
    radius: float

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        n = 8 * per_span
        return [(self.center[0] + self.radius * math.cos(2 * math.pi * k / n),
                 self.center[1] + self.radius * math.sin(2 * math.pi * k / n)) for k in range(n)]


Segment = typing.Union[Arc, Line, Spline]


@dataclasses.dataclass(frozen=True)
class Outline:
    """The gear's cross-section: a closed outer loop, counter-clockwise, in which
    each segment starts where the previous one ends, and the holes cut out of it."""
    segments: typing.Tuple[Segment, ...]
    teeth: int
    holes: typing.Tuple[Circle, ...] = ()

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        pts = []
        for seg in self.segments:
            pts += seg.sample(per_span)[:-1]
        return pts

    def area(self, per_span: int = 64) -> float:
        """Enclosed area, by Green's theorem. Arcs and lines are exact; splines are
        sampled with per_span points per span."""
        total = 0.0
        for seg in self.segments:
            (x0, y0), (x1, y1) = seg.start, seg.end
            if isinstance(seg, Arc):
                cx, cy = seg.center
                total += seg.radius ** 2 * seg.sweep + cx * (y1 - y0) - cy * (x1 - x0)
            elif isinstance(seg, Line):
                total += x0 * y1 - x1 * y0
            else:
                pts = seg.sample(per_span)
                total += sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(pts, pts[1:]))
        return total / 2 - sum(math.pi * hole.radius ** 2 for hole in self.holes)

    def max_gap(self) -> float:
        """Largest distance between the end of a segment and the start of the next (ACC-3)."""
        segs = self.segments
        return max(math.dist(a.end, b.start) for a, b in zip(segs, segs[1:] + segs[:1]))


def half_tooth_splines(tooth: ToothProfile, tolerance: float):
    """Flank (tip to join) and root curve (join to root circle) of the half-tooth."""
    flank_end = tooth.involute_tangent(tooth.t_join)
    flank = spline_mod.fit(tooth.involute, tooth.t_tip, tooth.t_join, tolerance,
                           tooth.involute_tangent(tooth.t_tip), flank_end)
    # Without undercut the root curve leaves the flank tangentially. With undercut
    # it meets the flank at a corner (GEO-4), so its direction is taken from the
    # curve itself. Either way it meets the root circle tangentially.
    a = tooth.root_angle
    root = spline_mod.fit(tooth.trochoid, tooth.phi_join, tooth.phi_root, tolerance,
                          None if tooth.undercut else flank_end, (-math.sin(a), math.cos(a)))
    return flank, root


def _polar(radius: float, angle: float) -> Point:
    return radius * math.cos(angle), radius * math.sin(angle)


def gear_outline(p: GearParams) -> Outline:
    """The gear outline for the parameters (GEO-1 to GEO-11)."""
    problems = errors(p)
    if problems:
        raise GearError('; '.join('{}: {}'.format(i.id, i.message) for i in problems))
    if p.print_offset != 0:
        raise NotImplementedError('print offset (GEO-7)')
    tooth = ToothProfile(p)
    if tooth.r_join >= tooth.ra:
        raise GearError('No flank remains: the root curve reaches the tip circle.')

    flank, root = half_tooth_splines(tooth, p.tolerance)
    tip, root_ang, rf = tooth.tip_angle, tooth.root_angle, tooth.rf

    def tooth_segments(axis: float) -> list:
        # GEO-8: the lower side of the tooth is the mirror image of the upper side.
        return [root.transformed(axis, mirror=True).reversed(),
                flank.transformed(axis, mirror=True).reversed(),
                Arc(ORIGIN, tooth.ra, axis - tip, 2 * tip),             # GEO-5
                flank.transformed(axis),
                root.transformed(axis)]

    def root_arc(start: float, end: float) -> list:                     # GEO-3
        return [Arc(ORIGIN, rf, start, end - start)] if end - start > 1e-12 else []

    axes = tooth_axes(p)                                                # GEO-9
    segments = []
    if p.arc_span is None:
        for axis in axes:
            segments += tooth_segments(axis)
            segments += root_arc(axis + root_ang, axis + tooth.tau - root_ang)
        holes = (Circle(ORIGIN, p.bore / 2),) if p.bore > 0 else ()     # GEO-11
        return Outline(tuple(segments), len(axes), holes)

    # Arc mode (GEO-10): root circle from one end of the arc to the other, with the
    # teeth that fit, closed by two radial edges and the bore circle or the center.
    half = p.arc_span / 2
    at = -half
    for axis in axes:
        segments += root_arc(at, axis - root_ang)
        segments += tooth_segments(axis)
        at = axis + root_ang
    segments += root_arc(at, half)
    bore = p.bore / 2
    if bore > 0:
        segments += [Line(_polar(rf, half), _polar(bore, half)),
                     Arc(ORIGIN, bore, half, -p.arc_span),
                     Line(_polar(bore, -half), _polar(rf, -half))]
    else:
        segments += [Line(_polar(rf, half), ORIGIN), Line(ORIGIN, _polar(rf, -half))]
    return Outline(tuple(segments), len(axes))
