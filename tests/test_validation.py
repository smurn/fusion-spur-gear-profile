"""Validation, spec section 9 and the input ranges of section 4."""

import math

import pytest

from gearcore import ERROR, INFO, WARNING, GearParams, errors, validate
from gearcore.validation import max_fillet


def ids(params, severity=None):
    return {i.id for i in validate(params) if severity is None or i.severity == severity}


def test_defaults_are_valid():
    assert validate(GearParams(24.0)) == []


@pytest.mark.parametrize('params, issue', [
    (GearParams(2.4), 'VAL-2'),                              # 2 teeth
    (GearParams(24.0, profile_shift=2.0), 'VAL-3'),          # pointed
    (GearParams(24.0, addendum=0.1, profile_shift=-2.0), 'VAL-3'),   # tip inside the base circle
    (GearParams(3.0, dedendum=2.0), 'VAL-4'),
    (GearParams(24.0, fillet=0.5), 'VAL-5'),
    (GearParams(24.0, thickness=0.0), 'VAL-10'),
    (GearParams(24.0, bore=21.5), 'VAL-11'),
    (GearParams(24.0, bore=21.4, print_offset=-0.1), 'VAL-11'),   # the root circle shrinks to 21.3
    (GearParams(0.0), 'IN-1'),
    (GearParams(24.0, arc_span=0.0), 'IN-1'),
    (GearParams(24.0, module=0.0), 'IN-2'),
    (GearParams(24.0, pressure_angle=math.radians(9)), 'IN-3'),
    (GearParams(24.0, pressure_angle=math.radians(36)), 'IN-3'),
    (GearParams(24.0, addendum=0.0), 'IN-4'),
    (GearParams(24.0, dedendum=0.0), 'IN-5'),
    (GearParams(24.0, fillet=-0.1), 'IN-6'),
    (GearParams(24.0, backlash=-0.1), 'IN-8'),
    (GearParams(24.0, rotation=1.5), 'IN-10'),
    (GearParams(24.0, tolerance=0.2), 'IN-11'),
    (GearParams(24.0, tolerance=0.00001), 'IN-11'),
    (GearParams(24.0, bore=-1.0), 'IN-14'),
])
def test_errors(params, issue):
    assert issue in ids(params, ERROR)
    assert errors(params)


@pytest.mark.parametrize('params', [
    GearParams(24.0, pressure_angle=math.radians(10)),
    GearParams(24.0, pressure_angle=math.radians(35), dedendum=1.0, fillet=0.1),
    GearParams(24.0, rotation=1.0),
    GearParams(24.0, tolerance=0.0001),
    GearParams(24.0, tolerance=0.1),
    GearParams(24.0, bore=21.4),
    GearParams(100.0, profile_shift=1.2),
])
def test_range_limits_are_inclusive(params):
    assert errors(params) == []


def test_three_teeth_is_the_minimum():
    """VAL-2"""
    assert 'VAL-2' not in ids(GearParams(3.0))
    assert 'VAL-2' in ids(GearParams(2.4))


def test_thin_tip_is_a_warning():
    """VAL-7: s_a < 0.2 m is 0.1967 mm at x = 1.1 for z = 24."""
    assert ids(GearParams(24.0, profile_shift=1.0)) == set()
    assert ids(GearParams(24.0, profile_shift=1.1)) == {'VAL-7'}
    assert ids(GearParams(24.0, profile_shift=1.1), WARNING) == {'VAL-7'}


def test_undercut_is_info():
    """VAL-8"""
    assert ids(GearParams(12.0), INFO) == {'VAL-8'}
    assert errors(GearParams(12.0)) == []


def test_max_fillet_for_type_a():
    """VAL-5: about 0.47 for type A without backlash; backlash leaves more room."""
    assert max_fillet(GearParams(24.0)) == pytest.approx(0.47, abs=0.005)
    assert max_fillet(GearParams(24.0, backlash=0.1)) > max_fillet(GearParams(24.0))
    assert errors(GearParams(24.0, fillet=0.47)) == []
