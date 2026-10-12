"""The assembled outline: GEO-5, GEO-8, GEO-9, ACC-1, ACC-3, ACC-4."""

import dataclasses
import math

import pytest

from gearcore import Arc, GearError, GearParams, Spline, gear_outline
from gearcore.profile import ToothProfile
from gearcore.spline import dist_to_polyline

CASES = {
    'type A z24': GearParams(24.3),
    'z18': GearParams(18.0),
    'z200': GearParams(200.0),
    'module 5': GearParams(120.0, module=5.0),
    'shift and backlash': GearParams(30.0, module=2.0, profile_shift=0.3, backlash=0.1),
    'sharp rack corner': GearParams(24.0, fillet=0.0),
    'fine tolerance': GearParams(24.0, tolerance=0.0005),
    'rotated': GearParams(24.0, rotation=0.37),
    'undercut z12': GearParams(12.0),
    'undercut z6': GearParams(6.0),
    'undercut, sharp corner': GearParams(10.0, fillet=0.0),
}


@pytest.fixture(params=list(CASES), ids=list(CASES))
def case(request):
    p = CASES[request.param]
    return p, ToothProfile(p), gear_outline(p)


def exact_half_tooth(tooth, n=2000):
    """Dense polyline of the exact half-tooth, from the tooth axis to the gap center."""
    pts = [(tooth.ra * math.cos(a), tooth.ra * math.sin(a))
           for a in (tooth.tip_angle * i / 50 for i in range(50))]
    pts += [tooth.involute(tooth.t_tip + (tooth.t_join - tooth.t_tip) * i / n) for i in range(n + 1)]
    pts += [tooth.trochoid(tooth.phi_join + (tooth.phi_root - tooth.phi_join) * i / n)
            for i in range(1, n + 1)]
    pts += [(tooth.rf * math.cos(a), tooth.rf * math.sin(a))
            for a in (tooth.root_angle + tooth.phi_root * i / 50 for i in range(1, 51))]
    return pts


def fold(tooth, p, point):
    """Map a point of the full outline onto the half-tooth of tooth 0."""
    rad = math.hypot(*point)
    ang = (math.atan2(point[1], point[0]) - p.rotation * tooth.tau) % tooth.tau
    if ang > tooth.tau / 2:
        ang = tooth.tau - ang
    return rad * math.cos(ang), rad * math.sin(ang)


def test_outline_is_closed_and_ordered(case):
    """ACC-3"""
    _, _, outline = case
    assert outline.max_gap() < 1e-9


def test_segment_sequence(case):
    """GEO-5, GEO-8: per tooth two mirrored flank and root curves, a tip arc and a root arc."""
    _, tooth, outline = case
    assert outline.teeth == tooth.teeth
    assert len(outline.segments) == 6 * tooth.teeth
    kinds = [type(s) for s in outline.segments[:6]]
    assert kinds == [Spline, Spline, Arc, Spline, Spline, Arc]


def test_arcs_are_exact(case):
    """ACC-4, GEO-5"""
    _, tooth, outline = case
    arcs = [s for s in outline.segments if isinstance(s, Arc)]
    assert {round(a.radius, 9) for a in arcs} == {round(tooth.ra, 9), round(tooth.rf, 9)}
    assert all(a.center == (0.0, 0.0) and a.sweep > 0 for a in arcs)


def test_every_tooth_matches_the_exact_curves(case):
    """ACC-1, GEO-8, GEO-9: folded onto one half-tooth, the whole outline stays within
    the tolerance of the exact curves."""
    p, tooth, outline = case
    exact = exact_half_tooth(tooth)
    step = max(1, len(outline.segments) // 60)   # every tooth position, spread over the gear
    worst = 0.0
    for seg in outline.segments[::step] + outline.segments[:6]:
        worst = max(worst, max(dist_to_polyline(fold(tooth, p, q), exact) for q in seg.sample(12)))
    assert worst <= p.tolerance


def test_outline_is_counter_clockwise_with_the_right_area(case):
    p, tooth, outline = case
    half = exact_half_tooth(tooth)
    wedge = [(0.0, 0.0)] + half
    exact = tooth.teeth * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                              in zip(wedge, wedge[1:] + wedge[:1]))
    assert math.pi * tooth.rf ** 2 < outline.area() < math.pi * tooth.ra ** 2
    perimeter = sum(math.dist(a, b) for a, b in zip(half, half[1:])) * 2 * tooth.teeth
    assert abs(outline.area() - exact) <= perimeter * p.tolerance


def test_first_tooth_is_on_the_reference_direction():
    """GEO-9: with p = 0 a tooth axis lies on +X."""
    outline = gear_outline(GearParams(24.0))
    tip = outline.segments[2]
    assert tip.start_angle + tip.sweep / 2 == pytest.approx(0.0, abs=1e-12)


def test_rotation_turns_the_gear_by_a_fraction_of_the_pitch():
    """GEO-9, IN-10"""
    tau = 2 * math.pi / 24
    tip = gear_outline(GearParams(24.0, rotation=0.25)).segments[2]
    assert tip.start_angle + tip.sweep / 2 == pytest.approx(0.25 * tau)
    # 100 % is the same gear as 0 %.
    a = gear_outline(GearParams(24.0, rotation=1.0)).sample(4)
    b = gear_outline(GearParams(24.0)).sample(4)
    n = len(b) // 24
    flat = lambda pts: [c for p in pts for c in p]
    assert flat(a[:-n]) == pytest.approx(flat(b[n:]), abs=1e-9)


def test_tolerance_controls_the_number_of_control_points():
    """ACC-2"""
    coarse = gear_outline(GearParams(24.0, tolerance=0.05))
    fine = gear_outline(GearParams(24.0, tolerance=0.0002))
    count = lambda o: sum(len(s.control_points) for s in o.segments[:6] if isinstance(s, Spline))
    assert count(coarse) < count(fine)


def test_invalid_parameters_raise():
    with pytest.raises(GearError, match='VAL-3'):
        gear_outline(GearParams(24.0, profile_shift=2.0))
    with pytest.raises(GearError, match='VAL-2'):
        gear_outline(GearParams(2.0))


def test_undercut_makes_the_tooth_root_thinner():
    """GEO-4: with undercut, the outline at the base circle is narrower than the
    involute alone would make it."""
    p = GearParams(8.0)
    tooth = ToothProfile(p)
    outline = gear_outline(p)
    root_curve = outline.segments[4]   # upper root curve of the first tooth
    narrowest = min(math.atan2(y, x) for x, y in root_curve.sample(32))
    assert narrowest < math.atan2(*reversed(tooth.involute(tooth.t_join)))
