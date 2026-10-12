"""Cubic splines that approximate exact curves within a tolerance (ACC-1, ACC-2)."""

import dataclasses
import math
import typing

Point = typing.Tuple[float, float]
CurveFn = typing.Callable[[float], Point]


@dataclasses.dataclass(frozen=True)
class Spline:
    """A C2 cubic spline stored as connected Bezier segments.

    Segment i uses control_points[3i : 3i + 4]. Together with `knots` this is a
    degree-3 NURBS curve with unit weights: the knots are clamped and every
    interior knot has multiplicity 3."""
    control_points: typing.Tuple[Point, ...]
    knots: typing.Tuple[float, ...]
    degree: int = 3

    @property
    def start(self) -> Point:
        return self.control_points[0]

    @property
    def end(self) -> Point:
        return self.control_points[-1]

    @property
    def span_count(self) -> int:
        return (len(self.control_points) - 1) // 3

    def span_point(self, span: int, u: float) -> Point:
        """Point on segment `span` at local parameter u in [0, 1]."""
        p0, p1, p2, p3 = self.control_points[3 * span:3 * span + 4]
        w = ((1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3)
        return (w[0] * p0[0] + w[1] * p1[0] + w[2] * p2[0] + w[3] * p3[0],
                w[0] * p0[1] + w[1] * p1[1] + w[2] * p2[1] + w[3] * p3[1])

    def sample(self, per_span: int = 16) -> typing.List[Point]:
        pts = [self.start]
        for span in range(self.span_count):
            pts += [self.span_point(span, k / per_span) for k in range(1, per_span + 1)]
        return pts

    def reversed(self) -> 'Spline':
        last = self.knots[-1]
        return Spline(self.control_points[::-1], tuple(last - k for k in reversed(self.knots)))

    def transformed(self, angle: float = 0.0, mirror: bool = False) -> 'Spline':
        """Mirror about the X axis (optional), then rotate about the origin. The
        direction of travel is kept; use reversed() to keep an outline consistent."""
        c, s = math.cos(angle), math.sin(angle)
        sign = -1.0 if mirror else 1.0
        return Spline(tuple((x * c - sign * y * s, x * s + sign * y * c)
                            for x, y in self.control_points), self.knots)


def dist_to_polyline(p: Point, poly: typing.Sequence[Point]) -> float:
    px, py = p
    best = float('inf')
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        u = 0.0 if den == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
        ex, ey = ax + u * dx - px, ay + u * dy - py
        best = min(best, ex * ex + ey * ey)
    return math.sqrt(best)


def _unit(v: Point) -> Point:
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def _numeric_tangent(curve: CurveFn, t: float, toward: float) -> Point:
    """Unit direction of travel at t, for travel from t towards `toward`."""
    eps = (toward - t) * 1e-6
    a, b = curve(t), curve(t + eps)
    return _unit((b[0] - a[0], b[1] - a[1]))


def interpolate(points: typing.Sequence[Point], tangent0: Point, tangent1: Point) -> Spline:
    """C2 cubic spline through the points, chord-length parametrized, with the
    given unit end tangents."""
    n = len(points)
    h = [math.dist(points[i], points[i + 1]) for i in range(n - 1)]
    derivs = []
    for dim in (0, 1):
        y = [p[dim] for p in points]
        # Tridiagonal system for the derivatives at the points (Thomas algorithm).
        lower, diag, upper, rhs = [0.0] * n, [1.0] * n, [0.0] * n, [0.0] * n
        rhs[0], rhs[n - 1] = tangent0[dim], tangent1[dim]
        for i in range(1, n - 1):
            lower[i], diag[i], upper[i] = h[i], 2 * (h[i - 1] + h[i]), h[i - 1]
            rhs[i] = 3 * (h[i] * (y[i] - y[i - 1]) / h[i - 1] + h[i - 1] * (y[i + 1] - y[i]) / h[i])
        for i in range(1, n):
            f = lower[i] / diag[i - 1]
            diag[i] -= f * upper[i - 1]
            rhs[i] -= f * rhs[i - 1]
        d = [0.0] * n
        d[n - 1] = rhs[n - 1] / diag[n - 1]
        for i in range(n - 2, -1, -1):
            d[i] = (rhs[i] - upper[i] * d[i + 1]) / diag[i]
        derivs.append(d)
    cps, knots, u = [tuple(points[0])], [0.0] * 4, 0.0
    for i in range(n - 1):
        cps.append((points[i][0] + h[i] * derivs[0][i] / 3, points[i][1] + h[i] * derivs[1][i] / 3))
        cps.append((points[i + 1][0] - h[i] * derivs[0][i + 1] / 3,
                    points[i + 1][1] - h[i] * derivs[1][i + 1] / 3))
        cps.append(tuple(points[i + 1]))
        u += h[i]
        knots += [u] * (3 if i < n - 2 else 4)
    return Spline(tuple(cps), tuple(knots))


def _span_deviation(spline: Spline, span: int, curve: CurveFn, ta: float, tb: float) -> float:
    exact = [curve(ta + (tb - ta) * k / 64) for k in range(65)]
    return max(dist_to_polyline(spline.span_point(span, k / 16), exact) for k in range(1, 16))


def fit(curve: CurveFn, t0: float, t1: float, tolerance: float,
        tangent0: typing.Optional[Point] = None,
        tangent1: typing.Optional[Point] = None) -> Spline:
    """Spline from curve(t0) to curve(t1) that stays within `tolerance` of the
    exact curve. Points are added where the deviation is largest, so the spline
    uses few of them (ACC-2). The end points are exact (ACC-3).

    tangent0 and tangent1 are unit directions of travel at the ends; they are
    estimated numerically if not given."""
    tangent0 = tangent0 or _numeric_tangent(curve, t0, t1)
    if tangent1 is None:
        back = _numeric_tangent(curve, t1, t0)
        tangent1 = (-back[0], -back[1])
    # The deviation is only sampled, so aim a little below the tolerance.
    target = 0.9 * tolerance
    ts = [t0, (t0 + t1) / 2, t1]
    for _ in range(12):
        spline = interpolate([curve(t) for t in ts], tangent0, tangent1)
        bad = [i for i in range(len(ts) - 1)
               if _span_deviation(spline, i, curve, ts[i], ts[i + 1]) > target]
        if not bad:
            return spline
        for i in reversed(bad):
            ts.insert(i + 1, (ts[i] + ts[i + 1]) / 2)
    raise ArithmeticError('curve fit did not reach the tolerance of {} mm'.format(tolerance))


def max_deviation(spline: Spline, curve: CurveFn, t0: float, t1: float, samples: int = 4000) -> float:
    """Independent check of ACC-1: largest distance of the spline from the curve."""
    exact = [curve(t0 + (t1 - t0) * k / samples) for k in range(samples + 1)]
    return max(dist_to_polyline(p, exact) for p in spline.sample(12))
