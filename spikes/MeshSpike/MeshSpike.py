"""SPIKE-6: one custom feature that follows another (throwaway code).

Question: if gear B meshes with gear A, which dependency makes B recompute when A
changes, both A's parameters and A's circle, and does it carry on along a chain
A -> B -> C?

No gear math here. Each feature makes a small cylinder ("marker") on its circle at
an angle, its phase:

    A: phase = its rotation parameter
    B: phase = 2 * direction(A -> B) + pi - phase(A)      (a mirror, like meshing)
    C: the same, relative to B

The phase is computed recursively from the mate's parameters and circle, so a
feature is correct whenever it recomputes. The tests check whether it does.

Each variant is one chain A -> B -> C. They differ in what B depends on (and C on
B), besides its own circle:

    feature       A's custom feature (not in Autodesk's list of allowed entities)
    base          A's base feature (not in the list either)
    body          A's body
    param         A's rotation parameter and A's circle
    param-chain   as param, and C also depends on A's parameter and circle
    circle        A's circle only (control: should not see parameter changes)
    feature-join  A is joined to a plate; dependency on A's custom feature
    body-join     A is joined to a plate; dependency on the plate body

Running the add-in builds everything in a new, unsaved document after run() has
returned and writes results/<timestamp>/report.md next to this file.
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
FEATURE_ID = 'smurn.MeshSpike'
CM = 0.1  # mm to Fusion's internal cm
MARKER_R, MARKER_H = 1.5, 3.0   # mm

app = adsk.core.Application.get()
ui = app.userInterface
P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
NEW_BODY = adsk.fusion.FeatureOperations.NewBodyFeatureOperation

VARIANTS = ('feature', 'feature-store', 'base', 'body', 'param', 'param-chain', 'circle', 'feature-join', 'body-join')

_definition = None
_handlers = []
_creating = False
COMPUTES = []
REP = None
S = {}   # shared test state


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
        """fn returns (status, detail, data). Exceptions become ERROR."""
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
        lines = ['# Mesh dependency spike report', '', 'Fusion {}.'.format(app.version), '',
                 '| ID | Check | Status | Detail |', '|---|---|---|---|']
        for it in self.items:
            lines.append('| {} | {} | {} | {} |'.format(
                it['id'], it['title'], it['status'], str(it['detail']).replace('|', '/')))
        with open(os.path.join(self.dir, 'report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')


# ------------------------------------------------------------ feature logic --
def base_of(feat):
    return [f for f in feat.features if f.objectType == adsk.fusion.BaseFeature.classType()][0]


def source_bodies(base):
    try:
        return list(base.sourceBodies)
    except Exception:
        return [base.bodies.item(i) for i in range(base.bodies.count)]


def circle_of(feat):
    return feat.dependencies.itemById('curve').entity


def center_mm(curve):
    c = curve.worldGeometry.center
    return c.x / CM, c.y / CM


def mate_of(feat, log=None):
    """The feature this one meshes with, found by the entity token stored at creation,
    or by name if that fails."""
    values = feat.customNamedValues
    if not values.isExistingValue('mate'):
        return None
    try:
        found = S['design'].findEntityByToken(values.value('mate'))
        if found:
            if log is not None:
                log['mate_lookup'] = 'token'
            return adsk.fusion.CustomFeature.cast(found[0])
    except Exception as e:
        if log is not None:
            log['token_error'] = str(e)
    name = values.value('mate_name')
    feats = feat.parentComponent.features.customFeatures
    for i in range(feats.count):
        if feats.item(i).name == name:
            if log is not None:
                log['mate_lookup'] = 'name'
            return feats.item(i)
    raise RuntimeError('mate {} not found'.format(name))


def mesh_phase(mate_center, mate_phase, center):
    d = math.atan2(center[1] - mate_center[1], center[0] - mate_center[0])
    return 2 * d + math.pi - mate_phase


def phase_of(feat, depth=0):
    """Recursive phase in radians, from the parameters and circles of the chain."""
    if depth > 10:
        raise RuntimeError('mate chain too long, or a loop')
    rot = feat.parameters.itemById('rotation').value
    mate = mate_of(feat)
    if mate is None:
        return rot
    return mesh_phase(center_mm(circle_of(mate)), phase_of(mate, depth + 1),
                      center_mm(circle_of(feat))) + rot


def marker(curve, phase):
    geo = curve.worldGeometry
    r = 0.6 * geo.radius
    x, y, z = geo.center.x + r * math.cos(phase), geo.center.y + r * math.sin(phase), geo.center.z
    return adsk.fusion.TemporaryBRepManager.get().createCylinderOrCone(
        P3(x, y, z), MARKER_R * CM, P3(x, y, z + MARKER_H * CM), MARKER_R * CM)


def store_phase(feat, phase, log):
    try:
        feat.customNamedValues.addOrSetValue('phase', repr(phase))
        log['stored_phase'] = True
    except Exception as e:
        log['stored_phase'] = 'failed: {}'.format(e)


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
            mate = mate_of(feat, entry)
            phase = phase_of(feat)
            entry['phase_deg'] = round(math.degrees(phase), 4)
            if mate is not None and mate.customNamedValues.isExistingValue('phase'):
                # Is a value stored by the mate's own compute usable instead of recursion?
                stored = float(mate.customNamedValues.value('phase'))
                entry['mate_stored_matches'] = abs(math.remainder(stored - phase_of(mate), 2 * math.pi)) < 1e-9
            base = base_of(feat)
            base.startEdit()
            try:
                old = source_bodies(base)[0]
                entry['updated'] = base.updateBody(old, marker(circle_of(feat), phase))
            finally:
                base.finishEdit()
            # Run 2: every compute that stored a value left the body unchanged and the
            # feature in health state Unknown. Only the 'feature-store' chain stores now.
            if feat.customNamedValues.isExistingValue('store'):
                store_phase(feat, phase, entry)
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
    """Adds (id, entity or list of candidates) pairs with the timeline rolled back to
    before the feature. Returns {id: 'ok (how)' or the error}."""
    timeline = S['design'].timeline
    out = {'_marker_before': '{}/{}'.format(timeline.markerPosition, timeline.count)}
    feat.timelineObject.rollTo(True)
    try:
        for dep_id, candidates in deps:
            if not isinstance(candidates, list):
                candidates = [('as is', candidates)]
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
        # Run 1 rolled forward to the item before the marker, as the add-in does; the
        # marker then ended up before the features. Here it always goes to the end.
        timeline.moveToEnd()
        out['_marker_after'] = '{}/{}'.format(timeline.markerPosition, timeline.count)
    return out


def create_feature(curve, name, mate=None, join_target=None, store=False):
    global _creating
    comp = curve.parentSketch.parentComponent
    _creating = True
    try:
        phase = 0.0 if mate is None else mesh_phase(center_mm(circle_of(mate)), phase_of(mate),
                                                     center_mm(curve))
        base = comp.features.baseFeatures.add()
        base.startEdit()
        try:
            comp.bRepBodies.add(marker(curve, phase), base)
        finally:
            base.finishEdit()
        last = base
        if join_target:
            tools = adsk.core.ObjectCollection.create()
            tools.add(base.bodies.item(0))
            inp = comp.features.combineFeatures.createInput(join_target, tools)
            inp.operation = JOIN
            last = comp.features.combineFeatures.add(inp)
        inp = comp.features.customFeatures.createInput(_definition)
        inp.addCustomParameter('rotation', 'Rotation', VI.createByString('0 deg'), 'deg', True)
        inp.setStartAndEndFeatures(base, last)
        feat = comp.features.customFeatures.add(inp)
        feat.name = name
        if mate is not None:
            feat.customNamedValues.addOrSetValue('mate', mate.entityToken)
            feat.customNamedValues.addOrSetValue('mate_name', mate.name)
        feat.customNamedValues.addOrSetValue('phase', repr(phase))
        if store:
            feat.customNamedValues.addOrSetValue('store', '1')
        return feat
    finally:
        _creating = False


def mate_dependencies(variant, mate, chain_mate=None, plate=None):
    """What a feature depends on, besides its own circle, for each variant."""
    def param(f):
        p = f.parameters.itemById('rotation')
        cands = [('custom parameter', p)]
        try:
            cands.append(('model parameter by name', S['design'].allParameters.itemByName(p.name)))
        except Exception:
            pass
        return cands

    kind = variant.split('-')[0]
    if kind == 'feature':
        deps = [('mate', mate)]
    elif kind == 'base':
        deps = [('mate', base_of(mate))]
    elif variant == 'body':
        deps = [('mate', base_of(mate).bodies.item(0))]
    elif variant == 'body-join':
        # A's body is merged into the plate; B is a body of its own.
        deps = [('mate', plate if mate.name.startswith('A ') else base_of(mate).bodies.item(0))]
    elif kind == 'param':
        deps = [('mate_rotation', param(mate)), ('mate_curve', circle_of(mate))]
        if chain_mate is not None:
            deps += [('mate2_rotation', param(chain_mate)), ('mate2_curve', circle_of(chain_mate))]
    elif kind == 'circle':
        deps = [('mate_curve', circle_of(mate))]
    else:
        raise ValueError(variant)
    return deps


# -------------------------------------------------------------------- tests --
EVENT_ID = 'smurn_meshSpike_next'
CMD_ID = 'smurn_meshSpike_task'
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


def circle_sketch(root, name, x_mm, y_mm, r_mm):
    sk = root.sketches.add(root.xYConstructionPlane)
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


# Layout per variant: A (r 10) at (0, y), B (r 15) at (25, y), C (r 10) at (25, y + 25).
RADII = {'A': 10.0, 'B': 15.0, 'C': 10.0}


def layout(i):
    y = 70.0 * i
    return {'A': [0.0, y], 'B': [25.0, y], 'C': [25.0, y + 25.0]}


def expected(v):
    st = S['v'][v]
    c, phases = st['centers'], {'A': st['rotA']}
    phases['B'] = mesh_phase(c['A'], phases['A'], c['B'])
    phases['C'] = mesh_phase(c['B'], phases['B'], c['C'])
    return {k: (c[k][0] + 0.6 * RADII[k] * math.cos(p), c[k][1] + 0.6 * RADII[k] * math.sin(p))
            for k, p in phases.items()}


def marker_xy(feat):
    bodies = base_of(feat).bodies
    if bodies.count == 0:
        return None
    com = bodies.item(0).physicalProperties.centerOfMass
    return com.x / CM, com.y / CM


def timeline_state():
    tl = S['design'].timeline
    items = []
    for i in range(tl.count):
        it = tl.item(i)
        items.append('{}{}{}'.format(it.name, ' [group]' if it.isGroup else '',
                                     ' [rolled back]' if it.isRolledBack else ''))
    return {'marker': tl.markerPosition, 'count': tl.count, 'items': items}


def check(v, which=('A', 'B', 'C')):
    """{name: True/False/'n/a'} for whether each marker sits where it should."""
    st, want, out = S['v'][v], expected(v), {}
    for k in which:
        if k == 'A' and v.endswith('join'):
            out[k] = 'n/a'   # A's body is merged into the plate
            continue
        got = marker_xy(st['feats'][k])
        if got is None:
            out[k] = 'no body'
            continue
        ok = math.hypot(got[0] - want[k][0], got[1] - want[k][1]) < 1e-3
        out[k] = True if ok else 'at ({:.2f}, {:.2f}) not ({:.2f}, {:.2f})'.format(*got, *want[k])
    return out


def health(feat):
    try:
        return '{} {}'.format(str(feat.healthState).split('.')[-1], feat.errorOrWarningMessage or '')
    except Exception as e:
        return 'unreadable: {}'.format(e)


def build_queue():
    def setup():
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        try:
            design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        except Exception:
            pass
        S.update(design=design, root=design.rootComponent, v={})
    QUEUE.append(('direct', setup))

    for i, v in enumerate(VARIANTS):
        def create(v=v, i=i):
            root, pos = S['root'], layout(i)
            st = S['v'][v] = {'centers': pos, 'rotA': 0.0, 'sketches': {}, 'feats': {}}
            target = None
            if v.endswith('join'):
                sk = root.sketches.add(root.xYConstructionPlane)
                sk.name = 'Plate ' + v
                x, y = pos['A']
                sk.sketchCurves.sketchLines.addTwoPointRectangle(
                    P3((x - 15) * CM, (y - 15) * CM, 0), P3((x + 15) * CM, (y + 15) * CM, 0))
                target = root.features.extrudeFeatures.addSimple(
                    sk.profiles.item(0), VI.createByReal(-0.2), NEW_BODY).bodies.item(0)
            deps, prev = {}, None
            for k in 'ABC':
                c = circle_sketch(root, 'Sketch {} {}'.format(k, v), pos[k][0], pos[k][1], RADII[k])
                st['sketches'][k] = c
                name = '{} {}'.format(k, v)
                feat = create_feature(c['curve'], name, mate=prev, store=v.endswith('store'),
                                      join_target=target if k == 'A' else None)
                st['feats'][k] = feat
                extra = []
                if prev is not None:
                    chain = st['feats']['A'] if (v == 'param-chain' and k == 'C') else None
                    extra = mate_dependencies(v, prev, chain, target)
                deps[k] = add_dependencies(feat, [('curve', c['curve'])] + extra)
                prev = feat
            ok = check(v)
            failed = [k for k, d in deps.items() for r in d.values() if r.startswith('FAILED')]
            status = 'PASS' if not failed and all(x in (True, 'n/a') for x in ok.values()) else 'FAIL'
            return status, 'dependencies {}; markers {}'.format(deps, ok), {
                'deps': deps, 'health': {k: health(f) for k, f in st['feats'].items()},
                'timeline': timeline_state()}
        QUEUE.append(('cmd', lambda create=create, v=v: REP.run('C-' + v, 'Create chain, ' + v, create)))

    def edit(cid, title, v, action, mode='direct'):
        mark = {}

        def act():
            if v not in S['v']:
                return
            mark['first'] = len(COMPUTES)
            t0 = time.perf_counter()
            action(S['v'][v])
            for _ in range(5):
                adsk.doEvents()
            mark['s'] = round(time.perf_counter() - t0, 3)

        def verify():
            if v not in S['v']:
                REP.add(cid, title, 'SKIP', 'chain was not created')
                return
            computes = COMPUTES[mark.get('first', 0):]
            names = [c.get('feature') for c in computes]
            ok = check(v)
            data = {'computes': computes, 'seconds': mark.get('s'),
                    'health': {k: health(f) for k, f in S['v'][v]['feats'].items()}}
            tl = timeline_state()
            data['timeline'] = tl
            detail = 'markers {}; recomputed {}; marker {}/{}'.format(ok, names, tl['marker'], tl['count'])
            good = all(x in (True, 'n/a') for x in ok.values())
            if not good:
                S['design'].computeAll()
                adsk.doEvents()
                data['after_computeAll'] = check(v)
                detail += '; after computeAll {}'.format(data['after_computeAll'])
            errors = [c['feature'] for c in computes if c.get('error')]
            if errors:
                detail += '; compute errors in {}'.format(errors)
            REP.add(cid, title, 'PASS' if good else 'FAIL', detail, data)

        QUEUE.append((mode, act))
        QUEUE.append(('direct', verify))

    def set_rot(st, deg):
        st['rotA'] = math.radians(deg)
        st['feats']['A'].parameters.itemById('rotation').expression = '{} deg'.format(deg)

    def move(st, k, dx):
        st['centers'][k][0] += dx
        st['sketches'][k]['cx'].parameter.value = st['centers'][k][0] * CM

    for v in VARIANTS:
        edit('E1-' + v, "A's rotation parameter changes, " + v, v, lambda st: set_rot(st, 30))
        edit('E2-' + v, "A's circle moves, " + v, v, lambda st: move(st, 'A', -8))
        edit('E3-' + v, "B's circle moves (C should follow), " + v, v, lambda st: move(st, 'B', 4))
        edit('E4-' + v, "A's rotation changes inside a command, " + v, v,
             lambda st: set_rot(st, 55), mode='cmd')

    def delete_a(v):
        def fn():
            if v not in S['v']:
                return 'SKIP', 'chain was not created', {}
            st = S['v'][v]
            first = len(COMPUTES)
            ok = st['feats']['A'].deleteMe()
            adsk.doEvents()
            computes = COMPUTES[first:]
            hs = {k: health(st['feats'][k]) for k in 'BC'}
            return 'INFO', 'deleteMe {}; B and C health {}; computes {}'.format(
                ok, hs, [(c.get('feature'), 'error' if c.get('error') else 'ok') for c in computes]), {
                'computes': computes}
        QUEUE.append(('cmd', lambda: REP.run('D-' + v, 'Delete A, what happens to B and C, ' + v, fn)))
    for v in ('feature', 'body', 'param'):
        delete_a(v)

    def finish():
        tally = {}
        for it in REP.items:
            tally[it['status']] = tally.get(it['status'], 0) + 1
        REP.add('END', 'run finished', 'INFO', '{} compute events in total; {}'.format(len(COMPUTES), tally))
        app.activeViewport.fit()
        ui.messageBox(
            'Mesh dependency spike finished: {}\n\nReport:\n{}\n\nThe features stay live while this '
            'add-in runs. By hand, if you like:\n'
            "1. Modify > Change Parameters: change the Rotation of 'A param-chain'. Do B and C "
            'of that row follow?\n'
            '2. Undo a few times (the last steps deleted A in three chains).\n'
            '3. Save, close and reopen, then repeat step 1.'.format(tally, REP.dir))
    QUEUE.append(('direct', finish))


def run(context):
    global _definition, REP
    try:
        _definition = adsk.fusion.CustomFeatureDefinition.create(
            FEATURE_ID, 'Mesh Spike', os.path.join(HERE, 'resources'))
        handler = ComputeHandler()
        _definition.customFeatureCompute.add(handler)
        _handlers.append(handler)

        old = ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd = ui.commandDefinitions.addButtonDefinition(CMD_ID, 'Mesh spike task', '')
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
        build_queue()
        pump()   # the tests start once run() has returned
    except Exception:
        ui.messageBox('Mesh spike failed:\n{}'.format(traceback.format_exc()))


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
