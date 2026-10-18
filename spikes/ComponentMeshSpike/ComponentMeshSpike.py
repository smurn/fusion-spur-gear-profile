"""SPIKE-7: meshing gears in separate components (throwaway code).

SPIKE-6 showed that a custom feature can depend on another custom feature and
follows it along a chain, with all features in the root component. Here each gear
is in its own component, as in an assembly with joints. Questions:

1. Which form of dependency on another component's feature (or curve) does
   Fusion accept: the native object, or a proxy through the occurrence?
2. Does a gear follow changes to its mate's parameter and curve across
   components, and along a chain A -> B -> C?
3. What happens when the mate's occurrence is moved: by setting its transform,
   and by driving a revolute joint? Does the gear recompute?
4. With a second occurrence of the mate's component, what does the gear see?

As in SPIKE-6, each feature makes a small cylinder ("marker") on its circle at
an angle, its phase. Phases are worked out in root (assembly) space:

    A: phase = its rotation parameter + its occurrence's rotation
    B: phase = 2 * direction(A -> B) + pi - phase(A)      (a mirror, like meshing)
    C: the same, relative to B

and the marker is placed in the component's own space. The phase is recomputed
from the live state each time, so a feature is correct whenever it recomputes.

Variants, each in its own document (one broken feature can block a document's
recomputes, SPIKE-6). B depends on its own circle and on:

    feature-native   A's custom feature, as the native object
    feature-proxy    A's custom feature through A's occurrence
    curve-proxy      A's circle through A's occurrence (control: parameter changes
                     of A should not reach B)

Results go to results/<timestamp>/report.md next to this file.
"""

import datetime
import json
import math
import os
import time
import traceback

import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURE_ID = 'smurn.ComponentMeshSpike'
CM = 0.1  # mm to Fusion's internal cm
MARKER_R, MARKER_H = 1.5, 3.0   # mm

app = adsk.core.Application.get()
ui = app.userInterface
P3 = adsk.core.Point3D.create
V3 = adsk.core.Vector3D.create
VI = adsk.core.ValueInput

VARIANTS = ('feature-native', 'feature-proxy', 'curve-proxy')
RADII = {'A': 10.0, 'B': 15.0, 'C': 10.0}
LOCAL = {'A': (2.0, 1.0), 'B': (-1.0, 3.0), 'C': (1.5, -2.0)}   # circle center in its component
# Occurrence placement (mm, degrees). World centers come out about 25 mm apart.
PLACE = {'A': (0.0, 0.0, 0.0), 'B': (26.0, -3.5, 30.0), 'C': (24.0, 26.0, -50.0)}

_definition = None
_handlers = []
_creating = False
COMPUTES = []
REP = None
S = {'v': {}}


# ---------------------------------------------------------------- reporting --
class Report:
    def __init__(self):
        self.dir = os.path.join(HERE, 'results', datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        os.makedirs(self.dir, exist_ok=True)
        self.items = []

    def mark(self, msg):
        with open(os.path.join(self.dir, 'progress.log'), 'a', encoding='utf-8') as f:
            f.write('{} {}\n'.format(datetime.datetime.now().strftime('%H:%M:%S'), msg))

    def add(self, cid, title, status, detail, data=None):
        self.items.append({'id': cid, 'title': title, 'status': status, 'detail': detail,
                           'data': data or {}})
        self.mark('{} {}: {}'.format(status, cid, detail))
        self.save()

    def run(self, cid, title, fn):
        self.mark('start ' + cid)
        try:
            status, detail, data = fn()
        except Exception:
            status, detail = 'ERROR', traceback.format_exc().strip().splitlines()[-1]
            data = {'traceback': traceback.format_exc()}
        self.add(cid, title, status, detail, data)

    def save(self):
        with open(os.path.join(self.dir, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump({'fusion_version': app.version, 'items': self.items,
                       'computes': COMPUTES}, f, indent=1, default=str)
        lines = ['# Component mesh spike report', '', 'Fusion {}.'.format(app.version), '',
                 '| ID | Check | Status | Detail |', '|---|---|---|---|']
        for it in self.items:
            lines.append('| {} | {} | {} | {} |'.format(
                it['id'], it['title'], it['status'], str(it['detail']).replace('|', '/')))
        with open(os.path.join(self.dir, 'report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')


# ------------------------------------------------------------- feature logic --
def base_of(feat):
    return [f for f in feat.features if f.objectType == adsk.fusion.BaseFeature.classType()][0]


def source_bodies(base):
    try:
        return list(base.sourceBodies)
    except Exception:
        return [base.bodies.item(i) for i in range(base.bodies.count)]


def native(entity):
    return getattr(entity, 'nativeObject', None) or entity


def design_of(feat):
    return feat.parentComponent.parentDesign


def circle_of(feat):
    return native(feat.dependencies.itemById('curve').entity)


def occurrence_of(feat):
    """The occurrence the feature's gear sits in, from the token stored at creation."""
    token = feat.customNamedValues.value('occ')
    for entity in design_of(feat).findEntityByToken(token):
        occ = adsk.fusion.Occurrence.cast(entity)
        if occ:
            return occ
    raise RuntimeError('occurrence of {} not found'.format(feat.name))


def mate_of(feat):
    values = feat.customNamedValues
    if not values.isExistingValue('mate'):
        return None
    for entity in design_of(feat).findEntityByToken(values.value('mate')):
        mate = adsk.fusion.CustomFeature.cast(entity)
        if mate:
            return mate
    raise RuntimeError('mate of {} not found'.format(feat.name))


def local_center(curve):
    """Circle center in its component's space, mm."""
    p = curve.parentSketch.sketchToModelSpace(curve.geometry.center)
    return p.x / CM, p.y / CM


def placement(curve, occ):
    """World center (mm) and the occurrence's rotation about z."""
    p = curve.parentSketch.sketchToModelSpace(curve.geometry.center)
    p.transformBy(occ.transform2)
    _, x_axis, _, _ = occ.transform2.getAsCoordinateSystem()
    return (p.x / CM, p.y / CM), math.atan2(x_axis.y, x_axis.x)


def mesh_phase(mate_center, mate_phase, center):
    d = math.atan2(center[1] - mate_center[1], center[0] - mate_center[0])
    return 2 * d + math.pi - mate_phase


def world_phase(feat, depth=0):
    if depth > 10:
        raise RuntimeError('mate chain too long, or a loop')
    rot = feat.parameters.itemById('rotation').value
    center, occ_rot = placement(circle_of(feat), occurrence_of(feat))
    mate = mate_of(feat)
    if mate is None:
        return rot + occ_rot
    mate_center, _ = placement(circle_of(mate), occurrence_of(mate))
    return mesh_phase(mate_center, world_phase(mate, depth + 1), center) + rot


def local_phase(feat):
    _, occ_rot = placement(circle_of(feat), occurrence_of(feat))
    return world_phase(feat) - occ_rot


def marker(curve, phase):
    """Temporary cylinder in the component's own space."""
    x, y = local_center(curve)
    r = 0.6 * curve.geometry.radius / CM
    x, y = x + r * math.cos(phase), y + r * math.sin(phase)
    return adsk.fusion.TemporaryBRepManager.get().createCylinderOrCone(
        P3(x * CM, y * CM, 0), MARKER_R * CM, P3(x * CM, y * CM, MARKER_H * CM), MARKER_R * CM)


def describe(entity):
    """What a dependency hands back: type, and the occurrence if it is a proxy."""
    if entity is None:
        return 'None'
    ctx = getattr(entity, 'assemblyContext', None)
    return '{}{}'.format(entity.objectType.split('::')[-1], ' via ' + ctx.name if ctx else ' (native)')


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
            deps = feat.dependencies
            entry['deps'] = {deps.item(i).id: describe(deps.item(i).entity) for i in range(deps.count)}
            curve_dep = deps.itemById('curve').entity
            try:   # which space does worldGeometry use, for the entity as stored?
                c = curve_dep.worldGeometry.center
                entry['curve_worldGeometry_mm'] = [round(c.x / CM, 3), round(c.y / CM, 3)]
            except Exception as e:
                entry['curve_worldGeometry_mm'] = 'failed: {}'.format(e)
            comp = feat.parentComponent
            entry['occurrences_of_component'] = design_of(feat).rootComponent.allOccurrencesByComponent(comp).count
            phase = local_phase(feat)
            entry['local_phase_deg'] = round(math.degrees(phase), 4)
            base = base_of(feat)
            base.startEdit()
            try:
                old = source_bodies(base)[0]
                entry['updated'] = base.updateBody(old, marker(circle_of(feat), phase))
            finally:
                base.finishEdit()
        except Exception:
            entry['error'] = traceback.format_exc()
            try:
                args.computeStatus.statusMessages.addError('DRPOINT_COMPUTE_FAILED', '')
            except Exception:
                pass
        finally:
            entry['seconds'] = round(time.perf_counter() - t0, 3)
            COMPUTES.append(entry)
            if REP:
                REP.mark('compute {}'.format({k: v for k, v in entry.items() if k != 'error'}))


def add_dependencies(feat, deps):
    """(id, [(how, entity), ...]) pairs, with the timeline rolled back to before the
    feature. Returns {id: 'ok (how)' or 'FAILED ...'}."""
    timeline = S['design'].timeline
    out = {}
    feat.timelineObject.rollTo(True)
    try:
        for dep_id, candidates in deps:
            errors = []
            for how, entity in candidates:
                try:
                    feat.dependencies.add(dep_id, entity)
                    out[dep_id] = 'ok ({})'.format(how)
                    break
                except Exception as e:
                    errors.append('{}: {}'.format(how, str(e).strip().splitlines()[-1] if str(e) else e))
            else:
                out[dep_id] = 'FAILED ' + '; '.join(errors)
    finally:
        timeline.moveToEnd()
    return out


def create_feature(curve, occ, name, mate=None):
    global _creating
    comp = curve.parentSketch.parentComponent
    _creating = True
    try:
        base = comp.features.baseFeatures.add()
        base.startEdit()
        try:
            comp.bRepBodies.add(marker(curve, 0.0), base)   # the first compute places it
        finally:
            base.finishEdit()
        inp = comp.features.customFeatures.createInput(_definition)
        inp.addCustomParameter('rotation', 'Rotation', VI.createByString('0 deg'), 'deg', True)
        inp.setStartAndEndFeatures(base, base)
        feat = comp.features.customFeatures.add(inp)
        feat.name = name
        feat.customNamedValues.addOrSetValue('occ', occ.entityToken)
        if mate is not None:
            feat.customNamedValues.addOrSetValue('mate', mate.entityToken)
        return feat
    finally:
        _creating = False


# -------------------------------------------------------------------- tests --
EVENT_ID = 'smurn_componentMeshSpike_next'
CMD_ID = 'smurn_componentMeshSpike_task'
QUEUE = []


def pump():
    if QUEUE:
        app.fireCustomEvent(EVENT_ID, '')


def run_task(fn):
    try:
        fn()
    except Exception:
        REP.add('TASK', getattr(fn, '__name__', 'task'), 'ERROR',
                traceback.format_exc().strip().splitlines()[-1], {'traceback': traceback.format_exc()})
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


def matrix(x_mm, y_mm, deg):
    m = adsk.core.Matrix3D.create()
    m.setToRotation(math.radians(deg), V3(0, 0, 1), P3(0, 0, 0))
    m.translation = V3(x_mm * CM, y_mm * CM, 0)
    return m


def circle_sketch(comp, name, x_mm, y_mm, r_mm):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = name
    circle = sk.sketchCurves.sketchCircles.addByCenterRadius(P3(x_mm * CM, y_mm * CM, 0), r_mm * CM)
    hor = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    ver = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
    dims = sk.sketchDimensions
    return {'curve': circle,
            'cx': dims.addDistanceDimension(sk.originPoint, circle.centerSketchPoint, hor,
                                            P3(x_mm * CM / 2, y_mm * CM - 0.5, 0)),
            'cy': dims.addDistanceDimension(sk.originPoint, circle.centerSketchPoint, ver,
                                            P3(x_mm * CM - 0.5, y_mm * CM / 2, 0)),
            'dia': dims.addDiameterDimension(circle, P3((x_mm + r_mm) * CM, (y_mm + r_mm) * CM, 0))}


def use(v):
    st = S['v'][v]
    if app.activeDocument != st['doc']:
        st['doc'].activate()
    S['design'] = st['design']
    return st


def expected_now(v):
    """Where each marker should be, from the live state: occurrence transforms,
    circle positions and A's rotation parameter."""
    st = S['v'][v]
    place, phases = {}, {}
    for k in 'ABC':
        place[k] = placement(st['curves'][k], st['occ'][k])
    phases['A'] = st['feats']['A'].parameters.itemById('rotation').value + place['A'][1]
    phases['B'] = mesh_phase(place['A'][0], phases['A'], place['B'][0])
    phases['C'] = mesh_phase(place['B'][0], phases['B'], place['C'][0])
    out = {}
    for k in 'ABC':
        lx, ly = local_center(st['curves'][k])
        p = phases[k] - place[k][1]
        out[k] = (lx + 0.6 * RADII[k] * math.cos(p), ly + 0.6 * RADII[k] * math.sin(p))
    return out


def markers(v):
    out = {}
    for k, feat in S['v'][v]['feats'].items():
        bodies = base_of(feat).bodies
        if bodies.count == 0:
            out[k] = None
            continue
        com = bodies.item(0).physicalProperties.centerOfMass
        out[k] = (com.x / CM, com.y / CM)
    return out


def compare(got, want):
    out = {}
    for k in 'ABC':
        if got.get(k) is None:
            out[k] = 'no body'
        elif math.hypot(got[k][0] - want[k][0], got[k][1] - want[k][1]) < 1e-3:
            out[k] = True
        else:
            out[k] = 'at ({:.2f}, {:.2f}) not ({:.2f}, {:.2f})'.format(*got[k], *want[k])
    return out


def health(feat):
    try:
        return '{} {}'.format(str(feat.healthState).split('.')[-1], feat.errorOrWarningMessage or '')
    except Exception as e:
        return 'unreadable: {}'.format(e)


def build_queue():
    def new_document(v):
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        try:
            design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        except Exception:
            pass
        S['v'][v] = {'doc': doc, 'design': design}
        use(v)

    for v in VARIANTS:
        def create(v=v):
            st = use(v)
            root = st['design'].rootComponent
            housing = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            housing.component.name = 'Housing'
            housing.isGrounded = True
            st.update(housing=housing, occ={}, curves={}, sketches={}, feats={})
            deps, prev = {}, None
            for k in 'ABC':
                occ = root.occurrences.addNewComponent(matrix(*PLACE[k]))
                occ.component.name = 'Gear {}'.format(k)
                c = circle_sketch(occ.component, 'Circle {}'.format(k), LOCAL[k][0], LOCAL[k][1], RADII[k])
                curve = c['curve']
                st['occ'][k], st['curves'][k], st['sketches'][k] = occ, curve, c
                feat = create_feature(curve, occ, '{} {}'.format(k, v), mate=prev)
                st['feats'][k] = feat
                wanted = [('curve', [('native', curve), ('proxy', curve.createForAssemblyContext(occ))])]
                if prev is not None:
                    mate_occ, mate_curve = st['occ'][prev_k], st['curves'][prev_k]
                    if v == 'feature-native':
                        wanted.append(('mate', [('native', prev)]))
                    elif v == 'feature-proxy':
                        wanted.append(('mate', [('proxy', prev.createForAssemblyContext(mate_occ)),
                                                ('native', prev)]))
                    else:
                        wanted.append(('mate', [('proxy', mate_curve.createForAssemblyContext(mate_occ)),
                                                ('native', mate_curve)]))
                deps[k] = add_dependencies(feat, wanted)
                prev, prev_k = feat, k
            for _ in range(5):
                adsk.doEvents()
            ok = compare(markers(v), expected_now(v))
            failed = [d for dd in deps.values() for d in dd.values() if d.startswith('FAILED')]
            good = not failed and all(x is True for x in ok.values())
            return ('PASS' if good else 'FAIL', 'dependencies {}; markers {}'.format(deps, ok),
                    {'deps': deps, 'health': {k: health(f) for k, f in st['feats'].items()}})
        QUEUE.append(('direct', lambda v=v: new_document(v)))
        QUEUE.append(('cmd', lambda create=create, v=v: REP.run('C-' + v, 'Create chain, ' + v, create)))

    def edit(cid, title, v, action, mode='direct'):
        mark = {}

        def act():
            if 'feats' not in S['v'].get(v, {}):
                return
            st = use(v)
            mark['first'] = len(COMPUTES)
            mark['before'] = markers(v)
            t0 = time.perf_counter()
            mark['note'] = action(st)
            for _ in range(5):
                adsk.doEvents()
            mark['s'] = round(time.perf_counter() - t0, 3)

        def verify():
            if 'feats' not in S['v'].get(v, {}):
                REP.add(cid, title, 'SKIP', 'chain was not created')
                return
            st = use(v)
            computes = COMPUTES[mark.get('first', 0):]
            got = markers(v)
            ok = compare(got, expected_now(v))
            unchanged = {k: got.get(k) is not None and mark['before'].get(k) is not None and
                         math.hypot(got[k][0] - mark['before'][k][0], got[k][1] - mark['before'][k][1]) < 1e-6
                         for k in 'ABC'}
            data = {'computes': computes, 'seconds': mark.get('s'), 'note': mark.get('note'),
                    'health': {k: health(f) for k, f in st['feats'].items()}}
            detail = 'markers {}; unchanged {}; recomputed {}'.format(
                ok, [k for k, u in unchanged.items() if u], [c.get('feature') for c in computes])
            if mark.get('note'):
                detail += '; ' + str(mark['note'])
            good = all(x is True for x in ok.values())
            if not good:
                st['design'].computeAll()
                for _ in range(5):
                    adsk.doEvents()
                data['after_computeAll'] = compare(markers(v), expected_now(v))
                detail += '; after computeAll {}'.format(data['after_computeAll'])
            errors = [c['feature'] for c in computes if c.get('error')]
            if errors:
                detail += '; compute errors in {}'.format(errors)
            REP.add(cid, title, 'PASS' if good else 'FAIL', detail, data)

        QUEUE.append((mode, act))
        QUEUE.append(('direct', verify))

    def set_rot(st, deg):
        st['feats']['A'].parameters.itemById('rotation').expression = '{} deg'.format(deg)

    def move_circle(st, k, dx):
        dim = st['sketches'][k]['cx']
        dim.parameter.value = dim.parameter.value + dx * CM

    def move_occurrence(st):
        occ = st['occ']['A']
        occ.transform2 = matrix(-5.0, 2.0, 15.0)
        note = 'transform set'
        try:
            st['design'].snapshots.add()   # capture the position, as the UI asks to
            note += ', position captured'
        except Exception as e:
            note += ', capture failed: {}'.format(str(e).strip().splitlines()[-1])
        return note

    def drive_joint(st):
        occ, curve = st['occ']['A'], st['curves']['A']
        root = st['design'].rootComponent
        geo = adsk.fusion.JointGeometry.createByPoint(curve.centerSketchPoint.createForAssemblyContext(occ))
        inp = root.asBuiltJoints.createInput(occ, st['housing'], geo)
        inp.setAsRevoluteJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)
        joint = root.asBuiltJoints.add(inp)
        motion = adsk.fusion.RevoluteJointMotion.cast(joint.jointMotion)
        motion.rotationValue = math.radians(20)
        return 'revolute joint driven to 20 deg'

    def second_copy(st):
        root = st['design'].rootComponent
        st['copy'] = root.occurrences.addExistingComponent(st['occ']['A'].component, matrix(-60.0, 0.0, 45.0))
        st['feats']['A'].parameters.itemById('rotation').expression = '40 deg'   # forces recomputes
        return 'second occurrence of Gear A at (-60, 0), then A rotation 40 deg'

    for v in VARIANTS:
        edit('E1-' + v, "A's rotation parameter changes, " + v, v, lambda st: set_rot(st, 30))
        edit('E2-' + v, "A's circle moves in its component, " + v, v, lambda st: move_circle(st, 'A', -3))
        edit('E3-' + v, "B's circle moves (C should follow), " + v, v, lambda st: move_circle(st, 'B', 2))
        edit('E4-' + v, "A's rotation changes inside a command, " + v, v,
             lambda st: set_rot(st, 55), mode='cmd')
        edit('E5-' + v, "A's occurrence is moved and turned, " + v, v, move_occurrence, mode='cmd')
        edit('E6-' + v, "A's revolute joint is driven, " + v, v, drive_joint, mode='cmd')
        edit('E7-' + v, "Second occurrence of A's component, " + v, v, second_copy, mode='cmd')

    def finish():
        tally = {}
        for it in REP.items:
            tally[it['status']] = tally.get(it['status'], 0) + 1
        REP.add('END', 'run finished', 'INFO', '{} compute events in total; {}'.format(len(COMPUTES), tally))
        ui.messageBox('Component mesh spike finished: {}\n\nReport:\n{}\n\nEach variant is in its own '
                      'unsaved document; close them without saving.'.format(tally, REP.dir))
    QUEUE.append(('direct', finish))


def run(context):
    global _definition, REP
    try:
        _definition = adsk.fusion.CustomFeatureDefinition.create(
            FEATURE_ID, 'Component Mesh Spike', os.path.join(HERE, 'resources'))
        handler = ComputeHandler()
        _definition.customFeatureCompute.add(handler)
        _handlers.append(handler)

        old = ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd = ui.commandDefinitions.addButtonDefinition(CMD_ID, 'Component mesh spike task', '')
        created = TaskCommandCreated()
        cmd.commandCreated.add(created)
        _handlers.append(created)

        event = app.registerCustomEvent(EVENT_ID)
        on_next = NextHandler()
        event.add(on_next)
        _handlers.append(on_next)

        REP = Report()
        del QUEUE[:]
        COMPUTES.clear()
        S['v'] = {}
        build_queue()
        pump()   # the tests start once run() has returned
    except Exception:
        ui.messageBox('Component mesh spike failed:\n{}'.format(traceback.format_exc()))


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
