"""SPIKE-8: gears oriented from a layout sketch (throwaway code).

Design under test: a layout sketch holds the circles of all gears. Circles that
touch from outside mesh; an optional line from a circle's center fixes where a
tooth points, at most one per gear train. Each gear feature is built on a linked
projection of its layout circle in its own component, depends only on its own
circle and on the layout sketch, and works out its train's orientation from the
sketch alone. The gear features know nothing of each other and are created in an
arbitrary order.

Questions:
1. Can a gear feature in a component depend on the layout sketch, and in which
   form: the layout sketch in the root component, or in its own component
   through an occurrence?
2. Does a projected circle lead back to its layout circle (referencedEntity),
   and in which form (native or proxy)?
3. Does a change in the layout sketch reach gears whose own projected circle
   did not change: turning a train's start line, adding a start line?
4. Do gears in an arbitrary timeline order all compute correctly?

As in SPIKE-6 and 7, each feature makes a small cylinder ("marker") at an angle,
its phase. A simplified mesh rule is used (the plumbing is under test, not the
gear math): along a train, phase(next) = 2 * direction + pi - phase(current),
starting from the start line's angle, or from 0 at the train's first circle.

Variants, each in its own document. Each gear depends on its projected circle and:
    root-sketch        the layout sketch, in the root component
    root-circle        only its layout circle (control: a start line change
                       should not reach it)
    layout-component   the layout sketch, in a "Layout" component, through its
                       occurrence (turned and moved, to catch coordinate mix-ups)
"""

import collections
import datetime
import json
import math
import os
import time
import traceback

import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURE_ID = 'smurn.LayoutSketchSpike'
CM = 0.1  # mm to Fusion's internal cm
MARKER_R, MARKER_H = 1.2, 3.0   # mm
TOUCH = 1e-3                    # mm, tangency tolerance

app = adsk.core.Application.get()
ui = app.userInterface
P3 = adsk.core.Point3D.create
V3 = adsk.core.Vector3D.create
VI = adsk.core.ValueInput

VARIANTS = ('root-sketch', 'root-circle', 'layout-component')
# Layout circles (mm): train 1 = A-B-C, train 2 = D-E, F concentric with A (not connected).
RADII = {'A': 10.0, 'B': 15.0, 'C': 10.0, 'D': 8.0, 'E': 12.0, 'F': 6.0}


def polar(center, length, deg):
    return (center[0] + length * math.cos(math.radians(deg)), center[1] + length * math.sin(math.radians(deg)))


CENTERS = {'A': (0.0, 0.0), 'D': (-40.0, 0.0), 'F': (0.0, 0.0)}
CENTERS['B'] = polar(CENTERS['A'], 25.0, 20.0)
CENTERS['C'] = polar(CENTERS['B'], 25.0, 80.0)
CENTERS['E'] = polar(CENTERS['D'], 20.0, -110.0)
GEARS = 'ABCDE'
CREATE_ORDER = 'ECADB'   # deliberately not train order
# Gear component placement (mm, deg); the gears stay where the layout puts them.
PLACE = {'A': (5.0, -3.0, 25.0), 'B': (20.0, 10.0, -40.0), 'C': (0.0, 30.0, 70.0),
         'D': (-30.0, 5.0, 10.0), 'E': (-50.0, -20.0, -15.0)}
LAYOUT_PLACE = (4.0, -6.0, 15.0)   # the Layout component's occurrence, in that variant

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
        lines = ['# Layout sketch spike report', '', 'Fusion {}.'.format(app.version), '',
                 '| ID | Check | Status | Detail |', '|---|---|---|---|']
        for it in self.items:
            lines.append('| {} | {} | {} | {} |'.format(
                it['id'], it['title'], it['status'], str(it['detail']).replace('|', '/')))
        with open(os.path.join(self.dir, 'report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')


# ---------------------------------------------------------------- geometry --
def native(entity):
    return getattr(entity, 'nativeObject', None) or entity


def describe(entity):
    if entity is None:
        return 'None'
    ctx = getattr(entity, 'assemblyContext', None)
    return '{}{}'.format(entity.objectType.split('::')[-1], ' via ' + ctx.name if ctx else ' (native)')


def occurrence_of(entity, component):
    """The occurrence an entity sits in: its proxy's, else the component's only one."""
    ctx = getattr(entity, 'assemblyContext', None)
    if ctx:
        return ctx
    root = component.parentDesign.rootComponent
    if component == root:
        return None
    occs = root.allOccurrencesByComponent(component)
    if occs.count == 1:
        return occs.item(0)
    raise RuntimeError('{} has {} occurrences'.format(component.name, occs.count))


def to_world(point, occurrence):
    p = point.copy()
    while occurrence is not None:
        p.transformBy(native(occurrence).transform2)
        occurrence = getattr(occurrence, 'assemblyContext', None)
    return p


def rotation_of(occurrence):
    """Rotation about z of an occurrence path (all planes here are XY)."""
    angle = 0.0
    while occurrence is not None:
        _, x_axis, _, _ = native(occurrence).transform2.getAsCoordinateSystem()
        angle += math.atan2(x_axis.y, x_axis.x)
        occurrence = getattr(occurrence, 'assemblyContext', None)
    return angle


def world_xy(sketch, point, occurrence):
    p = to_world(sketch.sketchToModelSpace(point), occurrence)
    return p.x / CM, p.y / CM


def layout_of(sketch, occurrence):
    """Circles, arcs and lines of the layout sketch in world mm, by index."""
    curves = sketch.sketchCurves
    circles = []
    for i in range(curves.sketchCircles.count):
        c = curves.sketchCircles.item(i)
        circles.append({'key': ('circle', i), 'entity': c,
                        'center': world_xy(sketch, c.centerSketchPoint.geometry, occurrence),
                        'r': c.radius / CM})
    lines = []
    for i in range(curves.sketchLines.count):
        ln = curves.sketchLines.item(i)
        lines.append((world_xy(sketch, ln.startSketchPoint.geometry, occurrence),
                      world_xy(sketch, ln.endSketchPoint.geometry, occurrence)))
    return circles, lines, rotation_of(occurrence)


def train_phases(circles, lines, x_angle):
    """World phase of every circle that belongs to a train (touching from outside),
    by index into circles. Raises if a train has more than one start line."""
    n = len(circles)
    nbrs = collections.defaultdict(list)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = circles[i], circles[j]
            d = math.dist(a['center'], b['center'])
            if abs(d - (a['r'] + b['r'])) < TOUCH:
                nbrs[i].append(j)
                nbrs[j].append(i)
    phases, seen = {}, set()
    for start in range(n):
        if start in seen:
            continue
        group, queue = [], [start]
        seen.add(start)
        while queue:
            k = queue.pop(0)
            group.append(k)
            for m in nbrs[k]:
                if m not in seen:
                    seen.add(m)
                    queue.append(m)
        starts = []
        for k in group:
            c = circles[k]['center']
            for p, q in lines:
                if math.dist(p, c) < TOUCH:
                    starts.append((k, math.atan2(q[1] - c[1], q[0] - c[0])))
                elif math.dist(q, c) < TOUCH:
                    starts.append((k, math.atan2(p[1] - c[1], p[0] - c[0])))
        if len(starts) > 1:
            raise RuntimeError('train {} has {} start lines'.format(sorted(group), len(starts)))
        root, phase = starts[0] if starts else (min(group), x_angle)
        phases[root] = phase
        queue = [root]
        while queue:
            k = queue.pop(0)
            for m in nbrs[k]:
                if m not in phases:
                    a, b = circles[k]['center'], circles[m]['center']
                    d = math.atan2(b[1] - a[1], b[0] - a[0])
                    phases[m] = 2 * d + math.pi - phases[k]
                    queue.append(m)
    return phases


def local_center(curve):
    p = curve.parentSketch.sketchToModelSpace(curve.geometry.center)
    return p.x / CM, p.y / CM


def marker(curve, phase):
    x, y = local_center(curve)
    r = 0.6 * curve.geometry.radius / CM
    x, y = x + r * math.cos(phase), y + r * math.sin(phase)
    return adsk.fusion.TemporaryBRepManager.get().createCylinderOrCone(
        P3(x * CM, y * CM, 0), MARKER_R * CM, P3(x * CM, y * CM, MARKER_H * CM), MARKER_R * CM)


def gear_phase(feat, log=None):
    """Local phase of a gear feature, from its projected circle and the layout sketch."""
    stored = feat.dependencies.itemById('curve').entity
    projected = native(stored)
    source = projected.referencedEntity
    if log is not None:
        log['projected'] = describe(stored)
        log['referencedEntity'] = describe(source)
    if source is None:
        raise RuntimeError('the projected circle has no referenced entity')
    layout_circle = native(source)
    layout_occ = occurrence_of(source, layout_circle.parentSketch.parentComponent)
    circles, lines, x_angle = layout_of(layout_circle.parentSketch, layout_occ)
    phases = train_phases(circles, lines, x_angle)
    index = next(i for i, c in enumerate(circles) if c['entity'] == layout_circle)
    if log is not None:
        log['layout'] = '{} circles, {} lines, own index {}'.format(len(circles), len(lines), index)
    world = phases.get(index, x_angle)
    gear_occ = occurrence_of(stored, feat.parentComponent)
    return world - rotation_of(gear_occ)


# ---------------------------------------------------------- custom feature --
def base_of(feat):
    return [f for f in feat.features if f.objectType == adsk.fusion.BaseFeature.classType()][0]


def source_bodies(base):
    try:
        return list(base.sourceBodies)
    except Exception:
        return [base.bodies.item(i) for i in range(base.bodies.count)]


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
            phase = gear_phase(feat, entry)
            entry['local_phase_deg'] = round(math.degrees(phase), 4)
            base = base_of(feat)
            base.startEdit()
            try:
                old = source_bodies(base)[0]
                entry['updated'] = base.updateBody(old, marker(native(deps.itemById('curve').entity), phase))
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
    timeline = S['design'].timeline
    out = {}
    feat.timelineObject.rollTo(True)
    try:
        for dep_id, candidates in deps:
            errors = []
            for how, entity in candidates:
                try:
                    if entity is None:
                        raise RuntimeError('no entity')
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


def create_feature(curve, name):
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
        inp.addCustomParameter('thickness', 'Thickness', VI.createByString('3 mm'), 'mm', True)
        inp.setStartAndEndFeatures(base, base)
        feat = comp.features.customFeatures.add(inp)
        feat.name = name
        return feat
    finally:
        _creating = False


# -------------------------------------------------------------------- tests --
EVENT_ID = 'smurn_layoutSketchSpike_next'
CMD_ID = 'smurn_layoutSketchSpike_task'
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


def mm(x, y):
    return P3(x * CM, y * CM, 0)


def build_layout(comp):
    """The layout sketch with dimensions and constraints. Returns handles."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = 'Gear layout'
    circles, dims, cons = {}, sk.sketchDimensions, sk.geometricConstraints
    hor = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    ver = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
    for k in 'ABCDEF':
        circles[k] = sk.sketchCurves.sketchCircles.addByCenterRadius(mm(*CENTERS[k]), RADII[k] * CM)
    h = {'sketch': sk, 'circles': circles, 'lines': {}}
    for k in 'ABCDEF':
        x, y = CENTERS[k]
        h['dia_' + k] = dims.addDiameterDimension(circles[k], mm(x + RADII[k], y + RADII[k]))
    for k in 'AF':
        cons.addCoincident(circles[k].centerSketchPoint, sk.originPoint)
    cons.addTangent(circles['A'], circles['B'])
    cons.addTangent(circles['B'], circles['C'])
    cons.addTangent(circles['D'], circles['E'])
    h['y_B'] = dims.addDistanceDimension(sk.originPoint, circles['B'].centerSketchPoint, ver,
                                         mm(CENTERS['B'][0] + 3, CENTERS['B'][1] / 2))
    h['x_C'] = dims.addDistanceDimension(sk.originPoint, circles['C'].centerSketchPoint, hor,
                                         mm(CENTERS['C'][0] / 2, CENTERS['C'][1] + 3))
    for name, orient in (('x_D', hor), ('y_D', ver)):
        h[name] = dims.addDistanceDimension(sk.originPoint, circles['D'].centerSketchPoint, orient,
                                            mm(CENTERS['D'][0] / 2, CENTERS['D'][1] - 3))
    h['y_E'] = dims.addDistanceDimension(sk.originPoint, circles['E'].centerSketchPoint, ver,
                                         mm(CENTERS['E'][0] - 3, CENTERS['E'][1] / 2))
    add_start_line(h, 'A', 30.0)
    return h


def add_start_line(h, k, deg):
    """A start line from circle k's center, 15 mm long, its end fixed by dimensions."""
    sk = h['sketch']
    center = h['circles'][k].centerSketchPoint
    c = (center.geometry.x / CM, center.geometry.y / CM)
    end = polar(c, 15.0, deg)
    line = sk.sketchCurves.sketchLines.addByTwoPoints(center, mm(*end))
    hor = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    ver = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
    h['lines'][k] = line
    h['lx_' + k] = sk.sketchDimensions.addDistanceDimension(center, line.endSketchPoint, hor,
                                                            mm(end[0], end[1] + 2))
    h['ly_' + k] = sk.sketchDimensions.addDistanceDimension(center, line.endSketchPoint, ver,
                                                            mm(end[0] + 2, end[1]))
    return line


def use(v):
    st = S['v'][v]
    if app.activeDocument != st['doc']:
        st['doc'].activate()
    S['design'] = st['design']
    return st


def expected_now(v):
    """Where each gear's marker should be, from the live layout sketch and the
    gears' occurrence transforms."""
    st = S['v'][v]
    lay = st['layout']
    circles, lines, x_angle = layout_of(lay['sketch'], st['layout_occ'])
    phases = train_phases(circles, lines, x_angle)
    out = {}
    for k in GEARS:
        layout_circle = lay['circles'][k]
        index = next(i for i, c in enumerate(circles) if c['entity'] == layout_circle)
        p = phases.get(index, x_angle) - rotation_of(st['occ'][k])
        lx, ly = local_center(st['projected'][k])
        r = 0.6 * st['projected'][k].geometry.radius / CM
        out[k] = (lx + r * math.cos(p), ly + r * math.sin(p))
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
    for k in GEARS:
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

    def setup(v):
        """Layout sketch and gear components with projected circles, no gears yet."""
        st = use(v)
        root = st['design'].rootComponent
        if v == 'layout-component':
            layout_occ = root.occurrences.addNewComponent(matrix(*LAYOUT_PLACE))
            layout_occ.component.name = 'Layout'
            lay = build_layout(layout_occ.component)
        else:
            layout_occ, lay = None, build_layout(root)
        st.update(layout=lay, layout_occ=layout_occ, occ={}, projected={}, feats={}, how={})
        for k in GEARS:
            occ = root.occurrences.addNewComponent(matrix(*PLACE[k]))
            occ.component.name = 'Gear {}'.format(k)
            sk = occ.component.sketches.add(occ.component.xYConstructionPlane)
            sk.name = 'Gear {} circle'.format(k)
            source = lay['circles'][k]
            if layout_occ is not None:
                source = source.createForAssemblyContext(layout_occ)
            made, how = None, []
            for label, target in (('native sketch', sk), ('sketch in occurrence', sk.createForAssemblyContext(occ))):
                try:
                    made = target.project2([source], True)
                    how.append(label + ': ok')
                    break
                except Exception as e:
                    how.append('{}: {}'.format(label, str(e).strip().splitlines()[-1]))
            if not made:
                raise RuntimeError('projection failed for {}: {}'.format(k, how))
            st['occ'][k] = occ
            st['projected'][k] = native(made[0])
            st['how'][k] = how
        return 'PASS', 'projections {}'.format(st['how']), {}

    def create(v):
        st = use(v)
        deps = {}
        for k in CREATE_ORDER:
            curve, occ = st['projected'][k], st['occ'][k]
            feat = create_feature(curve, 'Gear {} {}'.format(k, v))
            st['feats'][k] = feat
            wanted = [('curve', [('proxy', curve.createForAssemblyContext(occ)), ('native', curve)])]
            lay = st['layout']
            if v == 'root-sketch':
                wanted.append(('layout', [('native sketch', lay['sketch'])]))
            elif v == 'root-circle':
                wanted.append(('layout', [('native circle', lay['circles'][k])]))
            else:
                proxy = lay['sketch'].createForAssemblyContext(st['layout_occ'])
                wanted.append(('layout', [('sketch proxy', proxy), ('native sketch', lay['sketch'])]))
            deps[k] = add_dependencies(feat, wanted)
        for _ in range(5):
            adsk.doEvents()
        ok = compare(markers(v), expected_now(v))
        failed = [d for dd in deps.values() for d in dd.values() if d.startswith('FAILED')]
        good = not failed and all(x is True for x in ok.values())
        return ('PASS' if good else 'FAIL', 'created in order {}; dependencies {}; markers {}'.format(
            CREATE_ORDER, deps, ok), {'deps': deps, 'health': {k: health(f) for k, f in st['feats'].items()}})

    for v in VARIANTS:
        QUEUE.append(('direct', lambda v=v: new_document(v)))
        QUEUE.append(('cmd', lambda v=v: REP.run('S-' + v, 'Layout and projections, ' + v, lambda: setup(v))))
        QUEUE.append(('cmd', lambda v=v: REP.run('C-' + v, 'Create gears in arbitrary order, ' + v,
                                                 lambda: create(v))))

    def edit(cid, title, v, action, mode='direct', expect_errors=False):
        mark = {}

        def act():
            if 'feats' not in S['v'].get(v, {}) or len(S['v'][v]['feats']) < len(GEARS):
                return
            st = use(v)
            mark['first'] = len(COMPUTES)
            mark['before'] = markers(v)
            mark['note'] = action(st)
            for _ in range(5):
                adsk.doEvents()

        def verify():
            if 'first' not in mark:
                REP.add(cid, title, 'SKIP', 'gears were not created')
                return
            st = use(v)
            computes = COMPUTES[mark['first']:]
            names = [c.get('feature') for c in computes]
            errors = sorted({c.get('feature') for c in computes if c.get('error')})
            data = {'computes': computes, 'health': {k: health(f) for k, f in st['feats'].items()}}
            if expect_errors:
                detail = 'recomputed {}; compute errors in {}; health {}'.format(names, errors, data['health'])
                if mark.get('note'):
                    detail += '; ' + str(mark['note'])
                REP.add(cid, title, 'INFO', detail, data)
                return
            got = markers(v)
            ok = compare(got, expected_now(v))
            moved = [k for k in GEARS if got.get(k) and mark['before'].get(k)
                     and math.dist(got[k], mark['before'][k]) > 1e-6]
            detail = 'markers {}; moved {}; recomputed {}'.format(ok, moved, names)
            if mark.get('note'):
                detail += '; ' + str(mark['note'])
            good = all(x is True for x in ok.values())
            if not good:
                st['design'].computeAll()
                for _ in range(5):
                    adsk.doEvents()
                data['after_computeAll'] = compare(markers(v), expected_now(v))
                detail += '; after computeAll {}'.format(data['after_computeAll'])
            if errors:
                detail += '; compute errors in {}'.format(errors)
            REP.add(cid, title, 'PASS' if good else 'FAIL', detail, data)

        QUEUE.append((mode, act))
        QUEUE.append(('direct', verify))

    def set_dim(st, name, mm_value):
        st['layout'][name].parameter.value = mm_value * CM

    for v in VARIANTS:
        edit('E1-' + v, 'B moves around A in the layout (B and C move), ' + v, v,
             lambda st: set_dim(st, 'y_B', 12.0))
        edit('E2-' + v, "Train 1's start line turns; no gear circle changes, " + v, v,
             lambda st: set_dim(st, 'ly_A', -7.5))
        edit('E3-' + v, 'A start line is added to train 2; no gear circle changes, ' + v, v,
             lambda st: add_start_line(st['layout'], 'D', 135.0) and None)
        edit('E4-' + v, 'A grows (B and C move to stay tangent), ' + v, v,
             lambda st: set_dim(st, 'dia_A', 22.0))
        edit('E5-' + v, "Train 2's start line turns, inside a command, " + v, v,
             lambda st: set_dim(st, 'ly_D', -4.0), mode='cmd')
        edit('E6-' + v, 'A second start line in train 1 (C): the train should fail, ' + v, v,
             lambda st: add_start_line(st['layout'], 'C', 200.0) and 'second start line added',
             expect_errors=True)

    def finish():
        tally = {}
        for it in REP.items:
            tally[it['status']] = tally.get(it['status'], 0) + 1
        REP.add('END', 'run finished', 'INFO', '{} compute events in total; {}'.format(len(COMPUTES), tally))
        ui.messageBox('Layout sketch spike finished: {}\n\nReport:\n{}\n\nEach variant is in its own '
                      'unsaved document; close them without saving.'.format(tally, REP.dir))
    QUEUE.append(('direct', finish))


def run(context):
    global _definition, REP
    try:
        _definition = adsk.fusion.CustomFeatureDefinition.create(
            FEATURE_ID, 'Layout Sketch Spike', os.path.join(HERE, 'resources'))
        handler = ComputeHandler()
        _definition.customFeatureCompute.add(handler)
        _handlers.append(handler)

        old = ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd = ui.commandDefinitions.addButtonDefinition(CMD_ID, 'Layout sketch spike task', '')
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
        ui.messageBox('Layout sketch spike failed:\n{}'.format(traceback.format_exc()))


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
