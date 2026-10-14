"""Meshing with another gear: DER-10, DER-11, VAL-16, VAL-18.

The main check places two real gear outlines by DER-11 at the DER-10 distance and
measures them: without backlash they must touch, with backlash each flank must
have a clearance of half of it.
"""

import dataclasses
import math

import pytest

from gearcore import (ERROR, WARNING, GearParams, gear_outline, ideal_center_distance, mesh_axis,
                      mesh_issues, rotation_for_axis)

DEG = math.pi / 180
FIT = 0.001   # fit tolerance of the outlines


def test_ideal_distance_without_shift_is_the_reference_distance():
    """DER-10"""
    assert ideal_center_distance(1.0, 20 * DEG, 20, 30, 0.0, 0.0) == pytest.approx(25.0)
    assert ideal_center_distance(2.0, 20 * DEG, 13, 31, 0.3, -0.3) == pytest.approx(44.0)


def test_ideal_distance_with_shift_matches_a_published_example():
    """DER-10. KHK gear technical reference, profile shifted spur gears: m = 3,
    alpha = 20 deg, z = 12 and 24, x = 0.6 and 0.36 give alpha_w = 26.0886 deg and
    a = 56.4999 mm."""
    assert ideal_center_distance(3.0, 20 * DEG, 12, 24, 0.6, 0.36) == pytest.approx(56.4999, abs=1e-3)


def test_ideal_distance_does_not_exist_for_very_negative_shift():
    """DER-10"""
    assert ideal_center_distance(1.0, 20 * DEG, 10, 10, -3.0, -3.0) is None


@pytest.mark.parametrize('mate_teeth, teeth', [(20, 30), (13, 31), (9, 9)])
def test_tooth_on_the_line_faces_a_gap(mate_teeth, teeth):
    """DER-11: the mate's tooth points at this gear, so this gear has a gap
    pointing back."""
    direction = 0.7
    axis = mesh_axis(direction, direction, mate_teeth, teeth)
    pitch = 2 * math.pi / teeth
    offset = ((direction + math.pi - axis) / pitch) % 1.0
    assert offset == pytest.approx(0.5)


def test_turning_the_mate_turns_this_gear_the_other_way():
    """DER-11: like rolling pitch circles, by z_mate / z as much."""
    mate_teeth, teeth, eps = 20, 30, 0.01
    a = mesh_axis(0.3, 0.1, mate_teeth, teeth)
    b = mesh_axis(0.3, 0.1 + eps, mate_teeth, teeth)
    pitch = 2 * math.pi / teeth
    turned = math.remainder(b - a, pitch)
    assert turned == pytest.approx(-eps * mate_teeth / teeth)


def test_rotation_for_axis():
    assert rotation_for_axis(0.0, 10) == 0.0
    assert rotation_for_axis(math.pi / 10, 10) == pytest.approx(0.5)
    assert rotation_for_axis(-math.pi / 10, 10) == pytest.approx(0.5)
    assert rotation_for_axis(2 * math.pi / 10 - 1e-15, 10) == 0.0


# ------------------------------------------------------------- real outlines --
def segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    u = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den))
    return math.hypot(a[0] + u * dx - p[0], a[1] + u * dy - p[1])


def inside(p, polygon):
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def placed(params, center, angle=0.0, mirror=False):
    """Outline points, optionally mirrored about the x axis (a plane whose normal
    points the other way), turned by angle and moved to center."""
    c, s = math.cos(angle), math.sin(angle)
    out = []
    for x, y in gear_outline(params).sample(24):
        if mirror:
            y = -y
        out.append((center[0] + x * c - y * s, center[1] + x * s + y * c))
    return out


def mesh_pair(z1, z2, x1, x2, backlash, mate_rotation, direction, mirror=False):
    """Mate at the origin, this gear placed by DER-11 at the DER-10 distance.
    Returns how deep this gear reaches into the mate, and the smallest gap,
    both near the line of centers."""
    m, alpha = 1.0, 20 * DEG
    mate = GearParams(z1 * m, module=m, profile_shift=x1, backlash=backlash, rotation=mate_rotation,
                      tolerance=FIT)
    a = ideal_center_distance(m, alpha, z1, z2, x1, x2)
    center = (a * math.cos(direction), a * math.sin(direction))
    axis = mesh_axis(direction, mate_rotation * 2 * math.pi / z1, z1, z2)
    # This gear's reference direction is the x axis, or its mirror image.
    rotation = rotation_for_axis(-axis if mirror else axis, z2)
    gear = dataclasses.replace(mate, diameter=z2 * m, profile_shift=x2, rotation=rotation)
    mate_pts = placed(mate, (0.0, 0.0))
    gear_pts = placed(gear, center, mirror=mirror)

    def near(pts):
        # Points around the contact zone: within 3 modules of the pitch point.
        px, py = (a * z1 / (z1 + z2) * math.cos(direction), a * z1 / (z1 + z2) * math.sin(direction))
        return [p for p in pts if math.hypot(p[0] - px, p[1] - py) < 3 * m]

    mate_near, gear_near = near(mate_pts), near(gear_pts)
    mate_edges = [(p, q) for p, q in zip(mate_pts, mate_pts[1:] + mate_pts[:1]) if p in mate_near]
    depth = max((min(segment_distance(p, *e) for e in mate_edges)
                 for p in gear_near if inside(p, mate_pts)), default=0.0)
    gap = min(min(segment_distance(p, *e) for e in mate_edges) for p in gear_near)
    return depth, gap


@pytest.mark.parametrize('z1, z2, x1, x2, mate_rotation, direction, mirror', [
    (20, 30, 0.0, 0.0, 0.0, 0.0, False),
    (20, 30, 0.0, 0.0, 0.37, 1.1, False),
    (13, 31, 0.3, -0.1, 0.21, -2.0, False),
    (9, 17, 0.4, 0.2, 0.6, 2.5, False),
    (20, 30, 0.0, 0.0, 0.37, 1.1, True),
])
def test_meshed_gears_touch_without_backlash(z1, z2, x1, x2, mate_rotation, direction, mirror):
    """DER-11, TST-2: at the ideal distance the flanks touch on both sides; the
    overlap is no deeper than the fit tolerance."""
    depth, gap = mesh_pair(z1, z2, x1, x2, 0.0, mate_rotation, direction, mirror)
    assert depth < 1.5 * FIT
    assert gap < 1.5 * FIT


@pytest.mark.parametrize('z1, z2, x1, x2, backlash', [(20, 30, 0.0, 0.0, 0.1), (9, 17, 0.4, 0.2, 0.05)])
def test_meshed_gears_have_half_the_backlash_on_each_flank(z1, z2, x1, x2, backlash):
    """DER-11, GEO-6, TST-2: centered in the backlash, each flank has j_bn / 2."""
    depth, gap = mesh_pair(z1, z2, x1, x2, backlash, 0.37, 0.8)
    assert depth == 0.0
    assert gap == pytest.approx(backlash / 2, abs=3 * FIT)


# ----------------------------------------------------------------- validation --
def test_module_and_pressure_angle_must_match():
    """VAL-16"""
    gear = GearParams(30.0)
    ids = [i.id for i in mesh_issues(gear, GearParams(20.0, module=1.25), 25.0)]
    assert ids == ['VAL-16']
    ids = [i.id for i in mesh_issues(gear, GearParams(20.0, pressure_angle=25 * DEG), 25.0)]
    assert ids == ['VAL-16']
    assert all(i.severity == ERROR for i in mesh_issues(gear, GearParams(20.0, module=2.0), 25.0))


def test_center_distance_warning():
    """VAL-18: more than 0.01 m off is a warning."""
    gear, mate = GearParams(30.0), GearParams(20.0)
    assert mesh_issues(gear, mate, 25.0) == []
    assert mesh_issues(gear, mate, 25.009) == []
    issues = mesh_issues(gear, mate, 25.02)
    assert [(i.id, i.severity) for i in issues] == [('VAL-18', WARNING)]
