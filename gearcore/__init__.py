"""Gear math for the Spur Gear add-in. Pure Python, no Fusion imports (ARC-1).

Lengths are in mm, angles in radians.
"""

from .derived import Derived, derive, tooth_axes, tooth_count
from .mesh import mesh_axis, rotation_for_axis
from .outline import Arc, Circle, Line, Outline, gear_outline
from .params import GearError, GearParams
from .spline import Spline
from .validation import ERROR, INFO, WARNING, Issue, errors, validate

__all__ = ['Arc', 'Circle', 'Derived', 'ERROR', 'GearError', 'GearParams', 'INFO', 'Issue', 'Line',
           'Outline', 'Spline', 'WARNING', 'derive', 'errors', 'gear_outline',
           'mesh_axis', 'rotation_for_axis', 'tooth_axes',
           'tooth_count', 'validate']
