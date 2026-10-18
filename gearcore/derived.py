"""Derived values (spec section 5)."""

import dataclasses
import math
import typing

from .params import GearParams, Mate


def inv(phi: float) -> float:
    """Involute function."""
    return math.tan(phi) - phi


@dataclasses.dataclass(frozen=True)
class Derived:
    teeth: int                 # DER-1, z
    reference_diameter: float  # DER-2, d
    base_diameter: float       # DER-3, d_b
    tip_diameter: float        # DER-4, d_a
    root_diameter: float       # DER-5, d_f
    tooth_thickness: float     # DER-6, s
    min_teeth: float           # DER-7, z_min
    undercut: bool             # DER-7
    #: DER-8, s_a. None if the tip circle lies inside the base circle.
    tip_thickness: typing.Optional[float]
    generated_teeth: int       # DER-9; equals `teeth` for a full circle
    #: DER-12, radians. None for a circle.
    motion_range: typing.Optional[float] = None


def tooth_count(p: GearParams) -> int:
    """DER-1. Exact halves round up."""
    return math.floor(p.diameter / p.module + 0.5)


def tip_radius(p: GearParams) -> float:
    """Half of DER-4."""
    return p.module * tooth_count(p) / 2 + p.module * (p.addendum + p.profile_shift) + p.print_offset


def overlap_angle(p: GearParams, mate: typing.Optional[Mate]) -> float:
    """GEO-13: the angle, seen from the gear's center, over which its tip circle
    overlaps the mate's, or a rack's if mate is None."""
    r, ra, h = p.diameter / 2, tip_radius(p), p.addendum * p.module
    if mate is None:
        c = (r - h) / ra
    else:
        a, ra_mate = r + mate.radius, mate.radius + h
        c = (a * a + ra * ra - ra_mate * ra_mate) / (2 * a * ra)
    return math.acos(max(-1.0, min(1.0, c)))


def _on_arc(p: GearParams) -> typing.List[typing.Tuple[float, Mate]]:
    """The mates whose direction is on the arc (TRN-12), with that direction
    measured from the arc's start, counter-clockwise."""
    slack = 1e-6
    found = []
    for mate in p.mates:
        d = (mate.direction + p.arc_span / 2) % (2 * math.pi)
        if d > 2 * math.pi - slack:
            d -= 2 * math.pi
        if d <= p.arc_span + slack:
            found.append((d, mate))
    return found


def reach(p: GearParams) -> typing.Tuple[float, float, float]:
    """GEO-13, DER-12 for an arc: how far the teeth must reach beyond its start and
    its end, and the range of motion."""
    mates = _on_arc(p)
    if not mates:
        gamma = overlap_angle(p, None) if p.auto_teeth else 0.0
        return gamma, gamma, p.arc_span
    first = min(d for d, _ in mates)
    last = max(d for d, _ in mates)
    motion = p.arc_span - (last - first)
    if not p.auto_teeth:
        return 0.0, 0.0, motion
    # When the gear has turned until the mate nearest an end is there, the others
    # are that much further in.
    start = max(overlap_angle(p, m) - (d - first) for d, m in mates)
    end = max(overlap_angle(p, m) - (last - d) for d, m in mates)
    return start, end, motion


@dataclasses.dataclass(frozen=True)
class Sector:
    """The generated teeth and the sector they are on (GEO-9, GEO-10, GEO-13).
    Angles are from the reference direction. start and end are None for a full gear."""
    axes: typing.List[float]
    start: typing.Optional[float] = None
    end: typing.Optional[float] = None
    motion: typing.Optional[float] = None   # DER-12, arcs only


def sector(p: GearParams) -> Sector:
    z = tooth_count(p)
    tau = 2 * math.pi / z
    full = [(p.rotation + k) * tau for k in range(z)]
    if p.arc_span is None:
        return Sector(full)
    before, after, motion = reach(p)
    half = p.arc_span / 2
    low, high = -half - before, half + after
    # Teeth whose pitch unit (axis +- tau / 2) overlaps low to high, plus the extra ones.
    eps = 1e-9
    extra = round(p.extra_teeth)
    first = math.floor((low + eps - tau / 2) / tau - p.rotation) + 1 - extra
    last = math.ceil((high - eps + tau / 2) / tau - p.rotation) - 1 + extra
    if last - first + 1 >= z:
        return Sector(full, motion=motion)
    axes = [(p.rotation + k) * tau for k in range(first, last + 1)]
    if not axes:
        return Sector([], -half, half, motion)
    start, end = min(-half, axes[0] - tau / 2), max(half, axes[-1] + tau / 2)
    if end - start >= 2 * math.pi - eps:
        return Sector(full, motion=motion)
    return Sector(axes, start, end, motion)


def tooth_axes(p: GearParams) -> typing.List[float]:
    """Angles of the axes of the generated teeth, ascending (GEO-9, GEO-13). The
    reference direction is angle 0; for an arc that is the direction to its midpoint."""
    return sector(p).axes


def derive(p: GearParams) -> Derived:
    """Derived values. Needs a positive module and a pressure angle in (0, 90 deg)."""
    m, a, x, delta = p.module, p.pressure_angle, p.profile_shift, p.print_offset
    z = tooth_count(p)
    d = m * z
    d_b = d * math.cos(a)
    d_a = d + 2 * m * (p.addendum + x) + 2 * delta
    d_f = d - 2 * m * (p.dedendum - x) + 2 * delta
    s = m * (math.pi / 2 + 2 * x * math.tan(a)) - p.backlash / (2 * math.cos(a))
    z_min = 2 * (p.dedendum - p.fillet * (1 - math.sin(a)) - x) / math.sin(a) ** 2
    s_a = None
    if delta > 0:
        # A positive offset rounds the tip corners (GEO-7); the tip arc keeps the
        # angle it has without offset and only moves out.
        plain = derive(dataclasses.replace(p, print_offset=0.0)).tip_thickness
        if plain is not None:
            s_a = plain * d_a / (d_a - 2 * delta)
    elif z > 0 and d_a > d_b > 0:
        # A curve parallel to an involute at distance delta is an involute of the
        # same base circle, turned by delta / r_b. That is the adjustment for delta.
        s_a = d_a * (s / d + inv(a) - inv(math.acos(d_b / d_a)) + 2 * delta / d_b)
    sec = sector(p) if z > 0 else Sector([])
    return Derived(teeth=z, reference_diameter=d, base_diameter=d_b, tip_diameter=d_a,
                   root_diameter=d_f, tooth_thickness=s, min_teeth=z_min, undercut=z < z_min,
                   tip_thickness=s_a, generated_teeth=len(sec.axes), motion_range=sec.motion)
