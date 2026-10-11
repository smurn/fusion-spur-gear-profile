"""Validation (spec section 9 and the input ranges of section 4)."""

import dataclasses
import math

from .derived import derive, tooth_count
from .params import GearParams

ERROR, WARNING, INFO = 'error', 'warning', 'info'


@dataclasses.dataclass(frozen=True)
class Issue:
    id: str        # requirement id, e.g. 'VAL-3' or 'IN-2'
    severity: str  # ERROR, WARNING or INFO
    message: str


def max_fillet(p: GearParams) -> float:
    """Largest rho_f* that fits the rack tip land (VAL-5)."""
    a = p.pressure_angle
    return ((math.pi / 4 + p.backlash / (4 * p.module * math.cos(a)) - p.dedendum * math.tan(a))
            * math.cos(a) / (1 - math.sin(a)))


def _range_issues(p: GearParams):
    deg = math.degrees(p.pressure_angle)
    checks = (
        ('IN-1', p.diameter > 0, 'The selected curve has no diameter.'),
        ('IN-1', p.arc_span is None or 0 < p.arc_span < 2 * math.pi,
         'The arc must cover more than 0 and less than 360 degrees.'),
        ('IN-2', p.module > 0, 'Module must be greater than 0.'),
        ('IN-3', 10 - 1e-9 <= deg <= 35 + 1e-9, 'Pressure angle must be between 10 and 35 degrees.'),
        ('IN-4', p.addendum > 0, 'Addendum coefficient must be greater than 0.'),
        ('IN-5', p.dedendum > 0, 'Dedendum coefficient must be greater than 0.'),
        ('IN-6', p.fillet >= 0, 'Root fillet radius coefficient must not be negative.'),
        ('IN-8', p.backlash >= 0, 'Backlash must not be negative.'),
        ('IN-10', 0 <= p.rotation <= 1, 'Start rotation must be between 0 and 100 %.'),
        ('IN-11', 1e-4 - 1e-12 <= p.tolerance <= 0.1 + 1e-12,
         'Max profile deviation must be between 0.0001 and 0.1 mm.'),
        ('VAL-10', p.thickness > 0, 'Thickness must be greater than 0.'),
        ('IN-14', p.bore >= 0, 'Bore diameter must not be negative.'),
    )
    return [Issue(cid, ERROR, msg) for cid, ok, msg in checks if not ok]


def validate(p: GearParams) -> list:
    """All issues with the parameters. VAL-1 and VAL-12 need the design and are
    checked by the Fusion layer."""
    issues = _range_issues(p)
    if issues:
        return issues   # the derived values are meaningless
    d = derive(p)
    if tooth_count(p) < 3:
        return [Issue('VAL-2', ERROR, 'Fewer than 3 teeth: the curve is too small for this module.')]
    if d.generated_teeth == 0:
        issues.append(Issue('VAL-6', ERROR, 'The arc is too short for a complete tooth.'))
    if d.root_diameter <= 0:
        issues.append(Issue('VAL-4', ERROR, 'The root diameter is not positive.'))
    if p.fillet > max_fillet(p):
        issues.append(Issue('VAL-5', ERROR, 'The root fillet radius coefficient is too large: at '
                            'most {:.3f} fits the rack tip.'.format(max_fillet(p))))
    if d.tip_thickness is None or d.tip_thickness <= 0:
        issues.append(Issue('VAL-3', ERROR, 'The teeth are pointed: the flanks meet below the '
                            'tip circle.'))
    elif d.tip_thickness < 0.2 * p.module:
        issues.append(Issue('VAL-7', WARNING, 'Thin tooth tips: {:.3f} mm is less than 0.2 x '
                            'module.'.format(d.tip_thickness)))
    if p.bore > 0 and p.bore - 2 * p.print_offset >= d.root_diameter:
        issues.append(Issue('VAL-11', ERROR, 'The bore does not fit inside the root circle.'))
    if d.undercut:
        issues.append(Issue('VAL-8', INFO, 'Undercut: {} teeth is below the limit of {:.1f}.'.format(
            d.teeth, d.min_teeth)))
    return issues


def errors(p: GearParams) -> list:
    return [i for i in validate(p) if i.severity == ERROR]
