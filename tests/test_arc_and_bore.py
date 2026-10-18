"""Arc mode and the bore: GEO-9, GEO-10, GEO-11, GEO-13, DER-9, VAL-6."""

import math

import pytest

from gearcore import Arc, Circle, GearError, GearParams, Line, Spline, derive, gear_outline, sector, tooth_axes, validate

DEG = math.pi / 180


def arc_gear(span_deg, **kwargs):
    return GearParams(24.0, arc_span=span_deg * DEG, **kwargs)


@pytest.mark.parametrize('span_deg, rotation, axes_deg', [
    (90, 0.0, [15 * k for k in range(-3, 4)]),   # pitch 15 deg; units must overlap +-45
    (90, 0.5, [-37.5, -22.5, -7.5, 7.5, 22.5, 37.5]),
    (89, 0.5, [-37.5, -22.5, -7.5, 7.5, 22.5, 37.5]),
    (15, 0.0, [0]),                               # the units at +-15 only touch the arc
    (14, 0.0, [0]),
    (15, 0.25, [-11.25, 3.75]),
    (359, 0.0, [15 * k for k in range(24)]),       # 25 would overlap: a full gear
])
def test_teeth_that_cover_the_arc(span_deg, rotation, axes_deg):
    """GEO-9, GEO-13, DER-9: without extra teeth, the teeth whose pitch unit overlaps the arc."""
    p = arc_gear(span_deg, rotation=rotation)
    assert [a / DEG for a in tooth_axes(p)] == pytest.approx(axes_deg, abs=1e-9)
    assert derive(p).generated_teeth == len(axes_deg)


def test_sector_is_symmetric_without_rotation():
    """GEO-9: with p = 0 the sector is symmetric about the arc midpoint."""
    axes = tooth_axes(arc_gear(100))
    assert axes == pytest.approx([-a for a in reversed(axes)])
    pts = gear_outline(arc_gear(100)).sample(8)
    assert sum(y for _, y in pts) / len(pts) == pytest.approx(0.0, abs=1e-9)


def test_full_circle_generates_every_tooth():
    """DER-9"""
    assert derive(GearParams(24.0)).generated_teeth == 24
    assert derive(GearParams(24.0, rotation=0.9)).generated_teeth == 24


def test_arc_without_a_complete_tooth_is_an_error():
    """VAL-6"""
    assert 'VAL-6' in {i.id for i in validate(arc_gear(14, extra_teeth=-1))}
    with pytest.raises(GearError, match='VAL-6'):
        gear_outline(arc_gear(14, extra_teeth=-1))


def test_arc_outline_without_bore_closes_at_the_center():
    """GEO-10"""
    p = arc_gear(90)
    outline = gear_outline(p)
    rf = derive(p).root_diameter / 2
    assert outline.max_gap() < 1e-9
    assert outline.teeth == 7 and outline.holes == ()
    first, *_, edge_in, edge_out = outline.segments
    # Root circle from the start of the sector, the outer edge of the tooth at -45
    # deg, to that tooth.
    assert isinstance(first, Arc) and first.radius == pytest.approx(rf)
    assert first.start == pytest.approx((rf * math.cos(-52.5 * DEG), rf * math.sin(-52.5 * DEG)))
    assert 0 < first.sweep < 7.5 * DEG
    assert isinstance(edge_in, Line) and isinstance(edge_out, Line)
    assert edge_in.start == pytest.approx((rf * math.cos(52.5 * DEG), rf * math.sin(52.5 * DEG)))
    assert edge_in.end == (0.0, 0.0) and edge_out.start == (0.0, 0.0)
    assert sum(isinstance(s, Spline) for s in outline.segments) == 4 * 7


def test_sector_ends_at_the_arc_when_the_teeth_stop_short():
    """GEO-10"""
    p = arc_gear(90, extra_teeth=-1)
    assert len(tooth_axes(p)) == 5
    assert (sector(p).start, sector(p).end) == pytest.approx((-45 * DEG, 45 * DEG))


def test_arc_outline_with_bore_closes_along_the_bore_circle():
    """GEO-10, GEO-11"""
    outline = gear_outline(arc_gear(90, bore=8.0))
    assert outline.max_gap() < 1e-9 and outline.holes == ()
    edge_in, bore, edge_out = outline.segments[-3:]
    assert isinstance(edge_in, Line) and isinstance(bore, Arc) and isinstance(edge_out, Line)
    assert bore.radius == pytest.approx(4.0)
    assert bore.sweep == pytest.approx(-105 * DEG)   # clockwise, back to the start of the sector
    # The edges are radial.
    for edge in (edge_in, edge_out):
        assert edge.start[0] * edge.end[1] - edge.start[1] * edge.end[0] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize('span_deg, bore', [(90, 0.0), (90, 8.0), (200, 0.0), (200, 6.0), (330, 3.0)])
def test_arc_area(span_deg, bore):
    """GEO-10: a sector of the root circle, plus the teeth, minus the bore sector."""
    p = arc_gear(span_deg, bore=bore)
    full = gear_outline(GearParams(24.0))
    rf = derive(p).root_diameter / 2
    tooth_area = (full.area() - math.pi * rf ** 2) / 24
    span = sector(p).end - sector(p).start
    want = (rf ** 2 - (bore / 2) ** 2) * span / 2 + derive(p).generated_teeth * tooth_area
    assert gear_outline(p).area() == pytest.approx(want, abs=1e-6)


def test_full_gear_bore_is_a_hole():
    """GEO-11"""
    plain = gear_outline(GearParams(24.0))
    bored = gear_outline(GearParams(24.0, bore=8.0))
    assert bored.holes == (Circle((0.0, 0.0), 4.0),)
    assert bored.segments == plain.segments
    assert bored.area() == pytest.approx(plain.area() - math.pi * 16.0)


def test_arc_mode_works_with_undercut_and_rotation():
    outline = gear_outline(GearParams(10.0, arc_span=200 * DEG, rotation=0.3, bore=2.0))
    assert outline.max_gap() < 1e-9
    assert outline.teeth == derive(GearParams(10.0, arc_span=200 * DEG, rotation=0.3)).generated_teeth > 0
