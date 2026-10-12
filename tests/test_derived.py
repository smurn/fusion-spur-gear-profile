"""Derived values, spec section 5."""

import math

import pytest

from gearcore import GearParams, derive, tooth_count


@pytest.mark.parametrize('diameter, module, teeth', [
    (24.0, 1.0, 24),
    (24.3, 1.0, 24),
    (24.49, 1.0, 24),
    (24.5, 1.0, 25),    # exact halves round up
    (23.5, 1.0, 24),
    (61.0, 2.5, 24),    # 24.4
    (50.0, 4.0, 13),    # 12.5 rounds up
])
def test_tooth_count_rounds_half_up(diameter, module, teeth):
    """DER-1"""
    assert tooth_count(GearParams(diameter, module=module)) == teeth


def test_hand_calculated_values_for_type_a_z24():
    """DER-2 to DER-8. Expected values calculated by hand for m = 1, z = 24, ISO 53 type A."""
    d = derive(GearParams(24.3))
    assert d.teeth == 24
    assert d.reference_diameter == pytest.approx(24.0)
    assert d.base_diameter == pytest.approx(22.552623, abs=1e-6)   # 24 cos 20 deg
    assert d.tip_diameter == pytest.approx(26.0)
    assert d.root_diameter == pytest.approx(21.5)
    assert d.tooth_thickness == pytest.approx(1.570796, abs=1e-6)  # pi / 2
    assert d.min_teeth == pytest.approx(17.0967, abs=1e-4)
    assert not d.undercut
    # alpha_a = acos(22.552623 / 26) = 29.8411 deg, inv = 0.052833; inv 20 deg = 0.014904
    assert d.tip_thickness == pytest.approx(0.71555, abs=1e-5)


def test_profile_shift_backlash_and_offset():
    """DER-4, DER-5, DER-6, DER-8"""
    a = math.radians(20)
    d = derive(GearParams(40.0, module=2.0, profile_shift=0.3, backlash=0.1, print_offset=0.05))
    assert d.teeth == 20
    assert d.tip_diameter == pytest.approx(40 + 2 * 2 * 1.3 + 0.1)
    assert d.root_diameter == pytest.approx(40 - 2 * 2 * 0.95 + 0.1)
    assert d.tooth_thickness == pytest.approx(2 * (math.pi / 2 + 0.6 * math.tan(a)) - 0.1 / (2 * math.cos(a)))
    # The print offset thickens the tip by about 2 delta / cos(alpha_a) and widens the tip circle.
    plain = derive(GearParams(40.0, module=2.0, profile_shift=0.3, backlash=0.1))
    assert plain.tip_thickness - 0.1 < d.tip_thickness < plain.tip_thickness + 0.1


def test_undercut_threshold_for_type_a():
    """DER-7, TST-2: undercut starts below z of about 17.1."""
    assert derive(GearParams(17.0)).undercut
    assert not derive(GearParams(18.0)).undercut
    assert derive(GearParams(17.0)).min_teeth == pytest.approx(17.1, abs=0.05)
    # Positive profile shift removes undercut.
    assert not derive(GearParams(14.0, profile_shift=0.2)).undercut


def test_tip_thickness_is_undefined_below_the_base_circle():
    """DER-8"""
    assert derive(GearParams(10.0, addendum=0.1, profile_shift=-1.0)).tip_thickness is None
