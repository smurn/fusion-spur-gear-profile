"""Throwaway gear math for the feasibility spikes (docs/spec.md section 12).

This is NOT the start of `gearcore`. It covers only what the spikes need: an
external gear without undercut, profile shift, backlash or print offset.

All lengths are in mm. The half-tooth lives in the "tooth frame": gear center
at the origin, tooth axis along +X, half-tooth on the +Y side, running from the
tooth axis (angle 0) to the gap center (angle tau/2).

Run `python spike_geom.py` for the self-checks.
"""

import math


def inv(phi):
    return math.tan(phi) - phi


class Gear:
    def __init__(self, m=1.0, z=24, alpha_deg=20.0, ha=1.0, hf=1.25, rho=0.38):
        self.m, self.z = m, z
        self.alpha = a = math.radians(alpha_deg)
        self.tau = 2 * math.pi / z
        self.r = m * z / 2
        self.rb = self.r * math.cos(a)
        self.ra = self.r + m * ha
        self.rf = self.r - m * hf
        self.rho = rho * m
        # Rack tip fillet center, in rack coordinates: u along the pitch line
        # from the rack tooth centerline, v radial from the pitch line.
        self.uc = (math.pi * m / 4 - hf * m * math.tan(a)
                   - self.rho * (1 - math.sin(a)) / math.cos(a))
        self.vc = -hf * m + self.rho
        if self.uc < 0:
            raise ValueError('rack fillet does not fit (VAL-5)')
        # Roll angles where the fillet meets the rack tip land and the flank.
        self.phi_root = self.uc / self.r
        self.phi_flank = (self.uc + self.vc / math.tan(a)) / self.r
        # Involute roll parameter t = tan(pressure angle at that radius).
        self.r_join = math.hypot(*self.trochoid(self.phi_flank))
        if self.r_join < self.rb:
            raise ValueError('undercut: not supported by the spike math')
        self.t_tip = math.sqrt((self.ra / self.rb) ** 2 - 1)
        self.t_join = math.sqrt((self.r_join / self.rb) ** 2 - 1)
        self.psi = math.pi / (2 * z)  # half tooth thickness angle at r

    # -- exact curves, tooth frame ------------------------------------------
    def involute(self, t):
        """Point on the flank for roll parameter t (t_join..t_tip)."""
        rad = self.rb * math.sqrt(1 + t * t)
        ang = self.psi + inv(self.alpha) - (t - math.atan(t))
        return rad * math.cos(ang), rad * math.sin(ang)

    def trochoid(self, phi):
        """Point on the root curve for rack roll angle phi (phi_flank..phi_root)."""
        r, uc, vc = self.r, self.uc, self.vc
        er = (math.cos(phi), math.sin(phi))
        et = (-math.sin(phi), math.cos(phi))
        du = uc - r * phi
        n = math.hypot(vc, du)
        # Fillet center plus rho along the line from the pitch point.
        kr = (r + vc) + self.rho * vc / n
        kt = du + self.rho * du / n
        x = kr * er[0] + kt * et[0]
        y = kr * er[1] + kt * et[1]
        # Gap frame to tooth frame: mirror so the tooth axis is at angle 0.
        ang = self.tau / 2 - math.atan2(y, x)
        rad = math.hypot(x, y)
        return rad * math.cos(ang), rad * math.sin(ang)

    def tip_angle(self):
        """Polar angle where the flank meets the tip circle."""
        return math.atan2(*reversed(self.involute(self.t_tip)))

    def root_angle(self):
        """Polar angle where the root curve meets the root circle."""
        return self.tau / 2 - self.phi_root

    # -- fit points ---------------------------------------------------------
    def involute_points(self, n, spacing='arc'):
        """n points from the tip down to the join. spacing: 'roll' or 'arc'."""
        pts = []
        for i in range(n):
            s = i / (n - 1)
            if spacing == 'roll':
                t = self.t_tip + (self.t_join - self.t_tip) * s
            else:  # arc length of an involute grows with t squared
                t2 = self.t_tip ** 2 + (self.t_join ** 2 - self.t_tip ** 2) * s
                t = math.sqrt(max(t2, 0.0))
            pts.append(self.involute(t))
        return pts

    def trochoid_points(self, n):
        """n points from the join down to the root circle, even in roll angle."""
        return [self.trochoid(self.phi_flank + (self.phi_root - self.phi_flank) * i / (n - 1))
                for i in range(n)]

    # -- dense polylines for deviation checks -------------------------------
    def involute_polyline(self, n=600):
        return self.involute_points(n, 'arc')

    def trochoid_polyline(self, n=400):
        return self.trochoid_points(n)

    def half_outline(self, n_inv=500, n_tro=350, n_arc=40):
        """Dense polyline of the half-tooth: tip arc, flank, root curve, root arc."""
        a_tip, a_root = self.tip_angle(), self.root_angle()
        pts = [(self.ra * math.cos(a_tip * i / n_arc), self.ra * math.sin(a_tip * i / n_arc))
               for i in range(n_arc)]
        pts += self.involute_polyline(n_inv)
        pts += self.trochoid_polyline(n_tro)[1:]
        for i in range(1, n_arc + 1):
            a = a_root + (self.tau / 2 - a_root) * i / n_arc
            pts.append((self.rf * math.cos(a), self.rf * math.sin(a)))
        return pts

    def fold(self, x, y):
        """Map any point of the full gear outline onto the half-tooth."""
        rad = math.hypot(x, y)
        ang = math.atan2(y, x) % self.tau
        if ang > self.tau / 2:
            ang = self.tau - ang
        return rad * math.cos(ang), rad * math.sin(ang)

    def area(self):
        """Area enclosed by the full gear outline (shoelace on the dense outline)."""
        half = self.half_outline()
        tooth = [(x, -y) for x, y in reversed(half)] + half[1:]
        a = 0.0
        for (x0, y0), (x1, y1) in zip(tooth, tooth[1:]):
            a += x0 * y1 - x1 * y0
        return self.z * a / 2


def dist_to_polyline(p, poly):
    """Smallest distance from point p to the polyline."""
    px, py = p
    best = float('inf')
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        u = 0.0 if den == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
        ex, ey = ax + u * dx - px, ay + u * dy - py
        d = ex * ex + ey * ey
        if d < best:
            best = d
    return math.sqrt(best)


def max_deviation(points, poly):
    return max(dist_to_polyline(p, poly) for p in points)


# -- pure-Python cubic interpolation, to compare with Fusion's fitted spline --
def _solve(a, b):
    n = len(b)
    a = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda i: abs(a[i][c]))
        a[c], a[p] = a[p], a[c]
        for i in range(c + 1, n):
            f = a[i][c] / a[c][c]
            for k in range(c, n + 1):
                a[i][k] -= f * a[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (a[i][n] - sum(a[i][k] * x[k] for k in range(i + 1, n))) / a[i][i]
    return x


def cubic_spline_samples(pts, per_span=30, param='chord', end='natural'):
    """Sample a C2 cubic spline through pts. param: chord|centripetal|uniform,
    end: natural|notaknot."""
    n = len(pts)
    if n < 3 or (end == 'notaknot' and n < 4):
        end = 'natural'
    exp = {'chord': 1.0, 'centripetal': 0.5, 'uniform': 0.0}[param]
    h = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) ** exp
         for i in range(n - 1)]
    out = None
    for dim in (0, 1):
        y = [p[dim] for p in pts]
        a = [[0.0] * n for _ in range(n)]
        b = [0.0] * n
        for i in range(1, n - 1):
            a[i][i - 1], a[i][i], a[i][i + 1] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
            b[i] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
        if end == 'natural':
            a[0][0] = a[n - 1][n - 1] = 1.0
        else:
            a[0][0], a[0][1], a[0][2] = h[1], -(h[0] + h[1]), h[0]
            a[n - 1][n - 3], a[n - 1][n - 2], a[n - 1][n - 1] = h[n - 2], -(h[n - 3] + h[n - 2]), h[n - 3]
        mm = _solve(a, b)
        vals = []
        for i in range(n - 1):
            for k in range(per_span + (1 if i == n - 2 else 0)):
                s = h[i] * k / per_span
                c1 = (y[i + 1] - y[i]) / h[i] - h[i] * (2 * mm[i] + mm[i + 1]) / 6
                vals.append(y[i] + c1 * s + mm[i] / 2 * s ** 2
                            + (mm[i + 1] - mm[i]) / (6 * h[i]) * s ** 3)
        out = vals if out is None else list(zip(out, vals))
    return out


def _self_check():
    for m, z in ((1, 18), (1, 24), (1, 100), (5, 24), (1, 200)):
        g = Gear(m=m, z=z)
        # Involute points satisfy the involute equation of the base circle.
        for t in (g.t_join, (g.t_join + g.t_tip) / 2, g.t_tip):
            x, y = g.involute(t)
            rad = math.hypot(x, y)
            want = g.psi + inv(g.alpha) - inv(math.acos(g.rb / rad))
            assert abs(math.atan2(y, x) - want) < 1e-12, (z, t)
        # Tooth thickness at the reference circle is pi*m/2 (DER-6, x = 0).
        t_ref = math.tan(g.alpha)
        x, y = g.involute(t_ref)
        assert abs(2 * math.atan2(y, x) * g.r - math.pi * m / 2) < 1e-9
        # The root curve starts on the flank, tangent to it, and ends on the
        # root circle, tangent to it.
        j_tro, j_inv = g.trochoid(g.phi_flank), g.involute(g.t_join)
        assert math.hypot(j_tro[0] - j_inv[0], j_tro[1] - j_inv[1]) < 1e-9 * m, z
        e = 1e-6
        d_tro = [b - a for a, b in zip(j_tro, g.trochoid(g.phi_flank + e))]
        d_inv = [b - a for a, b in zip(j_inv, g.involute(g.t_join - e))]
        cross = d_tro[0] * d_inv[1] - d_tro[1] * d_inv[0]
        assert abs(cross) / (math.hypot(*d_tro) * math.hypot(*d_inv)) < 1e-4, z
        x, y = g.trochoid(g.phi_root)
        assert abs(math.hypot(x, y) - g.rf) < 1e-9 * m
        assert abs(math.atan2(y, x) - g.root_angle()) < 1e-12
        # The root curve never dips below the root circle.
        assert min(math.hypot(*p) for p in g.trochoid_polyline()) > g.rf - 1e-9 * m
        # Area lies between the root and tip discs; folding maps onto the half-tooth.
        assert math.pi * g.rf ** 2 < g.area() < math.pi * g.ra ** 2
        half = g.half_outline()
        k = 5 % z
        c, s = math.cos(k * g.tau), math.sin(k * g.tau)
        for x, y in half[::97]:
            assert dist_to_polyline(g.fold(x * c + y * s, x * s - y * c), half) < 1e-9 * m
        print('ok  m={} z={:3d}  r_join={:.4f} rb={:.4f} rf={:.4f} area={:.3f}'.format(
            m, z, g.r_join, g.rb, g.rf, g.area()))
    # A cubic spline through points of a circle stays close to the circle.
    circ = [(math.cos(a / 10), math.sin(a / 10)) for a in range(8)]
    for end in ('natural', 'notaknot'):
        dev = max(abs(math.hypot(*p) - 1) for p in cubic_spline_samples(circ, end=end))
        assert dev < 1e-3, (end, dev)
    print('all checks passed')


if __name__ == '__main__':
    _self_check()
