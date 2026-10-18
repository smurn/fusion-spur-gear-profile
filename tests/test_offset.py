"""Print offset, GEO-7: the outline moved by delta along its normal.

The offset applies to the toothed profile only, not to the bore or to the radial
edges of a sector gear. The main check does not use any offset formula: every
point of the offset profile must lie at distance |delta| from the profile
without offset, on the right side of it.
"""

import dataclasses
import math

import pytest

from gearcore import Arc, GearError, GearParams, Line, Spline, derive, gear_outline, sector
from gearcore.profile import ToothProfile

DEG = math.pi / 180
FINE = 0.0005   # fit tolerance used for both outlines


def segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    u = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den))
    return math.hypot(a[0] + u * dx - p[0], a[1] + u * dy - p[1])


def inside(p, polygon):
    """Even-odd test."""
    hit = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > p[1]) != (y1 > p[1]) and p[0] < x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def dense(outline):
    """Sample points no more than about 0.02 mm apart on arcs, so that chords do not
    distort the distances."""
    pts = []
    for seg in outline.segments:
        n = 40
        if isinstance(seg, Arc):
            n = max(8, int(abs(seg.sweep) * seg.radius / 0.02))
        pts += seg.sample(n)[:-1]
    return pts


def check_offset(params, window=None, slack=0.0):
    """Compare the offset outline with the outline without offset. `window` limits
    the comparison to polar angles within +-window, to keep full gears fast."""
    delta = params.print_offset
    plain = gear_outline(dataclasses.replace(params, print_offset=0.0, tolerance=FINE))
    moved = gear_outline(dataclasses.replace(params, tolerance=FINE))
    assert moved.max_gap() < 1e-9

    def near(pt, reach):
        return window is None or abs(math.atan2(pt[1], pt[0])) <= reach

    reference = dense(plain)
    pairs = [(a, b) for a, b in zip(reference, reference[1:] + reference[:1])
             if window is None or (near(a, 2 * window) and near(b, 2 * window))]
    coarse = plain.sample(6)
    worst = 0.0
    for i, pt in enumerate(q for q in moved.sample(10) if near(q, window)):
        dist = min(segment_distance(pt, a, b) for a, b in pairs)
        worst = max(worst, abs(dist - abs(delta)))
        if i % 7 == 0:
            assert inside(pt, coarse) == (delta < 0), 'wrong side at {}'.format(pt)
    assert worst <= 2 * FINE + 1e-4 + slack, 'offset is off by {:.5f} mm'.format(worst)
    return plain, moved


TOOTH_CASES = {
    'z24 +0.1': GearParams(24.0, print_offset=0.1),
    'z24 -0.1': GearParams(24.0, print_offset=-0.1),
    'z24 +0.3': GearParams(24.0, print_offset=0.3),
    'z24 -0.3': GearParams(24.0, print_offset=-0.3),
    'z18 -0.2, past the start of the involute': GearParams(18.0, print_offset=-0.2),
    'z40 -0.15': GearParams(40.0, print_offset=-0.15),
    'undercut z10 +0.1': GearParams(10.0, print_offset=0.1),
    'undercut z10 -0.1': GearParams(10.0, print_offset=-0.1),
    'undercut z6 +0.2': GearParams(6.0, print_offset=0.2),
    'undercut z6 -0.2': GearParams(6.0, print_offset=-0.2),
    'sharp rack corner +0.1': GearParams(24.0, fillet=0.0, print_offset=0.1),
    'sharp rack corner -0.1': GearParams(24.0, fillet=0.0, print_offset=-0.1),
    'module 0.5 -0.1': GearParams(12.0, module=0.5, print_offset=-0.1),
    'module 3 +0.2': GearParams(60.0, module=3.0, print_offset=0.2),
    'shift and backlash +0.1': GearParams(30.0, module=2.0, profile_shift=0.3, backlash=0.1,
                                          print_offset=0.1),
    'shift and backlash -0.1': GearParams(30.0, module=2.0, profile_shift=0.3, backlash=0.1,
                                          print_offset=-0.1),
    'rotated +0.1': GearParams(24.0, rotation=0.4, print_offset=0.1),
}


@pytest.mark.parametrize('name', list(TOOTH_CASES))
def test_tooth_outline_is_parallel_to_the_plain_one(name):
    """GEO-7"""
    p = TOOTH_CASES[name]
    check_offset(p, window=math.pi / derive(p).teeth * 1.5)


ARC_CASES = {
    'quarter +0.1': GearParams(24.0, arc_span=90 * DEG, print_offset=0.1),
    'quarter -0.1': GearParams(24.0, arc_span=90 * DEG, print_offset=-0.1),
    'quarter with bore +0.1': GearParams(24.0, arc_span=90 * DEG, bore=8.0, print_offset=0.1),
    'reflex with bore -0.15': GearParams(24.0, arc_span=220 * DEG, bore=6.0, print_offset=-0.15),
    'teeth fill the arc exactly, +0.1': GearParams(24.0, arc_span=90 * DEG, rotation=0.5,
                                                    print_offset=0.1),
    'teeth fill the arc exactly, -0.1': GearParams(24.0, arc_span=90 * DEG, rotation=0.5,
                                                    print_offset=-0.1),
    'rotated, bore, undercut -0.1': GearParams(10.0, arc_span=200 * DEG, rotation=0.3, bore=3.0,
                                               print_offset=-0.1),
}


@pytest.mark.parametrize('name', list(ARC_CASES))
def test_sector_offset_moves_the_toothed_profile_only(name):
    """GEO-7, GEO-10: teeth and root circle are offset; the radial edges and the bore
    stay where they are."""
    p = ARC_CASES[name]
    delta, sec = p.print_offset, sector(p)
    plain = gear_outline(dataclasses.replace(p, print_offset=0.0, tolerance=FINE))
    moved = gear_outline(dataclasses.replace(p, tolerance=FINE))
    assert moved.max_gap() < 1e-9
    rf = derive(p).root_diameter / 2
    assert rf == pytest.approx(derive(dataclasses.replace(p, print_offset=0.0)).root_diameter / 2 + delta)

    # The closure: radial edges at the ends of the arc, from the moved root circle
    # to the unchanged bore circle or to the center.
    closing = 3 if p.bore else 2
    edge_in, edge_out = moved.segments[-closing], moved.segments[-1]
    inner = p.bore / 2
    flat = lambda pt: [round(c, 9) for c in pt]
    assert flat(edge_in.start) == flat((rf * math.cos(sec.end), rf * math.sin(sec.end)))
    assert flat(edge_in.end) == flat((inner * math.cos(sec.end), inner * math.sin(sec.end)))
    assert flat(edge_out.start) == flat((inner * math.cos(sec.start), inner * math.sin(sec.start)))
    assert flat(edge_out.end) == flat((rf * math.cos(sec.start), rf * math.sin(sec.start)))
    if p.bore:
        assert moved.segments[-2] == plain.segments[-2]   # the bore arc is identical

    # The toothed part is parallel to the plain toothed part.
    toothed = dataclasses.replace(plain, segments=plain.segments[:-closing])
    reference = dense(toothed) + [toothed.segments[-1].end]
    pairs = list(zip(reference, reference[1:]))
    worst = 0.0
    for seg in moved.segments[:-closing]:
        for pt in seg.sample(6):
            worst = max(worst, abs(min(segment_distance(pt, a, b) for a, b in pairs) - abs(delta)))
    assert worst <= 2 * FINE + 1e-4


def test_flank_is_the_parallel_of_the_plain_flank():
    """GEO-7: an involute moved along its normal is an involute of the same base circle."""
    p = GearParams(24.0, print_offset=0.15)
    plain, moved = ToothProfile(dataclasses.replace(p, print_offset=0.0)), ToothProfile(p)
    for t in (plain.t_join, 0.3, 0.45, plain.t_tip):
        x, y = plain.involute(t)
        tx, ty = plain.involute_tangent(t)
        want = (x + 0.15 * ty, y - 0.15 * tx)   # the gap is to the right of tip-to-root travel
        assert moved.involute(t + 0.15 / plain.rb) == pytest.approx(want, abs=1e-9)


def test_positive_offset_rounds_the_tip_corners():
    """GEO-7: gaps at convex corners are filled with arcs of radius delta."""
    plain = gear_outline(GearParams(24.0))
    moved = gear_outline(GearParams(24.0, print_offset=0.2))
    assert len(moved.segments) == len(plain.segments) + 2 * 24
    kinds = [type(s) for s in moved.segments[:8]]
    assert kinds == [Spline, Spline, Arc, Arc, Arc, Spline, Spline, Arc]
    corner, tip, corner2 = moved.segments[2:5]
    assert corner.radius == corner2.radius == pytest.approx(0.2)
    assert tip.radius == pytest.approx(13.2)
    assert tip.sweep == pytest.approx(plain.segments[2].sweep)   # the tip arc only moves out
    assert corner.sweep > 0 and corner2.sweep > 0


def test_negative_offset_keeps_sharp_tip_corners():
    """GEO-7: overlaps are trimmed."""
    plain = gear_outline(GearParams(24.0))
    moved = gear_outline(GearParams(24.0, print_offset=-0.2))
    assert len(moved.segments) == len(plain.segments)
    assert moved.segments[2].radius == pytest.approx(12.8)
    assert moved.segments[2].sweep < plain.segments[2].sweep


def test_positive_offset_rounds_the_undercut_corner():
    """GEO-7, GEO-4"""
    moved = gear_outline(GearParams(10.0, print_offset=0.1))
    upper = moved.segments[5:9]   # after the tip arc: corner, flank, undercut corner, root curve
    assert [type(s) for s in upper] == [Arc, Spline, Arc, Spline]
    assert upper[2].radius == pytest.approx(0.1)


@pytest.mark.parametrize('offset', [0.1, -0.1])
def test_root_and_tip_circles_move_by_the_offset(offset):
    """DER-4, DER-5, GEO-7"""
    p = GearParams(24.0, print_offset=offset)
    radii = sorted({round(s.radius, 9) for s in gear_outline(p).segments
                    if isinstance(s, Arc) and s.center == (0.0, 0.0)})
    assert radii == pytest.approx([10.75 + offset, 13.0 + offset])
    assert derive(p).tip_diameter == pytest.approx(26.0 + 2 * offset)


@pytest.mark.parametrize('offset', [0.1, -0.1, 0.0])
def test_bore_is_not_affected_by_the_offset(offset):
    """GEO-7, GEO-11, D-20"""
    assert gear_outline(GearParams(24.0, bore=8.0, print_offset=offset)).holes[0].radius == 4.0


def test_area_grows_with_the_offset():
    """GEO-7: to first order the area changes by offset times perimeter."""
    plain = gear_outline(GearParams(24.0))
    pts = plain.sample(32)
    perimeter = sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))
    for offset in (0.05, -0.05):
        change = gear_outline(GearParams(24.0, print_offset=offset)).area() - plain.area()
        assert change == pytest.approx(offset * perimeter, rel=0.05)


def test_too_large_offsets_are_rejected_cleanly():
    with pytest.raises(GearError):
        gear_outline(GearParams(24.0, print_offset=2.0))
    with pytest.raises(GearError):
        gear_outline(GearParams(24.0, print_offset=-2.0))
