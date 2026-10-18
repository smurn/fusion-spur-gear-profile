"""Arc gears: teeth for the range of motion. GEO-13, DER-12, IN-30, IN-31, TRN-12."""

import math

import pytest

from gearcore import GearParams, Mate, derive, gear_outline, overlap_angle, sector, validate

DEG = math.pi / 180


def arc_gear(span_deg, mates=(), **kwargs):
    """z = 20, m = 1, pitch 18 deg. Mates as (direction in deg, layout radius)."""
    kwargs.setdefault('auto_teeth', True)
    return GearParams(20.0, arc_span=span_deg * DEG,
                      mates=tuple(Mate(d * DEG, r) for d, r in mates), **kwargs)


def test_overlap_angle_by_hand():
    """GEO-13: z = 20 with z = 20: cos g = (20^2 + 11^2 - 11^2) / (2 * 20 * 11)."""
    p = arc_gear(90)
    assert overlap_angle(p, Mate(0.0, 10.0)) == pytest.approx(math.acos(400 / 440))
    assert overlap_angle(p, Mate(0.0, 10.0)) / DEG == pytest.approx(24.62, abs=0.01)
    # A rack: the tip line at r - m from the center, cos g = 9 / 11.
    assert overlap_angle(p, None) == pytest.approx(math.acos(9 / 11))


def test_rack_is_the_largest_mate():
    """GEO-13: without mates a rack is assumed, which needs the most."""
    p = arc_gear(90)
    sizes = [overlap_angle(p, Mate(0.0, r)) for r in (2.0, 5.0, 10.0, 50.0, 1000.0)]
    assert sizes == sorted(sizes)
    assert sizes[-1] < overlap_angle(p, None)


def test_without_mates_a_rack_is_assumed_at_both_ends():
    """GEO-13, DER-12"""
    p = arc_gear(90)
    gamma = overlap_angle(p, None) / DEG   # 35.1 deg
    sec = sector(p)
    # Teeth whose units (axis +- 9) overlap -45 - 35.1 to 45 + 35.1: axes up to +-72.
    assert gamma == pytest.approx(35.1, abs=0.05)
    assert [round(a / DEG, 6) for a in sec.axes] == [18.0 * k for k in range(-4, 5)]
    assert sec.motion == pytest.approx(90 * DEG)
    assert derive(p).motion_range == pytest.approx(90 * DEG)


def test_without_automatic_only_the_arc_is_covered():
    """IN-30"""
    p = arc_gear(90, auto_teeth=False)
    assert [round(a / DEG, 6) for a in sector(p).axes] == [18.0 * k for k in range(-2, 3)]


@pytest.mark.parametrize('extra', [-2, -1, 1, 3])
def test_extra_teeth_at_each_end(extra):
    """IN-31: on top of the automatic teeth, or without them; negative removes."""
    for auto in (True, False):
        base = len(sector(arc_gear(90, auto_teeth=auto)).axes)
        assert len(sector(arc_gear(90, auto_teeth=auto, extra_teeth=extra)).axes) == base + 2 * extra


def test_extra_teeth_must_be_whole():
    """IN-31"""
    assert 'IN-31' in {i.id for i in validate(arc_gear(90, extra_teeth=0.5))}
    assert 'IN-31' not in {i.id for i in validate(arc_gear(90, extra_teeth=-2))}


def test_one_mate_reaches_by_its_overlap_angle():
    """GEO-13: wherever the mate is on the arc, the reach is its overlap angle at both
    ends, and the gear turns the whole arc."""
    for direction in (-40, 0, 25):
        p = arc_gear(90, [(direction, 10.0)])
        gamma = overlap_angle(p, Mate(0.0, 10.0)) / DEG   # 24.6 deg
        sec = sector(p)
        assert sec.axes[0] / DEG - 9 < -45 - gamma < sec.axes[0] / DEG + 9
        assert sec.axes[-1] / DEG - 9 < 45 + gamma < sec.axes[-1] / DEG + 9
        assert sec.motion == pytest.approx(90 * DEG)


def test_two_mates_limit_the_motion():
    """DER-12: the arc's angle minus the angle between the outermost mates."""
    p = arc_gear(180, [(-30, 10.0), (30, 10.0), (0, 5.0)])
    assert sector(p).motion == pytest.approx(120 * DEG)
    assert sector(arc_gear(180, [(-30, 10.0), (30, 10.0)], auto_teeth=False)).motion \
        == pytest.approx(120 * DEG)


def test_a_large_mate_just_inside_a_small_one_decides():
    """GEO-13: the reach is the largest over all mates, not only the nearest one."""
    small, large = Mate(0.0, 2.0), Mate(0.0, 60.0)
    p = arc_gear(120, [(-50, 2.0), (-45, 60.0)])
    g_small, g_large = overlap_angle(p, small), overlap_angle(p, large)
    assert g_large - 5 * DEG > g_small   # so the large one decides at the start
    sec = sector(p)
    low = -60 * DEG - (g_large - 5 * DEG)
    assert sec.axes[0] - 9 * DEG < low < sec.axes[0] + 9 * DEG


def test_mates_off_the_arc_are_not_counted():
    """TRN-12"""
    alone = sector(arc_gear(90, [(0, 10.0)]))
    assert sector(arc_gear(90, [(0, 10.0), (150, 10.0)])) == alone


def test_teeth_all_around_make_a_full_gear():
    """GEO-13: a full gear, with the bore as a hole."""
    p = arc_gear(280, bore=4.0)
    sec = sector(p)
    assert sec.start is None and len(sec.axes) == 20
    outline = gear_outline(p)
    assert outline.teeth == 20 and len(outline.holes) == 1
    assert sector(arc_gear(280, extra_teeth=-2)).start is not None


def _mate_meets_complete_teeth(p: GearParams):
    """Turn the gear to both ends of its motion and check, independently of the reach
    formula, that wherever a mate's tip circle reaches inside the gear's tip circle,
    there are generated teeth: the angle lies within the outer edges of the outermost
    pitch units."""
    sec = sector(p)
    tau = 2 * math.pi / 20
    lo, hi = sec.axes[0] - tau / 2, sec.axes[-1] + tau / 2
    half = p.arc_span / 2
    ra = derive(p).tip_diameter / 2
    on_arc = [m for m in p.mates if -half - 1e-9 <= math.remainder(m.direction, 2 * math.pi) <= half + 1e-9]
    first = min(m.direction for m in on_arc)
    last = max(m.direction for m in on_arc)
    # Turning by psi moves the body angle at a fixed direction b to b - psi.
    for psi in (first + half, last - half):
        for mate in on_arc:
            a = p.diameter / 2 + mate.radius
            ra_mate = mate.radius + p.addendum * p.module
            body = mate.direction - psi
            cx, cy = a * math.cos(body), a * math.sin(body)
            for k in range(3600):
                t = 2 * math.pi * k / 3600
                x, y = cx + ra_mate * math.cos(t), cy + ra_mate * math.sin(t)
                if math.hypot(x, y) < ra:
                    angle = math.atan2(y, x)
                    assert lo - 1e-9 <= angle <= hi + 1e-9, (mate, psi, angle)


@pytest.mark.parametrize('span_deg, mates, rotation', [
    (90, [(0, 10.0)], 0.0),
    (90, [(20, 10.0)], 0.37),
    (120, [(-50, 2.0), (-45, 60.0)], 0.5),
    (160, [(-60, 8.0), (10, 15.0), (70, 4.0)], 0.81),
    (60, [(-25, 30.0), (25, 30.0)], 0.2),
])
def test_a_mate_at_the_end_of_the_motion_meets_complete_teeth(span_deg, mates, rotation):
    """GEO-13, TST-2"""
    _mate_meets_complete_teeth(arc_gear(span_deg, mates, rotation=rotation))
