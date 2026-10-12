"""Exact curves of one half-tooth (GEO-1 to GEO-7).

Tooth frame: gear center at the origin, tooth axis along +X. The half-tooth is
on the +Y side and runs from the tooth axis (angle 0) to the gap center
(angle tau / 2): tip arc, flank (involute), root curve (trochoid), root arc.

Print offset (GEO-7). It applies to the toothed profile only: tip, flanks, root
curves and root circle. Moving that profile by delta along its normal is the same
as generating the gear with a rack that is shrunk by delta: the flank of the
rack moves in by delta, its tip is lowered by delta and its tip fillet keeps
its center and gets the radius rho - delta. The flank is then an involute of
the same base circle, turned by delta / r_b, and the root curve is the curve
parallel to the original one. A negative radius is meaningful here: it is the
parallel curve on the other side of the path of the fillet center. Generating
with that rack also trims the outline correctly where a negative offset makes
the flank and the root curve overlap.
Two places need more than that, both for a positive offset, where a convex
corner of the outline opens a gap that is filled with an arc of radius delta:
the tip corners, and the corner between flank and root curve of an undercut tooth.
"""

import dataclasses
import math
import typing

from .derived import derive, inv
from .params import GearError, GearParams

#: Arc that fills a corner: center, start angle, sweep. Its radius is the print offset.
CornerArc = typing.Tuple[typing.Tuple[float, float], float, float]


class ToothProfile:
    def __init__(self, p: GearParams):
        d = derive(p)
        m, a, delta = p.module, p.pressure_angle, p.print_offset
        self.teeth = d.teeth
        self.tau = 2 * math.pi / d.teeth
        self.r = d.reference_diameter / 2
        self.rb = d.base_diameter / 2
        self.ra = d.tip_diameter / 2     # includes the print offset
        self.rf = d.root_diameter / 2    # includes the print offset
        self.alpha = a
        self.delta = delta
        # Half tooth thickness angle at the reference circle (DER-6), plus the
        # turn of the involute caused by the print offset.
        psi = d.tooth_thickness / d.reference_diameter + delta / self.rb
        self._involute_turn = psi + inv(a)

        # The generating rack (GEO-1), in rack coordinates: u along the pitch line
        # from the centerline of a rack tooth, v from the pitch line away from the
        # gear center. The rack rolls on the reference circle.
        # Backlash thickens the rack tooth (GEO-6); profile shift moves its datum
        # line to v = x * m, which leaves the tip corner at the same u.
        rho = p.fillet * m
        #: Fillet radius of the shrunk rack; negative if the offset exceeds the fillet.
        self.rho = rho - delta
        #: Center of the tip fillet. The print offset does not move it.
        self.uc = (math.pi * m / 4 + p.backlash / (4 * math.cos(a)) - p.dedendum * m * math.tan(a)
                   - rho * (1 - math.sin(a)) / math.cos(a))
        self.vc = (p.profile_shift - p.dedendum) * m + rho
        if abs(self.vc) < 1e-9 * m:
            raise GearError('This profile shift puts the center of the rack fillet exactly on '
                            'the reference circle, where the root curve has a cusp. Change it '
                            'slightly.')
        if self.rf <= 0:
            raise GearError('The print offset is too large: nothing is left of the root circle.')
        #: Rack roll angles at which the fillet contact reaches the tip land and the flank.
        self.phi_root = self.uc / self.r
        self.phi_flank = (self.uc + self.vc / math.tan(a)) / self.r
        #: The end of the rack flank reaches below the base circle (DER-7, for this rack).
        self.undercut = -(self.vc - self.rho * math.sin(a)) > self.r * math.sin(a) ** 2 * (1 + 1e-12)

        base = ToothProfile(dataclasses.replace(p, print_offset=0.0)) if delta > 0 else None

        # Where the root curve meets the flank.
        #: Arc filling the corner between flank and root curve, if any.
        self.ridge: typing.Optional[CornerArc] = None
        if base is not None and base.corner_join:
            # Positive offset of an undercut tooth: flank and root curve are the
            # parallels of the original ones up to its corner, joined by an arc.
            self.phi_join = base.phi_join
            self.t_join = base.t_join + delta / self.rb
            self.corner_join = True
            center = base.trochoid(base.phi_join)
            self.ridge = _corner(center, self.involute(self.t_join), self.trochoid(self.phi_join))
        else:
            #: Rack roll angle at which the root curve meets the flank. Without
            #: undercut that is where the fillet ends and the two curves are tangent.
            #: With undercut the root curve cuts into the flank and crosses it (GEO-4).
            self.phi_join = self._undercut_crossing() if self.undercut else self.phi_flank
            #: The curves meet at a corner, not tangentially.
            self.corner_join = self.phi_join != self.phi_flank
            radius = math.hypot(*self.trochoid(self.phi_join))
            #: Involute roll parameter (tangent of the pressure angle) at the join.
            self.t_join = math.sqrt(max((radius / self.rb) ** 2 - 1, 0.0))
        #: Radius where the flank ends.
        self.r_join = self.rb * math.sqrt(1 + self.t_join ** 2)
        self._check_root_curve()

        # Where the flank meets the tip circle (GEO-5).
        #: Arc filling the tip corner, if any.
        self.tip_corner: typing.Optional[CornerArc] = None
        if base is not None:
            # Positive offset: the flank ends at the parallel of the original tip
            # corner, and the corner is rounded.
            self.t_tip = base.t_tip + delta / self.rb
            #: Polar angle where the tip arc ends.
            self.tip_angle = base.tip_angle
            center = (base.ra * math.cos(base.tip_angle), base.ra * math.sin(base.tip_angle))
            self.tip_corner = (center, base.tip_angle, math.pi / 2 - math.atan(base.t_tip))
        else:
            self.t_tip = math.sqrt(max((self.ra / self.rb) ** 2 - 1, 0.0))
            x, y = self.involute(self.t_tip)
            self.tip_angle = math.atan2(y, x)

    def _check_root_curve(self):
        """A parallel curve folds back on itself where the offset exceeds the radius
        of curvature of the original. Refuse that instead of returning a loop."""
        if self.rho >= 0:
            return   # an envelope of real fillet circles, checked by the undercut logic
        steps = 40
        span = self.phi_root - self.phi_join
        for i in range(steps):
            phi = self.phi_join + span * i / steps
            ahead = phi + span / steps * 1e-3
            moved = _minus(self.trochoid(ahead), self.trochoid(phi))
            center = _minus(self._fillet_center(ahead), self._fillet_center(phi))
            if moved[0] * center[0] + moved[1] * center[1] <= 0:
                raise GearError('The print offset is too large for the root of the gap.')

    def _fillet_center(self, phi: float):
        rho, self.rho = self.rho, 0.0
        try:
            return self.trochoid(phi)
        finally:
            self.rho = rho

    def _beyond_flank(self, phi: float):
        """Angle by which the root curve point lies on the gap side of the involute
        at the same radius. Negative: it cuts into the flank. None inside the base
        circle, where there is no involute."""
        x, y = self.trochoid(phi)
        rad = math.hypot(x, y)
        if rad < self.rb:
            return None
        t = math.sqrt((rad / self.rb) ** 2 - 1)
        return math.atan2(y, x) - (self._involute_turn - (t - math.atan(t)))

    def _undercut_crossing(self) -> float:
        """Roll angle where the root curve, coming up from the root circle, leaves
        the flank it has undercut (GEO-4)."""
        steps = 600
        last_phi, last = None, None
        for i in range(steps + 1):
            phi = self.phi_root + (self.phi_flank - self.phi_root) * i / steps
            gap = self._beyond_flank(phi)
            if gap is None:
                last_phi, last = None, None
                continue
            if last is not None and last < 0 <= gap:
                lo, hi = last_phi, phi
                for _ in range(60):
                    mid = (lo + hi) / 2
                    if self._beyond_flank(mid) < 0:
                        lo = mid
                    else:
                        hi = mid
                return (lo + hi) / 2
            last_phi, last = phi, gap
        # So little undercut that the crossing is not resolved: treat the curves
        # as tangent where the fillet ends.
        return self.phi_flank

    # -- exact curves ----------------------------------------------------------
    def involute(self, t: float):
        """Flank point for roll parameter t (GEO-2)."""
        rad = self.rb * math.sqrt(1 + t * t)
        ang = self._involute_turn - (t - math.atan(t))
        return rad * math.cos(ang), rad * math.sin(ang)

    def involute_tangent(self, t: float):
        """Unit tangent of the flank in the direction of decreasing t (tip to root)."""
        ang = self._involute_turn - t
        return -math.cos(ang), -math.sin(ang)

    def trochoid(self, phi: float):
        """Root curve point for rack roll angle phi (GEO-3): the envelope of the
        rack's tip fillet. Valid from phi_flank to phi_root; the outline uses it
        from phi_join."""
        r, vc = self.r, self.vc
        du = self.uc - r * phi
        n = math.hypot(vc, du)
        # The fillet touches the gear on the line through the pitch point and the
        # fillet center, on the side that faces the gear center: beyond the fillet
        # center if that lies inside the reference circle, before it otherwise.
        reach = self.rho if vc < 0 else -self.rho
        radial = (r + vc) + reach * vc / n
        tangential = du + reach * du / n
        x = radial * math.cos(phi) - tangential * math.sin(phi)
        y = radial * math.sin(phi) + tangential * math.cos(phi)
        # That is centered on the gap; turn it so the tooth axis is at angle 0.
        rad, ang = math.hypot(x, y), self.tau / 2 - math.atan2(y, x)
        return rad * math.cos(ang), rad * math.sin(ang)

    @property
    def root_angle(self) -> float:
        """Polar angle where the root curve meets the root circle."""
        return self.tau / 2 - self.phi_root


def _minus(a, b):
    return a[0] - b[0], a[1] - b[1]


def _corner(center, start, end) -> CornerArc:
    """Arc about `center` from `start` to `end`, the short way round."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return center, a0, sweep
