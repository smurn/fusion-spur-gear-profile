"""Feasibility spikes SPIKE-1 to SPIKE-4 (docs/spec.md section 12).

Run from Fusion: UTILITIES > ADD-INS > Scripts and Add-Ins > Scripts > "+" and
pick this folder. The script opens new, unsaved documents, runs every check and
writes results/<timestamp>/report.md, report.json and screenshots next to this
file. Nothing is saved to the cloud. Throwaway code.
"""

import datetime
import importlib
import json
import math
import os
import statistics
import sys
import time
import traceback

import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import spike_geom  # noqa: E402
importlib.reload(spike_geom)
from spike_geom import Gear, max_deviation, cubic_spline_samples  # noqa: E402

# Spikes to run. S5 (cost drivers) and S6 (robust edits) were added after the
# first runs. The findings in docs/spikes.md come from separate runs of
# ('S1', 'S3'), ('S5',) and ('S6', 'S4', 'S2').
RUN = ('S1', 'S3', 'S5', 'S6', 'S4', 'S2')
Z_PERF = (25, 50, 100, 200)      # SPIKE-2 tooth counts, smallest first
PERF_SKIP_AFTER_S = 60           # skip larger z once a build took this long
SOLVE_LIMIT_S = 5                # ... or once a single solve took this long. A
                                 # running API call cannot be interrupted, and the
                                 # first run hung Fusion at z = 100.
TOL = 0.010                      # IN-11 default, mm
CM = 0.1                         # mm to Fusion's internal cm
KEEP_DOCS = False                # keep the SPIKE-1/3/4 documents open too

app = adsk.core.Application.get()
ui = app.userInterface
P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput
ALIGNED = adsk.fusion.DimensionOrientations.AlignedDimensionOrientation
HORIZONTAL = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
VERTICAL = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation


# ---------------------------------------------------------------- reporting --
class Report:
    def __init__(self):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        self.dir = os.path.join(HERE, 'results', stamp)
        os.makedirs(self.dir, exist_ok=True)
        self.items = []
        self.t0 = time.perf_counter()

    def add(self, cid, title, status, detail='', data=None):
        self.items.append({'id': cid, 'title': title, 'status': status,
                           'detail': detail, 'data': data or {}})
        app.log('[{}] {} {}: {}'.format(status, cid, title, detail))
        self.save()
        adsk.doEvents()

    def run(self, cid, title, fn):
        """fn returns (status, detail, data). Exceptions become ERROR."""
        t = time.perf_counter()
        try:
            status, detail, data = fn()
        except Exception:
            status, detail, data = 'ERROR', traceback.format_exc().strip().splitlines()[-1], {
                'traceback': traceback.format_exc()}
        data = dict(data or {})
        data['seconds'] = round(time.perf_counter() - t, 3)
        self.add(cid, title, status, detail, data)
        return status, data

    def save(self):
        with open(os.path.join(self.dir, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump({'fusion_version': app.version, 'items': self.items}, f, indent=1,
                      default=str)
        lines = ['# Spike report', '', 'Fusion {}. Elapsed {:.0f} s.'.format(
            app.version, time.perf_counter() - self.t0), '',
            '| ID | Check | Status | Detail |', '|---|---|---|---|']
        for it in self.items:
            lines.append('| {} | {} | {} | {} |'.format(
                it['id'], it['title'], it['status'], str(it['detail']).replace('|', '/')))
        with open(os.path.join(self.dir, 'report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')


REP = None
# Constraint scheme for full gears. SPIKE-1 picks one when it runs; the default
# is the cheapest scheme found by S5: radius plus offset per fit point, and the
# mirror half fixed by its own dimensions instead of symmetry.
BEST = {'pin': 'b', 'mirror': 'pinned'}
STOP = {}                                 # 'reason' set once a small build is too slow
FIT = {}                                  # (m, z) -> (n_inv, n_tro), from SPIKE-3


# ------------------------------------------------------------------ helpers --
def new_doc(name):
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    try:
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    except Exception:
        pass
    return doc, design


def new_sketch(design, name, hide_others=True):
    root = design.rootComponent
    if hide_others:
        for i in range(root.sketches.count):
            root.sketches.item(i).isLightBulbOn = False
    sk = root.sketches.add(root.xYConstructionPlane)
    sk.name = name
    return sk


def close_doc(doc):
    if not KEEP_DOCS:
        try:
            doc.close(False)
        except Exception:
            pass


def items(coll):
    return [coll.item(i) for i in range(coll.count)]


def kind(ent):
    return ent.objectType.split('::')[-1]


def sample(curve, n):
    """n points along a sketch curve, in sketch mm."""
    ev = curve.geometry.evaluator
    _, t0, t1 = ev.getParameterExtents()
    _, pts = ev.getPointsAtParameters([t0 + (t1 - t0) * i / (n - 1) for i in range(n)])
    return [(p.x / CM, p.y / CM) for p in pts]


def outline_curves(sketch):
    return [c for c in items(sketch.sketchCurves)
            if not c.isConstruction and kind(c) != 'SketchCircle']


def unconstrained(sketch):
    out = {}
    for e in items(sketch.sketchCurves) + items(sketch.sketchPoints):
        if not e.isFullyConstrained:
            out[kind(e)] = out.get(kind(e), 0) + 1
    return out


def collection(pts_cm):
    oc = adsk.core.ObjectCollection.create()
    for x, y in pts_cm:
        oc.add(P3(x, y, 0))
    return oc


def shot(name, target_mm=None, extent_mm=None):
    """Save a viewport image. Returns the file name or the error text."""
    try:
        vp = app.activeViewport
        if target_mm:
            cam = vp.camera
            cam.isSmoothTransition = False
            cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
            cam.target = P3(target_mm[0] * CM, target_mm[1] * CM, 0)
            cam.eye = P3(target_mm[0] * CM, target_mm[1] * CM, 50)
            cam.upVector = adsk.core.Vector3D.create(0, 1, 0)
            cam.viewExtents = extent_mm * CM
            vp.camera = cam
        else:
            vp.fit()
        adsk.doEvents()
        vp.refresh()
        adsk.doEvents()
        vp.saveAsImageFile(os.path.join(REP.dir, name + '.png'), 1600, 1200)
        return name + '.png'
    except Exception:
        return 'screenshot failed: ' + traceback.format_exc().strip().splitlines()[-1]


class Frame:
    """The 'selected' circle plus the construction geometry of SKT-3, SKT-4, SKT-11."""

    def __init__(self, sketch, g, center=(30.0, 20.0), rot_deg=10.0, text='default'):
        self.sk, self.g, self.text = sketch, g, text
        self.errors = []
        self.joins = {}
        self.dims = 0
        cx, cy = center
        self._c, self._rot = center, math.radians(rot_deg)
        curves, sd, gc = sketch.sketchCurves, sketch.sketchDimensions, sketch.geometricConstraints
        self.gc, self.sd = gc, sd
        # Selected circle, d_sel slightly off m*z as in real use (DER-1 rounds it).
        self.circle = curves.sketchCircles.addByCenterRadius(
            P3(cx * CM, cy * CM, 0), g.m * (g.z + 0.3) / 2 * CM)
        self.center = self.circle.centerSketchPoint
        self.cx = sd.addDistanceDimension(sketch.originPoint, self.center, HORIZONTAL,
                                          P3(cx * CM / 2, -0.5, 0))
        self.cy = sd.addDistanceDimension(sketch.originPoint, self.center, VERTICAL,
                                          P3(-0.5, cy * CM / 2, 0))
        sd.addDiameterDimension(self.circle, P3(cx * CM, (cy - g.ra * 1.2) * CM, 0))
        self.ref_circle = curves.sketchCircles.addByCenterRadius(self.center, g.r * CM)
        self.ref_circle.isConstruction = True
        sd.addDiameterDimension(self.ref_circle, P3(cx * CM, (cy - g.ra * 1.4) * CM, 0))
        self.ref_line = self._ray(0.0)
        gc.addHorizontal(self.ref_line)
        self.axis = self._ray(self._rot)
        self.perp = self._ray(self._rot + math.pi / 2)
        gc.addPerpendicular2(self.axis, self.perp)
        mid = self._rot / 2
        self.angle = sd.addAngularDimension(
            self.ref_line, self.axis,
            P3((cx + g.r * 0.5 * math.cos(mid)) * CM, (cy + g.r * 0.5 * math.sin(mid)) * CM, 0))

    def _ray(self, ang):
        cx, cy = self._c
        line = self.sk.sketchCurves.sketchLines.addByTwoPoints(
            self.center, P3((cx + self.g.r * math.cos(ang)) * CM,
                            (cy + self.g.r * math.sin(ang)) * CM, 0))
        line.isConstruction = True
        self.gc.addCoincident(line.endSketchPoint, self.ref_circle)
        return line

    # Tooth frame (mm) to sketch (cm), using the frame as it was created.
    def cm(self, p, mirror=False):
        x, y = p[0], (-p[1] if mirror else p[1])
        c, s = math.cos(self._rot), math.sin(self._rot)
        return ((self._c[0] + x * c - y * s) * CM, (self._c[1] + x * s + y * c) * CM)

    # Current state, read back from the sketch.
    def center_mm(self):
        p = self.center.geometry
        return p.x / CM, p.y / CM

    def rot(self):
        a, b = self.axis.startSketchPoint.geometry, self.axis.endSketchPoint.geometry
        return math.atan2(b.y - a.y, b.x - a.x)

    def to_tooth(self, pts_mm):
        (cx, cy), r = self.center_mm(), self.rot()
        c, s = math.cos(r), math.sin(r)
        return [((x - cx) * c + (y - cy) * s, -(x - cx) * s + (y - cy) * c) for x, y in pts_mm]

    def tooth_samples(self, curve, n=40):
        return self.to_tooth(sample(curve, n))

    def attempt(self, label, fn):
        try:
            return fn()
        except Exception:
            self.errors.append(label + ': ' + traceback.format_exc().strip().splitlines()[-1])
            return None

    def join(self, label, keep, other):
        """Make two end points one. A coincident constraint between two spline
        ends failed to solve in the first run, so merging is tried first."""
        for how, fn in (('merge', lambda: keep.merge(other)),
                        ('coincident', lambda: self.gc.addCoincident(other, keep))):
            try:
                if fn():
                    self.joins[label] = how
                    return True
            except Exception:
                self.errors.append('{} by {}: {}'.format(
                    label, how, traceback.format_exc().strip().splitlines()[-1]))
        self.joins[label] = 'not joined'
        return False

    def attach(self, label, keep, other):
        """Make sure two sketch points are one and the same point."""
        try:
            if keep == other or keep.entityToken == other.entityToken:
                self.joins[label] = 'shared'
                return True
        except Exception:
            pass
        return self.join(label, keep, other)

    def spline(self, pts_tooth, mirror=False, perturb=0.0):
        pts = []
        for i, p in enumerate(pts_tooth):
            x, y = self.cm(p, mirror)
            pts.append((x + perturb * CM * math.sin(7 * i + 1), y + perturb * CM * math.cos(5 * i)))
        return self.sk.sketchCurves.sketchFittedSplines.add(collection(pts))

    def _text(self, p):
        if self.text == 'stacked':
            return P3(*self.cm((self.g.r * 0.3, self.g.r * 0.08)), 0)
        return P3(*self.cm(p), 0)

    def pin(self, pt, p, method):
        """Fix sketch point pt (tooth-frame position p) relative to center and axis."""
        x, y = p
        sd = self.sd
        if method == 'a':    # two offset dimensions
            self.attempt('pin a1', lambda: sd.addOffsetDimension(self.axis, pt, self._text((x, y / 2))))
            self.attempt('pin a2', lambda: sd.addOffsetDimension(self.perp, pt, self._text((x / 2, y))))
        elif method == 'b':  # radius plus offset from the tooth axis
            self.attempt('pin b1', lambda: sd.addDistanceDimension(
                self.center, pt, ALIGNED, self._text((x / 2, y / 2 + 0.3))))
            self.attempt('pin b2', lambda: sd.addOffsetDimension(self.axis, pt, self._text((x, y / 2))))
        else:                # 'c': radius plus angle, needs one construction line per point
            line = self.sk.sketchCurves.sketchLines.addByTwoPoints(self.center, pt)
            line.isConstruction = True
            self.attempt('pin c1', lambda: sd.addDistanceDimension(
                self.center, pt, ALIGNED, self._text((x / 2, y / 2 + 0.3))))
            self.attempt('pin c2', lambda: sd.addAngularDimension(
                self.axis, line, self._text((x * 0.7, y * 0.35))))
        self.dims += 2

    def set_rot(self, deg):
        self.angle.parameter.value = math.radians(deg)
        adsk.doEvents()

    def move_center(self, x_mm, y_mm):
        self.cx.parameter.value = x_mm * CM
        self.cy.parameter.value = y_mm * CM
        adsk.doEvents()


def arc_end(arc, pt, other=False):
    """The end point of the arc nearest to sketch point pt, or the other one."""
    a, b = arc.startSketchPoint, arc.endSketchPoint
    if a.geometry.distanceTo(pt.geometry) > b.geometry.distanceTo(pt.geometry):
        a, b = b, a
    return b if other else a


def arc_diag(arcs):
    """Which parts of each arc Fusion reports as fully constrained."""
    return {name: {'arc': a.isFullyConstrained, 'center': a.centerSketchPoint.isFullyConstrained,
                   'start': a.startSketchPoint.isFullyConstrained,
                   'end': a.endSketchPoint.isFullyConstrained} for name, a in arcs.items()}


def far_end(fr, spline):
    """The end of a flank spline that is farther from the center (the tip)."""
    c = fr.center.geometry
    a, b = spline.startSketchPoint, spline.endSketchPoint
    return a if a.geometry.distanceTo(c) > b.geometry.distanceTo(c) else b


def build_tooth(fr, n_inv, n_tro, pin, mirror, perturb=0.0):
    """Seed half-tooth, its mirror image and the tip arc. Returns the 7 curves."""
    g, sk, gc = fr.g, fr.sk, fr.gc
    arcs = sk.sketchCurves.sketchArcs
    p_inv, p_tro = g.involute_points(n_inv), g.trochoid_points(n_tro)
    inv, tro = fr.spline(p_inv), fr.spline(p_tro)
    joined = fr.join('join', inv.endSketchPoint, tro.startSketchPoint)
    for pt, p in zip(items(inv.fitPoints), p_inv):
        fr.pin(pt, p, pin)
    for pt, p in list(zip(items(tro.fitPoints), p_tro))[1 if joined else 0:]:
        fr.pin(pt, p, pin)
    # Passing sketch points to the arc methods did not attach the arcs in the
    # second run (their centers stayed free), so every shared point is checked.
    root = arcs.addByCenterStartSweep(fr.center, tro.endSketchPoint, g.phi_root)
    fr.attach('root center', fr.center, root.centerSketchPoint)
    fr.attach('root start', tro.endSketchPoint, arc_end(root, tro.endSketchPoint))
    root_free = arc_end(root, tro.endSketchPoint, other=True)
    gap = (g.rf * math.cos(g.tau / 2), g.rf * math.sin(g.tau / 2))
    fr.attempt('root end', lambda: fr.sd.addOffsetDimension(
        fr.axis, root_free, fr._text((gap[0], gap[1] / 2))))
    fr.dims += 1

    if mirror == 'none':     # half-teeth only, to measure what the mirror half costs
        return {'seed': [inv, tro, root], 'mirror': [], 'tip': None, 'all': [inv, tro, root]}
    if mirror == 'api':
        made = sk.mirror([inv, tro, root], fr.axis)
        minv, mtro, mroot = made[0], made[1], made[2]
    elif mirror == 'pinned':  # mirror half fixed by its own dimensions, no symmetry
        flip = lambda p: (p[0], -p[1])
        minv, mtro = fr.spline(p_inv, True), fr.spline(p_tro, True)
        mjoined = fr.join('mjoin', minv.endSketchPoint, mtro.startSketchPoint)
        for pt, p in zip(items(minv.fitPoints), p_inv):
            fr.pin(pt, flip(p), pin)
        for pt, p in list(zip(items(mtro.fitPoints), p_tro))[1 if mjoined else 0:]:
            fr.pin(pt, flip(p), pin)
        mroot = arcs.addByCenterStartSweep(fr.center, P3(*fr.cm(gap, True), 0), g.phi_root)
        fr.attach('mroot center', fr.center, mroot.centerSketchPoint)
        fr.attach('mroot join', mtro.endSketchPoint, arc_end(mroot, mtro.endSketchPoint))
        mroot_free = arc_end(mroot, mtro.endSketchPoint, other=True)
        fr.attempt('mroot end', lambda: fr.sd.addOffsetDimension(
            fr.axis, mroot_free, fr._text((gap[0], -gap[1] / 2))))
        fr.dims += 1
    else:
        minv = fr.spline(p_inv, True, perturb)
        mtro = fr.spline(p_tro, True, perturb)
        mjoined = fr.join('mjoin', minv.endSketchPoint, mtro.startSketchPoint)
        mroot = arcs.addByCenterStartSweep(fr.center, P3(*fr.cm(gap, True), 0), g.phi_root)
        fr.attach('mroot center', fr.center, mroot.centerSketchPoint)
        fr.attach('mroot join', mtro.endSketchPoint, arc_end(mroot, mtro.endSketchPoint))
        mroot_free = arc_end(mroot, mtro.endSketchPoint, other=True)
        if mirror == 'spline':
            for a, b, label in ((inv, minv, 'sym inv'), (tro, mtro, 'sym tro'), (root, mroot, 'sym root')):
                fr.attempt(label, lambda a=a, b=b: gc.addSymmetry(a, b, fr.axis))
        else:  # 'points'
            pairs = list(zip(items(inv.fitPoints), items(minv.fitPoints)))
            pairs += list(zip(items(tro.fitPoints), items(mtro.fitPoints)))[1 if joined and mjoined else 0:]
            pairs.append((root_free, mroot_free))
            for i, (a, b) in enumerate(pairs):
                fr.attempt('sym pt {}'.format(i), lambda a=a, b=b: gc.addSymmetry(a, b, fr.axis))
    tip = arcs.addByCenterStartEnd(fr.center, far_end(fr, minv), far_end(fr, inv))
    fr.attach('tip center', fr.center, tip.centerSketchPoint)
    for label, sp in (('tip end m', minv), ('tip end', inv)):
        fr.attach(label, far_end(fr, sp), arc_end(tip, far_end(fr, sp)))
    return {'seed': [inv, tro, root], 'mirror': [minv, mtro, mroot], 'tip': tip,
            'all': [tip, inv, tro, root, minv, mtro, mroot]}


def add_pattern(fr, curves, count, total='360 deg'):
    inp = fr.gc.createCircularPatternInput(curves, fr.center)
    try:
        inp.quantity = VI.createByReal(count)
    except Exception:
        inp.quantity = VI.createByString(str(count))
    inp.totalAngle = VI.createByString(total)
    return fr.gc.addCircularPattern(inp)


def mark(msg):
    """Progress line, flushed at once, to find where a hung run stopped."""
    with open(os.path.join(REP.dir, 'progress.log'), 'a', encoding='utf-8') as f:
        f.write('{} {}\n'.format(datetime.datetime.now().strftime('%H:%M:%S'), msg))


def timed(label, fn):
    mark('start ' + label)
    t0 = time.perf_counter()
    fn()
    dt = time.perf_counter() - t0
    mark('done  {} {:.3f} s'.format(label, dt))
    return dt


def too_slow(seconds, what):
    """Record that later, larger builds must be skipped."""
    if seconds > SOLVE_LIMIT_S and not STOP.get('reason'):
        STOP['reason'] = '{} took {:.1f} s'.format(what, seconds)
    return bool(STOP.get('reason'))


def build_gear(sketch, g, n_inv, n_tro, deferred=True, text='stacked', count=None,
               pin=None, mirror=None):
    """Full gear per SKT-3 to SKT-7. Returns (frame, tooth, pattern, timings).
    count < z patterns only that many teeth; count 1 adds no pattern."""
    t = {}
    t0 = time.perf_counter()
    count = count or g.z
    pin, mirror = pin or BEST['pin'], mirror or BEST['mirror']
    mark('build z={} count={} deferred={} pin={} mirror={}'.format(
        g.z, count, deferred, pin, mirror))
    sketch.isComputeDeferred = deferred
    fr = Frame(sketch, g, text=text)
    t['frame'] = time.perf_counter() - t0
    t1 = time.perf_counter()
    tooth = build_tooth(fr, n_inv, n_tro, pin, mirror)
    t['tooth'] = time.perf_counter() - t1
    mark('tooth built, joins {}'.format(fr.joins))
    t1 = time.perf_counter()
    total = '360 deg' if count == g.z else '{} deg'.format((count - 1) * 360.0 / g.z)
    pat = add_pattern(fr, tooth['all'], count, total) if count > 1 else None
    t['pattern'] = time.perf_counter() - t1
    mark('pattern added {:.3f} s'.format(t['pattern']))
    t1 = time.perf_counter()
    sketch.isComputeDeferred = False
    adsk.doEvents()
    mark('computed')
    t['compute'] = time.perf_counter() - t1
    t['total'] = time.perf_counter() - t0
    return fr, tooth, pat, {k: round(v, 3) for k, v in t.items()}


def outline_deviation(fr, curves=None, max_points=3000):
    """Max distance (mm) of the sketch outline from the exact outline, after
    folding every point onto the half-tooth."""
    half = fr.g.half_outline()
    curves = curves if curves is not None else outline_curves(fr.sk)
    per = [8 if kind(c) == 'SketchArc' else 30 for c in curves]
    stride = max(1, math.ceil(sum(per) / max_points))
    worst, n = 0.0, 0
    for c, k in list(zip(curves, per))[::stride]:
        pts = fr.to_tooth(sample(c, k))
        n += len(pts)
        worst = max(worst, max_deviation([fr.g.fold(x, y) for x, y in pts], half))
    return worst, len(curves), n


def fit_counts(sketch, g, tol, spacing='arc', n_max=40):
    """Fewest evenly spaced fit points so Fusion's spline stays within tol."""
    splines = sketch.sketchCurves.sketchFittedSplines
    out = {}
    for name, pts_fn, poly in (
            ('inv', lambda n: g.involute_points(n, spacing), g.involute_polyline()),
            ('tro', g.trochoid_points, g.trochoid_polyline())):
        out[name], out[name + '_dev'] = None, None
        for n in range(2, n_max + 1):
            try:
                sp = splines.add(collection([(x * CM, y * CM) for x, y in pts_fn(n)]))
            except Exception:
                continue
            dev = max_deviation(sample(sp, max(60, 25 * (n - 1))), poly)
            sp.deleteMe()
            if dev <= tol:
                out[name], out[name + '_dev'] = n, round(dev, 6)
                break
    return out


def counts_for(design, g):
    key = (g.m, g.z)
    if key not in FIT:
        sk = new_sketch(design, 'fit scratch', hide_others=False)
        c = fit_counts(sk, g, TOL)
        sk.deleteMe()
        FIT[key] = (c['inv'] or 6, c['tro'] or 6)
    return FIT[key]


# ------------------------------------------------------------------ SPIKE-1 --
def spike1():
    doc, design = new_doc('S1')
    g = Gear(1.0, 24)

    def pin_check(method):
        def fn():
            fr = Frame(new_sketch(design, 'S1 pin ' + method), g)
            pts = g.involute_points(5)
            sp = fr.spline(pts)
            n_fit = sp.fitPoints.count
            for pt, p in zip(items(sp.fitPoints), pts):
                fr.pin(pt, p, method)
            adsk.doEvents()
            data = {'fit_points': n_fit, 'dims': fr.dims, 'errors': fr.errors,
                    'spline_fully_constrained': sp.isFullyConstrained,
                    'sketch_fully_constrained': fr.sk.isFullyConstrained,
                    'unconstrained': unconstrained(fr.sk)}
            before = fr.tooth_samples(sp)
            fr.set_rot(37)
            data['rot_error_deg'] = abs(math.degrees(fr.rot()) - 37)
            after = fr.tooth_samples(sp)
            data['shape_change_after_rotate_mm'] = max(math.dist(a, b) for a, b in zip(before, after))
            fr.move_center(45, 13)
            cx, cy = fr.center_mm()
            data['center_error_mm'] = math.hypot(cx - 45, cy - 13)
            after = fr.tooth_samples(sp)
            data['shape_change_after_move_mm'] = max(math.dist(a, b) for a, b in zip(before, after))
            ok = (n_fit == 5 and not fr.errors and data['spline_fully_constrained']
                  and data['rot_error_deg'] < 1e-6 and data['center_error_mm'] < 1e-6
                  and data['shape_change_after_rotate_mm'] < 1e-5
                  and data['shape_change_after_move_mm'] < 1e-5)
            return ('PASS' if ok else 'FAIL',
                    'spline fully constrained={}, {} dims for 5 points, shape change {:.2e} mm, errors={}'.format(
                        data['spline_fully_constrained'], fr.dims,
                        max(data['shape_change_after_rotate_mm'], data['shape_change_after_move_mm']),
                        len(fr.errors)), data)
        return fn

    passed = [m for m in 'abc' if REP.run('S1-2' + m, {
        'a': 'Constrain spline: two offset dimensions per fit point',
        'b': 'Constrain spline: radius plus offset per fit point',
        'c': 'Constrain spline: radius plus angle per fit point'}[m], pin_check(m))[0] == 'PASS']
    if passed and BEST['pin'] not in passed:
        BEST['pin'] = passed[0]

    def sym_check(mode):
        def fn():
            fr = Frame(new_sketch(design, 'S1 symmetry ' + mode), g)
            tooth = build_tooth(fr, 5, 5, BEST['pin'], mode, perturb=0.0 if mode == 'api' else 0.05)
            adsk.doEvents()
            seed_dev = outline_deviation(fr, tooth['seed'])[0]
            mir_dev = outline_deviation(fr, tooth['mirror'])[0]
            fr.set_rot(37)
            mir_dev2 = outline_deviation(fr, tooth['mirror'])[0]
            data = {'errors': fr.errors, 'joins': fr.joins, 'seed_dev_mm': seed_dev,
                    'mirror_dev_mm': mir_dev, 'mirror_dev_after_rotate_mm': mir_dev2,
                    'seed_fully_constrained': [c.isFullyConstrained for c in tooth['seed']],
                    'arcs': arc_diag({'root': tooth['seed'][2], 'mroot': tooth['mirror'][2],
                                      'tip': tooth['tip']}),
                    'mirror_fully_constrained': [c.isFullyConstrained for c in tooth['mirror']],
                    'tip_fully_constrained': tooth['tip'].isFullyConstrained,
                    'sketch_fully_constrained': fr.sk.isFullyConstrained,
                    'unconstrained': unconstrained(fr.sk)}
            ok = (not fr.errors and all(data['mirror_fully_constrained'])
                  and max(mir_dev, mir_dev2) <= seed_dev + 1e-4)
            return ('PASS' if ok else 'FAIL',
                    'mirror deviation {:.5f} mm (seed {:.5f}), mirror fully constrained={}, errors={}'.format(
                        max(mir_dev, mir_dev2), seed_dev, all(data['mirror_fully_constrained']),
                        fr.errors[:2]), data)
        return fn

    titles = {'spline': 'Symmetry constraint directly on splines and arcs',
              'api': 'Sketch.mirror() on splines and arcs',
              'points': 'Symmetry constraint per fit point'}
    passed = [m for m in ('api', 'points', 'spline')
              if REP.run('S1-4-' + m, titles[m], sym_check(m))[0] == 'PASS']
    if passed and BEST['mirror'] == 'points':
        BEST['mirror'] = passed[0]

    state = {}

    def pattern_check(count):
        fr, tooth, pat, t = build_gear(new_sketch(design, 'S1 pattern {}'.format(count)), g, 5, 5,
                                       deferred=False, count=count)
        state['fr'] = fr
        too_slow(t['pattern'] + t['compute'], 'pattern of {} teeth'.format(count))
        created = [e for e in pat.createdEntities if kind(e) != 'SketchPoint']
        seed_dev = outline_deviation(fr, tooth['seed'])[0]
        dev, n_curves, _ = outline_deviation(fr)
        t['rotate'] = round(timed('rotate', lambda: fr.set_rot(37)), 3)
        too_slow(t['rotate'], 'rotating {} teeth'.format(count))
        dev_rot = outline_deviation(fr)[0]
        t['move'] = round(timed('move', lambda: fr.move_center(45, 13)), 3)
        too_slow(t['move'], 'moving {} teeth'.format(count))
        dev2 = max(dev_rot, outline_deviation(fr)[0])
        data = {'errors': fr.errors, 'joins': fr.joins, 'timings_s': t,
                'arcs': arc_diag({'root': tooth['seed'][2], 'mroot': tooth['mirror'][2],
                                  'tip': tooth['tip']}),
                'created_curves': len(created),
                'outline_curves': n_curves, 'seed_dev_mm': seed_dev, 'outline_dev_mm': dev,
                'outline_dev_after_rotate_mm': dev_rot,
                'outline_dev_after_rotate_and_move_mm': dev2,
                'seed_fully_constrained': [c.isFullyConstrained for c in tooth['all']],
                'created_fully_constrained': sum(1 for e in created if e.isFullyConstrained),
                'sketch_fully_constrained': fr.sk.isFullyConstrained,
                'unconstrained': unconstrained(fr.sk), 'pin': BEST['pin'], 'mirror': BEST['mirror'],
                'screenshot': shot('s1_pattern_{}_of_z24'.format(count))}
        ok = (len(created) == 7 * (count - 1) and n_curves == 7 * count
              and max(dev, dev2) <= seed_dev + 1e-4
              and data['created_fully_constrained'] == len(created))
        return ('PASS' if ok else 'FAIL',
                '{} curves created (want {}), {} fully constrained, outline deviation {:.5f} mm, '
                'sketch fully constrained={}, pattern {} s, rotate {} s, move {} s'.format(
                    len(created), 7 * (count - 1), data['created_fully_constrained'], max(dev, dev2),
                    data['sketch_fully_constrained'], t['pattern'], t['rotate'], t['move']), data)

    # Grow the pattern step by step: the second run hung on the full z=24 gear.
    for count in (2, 4, 8, 16, 24):
        cid = 'S1-5-n{}'.format(count)
        if STOP.get('reason'):
            REP.add(cid, 'Circular pattern, {} of 24 teeth'.format(count), 'SKIPPED', STOP['reason'])
            continue
        status, _ = REP.run(cid, 'Circular pattern of splines and arcs, {} of 24 teeth'.format(count),
                            lambda count=count: pattern_check(count))
        if status == 'ERROR':
            STOP['reason'] = STOP.get('reason') or 'pattern of {} teeth raised an error'.format(count)

    def partial_pattern():
        sk = new_sketch(design, 'S1 partial pattern')
        pts = sk.sketchPoints
        center, seed = pts.add(P3(0, 0, 0)), pts.add(P3(2, 0, 0))
        out = {}
        for label, sym in (('one_direction', False), ('symmetric', True)):
            inp = sk.geometricConstraints.createCircularPatternInput([seed], center)
            inp.quantity = VI.createByReal(5)
            inp.totalAngle = VI.createByString('90 deg')
            inp.isSymmetric = sym
            pat = sk.geometricConstraints.addCircularPattern(inp)
            out[label] = sorted(round(math.degrees(math.atan2(e.geometry.y, e.geometry.x)), 3)
                                for e in pat.createdEntities)
            pat.deleteMe()
        return 'INFO', 'quantity 5, total 90 deg gives instance angles {}'.format(out), out

    REP.run('S1-5b', 'Circular pattern: totalAngle semantics for a partial pattern', partial_pattern)

    def named_parameter():
        fr = state['fr']
        data = {}
        try:
            fr.angle.parameter.name = 'GearRotation'
            data['rename_model_parameter'] = fr.angle.parameter.name
        except Exception:
            data['rename_model_parameter'] = 'failed: ' + traceback.format_exc().strip().splitlines()[-1]
        up = design.userParameters.add('gear_rot', VI.createByString('15 deg'), 'deg', 'spike')
        fr.angle.parameter.expression = 'gear_rot'
        adsk.doEvents()
        data['rot_after_link_deg'] = math.degrees(fr.rot())
        up.expression = '21 deg'
        adsk.doEvents()
        data['rot_after_user_param_edit_deg'] = math.degrees(fr.rot())
        data['outline_dev_mm'] = outline_deviation(fr)[0]
        ok = (data['rename_model_parameter'] == 'GearRotation'
              and abs(data['rot_after_user_param_edit_deg'] - 21) < 1e-6)
        return 'PASS' if ok else 'FAIL', str(data), data

    if 'fr' in state:
        REP.run('S1-6', 'Rotation dimension as a named parameter (SKT-4)', named_parameter)

    def zero_angle():
        data = {}
        try:
            fr0 = Frame(new_sketch(design, 'S1 zero angle'), g, rot_deg=0.0)
            data['create_at_0_deg'] = 'ok, dimension value {:.4f} deg, axis at {:.4f} deg'.format(
                math.degrees(fr0.angle.parameter.value), math.degrees(fr0.rot()))
        except Exception:
            data['create_at_0_deg'] = 'failed: ' + traceback.format_exc().strip().splitlines()[-1]
        fr = Frame(new_sketch(design, 'S1 angle edits'), g, rot_deg=10.0)
        for deg in (0.0, 10.0, -5.0, 10.0, 14.9):
            try:
                fr.set_rot(deg)
                data['set_{}'.format(deg)] = 'axis at {:.4f} deg'.format(math.degrees(fr.rot()))
            except Exception:
                data['set_{}'.format(deg)] = 'failed: ' + traceback.format_exc().strip().splitlines()[-1]
        return 'INFO', str(data), data

    REP.run('S1-7', 'Rotation dimension at 0 deg (the default p = 0)', zero_angle)
    close_doc(doc)


# ------------------------------------------------------------------ SPIKE-3 --
def spike3():
    doc, design = new_doc('S3')

    def fit_table():
        sk = new_sketch(design, 'S3 fit')
        rows = []
        for m, z in ((1.0, 18), (1.0, 24), (1.0, 100), (5.0, 24)):
            g = Gear(m, z)
            for tol in (0.010, 0.001):
                arc = fit_counts(sk, g, tol, 'arc')
                roll = fit_counts(sk, g, tol, 'roll')
                n_inv = min(n for n in (arc['inv'], roll['inv']) if n) if (arc['inv'] or roll['inv']) else None
                row = {'m': m, 'z': z, 'tol_mm': tol, 'inv_arc_spacing': arc['inv'],
                       'inv_roll_spacing': roll['inv'], 'tro': arc['tro'],
                       'inv_dev': arc['inv_dev'], 'tro_dev': arc['tro_dev']}
                if n_inv and arc['tro']:
                    row['dims_per_half_tooth'] = 2 * (n_inv + arc['tro'] - 1) + 1
                    if tol == TOL:
                        FIT[(m, z)] = (arc['inv'] or n_inv, arc['tro'])
                rows.append(row)
        detail = '; '.join('m{:g} z{} tol{:g}: inv {} tro {} dims {}'.format(
            r['m'], r['z'], r['tol_mm'], r['inv_arc_spacing'], r['tro'],
            r.get('dims_per_half_tooth')) for r in rows)
        return 'INFO', detail, {'rows': rows}

    REP.run('S3-1', 'Fit points and dimensions per half-tooth', fit_table)

    def interpolation():
        sk = new_sketch(design, 'S3 interpolation')
        g = Gear(1.0, 24)
        out = {}
        for n in (4, 6, 9):
            pts = g.involute_points(n)
            sp = sk.sketchCurves.sketchFittedSplines.add(collection([(x * CM, y * CM) for x, y in pts]))
            _, cps, degree, knots, rational, _, _ = sp.geometry.getData()
            fusion_pts = sample(sp, 40 * (n - 1) + 1)
            chords = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
            res = {'degree': degree, 'control_points': len(cps), 'rational': rational,
                   'knots': [round(k, 6) for k in knots],
                   'chord_fractions': [round(sum(chords[:i]) / sum(chords), 6) for i in range(n)],
                   'dev_from_involute_mm': max_deviation(fusion_pts, g.involute_polyline())}
            for param in ('chord', 'centripetal', 'uniform'):
                for end in ('natural', 'notaknot'):
                    mine = cubic_spline_samples(pts, 80, param, end)
                    res['diff_{}_{}_mm'.format(param, end)] = max_deviation(fusion_pts, mine)
            out['n{}'.format(n)] = res
            sp.deleteMe()
        best = min((v, k) for k, v in out['n6'].items() if k.startswith('diff_'))
        ok = best[0] < 1e-5
        return ('PASS' if ok else 'FAIL',
                'Fusion spline degree {}; closest pure-Python cubic for 6 points: {} = {:.2e} mm'.format(
                    out['n6']['degree'], best[1], best[0]), out)

    REP.run('S3-2', 'Can Fusion fitted-spline interpolation be reproduced in pure Python (ARC-1)',
            interpolation)

    def clutter():
        g = Gear(1.0, 24)
        n_inv, n_tro = FIT.get((1.0, 24), (5, 5))
        data = {'n_inv': n_inv, 'n_tro': n_tro}
        for pin in 'ab':
            for text in ('default', 'stacked'):
                name = 's3_tooth_pin_{}_{}'.format(pin, text)
                sk = new_sketch(design, name)
                fr = Frame(sk, g, text=text)
                build_tooth(fr, n_inv, n_tro, pin, BEST['mirror'])
                sk.areDimensionsShown = True
                target = fr.cm((g.r, 0))
                target = (target[0] / CM, target[1] / CM)
                data[name] = {'dims': sk.sketchDimensions.count,
                              'constraints': sk.geometricConstraints.count,
                              'errors': fr.errors,
                              'zoom': shot(name, target, 8 * g.m), 'fit': shot(name + '_fit')}
                if text == 'stacked':
                    sk.areDimensionsShown = False
                    data[name]['hidden'] = shot(name + '_dims_hidden', target, 8 * g.m)
        return 'INFO', 'screenshots written, {} + {} fit points'.format(n_inv, n_tro), data

    REP.run('S3-3', 'Dimension clutter screenshots (SKT-12)', clutter)
    close_doc(doc)


# ------------------------------------------------------------------ SPIKE-4 --
def spike4():
    for z in (24, 100):
        doc, design = new_doc('S4 z{}'.format(z))

        def closure(z=z, design=design):
            g = Gear(1.0, z)
            n_inv, n_tro = counts_for(design, g)
            sk = new_sketch(design, 'S4 gear z{}'.format(z))
            fr, tooth, pat, t = build_gear(sk, g, n_inv, n_tro)
            data = {'errors': fr.errors, 'timings_s': t, 'fit_points': [n_inv, n_tro],
                    'outline_curves': len(outline_curves(sk)),
                    'profiles_with_selected_circle': sk.profiles.count}
            fr.circle.isConstruction = True
            adsk.doEvents()
            data['profiles_selected_circle_as_construction'] = sk.profiles.count
            if sk.profiles.count != 1:
                data['join_attempt'] = join_gaps(fr)
                data['profiles_after_join'] = sk.profiles.count
            profs = sorted(items(sk.profiles), key=lambda p: -p.areaProperties().area)
            if not profs:
                return 'FAIL', 'no profile found', data
            prof = profs[0]
            loops = items(prof.profileLoops)
            data['loops'] = len(loops)
            data['outer_loop_curves'] = max(lp.profileCurves.count for lp in loops if lp.isOuter)
            area = prof.areaProperties(
                adsk.fusion.CalculationAccuracy.HighCalculationAccuracy).area / CM ** 2
            data['area_mm2'], data['exact_area_mm2'] = area, g.area()
            data['area_rel_error'] = abs(area - g.area()) / g.area()
            ext = design.rootComponent.features.extrudeFeatures.addSimple(
                prof, VI.createByReal(0.5), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            body = ext.bodies.item(0)
            data['bodies'] = ext.bodies.count
            data['volume_rel_error'] = abs(body.volume / CM ** 3 - area * 5) / (area * 5)
            data['screenshot'] = shot('s4_extrude_z{}'.format(z))
            ok = (sk.profiles.count == 1 and data['outer_loop_curves'] == 7 * z
                  and data['area_rel_error'] < 5e-3 and data['volume_rel_error'] < 1e-6)
            return ('PASS' if ok else 'FAIL',
                    'profiles: {} with the selected circle as drawn, {} with it as construction; '
                    'outer loop {} curves (want {}); area error {:.2e}'.format(
                        data['profiles_with_selected_circle'],
                        data['profiles_selected_circle_as_construction'],
                        data['outer_loop_curves'], 7 * z, data['area_rel_error']), data)

        REP.run('S4-z{}'.format(z), 'One closed profile and extrude, z={}'.format(z), closure)
        close_doc(doc)


def join_gaps(fr):
    """Add coincident constraints between root arc ends that meet at gap centers."""
    buckets = {}
    for c in outline_curves(fr.sk):
        if kind(c) == 'SketchArc' and abs(c.radius / CM - fr.g.rf) < 1e-6:
            for p in (c.startSketchPoint, c.endSketchPoint):
                buckets.setdefault((round(p.geometry.x, 5), round(p.geometry.y, 5)), []).append(p)
    ok = failed = 0
    first_error = ''
    for pts in buckets.values():
        if len(pts) == 2 and pts[0] != pts[1]:
            try:
                fr.gc.addCoincident(pts[0], pts[1])
                ok += 1
            except Exception:
                failed += 1
                first_error = first_error or traceback.format_exc().strip().splitlines()[-1]
    adsk.doEvents()
    return {'added': ok, 'failed': failed, 'first_error': first_error}


# ------------------------------------------------------------------ SPIKE-2 --
def spike2():
    slow = False
    for z in Z_PERF:
        cid = 'S2-z{}'.format(z)
        if slow:
            REP.add(cid, 'Performance z={}'.format(z), 'SKIPPED',
                    'a smaller gear exceeded {} s to build or {} s to solve'.format(
                        PERF_SKIP_AFTER_S, SOLVE_LIMIT_S))
            continue
        doc, design = new_doc('S2 z{}'.format(z))

        def perf(z=z, design=design):
            g = Gear(1.0, z)
            n_inv, n_tro = counts_for(design, g)
            sk = new_sketch(design, 'S2 gear z{}'.format(z))
            fr, tooth, pat, t = build_gear(sk, g, n_inv, n_tro)
            data = {'errors': fr.errors, 'timings_s': t, 'fit_points': [n_inv, n_tro],
                    'dims': sk.sketchDimensions.count, 'constraints': sk.geometricConstraints.count,
                    'curves': sk.sketchCurves.count,
                    'sketch_fully_constrained': sk.isFullyConstrained}
            data['joins'] = fr.joins
            rot, mov = [], []
            # Stop repeating as soon as one solve is slow.
            for deg in (12.0, 3.0, 9.0):
                t0 = time.perf_counter()
                fr.set_rot(deg)
                rot.append(time.perf_counter() - t0)
                if rot[-1] > SOLVE_LIMIT_S:
                    break
            for x in (33.0, 28.0, 31.0):
                if max(rot + mov) > SOLVE_LIMIT_S:
                    break
                t0 = time.perf_counter()
                fr.move_center(x, 20.0)
                mov.append(time.perf_counter() - t0)
            mov = mov or [float('nan')]
            data['rotate_solve_s'] = [round(v, 4) for v in rot]
            data['move_solve_s'] = [round(v, 4) for v in mov]
            data['outline_dev_mm'] = outline_deviation(fr)[0]
            data['screenshot'] = shot('s2_gear_z{}'.format(z))
            # Free the gear so it can be dragged by hand afterwards.
            fr.attempt('free cx', fr.cx.deleteMe)
            fr.attempt('free cy', fr.cy.deleteMe)
            return ('INFO', 'create {:.2f} s, rotate {:.3f} s, move {:.3f} s (medians), '
                    'outline deviation {:.5f} mm, fully constrained={}'.format(
                        t['total'], statistics.median(rot), statistics.median(mov),
                        data['outline_dev_mm'], data['sketch_fully_constrained']), data)

        status, data = REP.run(cid, 'Performance z={}: constrained gear'.format(z), perf)
        solves = [v for v in data.get('rotate_solve_s', []) + data.get('move_solve_s', []) if v == v]
        slow = (status == 'ERROR' or data.get('timings_s', {}).get('total', 0) > PERF_SKIP_AFTER_S
                or max(solves or [0]) > SOLVE_LIMIT_S)
        # These documents stay open for the manual drag test.

    doc, design = new_doc('S2 baselines')

    def baseline():
        out = {}
        for z in Z_PERF:
            g = Gear(1.0, z)
            n_inv, n_tro = counts_for(design, g)
            sk = new_sketch(design, 'S2 plain z{}'.format(z))
            t0 = time.perf_counter()
            sk.isComputeDeferred = True
            splines, arcs = sk.sketchCurves.sketchFittedSplines, sk.sketchCurves.sketchArcs
            p_inv, p_tro = g.involute_points(n_inv), g.trochoid_points(n_tro)
            for k in range(z):
                c, s = math.cos(k * g.tau), math.sin(k * g.tau)
                for sign in (1, -1):
                    for pts in (p_inv, p_tro):
                        splines.add(collection([((x * c - sign * y * s) * CM, (x * s + sign * y * c) * CM)
                                                for x, y in pts]))
                a0 = k * g.tau - g.tip_angle()
                arcs.addByCenterStartSweep(P3(0, 0, 0), P3(g.ra * math.cos(a0) * CM,
                                                           g.ra * math.sin(a0) * CM, 0), 2 * g.tip_angle())
                a1 = k * g.tau + g.root_angle()
                arcs.addByCenterStartSweep(P3(0, 0, 0), P3(g.rf * math.cos(a1) * CM,
                                                           g.rf * math.sin(a1) * CM, 0), 2 * g.phi_root)
            sk.isComputeDeferred = False
            adsk.doEvents()
            out['z{}'.format(z)] = {'create_s': round(time.perf_counter() - t0, 3),
                                    'profiles': sk.profiles.count}
        return 'INFO', 'plain unconstrained outline: {}'.format(out), out

    REP.run('S2-baseline', 'Performance baseline: unconstrained geometry for every tooth', baseline)

    def no_defer():
        g = Gear(1.0, Z_PERF[0])
        n_inv, n_tro = counts_for(design, g)
        fr, tooth, pat, t = build_gear(new_sketch(design, 'S2 no defer'), g, n_inv, n_tro,
                                       deferred=False)
        return 'INFO', 'z={} without isComputeDeferred: {} s'.format(g.z, t['total']), {'timings_s': t}

    REP.run('S2-nodefer', 'Creation time without deferred compute', no_defer)
    close_doc(doc)


# ------------------------------------------------------- SPIKE-2b: cost drivers --
def spike5():
    """Which part of the constraint scheme makes moving the gear slow?

    The third run showed rotating grows linearly (0.22 s at 16 teeth) while
    moving grows much faster (8 s at 16 teeth). Each variant here is timed at
    8 teeth, where the default took about 2 s, so nothing can hang."""
    doc, design = new_doc('S5')
    g = Gear(1.0, 24)
    results = {}

    def variant(name, count=8, pin='a', mirror='points', circle_construction=False,
                defer_solve=False, profiles_shown=True):
        def fn():
            sk = new_sketch(design, 'S5 ' + name)
            fr, tooth, pat, t = build_gear(sk, g, 5, 5, deferred=False, count=count,
                                           pin=pin, mirror=mirror)
            if circle_construction:
                fr.circle.isConstruction = True
            sk.areProfilesShown = profiles_shown

            def change(param, value):
                if defer_solve:
                    sk.isComputeDeferred = True
                param.value = value
                if defer_solve:
                    sk.isComputeDeferred = False
                adsk.doEvents()

            t['rotate'] = timed(name + ' rotate', lambda: change(fr.angle.parameter, math.radians(37)))
            t['move_x'] = timed(name + ' move x', lambda: change(fr.cx.parameter, 4.5))
            t['move_y'] = timed(name + ' move y', lambda: change(fr.cy.parameter, 1.3))
            t['move_x_again'] = timed(name + ' move x again', lambda: change(fr.cx.parameter, 3.1))
            t = {k: round(v, 3) for k, v in t.items()}
            data = {'timings_s': t, 'errors': fr.errors, 'dims': sk.sketchDimensions.count,
                    'constraints': sk.geometricConstraints.count, 'curves': sk.sketchCurves.count,
                    'points': sk.sketchPoints.count, 'profiles': sk.profiles.count,
                    'sketch_fully_constrained': sk.isFullyConstrained,
                    'unconstrained': unconstrained(sk),
                    'outline_dev_mm': outline_deviation(fr)[0]}
            results[name] = t
            return ('INFO', 'rotate {} s, move x {} s, move y {} s, move x again {} s; {} dims, '
                    '{} constraints, {} profiles, fully constrained={}, deviation {:.5f} mm'.format(
                        t['rotate'], t['move_x'], t['move_y'], t['move_x_again'], data['dims'],
                        data['constraints'], data['profiles'], data['sketch_fully_constrained'],
                        data['outline_dev_mm']), data)
        REP.run('S5-' + name.replace(' ', '-'), 'Solve cost: ' + name, fn)

    variant('1 tooth no pattern', count=1)
    variant('8 default')
    variant('8 half teeth only', mirror='none')
    variant('8 mirror pinned no symmetry', mirror='pinned')
    variant('8 pin b', pin='b')
    variant('8 pin c', pin='c')
    variant('8 pin b mirror pinned', pin='b', mirror='pinned')
    variant('8 circle as construction', circle_construction=True)
    variant('8 profiles hidden', profiles_shown=False)
    variant('8 solve deferred', defer_solve=True)
    # Grow the cheapest full-tooth variant, as long as it stays fast.
    full = {k: v for k, v in results.items() if k.startswith('8 ') and 'half' not in k}
    if full:
        name = min(full, key=lambda k: full[k]['move_x'] + full[k]['move_y'])
        opts = {'8 mirror pinned no symmetry': {'mirror': 'pinned'}, '8 pin b': {'pin': 'b'},
                '8 pin c': {'pin': 'c'}, '8 pin b mirror pinned': {'pin': 'b', 'mirror': 'pinned'},
                '8 circle as construction': {'circle_construction': True},
                '8 profiles hidden': {'profiles_shown': False},
                '8 solve deferred': {'defer_solve': True}}.get(name, {})
        last = full[name]
        for count in (16, 24):
            if max(last['move_x'], last['move_y'], last['rotate']) > 2.0:
                REP.add('S5-grow-{}'.format(count), 'Solve cost: best variant at {} teeth'.format(count),
                        'SKIPPED', '"{}" already slow at the previous size'.format(name))
                continue
            label = '{} best ({})'.format(count, name[2:])
            variant(label, count=count, **opts)
            last = results.get(label, {'move_x': 99, 'move_y': 99, 'rotate': 99})
    # The document stays open for a manual drag test.


# ------------------------------------------------------- robustness of edits --
def spike6():
    """Do edits of the position and rotation dimensions always solve?

    In the fourth run, editing the horizontal position by hand gave a 'failed
    to solve' error on the default scheme. This sweeps many values on 8 teeth."""
    doc, design = new_doc('S6')
    g = Gear(1.0, 24)
    for name, pin, mirror in (('pin a with symmetry', 'a', 'points'),
                              ('pin b both halves dimensioned', 'b', 'pinned')):
        def fn(name=name, pin=pin, mirror=mirror):
            fr, tooth, pat, t = build_gear(new_sketch(design, 'S6 ' + name), g, 5, 5,
                                           deferred=False, count=8, pin=pin, mirror=mirror)
            steps = []

            def step(label, param, value, read, want):
                try:
                    param.value = value
                    adsk.doEvents()
                    dev = outline_deviation(fr)[0]
                    if abs(read() - want) > 1e-6:
                        res = 'NOT APPLIED (is {:.4f})'.format(read())
                    elif dev > 0.01:
                        res = 'WRONG SHAPE {:.3f} mm'.format(dev)
                    else:
                        res = 'ok'
                except Exception:
                    res = 'FAILED: ' + traceback.format_exc().strip().splitlines()[-1][:120]
                mark('{} {}: {}'.format(name, label, res))
                steps.append([label, res])

            for x in (32, 35, 45, 80, 31, 10, 31.5, 31):
                step('x={}'.format(x), fr.cx.parameter, x * CM, lambda: fr.center_mm()[0], x)
            for y in (21, 30, 60, 13, 5, 20):
                step('y={}'.format(y), fr.cy.parameter, y * CM, lambda: fr.center_mm()[1], y)
            for deg in (11, 14.9, 37, 60, 89, 91, 135, 179, 10, 37):
                step('rot={}'.format(deg), fr.angle.parameter, math.radians(deg),
                     lambda: math.degrees(fr.rot()) % 360, deg)
            for x in (40, 31, 33):   # the reported case: move x after a rotation to 37 deg
                step('x={} at 37 deg'.format(x), fr.cx.parameter, x * CM, lambda: fr.center_mm()[0], x)
            bad = [s for s in steps if s[1] != 'ok']
            return ('PASS' if not bad else 'FAIL',
                    '{} of {} edits failed: {}'.format(len(bad), len(steps), bad[:5]),
                    {'steps': steps, 'health': str(fr.sk.healthState),
                     'message': fr.sk.errorOrWarningMessage})
        REP.run('S6-' + name.replace(' ', '-'), 'Edits always solve: ' + name, fn)
    # The document stays open.


def run(context):
    global REP
    try:
        REP = Report()
        STOP.clear()
        FIT.clear()
        for name, fn in (('S1', spike1), ('S3', spike3), ('S5', spike5), ('S6', spike6),
                         ('S4', spike4), ('S2', spike2)):
            if name in ('S4', 'S2') and STOP.get('reason'):
                REP.add(name, 'spike skipped', 'SKIPPED',
                        'full gears would hang Fusion: ' + STOP['reason'])
                continue
            if name in RUN:
                try:
                    fn()
                except Exception:
                    REP.add(name, 'spike aborted', 'ERROR',
                            traceback.format_exc().strip().splitlines()[-1],
                            {'traceback': traceback.format_exc()})
        REP.add('END', 'run finished', 'INFO', 'pin={} mirror={}'.format(BEST['pin'], BEST['mirror']))
        tally = {}
        for it in REP.items:
            tally[it['status']] = tally.get(it['status'], 0) + 1
        ui.messageBox('Spikes finished: {}\n\nReport:\n{}\n\nThe "S2 gear" documents are left open '
                      'with the position dimensions removed. In each, edit the sketch, drag the '
                      'center of the large circle and note whether it feels smooth, laggy or '
                      'unusable.'.format(tally, REP.dir))
    except Exception:
        ui.messageBox('Spike script failed:\n{}'.format(traceback.format_exc()))
