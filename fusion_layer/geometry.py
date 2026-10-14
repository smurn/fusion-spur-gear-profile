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


def mesh_layout(frame: Frame, mate: Frame) -> typing.Optional[typing.Tuple[float, float]]:
    """Distance (mm) and direction from the mate's center to this gear's center,
    measured in the mate's plane (DER-10, DER-11). None if the planes are not
    parallel or the centers coincide (VAL-17)."""
    if frame.normal.crossProduct(mate.normal).length > 1e-6:
        return None
    offset = mate.origin.vectorTo(frame.origin)
    x, y = offset.dotProduct(mate.x) / CM, offset.dotProduct(mate.y) / CM
    distance = math.hypot(x, y)
    if distance < 1e-6:
        return None
    return distance, math.atan2(y, x)


def angle_in(frame: Frame, other: Frame, angle: float) -> float:
    """An angle measured in the other frame's plane, measured in this frame's
    plane instead. The planes are parallel; their normals may point either way."""
    direction = other.direction(angle)
    return math.atan2(direction.dotProduct(frame.y), direction.dotProduct(frame.x))


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
