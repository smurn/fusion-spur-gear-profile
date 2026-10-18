"""Gear trains: from a gear's curve to its layout sketch and back (spec section 7).

gearcore works out a train's orientation from plain data (ARC-8). This module
finds the layout sketch (TRN-1), reads it for gearcore, and turns the result into
the gear's start rotation (TRN-10). No gear math here (ARC-2).
"""

import dataclasses
import math
import typing

import adsk.core
import adsk.fusion

from .. import gearcore
from .geometry import CM, Frame, is_gear_curve, native


class AmbiguousOccurrence(gearcore.GearError):
    """A native entity in a component that has several occurrences: which copy is
    meant cannot be told."""


def occurrence_of(entity, component: adsk.fusion.Component):
    """The occurrence an entity was picked in, or None for the root component. A
    proxy carries it. A native entity in a component that is used once is in that
    one occurrence; with several, raises AmbiguousOccurrence."""
    context = getattr(entity, 'assemblyContext', None)
    if context:
        return context
    root = component.parentDesign.rootComponent
    if component == root:
        return None
    occurrences = root.allOccurrencesByComponent(component)
    if occurrences.count == 1:
        return occurrences.item(0)
    raise AmbiguousOccurrence('{} is used {} times; pick the curve in the assembly to tell which '
                              'one is meant.'.format(component.name, occurrences.count))


def to_assembly(frame: Frame, occurrence) -> Frame:
    """The frame, given in its component's coordinates, in assembly coordinates:
    moved by each occurrence's transform up the path to the root. Positions are
    those at the current place in the timeline (FEA-13, SPIKE-7)."""
    origin, axes = frame.origin.copy(), [frame.x.copy(), frame.y.copy(), frame.normal.copy()]
    while occurrence is not None:
        transform = native(occurrence).transform2   # relative to the parent component
        origin.transformBy(transform)
        for axis in axes:
            axis.transformBy(transform)
        occurrence = getattr(occurrence, 'assemblyContext', None)
    return dataclasses.replace(frame, origin=origin, x=axes[0], y=axes[1], normal=axes[2])


def angle_in(frame: Frame, other: Frame, angle: float) -> float:
    """An angle measured in the other frame's plane, measured in this frame's
    plane instead. The planes are parallel; their normals may point either way."""
    direction = other.direction(angle)
    return math.atan2(direction.dotProduct(frame.y), direction.dotProduct(frame.x))


def layout_curve_of(curve):
    """TRN-1: the curve itself, or the sketch circle or arc it is a linked
    projection of, followed back through further projections. A proxy keeps the
    occurrence of the sketch it is in (SPIKE-8)."""
    entity = curve
    for _ in range(20):   # a projection cannot refer to itself; this is just a guard
        source = native(entity)
        if not source.isReference:
            break
        referenced = source.referencedEntity
        if referenced is None or not is_gear_curve(native(referenced)):
            break
        entity = referenced
    return entity


def _sketch_frame(sketch: adsk.fusion.Sketch) -> Frame:
    x, y = sketch.xDirection, sketch.yDirection
    origin = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
    return Frame(origin, x, y, x.crossProduct(y), 0.0, None)


def _read(sketch: adsk.fusion.Sketch):
    """The layout circles (circles before arcs, TRN-7) and lines, in the sketch's
    own coordinates (mm), and the native curves in the same order."""
    curves, entities = [], []
    circles, arcs = sketch.sketchCurves.sketchCircles, sketch.sketchCurves.sketchArcs
    for i in range(circles.count):
        c = circles.item(i)
        p = c.centerSketchPoint.geometry
        curves.append(gearcore.LayoutCurve((p.x / CM, p.y / CM), c.radius / CM))
        entities.append(c)
    for i in range(arcs.count):
        a = arcs.item(i)
        p, s, e = a.centerSketchPoint.geometry, a.startSketchPoint.geometry, a.endSketchPoint.geometry
        # Sketch arcs run counter-clockwise from start to end in sketch coordinates.
        start = math.atan2(s.y - p.y, s.x - p.x)
        sweep = (math.atan2(e.y - p.y, e.x - p.x) - start) % (2 * math.pi) or 2 * math.pi
        curves.append(gearcore.LayoutCurve((p.x / CM, p.y / CM), a.radius / CM, start, sweep))
        entities.append(a)
    lines = []
    for i in range(sketch.sketchCurves.sketchLines.count):
        line = sketch.sketchCurves.sketchLines.item(i)
        s, e = line.startSketchPoint.geometry, line.endSketchPoint.geometry
        lines.append(gearcore.LayoutLine((s.x / CM, s.y / CM), (e.x / CM, e.y / CM)))
    return curves, lines, entities


@dataclasses.dataclass
class Train:
    """What the layout sketch says about a gear."""
    sketch: typing.Any                 # the layout sketch, native
    occurrence: typing.Any             # the layout sketch's occurrence, None in the root
    own_sketch: bool                   # whether the layout sketch is the curve's own sketch
    orientation: gearcore.Orientation
    rotation: typing.Optional[float]   # the gear's start rotation p, if the layout sets it
    issues: list


def train_of(curve, frame: Frame, params: gearcore.GearParams) -> Train:
    """The gear's train (TRN-1 to TRN-11). frame is the gear's own frame, in its
    component's coordinates; params must be valid."""
    layout_curve = layout_curve_of(curve)
    sketch = native(layout_curve).parentSketch
    occurrence = occurrence_of(layout_curve, sketch.parentComponent)
    own_sketch = sketch == native(curve).parentSketch
    curves, lines, entities = _read(sketch)
    index = next((i for i, e in enumerate(entities) if e == native(layout_curve)), None)
    if index is None:   # not expected: a curve is always in its own sketch
        return Train(sketch, occurrence, own_sketch, gearcore.Orientation(None, 1, 0, False, []),
                     None, [])
    orientation = gearcore.orientation(curves, lines, params.module, index)
    train = Train(sketch, occurrence, own_sketch, orientation, None, list(orientation.issues))
    if orientation.axis is None:
        return train

    component = native(curve).parentSketch.parentComponent
    own, layout = frame, _sketch_frame(sketch)
    if sketch.parentComponent != component:
        try:
            own = to_assembly(frame, occurrence_of(curve, component))
        except AmbiguousOccurrence as e:
            train.issues.append(gearcore.Issue('VAL-24', gearcore.ERROR, str(e)))
            return train
        layout = to_assembly(layout, occurrence)
    if own.normal.crossProduct(layout.normal).length > 1e-6:
        train.issues.append(gearcore.Issue('VAL-22', gearcore.ERROR, 'The layout sketch is not '
                                           'parallel to the gear\'s sketch.'))
        return train
    angle = angle_in(own, layout, orientation.axis)
    train.rotation = gearcore.rotation_for_axis(angle, gearcore.tooth_count(params))
    return train
