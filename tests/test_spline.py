"""Curve fitting, ACC-1 to ACC-3."""

import math

import pytest

from gearcore import GearParams
from gearcore.profile import ToothProfile
from gearcore.spline import Spline, fit, interpolate, max_deviation


def circle(t):
    return 10 * math.cos(t), 10 * math.sin(t)


@pytest.mark.parametrize('tolerance', [0.1, 0.01, 0.001, 0.0001])
def test_fit_stays_within_tolerance(tolerance):
    """ACC-1"""
    spline = fit(circle, 0.0, 2.0, tolerance)
    assert max_deviation(spline, circle, 0.0, 2.0) <= tolerance


def test_fit_end_points_are_exact():
    """ACC-3"""
    spline = fit(circle, 0.3, 1.7, 0.01)
    assert spline.start == circle(0.3)
    assert spline.end == circle(1.7)


def test_tighter_tolerance_needs_more_points():
    """ACC-2"""
    spans = [fit(circle, 0.0, 2.0, tol).span_count for tol in (0.1, 0.001, 0.00001)]
    assert spans == sorted(spans) and spans[0] < spans[-1]
    assert spans[0] == 2    # the smallest spline the fit produces


def test_fit_handles_the_start_of_an_involute():
    """ACC-1: the involute has zero radius of curvature on the base circle."""
    tooth = ToothProfile(GearParams(18.0))
    curve = tooth.involute
    for tolerance in (0.01, 0.0001):
        spline = fit(curve, tooth.t_tip, 0.0, tolerance,
                     tooth.involute_tangent(tooth.t_tip), tooth.involute_tangent(0.0))
        assert max_deviation(spline, curve, tooth.t_tip, 0.0) <= tolerance


def test_fit_uses_given_end_tangents():
    spline = fit(circle, 0.0, 1.0, 0.001, (0.0, 1.0), (-math.sin(1.0), math.cos(1.0)))
    p0, p1 = spline.control_points[:2]
    assert p1[0] - p0[0] == pytest.approx(0.0, abs=1e-12)
    assert p1[1] > p0[1]


def test_interpolate_passes_through_the_points_with_c2_continuity():
    pts = [circle(t) for t in (0.0, 0.2, 0.5, 0.6, 1.0)]
    spline = interpolate(pts, (0.0, 1.0), (-math.sin(1.0), math.cos(1.0)))
    assert spline.span_count == 4
    assert [spline.control_points[3 * i] for i in range(5)] == pytest.approx(pts)
    # NURBS form: degree 3, clamped, interior knots of multiplicity 3.
    assert len(spline.knots) == len(spline.control_points) + 4
    assert spline.knots[:4] == (0.0,) * 4 and len(set(spline.knots)) == 5
    for i in range(1, 4):
        a, b, c, d, e = spline.control_points[3 * i - 2:3 * i + 3]
        h0 = spline.knots[3 * i + 1] - spline.knots[3 * i]
        h1 = spline.knots[3 * i + 4] - spline.knots[3 * i + 1]
        for dim in (0, 1):
            # Equal first and second derivatives on both sides of the joint.
            assert (c[dim] - b[dim]) / h0 == pytest.approx((d[dim] - c[dim]) / h1, abs=1e-9)
            assert (c[dim] - 2 * b[dim] + a[dim]) / h0 ** 2 == pytest.approx(
                (e[dim] - 2 * d[dim] + c[dim]) / h1 ** 2, abs=1e-9)


def test_reversed_and_transformed():
    spline = fit(circle, 0.0, 1.0, 0.001)
    back = spline.reversed()
    assert back.start == spline.end and back.end == spline.start
    flat = lambda pts: [c for p in pts for c in p]
    assert flat(back.sample(4)) == pytest.approx(flat(spline.sample(4)[::-1]))
    assert back.knots[0] == 0.0 and back.knots[-1] == pytest.approx(spline.knots[-1])
    assert list(back.knots) == sorted(back.knots)

    turned = spline.transformed(math.pi / 2)
    assert turned.start == pytest.approx((0.0, 10.0))
    mirrored = spline.transformed(0.0, mirror=True)
    assert mirrored.end == pytest.approx((spline.end[0], -spline.end[1]))
    assert isinstance(mirrored, Spline) and mirrored.knots == spline.knots
