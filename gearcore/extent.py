"""Where along the sketch normal the gear begins and ends (GEO-12, IN-12, IN-13,
IN-21 to IN-26). Heights are in mm along the sketch normal, 0 on the curve's plane."""

import dataclasses
import typing

from .validation import ERROR, Issue

ONE_SIDE, TWO_SIDES, SYMMETRIC = 'One Side', 'Two Sides', 'Symmetric'   # IN-21


@dataclasses.dataclass(frozen=True)
class Side:
    """How far one side goes: a distance from the start, or to an object's height."""
    distance: typing.Optional[float] = None
    height: typing.Optional[float] = None


def extent_issues(direction: str, side1: Side, side2: typing.Optional[Side]) -> typing.List[Issue]:
    """VAL-10: a thickness used as a distance must be positive."""
    sides = [side1] + ([side2] if direction == TWO_SIDES and side2 is not None else [])
    if any(s.height is None and s.distance <= 0 for s in sides):
        return [Issue('VAL-10', ERROR, 'Thickness must be greater than 0.')]
    return []


def span(start: float, direction: str, flip: bool, side1: Side,
         side2: typing.Optional[Side] = None) -> typing.Tuple[float, float]:
    """The lowest and highest height of the gear. side1 goes along the sketch normal,
    or against it with flip; side2 (Two Sides) the other way. With Symmetric,
    side1's distance is the whole face width. A side that goes to an object ends at
    its height, whichever side of the start that is."""
    sign = -1.0 if flip else 1.0

    def end(side: Side, way: float) -> float:
        return side.height if side.height is not None else start + way * side.distance

    if direction == SYMMETRIC:
        half = side1.distance / 2
        ends = [start - half, start + half]
    elif direction == TWO_SIDES:
        ends = [start, end(side1, sign), end(side2, -sign)]
    else:
        ends = [start, end(side1, sign)]
    return min(ends), max(ends)
