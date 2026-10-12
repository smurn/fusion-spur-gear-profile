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

    def reversed(self) -> 'Line':
        return Line(self.end, self.start)

    def transformed(self, angle: float = 0.0, mirror: bool = False) -> 'Line':
        return Line(_place(self.start, angle, mirror), _place(self.end, angle, mirror))


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


def _root_spline(tooth: ToothProfile, tolerance: float, phi_end: float, end_tangent) -> Spline:
    # Without undercut the root curve leaves the flank tangentially. Where the two
    # meet at a corner (GEO-4), its direction is taken from the curve itself.
    start = None if tooth.corner_join else tooth.involute_tangent(tooth.t_join)
    return spline_mod.fit(tooth.trochoid, tooth.phi_join, phi_end, tolerance, start, end_tangent)


def half_tooth_chain(tooth: ToothProfile, tolerance: float) -> typing.List[Segment]:
    """The upper half of a tooth between its tip arc and its root arc, in the tooth
    frame: flank and root curve, plus the arcs a positive print offset adds at the
    tip corner and at the corner of an undercut (GEO-7)."""
    flank = spline_mod.fit(tooth.involute, tooth.t_tip, tooth.t_join, tolerance,
                           tooth.involute_tangent(tooth.t_tip), tooth.involute_tangent(tooth.t_join))
    a = tooth.root_angle   # the root curve meets the root circle tangentially
    root = _root_spline(tooth, tolerance, tooth.phi_root, (-math.sin(a), math.cos(a)))
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


@dataclasses.dataclass
class _ArcEnd:
    """How the outline leaves the root circle at the upper end of an arc-mode gear,
    described for the last tooth with the end of the arc at angle `half`."""
    root_end: float                    # angle where the root circle part ends
    start: Point                       # where the radial edge starts
    trimmed_root: typing.Optional[Spline] = None   # root curve of the last tooth, if cut short


def _arc_end(tooth: ToothProfile, tolerance: float, half: float, axis: float) -> _ArcEnd:
    """Upper end of the root circle for the tooth at `axis` (GEO-10, GEO-7)."""
    delta, radius = tooth.delta, tooth.rf
    if delta >= 0:
        # The corner between root circle and edge is rounded (or sharp, without
        # offset); the root circle runs to the end of the arc.
        return _ArcEnd(half, _polar(radius, half))
    # Negative offset: the edge moves into the sector and cuts the root circle short.
    root_end = half + math.atan2(delta, math.sqrt(radius ** 2 - delta ** 2))
    if root_end >= axis + tooth.root_angle - 1e-12:
        return _ArcEnd(root_end, _polar(radius, root_end))
    # The edge reaches the root curve of the last tooth. Find where, in the tooth frame.
    beta = half - axis
    nx, ny = -math.sin(beta), math.cos(beta)

    def beyond_edge(phi: float) -> float:
        x, y = tooth.trochoid(phi)
        return nx * x + ny * y - delta

    lo, hi = tooth.phi_join, tooth.phi_root
    if beyond_edge(lo) >= 0:
        raise GearError('The print offset cuts into the flank of a tooth at the end of the arc.')
    for _ in range(60):
        mid = (lo + hi) / 2
        if beyond_edge(mid) < 0:
            lo = mid
        else:
            hi = mid
    trimmed = _root_spline(tooth, tolerance, lo, None).transformed(axis)
    return _ArcEnd(root_end, trimmed.end, trimmed)


def _edge(start: Point, half: float, delta: float, bore: float, span: float) -> typing.List[Segment]:
    """Radial edge at the upper end of an arc-mode gear, from `start` on the root
    circle to where the inner closure begins, with its corner arcs (GEO-10, GEO-7)."""
    tangential = (-math.sin(half), math.cos(half))
    segments = []
    if delta > 0:   # outer corner, rounded about the corner of the outline without offset
        radius = math.hypot(*start) - delta
        segments.append(Arc(_polar(radius, half), delta, half, math.pi / 2))
        start = segments[-1].end
    inner_corner = None
    if bore > 0:
        if delta > 0:
            inner_corner = Arc(_polar(bore + delta, half), delta, half + math.pi / 2, math.pi / 2)
            end = inner_corner.start
        else:
            end = _polar(bore, half + math.atan2(delta, math.sqrt(bore ** 2 - delta ** 2)))
    elif delta == 0:
        end = ORIGIN
    elif abs(span - math.pi) < 1e-9 or (delta > 0) == (span < math.pi):
        # The two edges do not meet: the corner at the center is rounded.
        end = (delta * tangential[0], delta * tangential[1])
    else:
        # The two edges overlap and are trimmed where they cross.
        end = (-delta / math.sin(half), 0.0)
    segments.append(Line(start, end))
    if inner_corner:
        segments.append(inner_corner)
    return segments


def gear_outline(p: GearParams) -> Outline:
    """The gear outline for the parameters (GEO-1 to GEO-11)."""
    problems = errors(p)
    if problems:
        raise GearError('; '.join('{}: {}'.format(i.id, i.message) for i in problems))
    tooth = ToothProfile(p)
    if tooth.t_join >= tooth.t_tip:
        raise GearError('No flank remains: the root curve reaches the tip circle.')
    delta = p.print_offset
    chain = half_tooth_chain(tooth, p.tolerance)
    tip, root_ang, rf = tooth.tip_angle, tooth.root_angle, tooth.rf
    #: Bore radius with the print offset: a positive offset adds material (GEO-7).
    bore = max(p.bore / 2 - delta, 0.0) if p.bore > 0 else 0.0

    def tooth_segments(axis: float, lower_root=None, upper_root=None) -> list:
        # GEO-8: the lower side of the tooth is the mirror image of the upper side.
        lower = [s.transformed(axis, mirror=True).reversed() for s in reversed(chain)]
        upper = [s.transformed(axis) for s in chain]
        if lower_root is not None:
            lower[0] = lower_root
        if upper_root is not None:
            upper[-1] = upper_root
        return lower + [Arc(ORIGIN, tooth.ra, axis - tip, 2 * tip)] + upper   # GEO-5

    def root_arc(start: float, end: float) -> list:                     # GEO-3
        return [Arc(ORIGIN, rf, start, end - start)] if end - start > 1e-12 else []

    axes = tooth_axes(p)                                                # GEO-9
    segments = []
    if p.arc_span is None:
        for axis in axes:
            segments += tooth_segments(axis)
            segments += root_arc(axis + root_ang, axis + tooth.tau - root_ang)
        holes = (Circle(ORIGIN, bore),) if bore > 0 else ()             # GEO-11
        return Outline(tuple(segments), len(axes), holes)

    # Arc mode (GEO-10): root circle from one end of the arc to the other, with the
    # teeth that fit, closed by two radial edges and the bore circle or the center.
    # The lower end is the mirror image of an upper end for the mirrored first tooth.
    half = p.arc_span / 2
    upper = _arc_end(tooth, p.tolerance, half, axes[-1])
    lower = _arc_end(tooth, p.tolerance, half, -axes[0])
    lower_root = lower.trimmed_root.transformed(0.0, mirror=True).reversed() if lower.trimmed_root else None
    at = -lower.root_end
    for i, axis in enumerate(axes):
        if not (i == 0 and lower_root):
            segments += root_arc(at, axis - root_ang)
        segments += tooth_segments(axis, lower_root if i == 0 else None,
                                   upper.trimmed_root if i == len(axes) - 1 else None)
        at = axis + root_ang
    if not upper.trimmed_root:
        segments += root_arc(at, upper.root_end)

    edge_in = _edge(upper.start, half, delta, bore, p.arc_span)
    edge_out = [s.transformed(0.0, mirror=True).reversed()
                for s in reversed(_edge(lower.start, half, delta, bore, p.arc_span))]
    segments += edge_in
    inner_start, inner_end = edge_in[-1].end, edge_out[0].start
    if bore > 0:
        a = math.atan2(inner_start[1], inner_start[0])
        segments.append(Arc(ORIGIN, bore, a, -2 * a))
    elif math.dist(inner_start, inner_end) > 1e-12:
        a = math.atan2(inner_start[1], inner_start[0])
        segments.append(Arc(ORIGIN, abs(delta), a, math.pi - p.arc_span))
    segments += edge_out
    return Outline(tuple(segments), len(axes))
