"""Gear math for the Spur Gear add-in. Pure Python, no Fusion imports (ARC-1).

Lengths are in mm, angles in radians.
"""

from .derived import Derived, derive, tooth_count
from .outline import Arc, Outline, gear_outline
from .params import GearError, GearParams
from .spline import Spline
from .validation import ERROR, INFO, WARNING, Issue, errors, validate

__all__ = ['Arc', 'Derived', 'ERROR', 'GearError', 'GearParams', 'INFO', 'Issue', 'Outline',
           'Spline', 'WARNING', 'derive', 'errors', 'gear_outline', 'tooth_count', 'validate']
