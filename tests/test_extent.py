"""Where the gear begins and ends: GEO-12, IN-12, IN-21 to IN-29, VAL-10, D-36."""

import pytest

from gearcore import ONE_SIDE, SYMMETRIC, TWO_SIDES, Side, extent_issues, span


def test_one_side_distance_goes_along_the_normal_or_back_when_negative():
    """GEO-12, IN-12, D-36"""
    assert span(2.0, ONE_SIDE, Side(distance=5.0)) == (2.0, 7.0)
    assert span(2.0, ONE_SIDE, Side(distance=-5.0)) == (-3.0, 2.0)


def test_one_side_to_object_goes_to_the_object_on_either_side():
    """GEO-12, IN-22"""
    assert span(2.0, ONE_SIDE, Side(height=9.0)) == (2.0, 9.0)
    assert span(2.0, ONE_SIDE, Side(height=-4.0)) == (-4.0, 2.0)


def test_symmetric_distance_is_the_whole_face_width_whatever_its_sign():
    """GEO-12, IN-27"""
    assert span(1.0, SYMMETRIC, Side(distance=6.0)) == (-2.0, 4.0)
    assert span(1.0, SYMMETRIC, Side(distance=-6.0)) == (-2.0, 4.0)


def test_symmetric_half_length_goes_the_distance_each_way():
    """IN-27"""
    assert span(1.0, SYMMETRIC, Side(distance=3.0), half_length=True) == (-2.0, 4.0)
    assert span(1.0, SYMMETRIC, Side(distance=3.0), half_length=False) == (-0.5, 2.5)


def test_two_sides_span_both_sides():
    """GEO-12, IN-24 to IN-26: side 2's distance goes against the normal."""
    assert span(0.0, TWO_SIDES, Side(distance=5.0), Side(distance=2.0)) == (-2.0, 5.0)
    assert span(0.0, TWO_SIDES, Side(distance=-5.0), Side(distance=-2.0)) == (-5.0, 2.0)
    assert span(0.0, TWO_SIDES, Side(distance=5.0), Side(distance=-2.0)) == (0.0, 5.0)
    assert span(1.0, TWO_SIDES, Side(height=8.0), Side(distance=3.0)) == (-2.0, 8.0)
    assert span(1.0, TWO_SIDES, Side(distance=3.0), Side(height=-6.0)) == (-6.0, 4.0)


def test_to_object_offset_moves_the_end_past_the_object():
    """IN-28, IN-29: positive goes past the object, away from the start, on either side."""
    assert span(0.0, ONE_SIDE, Side(height=8.0, offset=1.0)) == (0.0, 9.0)
    assert span(0.0, ONE_SIDE, Side(height=8.0, offset=-0.5)) == (0.0, 7.5)
    assert span(0.0, ONE_SIDE, Side(height=-4.0, offset=1.0)) == (-5.0, 0.0)
    assert span(0.0, TWO_SIDES, Side(distance=5.0), Side(height=-3.0, offset=-1.0)) == (-2.0, 5.0)


def test_offset_from_an_object_on_the_start_plane_goes_the_sides_way():
    """IN-28, IN-29: along the normal for side 1, against it for side 2."""
    assert span(2.0, ONE_SIDE, Side(height=2.0, offset=3.0)) == (2.0, 5.0)
    assert span(2.0, TWO_SIDES, Side(distance=1.0), Side(height=2.0, offset=3.0)) == (-1.0, 3.0)


def test_object_on_the_start_plane_gives_no_width():
    """VAL-27 is decided by the caller from a zero span."""
    low, high = span(3.0, ONE_SIDE, Side(height=3.0))
    assert high - low == pytest.approx(0.0)


def test_distances_must_not_be_zero_but_may_be_negative():
    """VAL-10, D-36, only for the sides that use a distance."""
    assert [i.id for i in extent_issues(ONE_SIDE, Side(distance=0.0), None)] == ['VAL-10']
    assert extent_issues(ONE_SIDE, Side(distance=-5.0), None) == []
    assert extent_issues(ONE_SIDE, Side(height=0.0), None) == []
    assert [i.id for i in extent_issues(TWO_SIDES, Side(distance=5.0), Side(distance=0.0))] == ['VAL-10']
    assert extent_issues(TWO_SIDES, Side(distance=5.0), Side(distance=-1.0)) == []
    assert extent_issues(ONE_SIDE, Side(distance=5.0), Side(distance=0.0)) == []   # side 2 unused
