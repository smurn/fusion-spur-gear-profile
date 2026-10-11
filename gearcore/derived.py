"""Derived values (spec section 5)."""

import dataclasses
import math
import typing

from .params import GearParams


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


def tooth_count(p: GearParams) -> int:
    """DER-1. Exact halves round up."""
    return math.floor(p.diameter / p.module + 0.5)


def tooth_axes(p: GearParams) -> typing.List[float]:
    """Angles of the axes of the generated teeth, ascending (GEO-9). The reference
    direction is angle 0; for an arc that is the direction to its midpoint."""
    z = tooth_count(p)
    tau = 2 * math.pi / z
    if p.arc_span is None:
        return [(p.rotation + k) * tau for k in range(z)]
    # Arc: only teeth whose whole pitch unit (axis +- tau / 2) lies within the arc.
    reach = p.arc_span / 2 - tau / 2 + 1e-9
    first = math.ceil(-reach / tau - p.rotation)
    last = math.floor(reach / tau - p.rotation)
    return [(p.rotation + k) * tau for k in range(first, last + 1)]


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
    if z > 0 and d_a > d_b > 0:
        # A curve parallel to an involute at distance delta is an involute of the
        # same base circle, turned by delta / r_b. That is the adjustment for delta.
        s_a = d_a * (s / d + inv(a) - inv(math.acos(d_b / d_a)) + 2 * delta / d_b)
    return Derived(teeth=z, reference_diameter=d, base_diameter=d_b, tip_diameter=d_a,
                   root_diameter=d_f, tooth_thickness=s, min_teeth=z_min, undercut=z < z_min,
                   tip_thickness=s_a, generated_teeth=len(tooth_axes(p)) if z > 0 else 0)
