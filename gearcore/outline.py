"""The closed gear outline as exact arcs, lines and fitted splines (ARC-1).

Gear frame: gear center at the origin, +X is the reference direction of GEO-9.
"""

import dataclasses
import math
import typing

from . import spline as spline_mod
from .derived import sector
from .params import GearError, GearParams
from .profile import ToothProfile
from .spline import Point, Spline
from .validation import errors

ORIGIN = (0.0, 0.0)


def _place(p: Point, angle: float, mirror: bool) -> Point:
    """Mirror about the X axis (optional), then rotate about the origin."""
    x, y = p[0], (-p[1] if mirror else p[1])
    c, s = math.cos(angle), math.sin(angle)
    return x * c - y * s, x * s + y * c


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

    def reversed(self) -> 'Arc':
        return Arc(self.center, self.radius, self.start_angle + self.sweep, -self.sweep)

    def transformed(self, angle: float = 0.0, mirror: bool = False) -> 'Arc':
        sign = -1.0 if mirror else 1.0
        return Arc(_place(self.center, angle, mirror), self.radius,
                   sign * self.start_angle + angle, sign * self.sweep)


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


def _polar(radius: float, angle: float) -> Point:
    return radius * math.cos(angle), radius * math.sin(angle)


def half_tooth_chain(tooth: ToothProfile, tolerance: float) -> typing.List[Segment]:
    """The upper half of a tooth between its tip arc and its root arc, in the tooth
    frame: flank and root curve, plus the arcs a positive print offset adds at the
    tip corner and at the corner of an undercut (GEO-7)."""
    flank = spline_mod.fit(tooth.involute, tooth.t_tip, tooth.t_join, tolerance,
                           tooth.involute_tangent(tooth.t_tip), tooth.involute_tangent(tooth.t_join))
    # Without undercut the root curve leaves the flank tangentially. Where the two
    # meet at a corner (GEO-4), its direction is taken from the curve itself. It
    # meets the root circle tangentially.
    a = tooth.root_angle
    root = spline_mod.fit(tooth.trochoid, tooth.phi_join, tooth.phi_root, tolerance,
                          None if tooth.corner_join else tooth.involute_tangent(tooth.t_join),
                          (-math.sin(a), math.cos(a)))
    if not tooth.ridge:
        # Where the two curves cross, the point is found numerically, and close to
        # the base circle the involute is too sensitive to hit it exactly. Make the
        # flank end where the root curve starts (ACC-3). The shift is below a micron.
        flank = Spline(flank.control_points[:-1] + (root.start,), flank.knots)
    chain = []
    if tooth.tip_corner:
        chain.append(Arc(tooth.tip_corner[0], tooth.delta, *tooth.tip_corner[1:]))
    chain.append(flank)
    if tooth.ridge:
        chain.append(Arc(tooth.ridge[0], tooth.delta, *tooth.ridge[1:]))
    chain.append(root)
    return chain


def gear_outline(p: GearParams) -> Outline:
    """The gear outline for the parameters (GEO-1 to GEO-11)."""
    problems = errors(p)
    if problems:
        raise GearError('; '.join('{}: {}'.format(i.id, i.message) for i in problems))
    tooth = ToothProfile(p)
    if tooth.t_join >= tooth.t_tip:
        raise GearError('No flank remains: the root curve reaches the tip circle.')
    chain = half_tooth_chain(tooth, p.tolerance)
    tip, root_ang, rf = tooth.tip_angle, tooth.root_angle, tooth.rf
    bore = p.bore / 2   # not moved by the print offset (GEO-7)

    def tooth_segments(axis: float) -> list:
        # GEO-8: the lower side of the tooth is the mirror image of the upper side.
        return ([s.transformed(axis, mirror=True).reversed() for s in reversed(chain)]
                + [Arc(ORIGIN, tooth.ra, axis - tip, 2 * tip)]             # GEO-5
                + [s.transformed(axis) for s in chain])

    def root_arc(start: float, end: float) -> list:                     # GEO-3
        return [Arc(ORIGIN, rf, start, end - start)] if end - start > 1e-12 else []

    sec = sector(p)                                                     # GEO-9, GEO-13
    axes = sec.axes
    segments = []
    if sec.start is None:
        for axis in axes:
            segments += tooth_segments(axis)
            segments += root_arc(axis + root_ang, axis + tooth.tau - root_ang)
        holes = (Circle(ORIGIN, bore),) if bore > 0 else ()             # GEO-11
        return Outline(tuple(segments), len(axes), holes)

    # Arc mode (GEO-10): root circle from one end of the sector to the other, with
    # the teeth, closed by two radial edges and the bore circle or the center.
    # The print offset moves the root circle but not the edges or the bore (GEO-7).
    start, end = sec.start, sec.end
    at = start
    for axis in axes:
        segments += root_arc(at, axis - root_ang)
        segments += tooth_segments(axis)
        at = axis + root_ang
    segments += root_arc(at, end)
    if bore > 0:
        segments += [Line(_polar(rf, end), _polar(bore, end)),
                     Arc(ORIGIN, bore, end, start - end),
                     Line(_polar(bore, start), _polar(rf, start))]
    else:
        segments += [Line(_polar(rf, end), ORIGIN), Line(ORIGIN, _polar(rf, start))]
    return Outline(tuple(segments), len(axes))
