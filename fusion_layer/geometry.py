"""From the selected curve and a gearcore outline to a solid body (ARC-3).

No gear math here (ARC-2). Fusion's internal length unit is cm, gearcore uses mm.
"""

import dataclasses
import math
import typing

import adsk.core
import adsk.fusion

from .. import gearcore

CM = 0.1  # mm to cm


@dataclasses.dataclass
class Frame:
    """Where the gear goes: the plane of the selected curve, in the model space
    of the curve's component. `x` is the reference direction of GEO-9."""
    origin: adsk.core.Point3D
    x: adsk.core.Vector3D
    y: adsk.core.Vector3D
    normal: adsk.core.Vector3D
    diameter: float                       # mm
    arc_span: typing.Optional[float]      # radians, None for a circle

    def point(self, p) -> adsk.core.Point3D:
        o, x, y = self.origin, self.x, self.y
        return adsk.core.Point3D.create(o.x + (p[0] * x.x + p[1] * y.x) * CM,
                                        o.y + (p[0] * x.y + p[1] * y.y) * CM,
                                        o.z + (p[0] * x.z + p[1] * y.z) * CM)

    def direction(self, angle: float) -> adsk.core.Vector3D:
        c, s = math.cos(angle), math.sin(angle)
        x, y = self.x, self.y
        return adsk.core.Vector3D.create(c * x.x + s * y.x, c * x.y + s * y.y, c * x.z + s * y.z)


def native(entity):
    """The entity in its own component, for entities picked through an occurrence."""
    return getattr(entity, 'nativeObject', None) or entity


def is_gear_curve(entity) -> bool:
    return entity is not None and entity.objectType in (
        adsk.fusion.SketchCircle.classType(), adsk.fusion.SketchArc.classType())


def frame_of(curve) -> Frame:
    """Frame of a sketch circle or arc (IN-1, GEO-9)."""
    curve = native(curve)
    sketch = curve.parentSketch
    geo = curve.geometry
    x, y = sketch.xDirection, sketch.yDirection
    normal = x.crossProduct(y)
    origin = sketch.sketchToModelSpace(geo.center)
    span = None
    if curve.objectType == adsk.fusion.SketchArc.classType():
        # Sketch arcs run counter-clockwise from start to end about the sketch normal.
        span = (geo.endAngle - geo.startAngle) % (2 * math.pi) or 2 * math.pi
        start = origin.vectorTo(sketch.sketchToModelSpace(curve.startSketchPoint.geometry))
        start.normalize()
        side = normal.crossProduct(start)
        c, s = math.cos(span / 2), math.sin(span / 2)
        # GEO-9: the reference direction points to the middle of the arc.
        x = adsk.core.Vector3D.create(c * start.x + s * side.x, c * start.y + s * side.y,
                                      c * start.z + s * side.z)
        y = normal.crossProduct(x)
    return Frame(origin, x, y, normal, 2 * geo.radius / CM, span)


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
    return component_occurrence(component)


def component_occurrence(component: adsk.fusion.Component):
    """The component's only occurrence, or None for the root component. With
    several, raises AmbiguousOccurrence."""
    root = component.parentDesign.rootComponent
    if component == root:
        return None
    occurrences = root.allOccurrencesByComponent(component)
    if occurrences.count == 1:
        return occurrences.item(0)
    raise AmbiguousOccurrence('{} is used {} times; pick the curve in the assembly to tell which '
                              'one is meant.'.format(component.name, occurrences.count))


def _up(points: list, vectors: list, occurrence):
    """Copies of points and vectors given in the occurrence's component, in assembly
    coordinates: moved by each occurrence's transform up the path to the root.
    Positions are those at the current place in the timeline (FEA-13, SPIKE-7)."""
    points, vectors = [p.copy() for p in points], [v.copy() for v in vectors]
    while occurrence is not None:
        transform = native(occurrence).transform2   # relative to the parent component
        for item in points + vectors:
            item.transformBy(transform)
        occurrence = getattr(occurrence, 'assemblyContext', None)
    return points, vectors


def _down(points: list, vectors: list, occurrence):
    """The reverse of _up: from assembly coordinates into the occurrence's component."""
    path = []
    while occurrence is not None:
        path.append(occurrence)
        occurrence = getattr(occurrence, 'assemblyContext', None)
    points, vectors = [p.copy() for p in points], [v.copy() for v in vectors]
    for step in reversed(path):   # from the top level down
        inverse = native(step).transform2.copy()
        inverse.invert()
        for item in points + vectors:
            item.transformBy(inverse)
    return points, vectors


def to_assembly(frame: Frame, occurrence) -> Frame:
    """The frame, given in its component's coordinates, in assembly coordinates."""
    (origin,), (x, y, normal) = _up([frame.origin], [frame.x, frame.y, frame.normal], occurrence)
    return dataclasses.replace(frame, origin=origin, x=x, y=y, normal=normal)


def angle_in(frame: Frame, other: Frame, angle: float) -> float:
    """An angle measured in the other frame's plane, measured in this frame's
    plane instead. The planes are parallel; their normals may point either way."""
    direction = other.direction(angle)
    return math.atan2(direction.dotProduct(frame.y), direction.dotProduct(frame.x))


def from_assembly(frame: Frame, occurrence) -> Frame:
    """The reverse of to_assembly: a frame in assembly coordinates, in the
    coordinates of the occurrence's component."""
    (origin,), (x, y, normal) = _down([frame.origin], [frame.x, frame.y, frame.normal], occurrence)
    return dataclasses.replace(frame, origin=origin, x=x, y=y, normal=normal)


def frame_in(curve, component: adsk.fusion.Component, occurrence) -> Frame:
    """The curve's frame in the coordinates of the gear's component (FEA-14),
    which may differ from the curve's own component, for example when the gear is
    made from a circle of a layout sketch. occurrence is the gear component's."""
    frame = frame_of(curve)
    own = native(curve).parentSketch.parentComponent
    if own == component:
        return frame
    return from_assembly(to_assembly(frame, occurrence_of(curve, own)), occurrence)


class ObjectError(gearcore.GearError):
    """A start or extent object cannot be used (VAL-26)."""


def _object_geometry(entity):
    """Point, normal (None for a point) and component of a start or extent object
    (IN-20, IN-23, IN-26),
    in that component's coordinates. None if the entity is no start object."""
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        plane = adsk.core.Plane.cast(face.geometry)
        return (plane.origin, plane.normal, face.body.parentComponent) if plane else None
    construction_plane = adsk.fusion.ConstructionPlane.cast(entity)
    if construction_plane:
        plane = construction_plane.geometry
        return plane.origin, plane.normal, construction_plane.component
    vertex = adsk.fusion.BRepVertex.cast(entity)
    if vertex:
        return vertex.geometry, None, vertex.body.parentComponent
    sketch_point = adsk.fusion.SketchPoint.cast(entity)
    if sketch_point:
        sketch = sketch_point.parentSketch
        return sketch.sketchToModelSpace(sketch_point.geometry), None, sketch.parentComponent
    construction_point = adsk.fusion.ConstructionPoint.cast(entity)
    if construction_point:
        return construction_point.geometry, None, construction_point.component
    return None


def is_height_object(entity) -> bool:
    """A planar face, construction plane, vertex, sketch point or construction point."""
    return entity is not None and _object_geometry(native(entity)) is not None


def object_height(entity, frame: Frame, component: adsk.fusion.Component, occurrence) -> float:
    """GEO-12: the height, in cm along the frame's normal, of a start or extent
    object's plane or point above the frame's plane. frame is in the coordinates of the
    gear's component; occurrence is the gear component's. Raises ObjectError for a
    plane that is not parallel."""
    found = _object_geometry(native(entity))
    if found is None:
        raise ObjectError('Start and extent objects must be planar faces, construction planes '
                          'or points.')
    point, normal, own = found
    if own != component:
        points, vectors = _up([point], [normal] if normal else [], occurrence_of(entity, own))
        points, vectors = _down(points, vectors, occurrence)
        point, normal = points[0], (vectors[0] if vectors else None)
    if normal is not None and normal.crossProduct(frame.normal).length > 1e-6:
        raise ObjectError('Start and extent planes must be parallel to the sketch plane.')
    return frame.origin.vectorTo(point).dotProduct(frame.normal)


def shifted(frame: Frame, distance: float) -> Frame:
    """The frame moved along its normal by distance (cm), to the gear's lowest plane (GEO-12)."""
    o, n = frame.origin, frame.normal
    origin = adsk.core.Point3D.create(o.x + n.x * distance, o.y + n.y * distance, o.z + n.z * distance)
    return dataclasses.replace(frame, origin=origin)


def source_bodies(base: adsk.fusion.BaseFeature) -> list:
    """Bodies owned by the base feature while it is being edited."""
    try:
        return list(base.sourceBodies)
    except Exception:
        return [base.bodies.item(i) for i in range(base.bodies.count)]


def touching_bodies(component: adsk.fusion.Component, tool: adsk.fusion.BRepBody,
                    ignore: typing.Optional[adsk.fusion.BRepBody] = None) -> list:
    """Visible solid bodies of the component that the tool touches or overlaps.
    These are the bodies Join merges the gear into, as Extrude does (FEA-6)."""
    manager = adsk.fusion.TemporaryBRepManager.get()
    union = adsk.fusion.BooleanTypes.UnionBooleanType
    found = []
    for i in range(component.bRepBodies.count):
        body = component.bRepBodies.item(i)
        if body == tool or body == ignore or not body.isSolid or not body.isVisible:
            continue
        if not body.boundingBox.intersects(tool.boundingBox):
            continue
        merged = manager.copy(body)
        manager.booleanOperation(merged, manager.copy(tool), union)
        # Bodies that touch fuse into one lump; separate ones stay separate.
        if merged.lumps.count <= body.lumps.count:
            found.append(body)
    return found


def envelope_body(frame: Frame, radius: float, thickness: float, flip: bool) -> adsk.fusion.BRepBody:
    """Temporary cylinder that encloses a gear with the given tip radius (mm)."""
    t = thickness * CM * (-1.0 if flip else 1.0)
    o, n = frame.origin, frame.normal
    top = adsk.core.Point3D.create(o.x + n.x * t, o.y + n.y * t, o.z + n.z * t)
    return adsk.fusion.TemporaryBRepManager.get().createCylinderOrCone(
        o, radius * CM, top, radius * CM)


def _curves(frame: Frame, outline: gearcore.Outline) -> list:
    curves = []
    for seg in outline.segments:
        if isinstance(seg, gearcore.Arc):
            # Arc3D runs counter-clockwise about the normal; a clockwise outline arc
            # is the same curve started from its other end.
            start = seg.start_angle + min(seg.sweep, 0.0)
            curves.append(adsk.core.Arc3D.createByCenter(
                frame.point(seg.center), frame.normal, frame.direction(start),
                seg.radius * CM, 0.0, abs(seg.sweep)))
        elif isinstance(seg, gearcore.Line):
            curves.append(adsk.core.Line3D.create(frame.point(seg.start), frame.point(seg.end)))
        else:
            curves.append(adsk.core.NurbsCurve3D.createNonRational(
                [frame.point(p) for p in seg.control_points], seg.degree, list(seg.knots), False))
    return curves


def build_body(component: adsk.fusion.Component, base: adsk.fusion.BaseFeature, frame: Frame,
               outline: gearcore.Outline, thickness: float, flip: bool) -> adsk.fusion.BRepBody:
    """Add the gear body to the base feature, which must be in edit mode (GEO-12).

    The outline becomes a planar face in memory. The face is extruded inside the
    base feature, which adds nothing to the timeline."""
    manager = adsk.fusion.TemporaryBRepManager.get()
    wires = [manager.createWireFromCurves(_curves(frame, outline), False)[0]]
    for hole in outline.holes:   # GEO-11
        circle = adsk.core.Circle3D.createByCenter(
            frame.point(hole.center), frame.normal, hole.radius * CM)
        wires.append(manager.createWireFromCurves([circle], False)[0])
    face_body = component.bRepBodies.add(manager.createFaceFromPlanarWires(wires), base)
    try:
        face = face_body.faces.item(0)
        want = -1.0 if flip else 1.0   # side of the plane, along the sketch normal
        _, face_normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
        directions = adsk.fusion.ExtentDirections
        order = [directions.PositiveExtentDirection, directions.NegativeExtentDirection]
        if face_normal.dotProduct(frame.normal) * want < 0:
            order.reverse()
        for direction in order:
            known = {b.entityToken for b in source_bodies(base)}
            extrudes = component.features.extrudeFeatures
            inp = extrudes.createInput(face, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(thickness * CM)), direction)
            inp.targetBaseFeature = base
            extrudes.add(inp)
            made = [b for b in source_bodies(base) if b.entityToken not in known and b.isSolid]
            if not made:
                raise RuntimeError('The extrude inside the base feature produced no solid body.')
            body = made[-1]
            com = body.physicalProperties.centerOfMass
            if frame.origin.vectorTo(com).dotProduct(frame.normal) * want > 0:
                return body
            body.deleteMe()
        raise RuntimeError('The gear body could not be placed on the requested side.')
    finally:
        face_body.deleteMe()
