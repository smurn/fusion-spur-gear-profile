"""The tooth outline against an independent model of the generating rack.

GEO-1 to GEO-4, GEO-6. The rack here is described directly from the parameters,
without using any of gearcore's curve formulas: a gap point must be swept by the
rack in some position, a point just inside the tooth by none. This also covers
undercut, where the root curve cuts into the flank.
"""

import math

import pytest

from gearcore import GearParams
from gearcore.profile import ToothProfile

CASES = {
    'type A z24': GearParams(24.0),
    'z18': GearParams(18.0),
    'shift and backlash': GearParams(30.0, module=2.0, profile_shift=0.3, backlash=0.1),
    'sharp rack corner': GearParams(24.0, fillet=0.0),
    'undercut z14': GearParams(14.0),
    'undercut z8': GearParams(8.0),
    'undercut z5': GearParams(5.0),
    'undercut, negative shift': GearParams(20.0, profile_shift=-0.3),
    'undercut, sharp corner': GearParams(10.0, fillet=0.0),
    'undercut alpha 14.5': GearParams(24.0, pressure_angle=math.radians(14.5)),
    'barely undercut z17': GearParams(17.0),
    'large shift, fillet center outside the reference circle': GearParams(24.0, profile_shift=1.0),
    'very large shift z100': GearParams(100.0, profile_shift=1.5),
    'shift just past the fillet center limit': GearParams(40.0, profile_shift=0.9),
}


def rack_covers(p: GearParams, tooth: ToothProfile, point, phi: float) -> bool:
    """True if the rack tooth cutting this gap contains `point` (tooth frame) when
    the rack has rolled by phi."""
    m, a = p.module, p.pressure_angle
    r = m * tooth.teeth / 2
    half_width = math.pi * m / 4 + p.backlash / (4 * math.cos(a))   # at the datum line
    v_datum = p.profile_shift * m
    v_tip = v_datum - p.dedendum * m
    rho = p.fillet * m
    # Tooth frame to the frame centered on the gap, then to rack coordinates.
    rad, ang = math.hypot(*point), tooth.tau / 2 - math.atan2(point[1], point[0])
    x, y = rad * math.cos(ang), rad * math.sin(ang)
    v = x * math.cos(phi) + y * math.sin(phi) - r
    u = abs(-x * math.sin(phi) + y * math.cos(phi) + r * phi)
    if v < v_tip or u > half_width - (v_datum - v) * math.tan(a):
        return False
    # The corner of the rack tooth is rounded with radius rho.
    uc = half_width - p.dedendum * m * math.tan(a) - rho * (1 - math.sin(a)) / math.cos(a)
    du, dv = u - uc, v - (v_tip + rho)
    in_corner = du >= 0 and math.cos(a) * dv + math.sin(a) * du <= 0
    return not in_corner or du * du + dv * dv <= rho * rho


def generated_points(tooth: ToothProfile, n: int = 9):
    """Points on the flank and the root curve with their normals pointing into the gap."""
    curves = [(tooth.involute, tooth.t_tip, tooth.t_join), (tooth.trochoid, tooth.phi_join, tooth.phi_root)]
    for curve, t0, t1 in curves:
        for i in range(n):
            t = t0 + (t1 - t0) * (i + 0.5) / n
            p, q = curve(t), curve(t + (t1 - t0) * 1e-6)
            length = math.dist(p, q)
            # Both curves run from the tip towards the root, with the gap on the right.
            yield p, ((q[1] - p[1]) / length, -(q[0] - p[0]) / length)


@pytest.mark.parametrize('name', list(CASES))
def test_outline_is_the_boundary_of_what_the_rack_cuts(name):
    p = CASES[name]
    tooth = ToothProfile(p)
    eps = 5e-3 * p.module
    reach = 6 * p.module / tooth.r
    phis = [-reach + 2 * reach * i / 12000 for i in range(12001)]
    for point, normal in generated_points(tooth):
        inside = (point[0] - eps * normal[0], point[1] - eps * normal[1])
        outside = (point[0] + eps * normal[0], point[1] + eps * normal[1])
        assert not any(rack_covers(p, tooth, inside, phi) for phi in phis), \
            'the rack cuts into the tooth near {}'.format(point)
        assert any(rack_covers(p, tooth, outside, phi) for phi in phis), \
            'material is left in the gap near {}'.format(point)


@pytest.mark.parametrize('name', [n for n in CASES if 'undercut' in n and 'barely' not in n])
def test_undercut_root_curve_crosses_the_flank(name):
    """GEO-4: the join lies on both curves, above the base circle, and is a corner."""
    tooth = ToothProfile(CASES[name])
    assert tooth.undercut
    assert tooth.phi_flank < tooth.phi_join < tooth.phi_root
    join = tooth.trochoid(tooth.phi_join)
    on_flank = tooth.involute(tooth.t_join)
    assert math.dist(join, on_flank) < 1e-9 * tooth.r
    assert tooth.rb < tooth.r_join < tooth.ra
    # The root curve leaves the flank at an angle, not tangentially.
    step = (tooth.phi_root - tooth.phi_join) * 1e-6
    nxt = tooth.trochoid(tooth.phi_join + step)
    length = math.dist(join, nxt)
    direction = ((nxt[0] - join[0]) / length, (nxt[1] - join[1]) / length)
    flank = tooth.involute_tangent(tooth.t_join)
    assert direction[0] * flank[0] + direction[1] * flank[1] < 0.999


def test_undercut_removes_more_of_the_flank_with_fewer_teeth():
    """GEO-4"""
    shares = []
    for z in (16, 12, 8):
        tooth = ToothProfile(GearParams(float(z)))
        shares.append((tooth.r_join - tooth.rb) / (tooth.ra - tooth.rb))
    assert shares == sorted(shares)


def test_no_undercut_keeps_the_tangent_join():
    tooth = ToothProfile(GearParams(18.0))
    assert not tooth.undercut and tooth.phi_join == tooth.phi_flank
