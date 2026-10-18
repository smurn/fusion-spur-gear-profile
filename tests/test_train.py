"""Gear trains in a layout sketch: TRN-3 to TRN-9, TRN-11, TRN-12, VAL-20, VAL-21, VAL-23."""

import math

import pytest

from gearcore import ERROR, WARNING, LayoutCurve, LayoutLine, mesh_axis, orientation

DEG = math.pi / 180


def circle(x, y, r):
    return LayoutCurve((x, y), r)


def polar(center, length, deg):
    return (center[0] + length * math.cos(deg * DEG), center[1] + length * math.sin(deg * DEG))


def start_line(curve, deg):
    return LayoutLine(curve.center, polar(curve.center, curve.radius, deg))


def ids(o):
    return [i.id for i in o.issues]


def meshes(curves, k, n, axes, module=1.0):
    """Whether two curves' tooth axes satisfy the pair rule, by the mesh condition
    u_k + u_n = 1/2 (mod 1) rather than by the rule itself."""
    zk, zn = (round(2 * curves[i].radius / module) for i in (k, n))
    beta = math.atan2(curves[n].center[1] - curves[k].center[1], curves[n].center[0] - curves[k].center[0])
    uk = ((beta - axes[k]) / (2 * math.pi / zk)) % 1.0
    un = ((beta + math.pi - axes[n]) / (2 * math.pi / zn)) % 1.0
    return abs(math.remainder(uk + un - 0.5, 1.0)) < 1e-9


# Train 1: A-B-C; train 2: D-E; F on A's center.
A = circle(0, 0, 10)
B = LayoutCurve(polar(A.center, 25, 20), 15)
C = LayoutCurve(polar(B.center, 25, 80), 10)
D = circle(-40, 0, 8)
E = LayoutCurve(polar(D.center, 20, -110), 12)
F = circle(0, 0, 6)
LAYOUT = [A, B, C, D, E, F]


def test_touching_circles_form_trains():
    """TRN-3, TRN-4: two trains on one sketch; F on A's center is not connected."""
    sizes = [orientation(LAYOUT, [], 1.0, k).train_size for k in range(6)]
    assert sizes == [3, 3, 3, 2, 2, 1]
    assert orientation(LAYOUT, [], 1.0, 1).touching == 2
    assert orientation(LAYOUT, [], 1.0, 5).touching == 0


def test_every_touching_pair_meshes():
    """TRN-6, TRN-7"""
    axes = {k: orientation(LAYOUT, [], 1.0, k).axis for k in range(5)}
    for k, n in ((0, 1), (1, 2), (3, 4)):
        assert meshes(LAYOUT, k, n, axes)


def test_without_start_line_the_first_circle_has_a_tooth_on_the_x_axis():
    """TRN-7"""
    o = orientation(LAYOUT, [], 1.0, 0)
    assert o.axis == 0.0 and not o.start_line
    assert orientation(LAYOUT, [], 1.0, 3).axis == 0.0   # D is first in its train


def test_start_line_sets_the_train_and_only_that_train():
    """TRN-5, TRN-7"""
    plain = {k: orientation(LAYOUT, [], 1.0, k).axis for k in range(5)}
    line = [start_line(B, 200)]
    o = orientation(LAYOUT, line, 1.0, 1)
    assert o.start_line and o.axis == pytest.approx(200 * DEG - 2 * math.pi)
    axes = {k: orientation(LAYOUT, line, 1.0, k).axis for k in range(5)}
    assert meshes(LAYOUT, 0, 1, axes) and meshes(LAYOUT, 1, 2, axes)
    assert axes[0] != pytest.approx(plain[0])
    assert (axes[3], axes[4]) == (plain[3], plain[4])   # the other train is untouched


def test_start_line_belongs_to_the_circle_it_ends_on():
    """TRN-5: on a common center, a line ending on F is F's, not A's."""
    o = orientation(LAYOUT, [start_line(F, 45)], 1.0, 5)
    assert o.start_line and o.axis == pytest.approx(45 * DEG)
    assert not orientation(LAYOUT, [start_line(F, 45)], 1.0, 0).start_line
    # A line from the center that ends beyond the circle is no start line.
    long_line = LayoutLine(A.center, polar(A.center, 14, 10))
    assert not orientation(LAYOUT, [long_line], 1.0, 0).start_line


def test_lone_circle_without_start_line_is_not_oriented():
    """TRN-10: the gear's own start rotation applies."""
    o = orientation(LAYOUT, [], 1.0, 5)
    assert o.axis is None and o.issues == []


def test_two_start_lines_in_a_train_fail_only_that_train():
    """VAL-20"""
    lines = [start_line(A, 30), start_line(C, 100)]
    o = orientation(LAYOUT, lines, 1.0, 1)
    assert o.axis is None and ids(o) == ['VAL-20'] and o.issues[0].severity == ERROR
    assert orientation(LAYOUT, lines, 1.0, 3).axis == 0.0


def test_touching_needs_tangency_within_a_micrometre():
    """TRN-3"""
    near = [circle(0, 0, 10), circle(25.0009, 0, 15)]
    assert orientation(near, [], 1.0, 0).train_size == 2
    apart = [circle(0, 0, 10), circle(25.002, 0, 15)]
    assert orientation(apart, [], 1.0, 0).train_size == 1


def test_inside_touching_does_not_count():
    """TRN-3: an internal contact is no mesh."""
    curves = [circle(0, 0, 20), circle(10, 0, 10)]
    assert orientation(curves, [], 1.0, 0).train_size == 1


def test_arc_touches_only_where_it_runs():
    """TRN-3: the touching point must lie on the arc."""
    facing = LayoutCurve((25, 0), 15, start=150 * DEG, sweep=60 * DEG)    # covers 180 deg
    away = LayoutCurve((25, 0), 15, start=-30 * DEG, sweep=60 * DEG)      # covers 0 deg
    assert orientation([A, facing], [], 1.0, 0).train_size == 2
    assert orientation([A, away], [], 1.0, 0).train_size == 1


def test_near_miss_warns():
    """TRN-11, VAL-23: within 0.25 m of touching, and only for the train concerned."""
    curves = [circle(0, 0, 10), circle(25.2, 0, 15), circle(100, 0, 10)]
    o = orientation(curves, [], 1.0, 0)
    assert ids(o) == ['VAL-23'] and o.issues[0].severity == WARNING
    assert orientation(curves, [], 1.0, 2).issues == []
    assert orientation([circle(0, 0, 10), circle(25.3, 0, 15)], [], 1.0, 0).issues == []
    assert ids(orientation([circle(0, 0, 10), circle(25.3, 0, 15)], [], 2.0, 0)) == ['VAL-23']


def test_square_loop_meshes():
    """TRN-8: four equal gears on the corners of a square mesh all round."""
    curves = [circle(0, 0, 12), circle(24, 0, 12), circle(24, 24, 12), circle(0, 24, 12)]
    axes = {}
    for k in range(4):
        o = orientation(curves, [], 1.0, k)
        assert o.issues == [] and o.train_size == 4
        axes[k] = o.axis
    for k in range(4):
        assert meshes(curves, k, (k + 1) % 4, axes)


def test_triangle_loop_that_does_not_mesh_fails():
    """TRN-8, VAL-21: three equal 24-tooth gears touching each other cannot all mesh."""
    curves = [circle(0, 0, 12), LayoutCurve(polar((0, 0), 24, 0), 12), LayoutCurve(polar((0, 0), 24, 60), 12)]
    o = orientation(curves, [], 1.0, 1)
    assert o.axis is None and ids(o) == ['VAL-21']


def test_tooth_counts_use_this_gears_module():
    """TRN-9: with module 2 the same circles have half the teeth."""
    curves = [circle(0, 0, 10), circle(25, 0, 15)]
    axis = orientation(curves, [], 2.0, 1).axis
    assert axis == pytest.approx(mesh_axis(0.0, 0.0, 10, 15))


def test_circles_too_small_for_a_gear_are_left_out():
    """TRN-9"""
    curves = [circle(0, 0, 10), circle(11, 0, 1)]   # 2 teeth at module 1
    assert orientation(curves, [], 1.0, 0).train_size == 1


def test_an_arc_knows_its_mates():
    """TRN-12: the curves it touches, with their direction and radius."""
    arc = LayoutCurve((0, 0), 10, start=-90 * DEG, sweep=180 * DEG)
    right = circle(15, 0, 5)
    up = LayoutCurve(polar((0, 0), 18, 60), 8)
    behind = circle(-15, 0, 5)     # touches the full circle, but not the arc
    o = orientation([right, up, behind, arc], [], 1.0, 3)
    assert sorted((round(d / DEG, 6), r) for d, r in o.mates) == [(0.0, 5), (60.0, 8)]
    assert orientation([right, behind], [], 1.0, 0).mates == []
