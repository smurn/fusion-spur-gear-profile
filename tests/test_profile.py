"""Exact tooth curves, GEO-1 to GEO-6."""

import math

import pytest

from gearcore import GearParams, derive
from gearcore.profile import ToothProfile

CASES = {
    'type A z24': GearParams(24.0),
    'z18': GearParams(18.0),
    'z100': GearParams(100.0),
    'module 5': GearParams(120.0, module=5.0),
    'shift +0.5': GearParams(24.0, profile_shift=0.5),
    'shift -0.2': GearParams(40.0, profile_shift=-0.2),
    'backlash': GearParams(24.0, backlash=0.15),
    'shift and backlash': GearParams(30.0, module=2.0, profile_shift=0.3, backlash=0.1),
    'sharp rack corner': GearParams(24.0, fillet=0.0),
    'alpha 25': GearParams(24.0, pressure_angle=math.radians(25), fillet=0.3),
    'alpha 14.5': GearParams(40.0, pressure_angle=math.radians(14.5)),
    'type C rack': GearParams(24.0, fillet=0.25),
}


@pytest.fixture(params=list(CASES), ids=list(CASES))
def case(request):
    p = CASES[request.param]
    return p, ToothProfile(p)


def linspace(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def tangent(curve, t, eps=1e-7):
    a, b = curve(t - eps), curve(t + eps)
    n = math.dist(a, b)
    return (b[0] - a[0]) / n, (b[1] - a[1]) / n


def test_flank_is_an_involute_of_the_base_circle(case):
    """GEO-2, TST-2: every normal of an involute is tangent to its base circle."""
    _, tooth = case
    for t in linspace(tooth.t_join + 1e-3, tooth.t_tip, 9):
        x, y = tooth.involute(t)
        tx, ty = tangent(tooth.involute, t)
        # Distance of the origin from the normal line through (x, y).
        assert abs(x * tx + y * ty) == pytest.approx(tooth.rb, rel=1e-6)


def test_involute_tangent_matches_the_curve(case):
    _, tooth = case
    for t in linspace(tooth.t_join + 1e-3, tooth.t_tip, 5):
        tx, ty = tangent(tooth.involute, t)
        ax, ay = tooth.involute_tangent(t)
        assert (-tx, -ty) == pytest.approx((ax, ay), abs=1e-6)


def test_tooth_thickness_at_the_reference_circle(case):
    """DER-6, TST-2: the flank crosses the reference circle at half the tooth thickness."""
    p, tooth = case
    x, y = tooth.involute(math.tan(p.pressure_angle))
    assert math.hypot(x, y) == pytest.approx(tooth.r)
    assert 2 * math.atan2(y, x) * tooth.r == pytest.approx(derive(p).tooth_thickness)


def test_flank_spans_from_join_to_tip(case):
    """GEO-2, GEO-5"""
    _, tooth = case
    assert math.hypot(*tooth.involute(tooth.t_tip)) == pytest.approx(tooth.ra)
    assert tooth.rb <= tooth.r_join < tooth.ra
    assert 0 < tooth.tip_angle < tooth.root_angle <= tooth.tau / 2


def test_root_curve_meets_the_flank_tangentially(case):
    """GEO-1, GEO-3: the point cut by the end of the rack's straight flank lies on
    the involute derived from the tooth thickness. This ties the rack model
    (profile shift, backlash) to DER-6."""
    _, tooth = case
    join = tooth.trochoid(tooth.phi_flank)
    assert join == pytest.approx(tooth.involute(tooth.t_join), abs=1e-9)
    span = tooth.phi_root - tooth.phi_flank
    a, b = join, tooth.trochoid(tooth.phi_flank + span * 1e-6)
    n = math.dist(a, b)
    assert ((b[0] - a[0]) / n, (b[1] - a[1]) / n) == pytest.approx(
        tooth.involute_tangent(tooth.t_join), abs=1e-4)


def test_root_curve_meets_the_root_circle_tangentially(case):
    """GEO-3"""
    _, tooth = case
    x, y = tooth.trochoid(tooth.phi_root)
    assert math.hypot(x, y) == pytest.approx(tooth.rf)
    assert math.atan2(y, x) == pytest.approx(tooth.root_angle)
    span = tooth.phi_root - tooth.phi_flank
    bx, by = tooth.trochoid(tooth.phi_root - span * 1e-4)
    # Approaching the root circle, the radius changes only in second order.
    assert math.hypot(bx, by) - tooth.rf < 1e-6 * tooth.r
    assert all(math.hypot(*tooth.trochoid(phi)) >= tooth.rf - 1e-12
               for phi in linspace(tooth.phi_flank, tooth.phi_root, 50))


def test_root_curve_is_the_envelope_of_the_rack_fillet(case):
    """GEO-1, GEO-3: no position of the rack's tip fillet cuts deeper than the root
    curve, and one position touches each of its points."""
    _, tooth = case

    def fillet_center(phi):
        # Rack kinematics, independent of ToothProfile.trochoid.
        radial, tangential = tooth.r + tooth.vc, tooth.uc - tooth.r * phi
        x = radial * math.cos(phi) - tangential * math.sin(phi)
        y = radial * math.sin(phi) + tangential * math.cos(phi)
        rad, ang = math.hypot(x, y), tooth.tau / 2 - math.atan2(y, x)
        return rad * math.cos(ang), rad * math.sin(ang)

    span = tooth.phi_root - tooth.phi_flank
    centers = [fillet_center(phi) for phi in linspace(tooth.phi_flank - span, tooth.phi_root + span, 6001)]
    for phi in linspace(tooth.phi_flank, tooth.phi_root, 11):
        point = tooth.trochoid(phi)
        nearest = min(math.dist(point, c) for c in centers)
        assert nearest == pytest.approx(tooth.rho, abs=1e-6 * tooth.r)


def test_backlash_thins_the_tooth_but_keeps_the_root(case):
    """GEO-6"""
    p, tooth = case
    import dataclasses
    more = ToothProfile(dataclasses.replace(p, backlash=p.backlash + 0.1))
    assert more.rf == tooth.rf
    assert more.psi < tooth.psi
    assert more.tip_angle < tooth.tip_angle


def test_undercut_flag_follows_der7():
    """DER-7"""
    assert ToothProfile(GearParams(17.0)).undercut
    assert not ToothProfile(GearParams(18.0)).undercut
