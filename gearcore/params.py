"""Gear inputs (spec section 4). Lengths are in mm, angles in radians."""

import dataclasses
import math
import typing


@dataclasses.dataclass(frozen=True)
class GearParams:
    #: Diameter of the selected circle or arc, d_sel (IN-1).
    diameter: float
    #: Arc mode: angle covered by the selected arc. None for a full circle (IN-1).
    arc_span: typing.Optional[float] = None
    module: float = 1.0                         # IN-2
    pressure_angle: float = math.radians(20.0)  # IN-3
    addendum: float = 1.0                       # IN-4, h_a*
    dedendum: float = 1.25                      # IN-5, h_f*
    fillet: float = 0.38                        # IN-6, rho_f*
    profile_shift: float = 0.0                  # IN-7, x
    backlash: float = 0.0                       # IN-8, j_bn
    print_offset: float = 0.0                   # IN-9, delta
    #: Start rotation as a fraction of one tooth pitch, 0 <= p < 1 (IN-10).
    rotation: float = 0.0
    tolerance: float = 0.010                    # IN-11
    thickness: float = 5.0                      # IN-12, b
    bore: float = 0.0                           # IN-14, d_B


class GearError(ValueError):
    """The parameters do not describe a gear that can be generated."""
