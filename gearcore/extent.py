"""Where along the sketch normal the gear begins and ends (GEO-12, IN-12, IN-13,
IN-21 to IN-29). Heights are in mm along the sketch normal, 0 on the curve's plane."""

import dataclasses
import typing

from .validation import ERROR, Issue

ONE_SIDE, TWO_SIDES, SYMMETRIC = 'One Side', 'Two Sides', 'Symmetric'   # IN-21


@dataclasses.dataclass(frozen=True)
class Side:
    """How far one side goes: a distance from the start, or to an object's height,
    moved by offset away from the start (IN-28, IN-29)."""
    distance: typing.Optional[float] = None
    height: typing.Optional[float] = None
    offset: float = 0.0


def extent_issues(direction: str, side1: Side, side2: typing.Optional[Side]) -> typing.List[Issue]:
    """VAL-10: a thickness used as a distance must be positive."""
    sides = [side1] + ([side2] if direction == TWO_SIDES and side2 is not None else [])
    if any(s.height is None and s.distance <= 0 for s in sides):
        return [Issue('VAL-10', ERROR, 'Thickness must be greater than 0.')]
    return []


def span(start: float, direction: str, flip: bool, side1: Side,
         side2: typing.Optional[Side] = None, half_length: bool = False) -> typing.Tuple[float, float]:
    """The lowest and highest height of the gear. side1 goes along the sketch normal,
    or against it with flip; side2 (Two Sides) the other way. With Symmetric,
    side1's distance is the whole face width, or with half_length the distance each
    way (IN-27). A side that goes to an object ends at its height, whichever side of
    the start that is, moved by its offset away from the start; for an object on the
    start plane, away means the side's own way."""
    sign = -1.0 if flip else 1.0

    def end(side: Side, way: float) -> float:
        if side.height is None:
            return start + way * side.distance
        away = way if abs(side.height - start) < 1e-9 else (1.0 if side.height > start else -1.0)
        return side.height + away * side.offset

    if direction == SYMMETRIC:
        reach = side1.distance if half_length else side1.distance / 2
        ends = [start - reach, start + reach]
    elif direction == TWO_SIDES:
        ends = [start, end(side1, sign), end(side2, -sign)]
    else:
        ends = [start, end(side1, sign)]
    return min(ends), max(ends)
