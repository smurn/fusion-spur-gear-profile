"""Where the gear begins and ends: GEO-12, IN-13, IN-21 to IN-26, VAL-10."""

import pytest

from gearcore import ONE_SIDE, SYMMETRIC, TWO_SIDES, Side, extent_issues, span


def test_one_side_distance_goes_along_the_normal_or_flipped():
    """GEO-12, IN-13"""
    assert span(2.0, ONE_SIDE, False, Side(distance=5.0)) == (2.0, 7.0)
    assert span(2.0, ONE_SIDE, True, Side(distance=5.0)) == (-3.0, 2.0)


def test_one_side_to_object_goes_to_the_object_on_either_side():
    """GEO-12, IN-22: the flip does not matter."""
    assert span(2.0, ONE_SIDE, False, Side(height=9.0)) == (2.0, 9.0)
    assert span(2.0, ONE_SIDE, False, Side(height=-4.0)) == (-4.0, 2.0)
    assert span(2.0, ONE_SIDE, True, Side(height=9.0)) == (2.0, 9.0)


def test_symmetric_thickness_is_the_whole_face_width():
    """GEO-12, D-33"""
    assert span(1.0, SYMMETRIC, False, Side(distance=6.0)) == (-2.0, 4.0)
    assert span(1.0, SYMMETRIC, True, Side(distance=6.0)) == (-2.0, 4.0)


def test_two_sides_span_both_sides():
    """GEO-12, IN-24 to IN-26: side 2 goes the other way, flipped with side 1."""
    assert span(0.0, TWO_SIDES, False, Side(distance=5.0), Side(distance=2.0)) == (-2.0, 5.0)
    assert span(0.0, TWO_SIDES, True, Side(distance=5.0), Side(distance=2.0)) == (-5.0, 2.0)
    assert span(1.0, TWO_SIDES, False, Side(height=8.0), Side(distance=3.0)) == (-2.0, 8.0)
    assert span(1.0, TWO_SIDES, False, Side(distance=3.0), Side(height=-6.0)) == (-6.0, 4.0)


def test_object_on_the_start_plane_gives_no_width():
    """VAL-27 is decided by the caller from a zero span."""
    low, high = span(3.0, ONE_SIDE, False, Side(height=3.0))
    assert high - low == pytest.approx(0.0)


def test_distances_must_be_positive():
    """VAL-10, only for the sides that use a distance."""
    assert [i.id for i in extent_issues(ONE_SIDE, Side(distance=0.0), None)] == ['VAL-10']
    assert extent_issues(ONE_SIDE, Side(height=0.0), None) == []
    assert [i.id for i in extent_issues(TWO_SIDES, Side(distance=5.0), Side(distance=-1.0))] == ['VAL-10']
    assert extent_issues(TWO_SIDES, Side(distance=5.0), Side(height=-1.0)) == []
    assert extent_issues(ONE_SIDE, Side(distance=5.0), Side(distance=-1.0)) == []   # side 2 unused


def test_symmetric_half_length_goes_the_thickness_each_way():
    """IN-27"""
    assert span(1.0, SYMMETRIC, False, Side(distance=3.0), half_length=True) == (-2.0, 4.0)
    assert span(1.0, SYMMETRIC, False, Side(distance=3.0), half_length=False) == (-0.5, 2.5)


def test_to_object_offset_moves_the_end_past_the_object():
    """IN-28, IN-29: positive goes past the object, away from the start, on either side."""
    assert span(0.0, ONE_SIDE, False, Side(height=8.0, offset=1.0)) == (0.0, 9.0)
    assert span(0.0, ONE_SIDE, False, Side(height=8.0, offset=-0.5)) == (0.0, 7.5)
    assert span(0.0, ONE_SIDE, False, Side(height=-4.0, offset=1.0)) == (-5.0, 0.0)
    assert span(0.0, TWO_SIDES, False, Side(distance=5.0), Side(height=-3.0, offset=-1.0)) == (-2.0, 5.0)


def test_offset_from_an_object_on_the_start_plane_goes_the_sides_way():
    """IN-28: away from the start is then the side's own way, so flip turns it."""
    assert span(2.0, ONE_SIDE, False, Side(height=2.0, offset=3.0)) == (2.0, 5.0)
    assert span(2.0, ONE_SIDE, True, Side(height=2.0, offset=3.0)) == (-1.0, 2.0)
