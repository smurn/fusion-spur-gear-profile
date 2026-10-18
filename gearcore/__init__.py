"""Gear math for the Spur Gear add-in. Pure Python, no Fusion imports (ARC-1).

Lengths are in mm, angles in radians.
"""

from .derived import Derived, derive, tooth_axes, tooth_count
from .extent import ONE_SIDE, SYMMETRIC, TWO_SIDES, Side, extent_issues, span
from .mesh import mesh_axis, rotation_for_axis
from .outline import Arc, Circle, Line, Outline, gear_outline
from .params import GearError, GearParams
from .spline import Spline
from .train import LayoutCurve, LayoutLine, Orientation, orientation
from .validation import ERROR, INFO, WARNING, Issue, errors, validate

__all__ = ['Arc', 'Circle', 'Derived', 'ERROR', 'GearError', 'GearParams', 'INFO', 'Issue',
           'LayoutCurve', 'LayoutLine', 'Line', 'ONE_SIDE', 'Orientation', 'Outline', 'SYMMETRIC',
           'Side', 'Spline', 'TWO_SIDES', 'WARNING', 'derive', 'errors', 'extent_issues',
           'gear_outline', 'mesh_axis', 'orientation', 'rotation_for_axis', 'span', 'tooth_axes',
           'tooth_count', 'validate']
