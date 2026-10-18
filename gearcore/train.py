"""Gear trains in a layout sketch (spec section 7, TRN-2 to TRN-9 and TRN-11).

The layout sketch comes in as plain data, in its own 2D coordinates (mm): its
circles and arcs, and its lines. Out comes the orientation of one of them: the
angle of a tooth axis, worked out for its whole train.
"""

import collections
import dataclasses
import math
import typing

from .derived import tooth_count
from .mesh import mesh_axis
from .params import GearParams
from .validation import ERROR, WARNING, Issue

Point = typing.Tuple[float, float]

TOUCH = 0.001      # mm: touching, start line ends, loop mismatch (TRN-3, TRN-5, TRN-8)
NEAR_MISS = 0.25   # in modules (TRN-11)


@dataclasses.dataclass(frozen=True)
class LayoutCurve:
    """A circle, or an arc running counter-clockwise from start by sweep (radians)."""
    center: Point
    radius: float
    start: typing.Optional[float] = None
    sweep: typing.Optional[float] = None

    def covers(self, angle: float) -> bool:
        """Whether the curve passes through the point at this angle from its center."""
        if self.start is None:
            return True
        slack = TOUCH / self.radius
        return (angle - self.start + slack) % (2 * math.pi) <= self.sweep + 2 * slack


@dataclasses.dataclass(frozen=True)
class LayoutLine:
    start: Point
    end: Point


@dataclasses.dataclass
class Orientation:
    """What the layout sketch says about one of its curves (TRN-10, UI-9)."""
    axis: typing.Optional[float]   # angle of a tooth axis, or None if not set by the layout
    train_size: int                # number of curves in the train, this one included
    touching: int                  # number of curves this one touches
    start_line: bool               # whether the train is oriented by a start line
    issues: typing.List[Issue]     # VAL-20, VAL-21, VAL-23 for this train


def _direction(a: Point, b: Point) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _gap(a: LayoutCurve, b: LayoutCurve) -> typing.Optional[float]:
    """How far two curves are from touching from outside (TRN-3), or None if they
    cannot touch: common center, or the touching point is not on an arc."""
    distance = math.dist(a.center, b.center)
    if distance < TOUCH:
        return None
    if not (a.covers(_direction(a.center, b.center)) and b.covers(_direction(b.center, a.center))):
        return None
    return abs(distance - (a.radius + b.radius))


def _start_line_angle(curve: LayoutCurve, line: LayoutLine) -> typing.Optional[float]:
    """The line's angle if it is a start line of the curve: from its center to a
    point on it (TRN-5)."""
    for center_end, other in ((line.start, line.end), (line.end, line.start)):
        if (math.dist(center_end, curve.center) <= TOUCH
                and abs(math.dist(other, curve.center) - curve.radius) <= TOUCH):
            return _direction(curve.center, other)
    return None


def orientation(curves: typing.Sequence[LayoutCurve], lines: typing.Sequence[LayoutLine],
                module: float, index: int) -> Orientation:
    """Orientation of curves[index] from its train. curves are in sketch order:
    circles before arcs, as Fusion lists them (TRN-7). All curves are taken as
    gears with this module (TRN-9); curves too small for a gear (fewer than 3
    teeth) are left out of trains."""
    teeth = [tooth_count(GearParams(diameter=2 * c.radius, module=module)) for c in curves]
    usable = [z >= 3 for z in teeth]

    # TRN-3, TRN-11: who touches whom, and who nearly does.
    neighbours = collections.defaultdict(list)
    near = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            if not (usable[i] and usable[j]):
                continue
            gap = _gap(curves[i], curves[j])
            if gap is None:
                continue
            if gap <= TOUCH:
                neighbours[i].append(j)
                neighbours[j].append(i)
            elif gap <= NEAR_MISS * module:
                near.append((i, j, gap))

    # TRN-4: the train, breadth first from this curve.
    train, queue = [index], [index]
    while queue:
        k = queue.pop(0)
        for n in neighbours[k]:
            if n not in train:
                train.append(n)
                queue.append(n)
    members = set(train)

    issues = []
    for i, j, gap in near:
        if i in members or j in members:
            issues.append(Issue('VAL-23', WARNING, 'Two circles of this gear train nearly touch, '
                                '{:.3f} mm from touching, at ({:.2f}, {:.2f}) and ({:.2f}, {:.2f}) '
                                'mm: add a tangent constraint, or move them apart.'.format(
                                    gap, *curves[i].center, *curves[j].center)))

    # TRN-5: start lines of the train.
    starts = []
    for k in sorted(members):
        for line in lines:
            angle = _start_line_angle(curves[k], line)
            if angle is not None:
                starts.append((k, angle))
    result = Orientation(None, len(train), len(neighbours[index]), bool(starts), issues)
    if len(starts) > 1:
        issues.append(Issue('VAL-20', ERROR, 'This gear train has {} start lines; it may have at '
                            'most one.'.format(len(starts))))
        return result
    if len(train) < 2 and not starts:
        return result   # a lone circle: the gear's own start rotation applies (TRN-10)
    if not usable[index]:
        return result   # VAL-2 is reported for the gear itself

    # TRN-7: from the first curve, along the fewest touchings.
    first, axis = starts[0] if starts else (min(members), 0.0)
    axes, tree = {first: axis}, set()
    queue = [first]
    while queue:
        k = queue.pop(0)
        for n in sorted(neighbours[k]):
            if n not in axes:
                axes[n] = mesh_axis(_direction(curves[k].center, curves[n].center), axes[k],
                                    teeth[k], teeth[n])
                tree.add(frozenset((k, n)))
                queue.append(n)

    # TRN-8: every other touching pair must mesh as well.
    worst = 0.0
    for k in members:
        for n in neighbours[k]:
            if k < n and frozenset((k, n)) not in tree:
                wanted = mesh_axis(_direction(curves[k].center, curves[n].center), axes[k],
                                   teeth[k], teeth[n])
                pitch = 2 * math.pi / teeth[n]
                off = abs(math.remainder(axes[n] - wanted, pitch)) * module * teeth[n] / 2
                worst = max(worst, off)
    if worst > TOUCH:
        issues.append(Issue('VAL-21', ERROR, 'The gears of this train form a loop that does not '
                            'mesh: the teeth are {:.3f} mm off.'.format(worst)))
        return result
    result.axis = axes[index]
    return result
