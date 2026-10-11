"""SPIKE-5: the gear as a custom feature (throwaway code).

An add-in, not a script, because the compute handler must stay loaded. Running
it registers the custom feature, then (after run() has returned) builds test
gears in a new, unsaved document and writes results/<timestamp>/report.md next
to this file. The document stays open and the gears stay live until the add-in
is stopped. Results are in docs/spikes.md.

Pattern under test: the gear body lives in a base feature and is made without
timeline features (an extrude inside the base feature). The custom feature
groups the base feature and, for Join, one combine feature. On recompute the
body is rebuilt and swapped in with BaseFeature.updateBody.

Two ways to make the outline are compared:
  'sketch'  a temporary sketch inside the base feature, extrude its profile
  'face'    a planar face built in memory from exact curves, extrude that face
"""

import datetime
import importlib
import json
import math
import os
import sys
import time
import traceback

import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM_DIR = os.path.join(os.path.dirname(HERE), 'GearSpikes')
if GEOM_DIR not in sys.path:
    sys.path.insert(0, GEOM_DIR)
import spike_geom  # noqa: E402
importlib.reload(spike_geom)
from spike_geom import Gear, spline_bezier  # noqa: E402

FEATURE_ID = 'smurn.SpurGearSpike'
CM = 0.1  # mm to Fusion's internal cm

app = adsk.core.Application.get()
ui = app.userInterface
P3 = adsk.core.Point3D.create
V3 = adsk.core.Vector3D.create
VI = adsk.core.ValueInput
NEW_BODY = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation

_definition = None
_handlers = []
_creating = False   # compute events during creation are ignored
COMPUTES = []       # one entry per compute event
REP = None


# ---------------------------------------------------------------- reporting --
class Report:
    def __init__(self):
        self.dir = os.path.join(HERE, 'results', datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        os.makedirs(self.dir, exist_ok=True)
        self.items = []

    def mark(self, msg):
        with open(os.path.join(self.dir, 'progress.log'), 'a', encoding='utf-8') as f:
            f.write('{} {}\n'.format(datetime.datetime.now().strftime('%H:%M:%S'), msg))

    def run(self, cid, title, fn):
        """fn returns (status, detail, data). Exceptions become ERROR."""
        self.mark('start ' + cid)
        first = len(COMPUTES)
        t = time.perf_counter()
        try:
            status, detail, data = fn()
        except Exception:
            status, detail = 'ERROR', traceback.format_exc().strip().splitlines()[-1]
            data = {'traceback': traceback.format_exc()}
        data = dict(data or {})
        data['seconds'] = round(time.perf_counter() - t, 3)
        data['computes'] = COMPUTES[first:]
        failed = [c for c in data['computes'] if c.get('error')]
        if failed and status == 'PASS':
            status = 'FAIL'
            detail += '; compute error: ' + failed[0]['error'].strip().splitlines()[-1]
        self.items.append({'id': cid, 'title': title, 'status': status, 'detail': detail,
                           'data': data})
        self.mark('{} {}: {}'.format(status, cid, detail))
        self.save()
        adsk.doEvents()
        return status, data

    def save(self):
        with open(os.path.join(self.dir, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump({'fusion_version': app.version, 'items': self.items}, f, indent=1, default=str)
        lines = ['# Custom feature spike report', '', 'Fusion {}.'.format(app.version), '',
                 '| ID | Check | Status | Detail |', '|---|---|---|---|']
        for it in self.items:
            lines.append('| {} | {} | {} | {} |'.format(
                it['id'], it['title'], it['status'], str(it['detail']).replace('|', '/')))
        with open(os.path.join(self.dir, 'report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')


# ----------------------------------------------------------------- geometry --
def curve_frame(curve):
    """Center, in-plane axes and radius of the selected circle or arc, in model space."""
    sk = curve.parentSketch
    geo = curve.worldGeometry
    x, y = sk.xDirection, sk.yDirection
    return {'c': geo.center, 'x': x, 'y': y, 'n': x.crossProduct(y),
            'radius_mm': geo.radius / CM, 'sketch': sk}


def world(fr, x_mm, y_mm):
    c, x, y = fr['c'], fr['x'], fr['y']
    return P3(c.x + (x_mm * x.x + y_mm * y.x) * CM, c.y + (x_mm * x.y + y_mm * y.y) * CM,
              c.z + (x_mm * x.z + y_mm * y.z) * CM)


def direction(fr, ang):
    x, y = fr['x'], fr['y']
    c, s = math.cos(ang), math.sin(ang)
    return V3(c * x.x + s * y.x, c * x.y + s * y.y, c * x.z + s * y.z)


def gear_for(radius_mm, module_mm):
    return Gear(module_mm, int(2 * radius_mm / module_mm + 0.5))   # DER-1


def outline(g, rot, n):
    """Closed outline, counter-clockwise, in the gear plane (mm). Items are
    ('spline', points) or ('arc', radius, start angle, end angle)."""
    inv, tro = g.involute_points(n), g.trochoid_points(n)
    out = []
    for k in range(g.z):
        a = rot + k * g.tau
        c, s = math.cos(a), math.sin(a)

        def place(pts, sign):
            return [(x * c - sign * y * s, x * s + sign * y * c) for x, y in pts]

        out.append(('spline', place(tro[::-1], -1)))
        out.append(('spline', place(inv[::-1], -1)))
        out.append(('arc', g.ra, a - g.tip_angle(), a + g.tip_angle()))
        out.append(('spline', place(inv, 1)))
        out.append(('spline', place(tro, 1)))
        out.append(('arc', g.rf, a + g.root_angle(), a + g.tau - g.root_angle()))
    return out


def source_bodies(base):
    try:
        return list(base.sourceBodies)
    except Exception:
        return [base.bodies.item(i) for i in range(base.bodies.count)]


def extrude_in_base(comp, base, profile, fr, thickness_cm):
    """Extrude inside the base feature (no timeline entry). Returns the new body,
    on the side of the plane the sketch normal points to."""
    dirs = adsk.fusion.ExtentDirections
    for side_dir in (dirs.PositiveExtentDirection, dirs.NegativeExtentDirection):
        known = {b.entityToken for b in source_bodies(base)}
        extrudes = comp.features.extrudeFeatures
        inp = extrudes.createInput(profile, NEW_BODY)
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(
            VI.createByReal(thickness_cm)), side_dir)
        inp.targetBaseFeature = base
        extrudes.add(inp)
        made = [b for b in source_bodies(base) if b.entityToken not in known and b.isSolid]
        if not made:
            raise RuntimeError('the extrude inside the base feature produced no solid body')
        body = made[-1]
        com = body.physicalProperties.centerOfMass
        side = ((com.x - fr['c'].x) * fr['n'].x + (com.y - fr['c'].y) * fr['n'].y
                + (com.z - fr['c'].z) * fr['n'].z)
        if side > 0:
            return body
        body.deleteMe()
    raise RuntimeError('extrude never landed on the positive side of the plane')


def body_via_sketch(comp, base, fr, g, rot, thickness_cm):
    sk = comp.sketches.addToBaseOrFormFeature(fr['sketch'].referencePlane, base, False)
    sk.isComputeDeferred = True
    splines, arcs = sk.sketchCurves.sketchFittedSplines, sk.sketchCurves.sketchArcs

    def pt(x, y):
        return sk.modelToSketchSpace(world(fr, x, y))

    for item in outline(g, rot, 6):
        if item[0] == 'spline':
            oc = adsk.core.ObjectCollection.create()
            for x, y in item[1]:
                oc.add(pt(x, y))
            splines.add(oc)
        else:
            _, rad, a0, a1 = item
            arcs.addByThreePoints(*[pt(rad * math.cos(a), rad * math.sin(a))
                                    for a in (a0, (a0 + a1) / 2, a1)])
    sk.isComputeDeferred = False
    profiles = [sk.profiles.item(i) for i in range(sk.profiles.count)]
    if len(profiles) != 1:
        raise RuntimeError('expected 1 profile, got {}'.format(len(profiles)))
    body = extrude_in_base(comp, base, profiles[0], fr, thickness_cm)
    sk.deleteMe()
    return body


def body_via_face(comp, base, fr, g, rot, thickness_cm):
    tm = adsk.fusion.TemporaryBRepManager.get()
    curves = []
    for item in outline(g, rot, 12):
        if item[0] == 'spline':
            cps, knots = spline_bezier(item[1])
            curves.append(adsk.core.NurbsCurve3D.createNonRational(
                [world(fr, x, y) for x, y in cps], 3, knots, False))
        else:
            _, rad, a0, a1 = item
            curves.append(adsk.core.Arc3D.createByCenter(
                fr['c'], fr['n'], direction(fr, a0), rad * CM, 0.0, a1 - a0))
    wire, _ = tm.createWireFromCurves(curves, False)
    face_body = comp.bRepBodies.add(tm.createFaceFromPlanarWires([wire]), base)
    body = extrude_in_base(comp, base, face_body.faces.item(0), fr, thickness_cm)
    face_body.deleteMe()
    return body


BUILDERS = {'sketch': body_via_sketch, 'face': body_via_face}


# ----------------------------------------------------------- custom feature --
def base_of(feat):
    return [f for f in feat.features
            if f.objectType == adsk.fusion.BaseFeature.classType()][0]


def create_feature(curve, builder, target=None, module_mm=1.0, thickness_mm=5.0):
    """Create the gear custom feature. target None makes a new body, else joins."""
    global _creating
    comp = curve.parentSketch.parentComponent
    fr = curve_frame(curve)
    g = gear_for(fr['radius_mm'], module_mm)
    _creating = True
    try:
        base = comp.features.baseFeatures.add()
        base.startEdit()
        try:
            BUILDERS[builder](comp, base, fr, g, 0.0, thickness_mm * CM)
        finally:
            base.finishEdit()
        last = base
        if target:
            tools = adsk.core.ObjectCollection.create()
            tools.add(base.bodies.item(0))
            inp = comp.features.combineFeatures.createInput(target, tools)
            inp.operation = JOIN
            last = comp.features.combineFeatures.add(inp)
        inp = comp.features.customFeatures.createInput(_definition)
        inp.addCustomParameter('module', 'Module', VI.createByString('{} mm'.format(module_mm)), 'mm', True)
        inp.addCustomParameter('thickness', 'Thickness',
                               VI.createByString('{} mm'.format(thickness_mm)), 'mm', True)
        inp.addCustomParameter('rotation', 'Rotation', VI.createByString('0 deg'), 'deg', True)
        inp.setStartAndEndFeatures(base, last)
        feat = comp.features.customFeatures.add(inp)
        feat.customNamedValues.addOrSetValue('builder', builder)
        # Dependencies are added after creation with the timeline rolled back to
        # before the feature, as in the Laser Finger Joint add-in. In the first
        # run, CustomFeatureInput.addDependency gave a feature that never recomputed.
        timeline = adsk.fusion.Design.cast(app.activeProduct).timeline
        resume_at = timeline.item(timeline.markerPosition - 1)
        feat.timelineObject.rollTo(True)
        feat.dependencies.add('curve', curve)
        resume_at.rollTo(False)
        return feat
    finally:
        _creating = False


class ComputeHandler(adsk.fusion.CustomFeatureEventHandler):
    def notify(self, args):
        entry = {'at': datetime.datetime.now().strftime('%H:%M:%S')}
        t0 = time.perf_counter()
        try:
            feat = adsk.fusion.CustomFeatureEventArgs.cast(args).customFeature
            entry['feature'] = feat.name
            if _creating:
                entry['skipped'] = 'during creation'
                return
            builder = feat.customNamedValues.value('builder')
            params = feat.parameters
            module = params.itemById('module').value / CM
            thickness = params.itemById('thickness').value
            rot = params.itemById('rotation').value
            curve = feat.dependencies.itemById('curve').entity
            fr = curve_frame(curve)
            g = gear_for(fr['radius_mm'], module)
            entry.update(builder=builder, z=g.z, module_mm=module)
            base = base_of(feat)
            comp = feat.parentComponent
            base.startEdit()
            try:
                old = source_bodies(base)[0]
                new = BUILDERS[builder](comp, base, fr, g, rot, thickness)
                entry['updated'] = base.updateBody(
                    old, adsk.fusion.TemporaryBRepManager.get().copy(new))
                new.deleteMe()
                entry['source_bodies_after'] = len(source_bodies(base))
            finally:
                base.finishEdit()
        except Exception:
            entry['error'] = traceback.format_exc()
            try:   # marks the feature red in the timeline
                args.computeStatus.statusMessages.addError('DRPOINT_COMPUTE_FAILED', '')
            except Exception:
                pass
        finally:
            entry['seconds'] = round(time.perf_counter() - t0, 3)
            COMPUTES.append(entry)
            if REP:
                REP.mark('compute {}'.format({k: v for k, v in entry.items() if k != 'error'}))


# -------------------------------------------------------------------- tests --
def gear_state(feat, body=None):
    body = body or base_of(feat).bodies.item(0)
    com = body.physicalProperties.centerOfMass
    return {'volume_mm3': body.volume / CM ** 3,
            'com_mm': [round(com.x / CM, 4), round(com.y / CM, 4), round(com.z / CM, 4)],
            'health': str(feat.healthState), 'message': feat.errorOrWarningMessage}


def rel(a, b):
    return abs(a - b) / b


def circle_sketch(root, name, x_mm, y_mm, r_mm):
    sk = root.sketches.add(root.xYConstructionPlane)
    sk.name = name
    circle = sk.sketchCurves.sketchCircles.addByCenterRadius(P3(x_mm * CM, y_mm * CM, 0), r_mm * CM)
    hor = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    ver = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
    dims = sk.sketchDimensions
    return {'sketch': sk, 'curve': circle,
            'cx': dims.addDistanceDimension(sk.originPoint, circle.centerSketchPoint, hor,
                                            P3(x_mm * CM / 2, y_mm * CM - 0.5, 0)),
            'cy': dims.addDistanceDimension(sk.originPoint, circle.centerSketchPoint, ver,
                                            P3(x_mm * CM - 0.5, y_mm * CM / 2, 0)),
            'dia': dims.addDiameterDimension(circle, P3((x_mm + r_mm) * CM, (y_mm + r_mm) * CM, 0))}


# The tests run as a queue of small tasks, each started by a custom event after
# run() has returned. In the first version everything ran inside run(): the
# features then showed "The extension that owns this feature is not running" and
# never recomputed. 'cmd' tasks run inside a command's execute handler, like a
# real create dialog; 'direct' tasks run straight from the custom event.
EVENT_ID = 'smurn_gearFeatureSpike_next'
CMD_ID = 'smurn_gearFeatureSpike_task'
QUEUE = []
S = {}   # shared test state


def pump():
    if QUEUE:
        app.fireCustomEvent(EVENT_ID, '')


def run_task(fn):
    try:
        fn()
    except Exception:
        REP.items.append({'id': 'TASK', 'title': getattr(fn, '__name__', 'task'), 'status': 'ERROR',
                          'detail': traceback.format_exc().strip().splitlines()[-1],
                          'data': {'traceback': traceback.format_exc()}})
        REP.save()
    pump()


class NextHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            if not QUEUE:
                return
            if QUEUE[0][0] == 'cmd':
                ui.commandDefinitions.itemById(CMD_ID).execute()
            else:
                run_task(QUEUE.pop(0)[1])
        except Exception:
            ui.messageBox('Spike task failed:\n{}'.format(traceback.format_exc()))


class TaskCommandCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        handler = TaskCommandExecute()
        args.command.execute.add(handler)
        _handlers.append(handler)


class TaskCommandExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            if QUEUE:
                run_task(QUEUE.pop(0)[1])
        except Exception:
            ui.messageBox('Spike task failed:\n{}'.format(traceback.format_exc()))


def timeline_names():
    tl = S['design'].timeline
    return ['{}{}'.format(tl.item(i).name, ' (group)' if tl.item(i).isGroup else '')
            for i in range(tl.count)]


def set_mm(dim, mm):
    dim.parameter.value = mm * CM


def gears_check(feats, want_volume, want_xy):
    out, ok = {}, bool(feats)
    for name, feat in feats.items():
        st = gear_state(feat)
        st['volume_rel_error'] = rel(st['volume_mm3'], want_volume)
        st['ok'] = (st['volume_rel_error'] < 5e-3 and abs(st['com_mm'][0] - want_xy[0]) < 1e-3
                    and abs(st['com_mm'][1] - want_xy[1]) < 1e-3)
        ok = ok and st['ok']
        out[name] = st
    return ok, 'gears follow: {}'.format({n: s['ok'] for n, s in out.items()}), out


def queue_create(cid, title, fn):
    QUEUE.append(('cmd', lambda: REP.run(cid, title, fn)))


def queue_edit(cid, title, mode, action, verify):
    """Queue an edit and, one event later, a check that the gears followed."""
    mark = {}

    def act():
        mark['first'] = len(COMPUTES)
        t0 = time.perf_counter()
        action()
        adsk.doEvents()
        mark['action_s'] = round(time.perf_counter() - t0, 3)

    def check():
        def fn():
            ok, detail, data = verify()
            data = {'state': data, 'action_s': mark.get('action_s'),
                    'computes_for_edit': COMPUTES[mark.get('first', 0):]}
            n = len(data['computes_for_edit'])
            if not ok:
                S['design'].computeAll()
                adsk.doEvents()
                data['ok_after_computeAll'] = verify()[0]
                detail += '; after computeAll: {}'.format(
                    'ok' if data['ok_after_computeAll'] else 'still wrong')
            times = [c['seconds'] for c in data['computes_for_edit']]
            return ('PASS' if ok else 'FAIL', '{}; {} compute events {} (edit made {}, took {} s)'.format(
                detail, n, times, 'in a command' if mode == 'cmd' else 'directly',
                mark.get('action_s')), data)
        REP.run(cid, title, fn)

    QUEUE.append((mode, act))
    QUEUE.append(('direct', check))


def build_queue():
    feats = {}
    area24, area30 = Gear(1.0, 24).area(), Gear(1.0, 30).area()

    def setup():
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        try:
            design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        except Exception:
            pass
        S.update(design=design, root=design.rootComponent)
        S['c1'] = circle_sketch(design.rootComponent, 'Gear circle', 30, 20, 12.15)
    QUEUE.append(('direct', setup))

    for builder in ('sketch', 'face'):
        def create(builder=builder):
            t0 = time.perf_counter()
            feat = create_feature(S['c1']['curve'], builder)
            dt = time.perf_counter() - t0
            feats[builder] = feat
            st = gear_state(feat)
            st.update(create_s=round(dt, 3), volume_rel_error=rel(st['volume_mm3'], area24 * 5),
                      timeline=timeline_names(), bodies=S['root'].bRepBodies.count,
                      dependencies=feat.dependencies.count)
            ok = (st['volume_rel_error'] < 5e-3 and abs(st['com_mm'][0] - 30) < 1e-3
                  and abs(st['com_mm'][1] - 20) < 1e-3)
            return ('PASS' if ok else 'FAIL', 'created in {} s, volume error {:.1e}, center {}, '
                    'health {} {}, timeline {}'.format(
                        st['create_s'], st['volume_rel_error'], st['com_mm'], st['health'],
                        st['message'], st['timeline']), st)
        queue_create('F1-' + builder, 'Create as new body, z=24, outline via ' + builder, create)

    def set_param(pid, expr):
        for feat in feats.values():
            feat.parameters.itemById(pid).expression = expr

    queue_edit('F2-move', 'Recompute when the circle moves', 'direct',
               lambda: set_mm(S['c1']['cx'], 50), lambda: gears_check(feats, area24 * 5, (50, 20)))
    queue_edit('F2b-move', 'Recompute when the circle moves back', 'cmd',
               lambda: set_mm(S['c1']['cx'], 30), lambda: gears_check(feats, area24 * 5, (30, 20)))
    queue_edit('F3-resize', 'Recompute when the circle grows (z 24 to 30)', 'direct',
               lambda: set_mm(S['c1']['dia'], 30.3), lambda: gears_check(feats, area30 * 5, (30, 20)))
    queue_edit('F4-thickness', 'Recompute when the thickness parameter changes', 'direct',
               lambda: set_param('thickness', '8 mm'), lambda: gears_check(feats, area30 * 8, (30, 20)))
    queue_edit('F5-module', 'Recompute when the module parameter changes (z 30 to 20)', 'cmd',
               lambda: set_param('module', '1.5 mm'),
               lambda: gears_check(feats, Gear(1.5, 20).area() * 8, (30, 20)))
    queue_edit('F6-rotation', 'Recompute when the rotation parameter changes', 'direct',
               lambda: set_param('rotation', '7 deg'),
               lambda: gears_check(feats, Gear(1.5, 20).area() * 8, (30, 20)))

    def best():
        ok = [b for b in ('face', 'sketch')
              if any(i['id'] == 'F1-' + b and i['status'] == 'PASS' for i in REP.items)]
        return ok[0] if ok else 'face'

    def join():
        root = S['root']
        sk = root.sketches.add(root.xYConstructionPlane)
        sk.name = 'Plate'
        sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(10, -4, 0), P3(18, 4, 0))
        plate = root.features.extrudeFeatures.addSimple(
            sk.profiles.item(0), VI.createByReal(-0.2), NEW_BODY).bodies.item(0)
        S['c2'] = circle_sketch(root, 'Join circle', 130, 0, 12.15)
        before = root.bRepBodies.count
        feat = create_feature(S['c2']['curve'], best(), target=plate)
        S['join'] = feat
        vol = max(root.bRepBodies.item(i).volume for i in range(root.bRepBodies.count)) / CM ** 3
        data = {'builder': best(), 'bodies_before': before, 'bodies_after': root.bRepBodies.count,
                'timeline': timeline_names(), 'features_in_group': [f.name for f in feat.features],
                'volume_rel_error': rel(vol, 80 * 80 * 2 + area24 * 5),
                'health': [str(feat.healthState), feat.errorOrWarningMessage]}
        ok = data['bodies_after'] == before and data['volume_rel_error'] < 5e-3
        return ('PASS' if ok else 'FAIL', 'bodies {} to {}, volume error {:.1e}, group contains {}, '
                'health {}'.format(before, data['bodies_after'], data['volume_rel_error'],
                                   data['features_in_group'], data['health']), data)
    queue_create('F7-join', 'Create as join to an existing body', join)
    queue_edit('F7b-join-move', 'Joined gear follows its circle', 'direct',
               lambda: set_mm(S['c2']['cx'], 150),
               lambda: gears_check({'join': S['join']}, area24 * 5, (150, 0)))

    def arc_input():
        root = S['root']
        sk = root.sketches.add(root.xYConstructionPlane)
        sk.name = 'Gear arc'
        arc = sk.sketchCurves.sketchArcs.addByCenterStartSweep(
            P3(-6, 0, 0), P3(-6 + 1.215, 0, 0), 2 * math.pi / 3)
        S['arc_rad'] = sk.sketchDimensions.addRadialDimension(arc, P3(-4, 1.5, 0))
        S['arc'] = create_feature(arc, best())
        st = gear_state(S['arc'])
        st['volume_rel_error'] = rel(st['volume_mm3'], area24 * 5)
        return ('PASS' if st['volume_rel_error'] < 5e-3 else 'FAIL',
                'arc as input: volume error {:.1e}'.format(st['volume_rel_error']), st)
    queue_create('F8-arc', 'Arc as the input curve (a full gear is drawn)', arc_input)
    queue_edit('F8b-arc-resize', 'Gear follows when the arc radius changes (z 24 to 30)', 'direct',
               lambda: set_mm(S['arc_rad'], 15.1),
               lambda: (lambda st: (rel(st['volume_mm3'], area30 * 5) < 5e-3,
                                    'volume error {:.1e}'.format(rel(st['volume_mm3'], area30 * 5)),
                                    st))(gear_state(S['arc'])))

    for builder in ('face', 'sketch'):
        key = 'big_' + builder

        def big(builder=builder, key=key):
            c = circle_sketch(S['root'], 'Gear circle z200 ' + builder, 0, 300, 100.15)
            t0 = time.perf_counter()
            feat = create_feature(c['curve'], builder)
            create_s = round(time.perf_counter() - t0, 3)
            S[key] = (c, feat)
            st = gear_state(feat)
            st.update(create_s=create_s,
                      volume_rel_error=rel(st['volume_mm3'], Gear(1.0, 200).area() * 5))
            return ('PASS' if st['volume_rel_error'] < 5e-3 else 'FAIL',
                    'z=200 created in {} s, volume error {:.1e}'.format(
                        create_s, st['volume_rel_error']), st)
        queue_create('F9-z200-' + builder, 'Create at z=200, outline via ' + builder, big)
        queue_edit('F9b-z200-move-' + builder, 'Recompute at z=200, outline via ' + builder, 'direct',
                   lambda key=key: set_mm(S[key][0]['cx'], 40),
                   lambda key=key: gears_check({'z200': S[key][1]},
                                               Gear(1.0, 200).area() * 5, (40, 300)))

    def finish():
        REP.run('END', 'run finished', lambda: ('INFO', '{} compute events in total'.format(
            len(COMPUTES)), {'timeline': timeline_names()}))
        app.activeViewport.fit()
        tally = {}
        for it in REP.items:
            tally[it['status']] = tally.get(it['status'], 0) + 1
        ui.messageBox(
            'Custom feature spike finished: {}\n\nReport:\n{}\n\nThe gears stay live while this '
            'add-in is running. Please try by hand:\n'
            '1. Edit sketch "Gear circle", drag the circle, Finish Sketch. Do the gears follow?\n'
            '2. Modify > Change Parameters: change a gear\'s Module or Thickness.\n'
            '3. Undo and redo a few steps.\n'
            '4. Optional: save, close and reopen the document, then repeat step 1.'.format(
                tally, REP.dir))
    QUEUE.append(('direct', finish))


def run(context):
    global _definition, REP
    try:
        _definition = adsk.fusion.CustomFeatureDefinition.create(
            FEATURE_ID, 'Spur Gear Spike', os.path.join(HERE, 'resources'))
        handler = ComputeHandler()
        _definition.customFeatureCompute.add(handler)
        _handlers.append(handler)

        old = ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd = ui.commandDefinitions.addButtonDefinition(CMD_ID, 'Gear feature spike task', '')
        created = TaskCommandCreated()
        cmd.commandCreated.add(created)
        _handlers.append(created)

        event = app.registerCustomEvent(EVENT_ID)
        on_next = NextHandler()
        event.add(on_next)
        _handlers.append(on_next)

        REP = Report()
        del QUEUE[:]
        build_queue()
        pump()   # the tests start once run() has returned
    except Exception:
        ui.messageBox('Custom feature spike failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        del QUEUE[:]
        app.unregisterCustomEvent(EVENT_ID)
        cmd = ui.commandDefinitions.itemById(CMD_ID)
        if cmd:
            cmd.deleteMe()
        _handlers.clear()
    except Exception:
        pass
