"""Exact curves of one half-tooth (GEO-1 to GEO-6).

Tooth frame: gear center at the origin, tooth axis along +X. The half-tooth is
on the +Y side and runs from the tooth axis (angle 0) to the gap center
(angle tau / 2): tip arc, flank (involute), root curve (trochoid), root arc.
"""

import math

from .derived import derive, inv
from .params import GearError, GearParams


class ToothProfile:
    def __init__(self, p: GearParams):
        d = derive(p)
        m, a = p.module, p.pressure_angle
        self.teeth = d.teeth
        self.tau = 2 * math.pi / d.teeth
        self.r = d.reference_diameter / 2
        self.rb = d.base_diameter / 2
        self.ra = d.tip_diameter / 2
        self.rf = d.root_diameter / 2
        self.rho = p.fillet * m
        self.alpha = a
        # Half tooth thickness angle at the reference circle (DER-6).
        self.psi = d.tooth_thickness / d.reference_diameter

        # The generating rack (GEO-1), in rack coordinates: u along the pitch line
        # from the centerline of a rack tooth, v from the pitch line away from the
        # gear center. The rack rolls on the reference circle.
        # Backlash thickens the rack tooth (GEO-6); profile shift moves its datum
        # line to v = x * m, which leaves the tip corner at the same u.
        half_width = math.pi * m / 4 + p.backlash / (4 * math.cos(a))
        #: Center of the tip fillet.
        self.uc = half_width - p.dedendum * m * math.tan(a) - self.rho * (1 - math.sin(a)) / math.cos(a)
        self.vc = -(p.dedendum - p.profile_shift) * m + self.rho
        if self.vc >= 0:
            raise GearError('The profile shift is too large: the rack fillet lies outside the '
                            'reference circle.')
        #: Rack roll angles at which the fillet contact reaches the tip land and the flank.
        self.phi_root = self.uc / self.r
        self.phi_flank = (self.uc + self.vc / math.tan(a)) / self.r

        self.undercut = d.undercut
        #: Rack roll angle at which the root curve meets the flank. Without undercut
        #: that is where the fillet ends and the two curves are tangent. With
        #: undercut the root curve cuts into the flank and crosses it (GEO-4).
        self.phi_join = self._undercut_crossing() if self.undercut else self.phi_flank
        #: Radius of that point, and the involute roll parameters (tangent of the
        #: pressure angle) there and at the tip.
        self.r_join = math.hypot(*self.trochoid(self.phi_join))
        self.t_join = math.sqrt(max((self.r_join / self.rb) ** 2 - 1, 0.0))
        self.t_tip = math.sqrt(max((self.ra / self.rb) ** 2 - 1, 0.0))

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

    @property
    def _involute_turn(self) -> float:
        return self.psi + inv(self.alpha)

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
        # Fillet center plus rho along the line from the pitch point through it.
        radial = (r + vc) + self.rho * vc / n
        tangential = du + self.rho * du / n
        x = radial * math.cos(phi) - tangential * math.sin(phi)
        y = radial * math.sin(phi) + tangential * math.cos(phi)
        # That is centered on the gap; turn it so the tooth axis is at angle 0.
        rad, ang = math.hypot(x, y), self.tau / 2 - math.atan2(y, x)
        return rad * math.cos(ang), rad * math.sin(ang)

    @property
    def tip_angle(self) -> float:
        """Polar angle where the flank meets the tip circle."""
        x, y = self.involute(self.t_tip)
        return math.atan2(y, x)

    @property
    def root_angle(self) -> float:
        """Polar angle where the root curve meets the root circle."""
        return self.tau / 2 - self.phi_root
