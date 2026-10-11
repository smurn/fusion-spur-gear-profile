# Fusion custom feature API: lessons learned

What we learned about Fusion's custom feature API while building the Spur Gear add-in, written
for whoever builds the next add-in on it. Everything here was observed on Fusion 2705.1.30
(October 2026) on Windows, with Python add-ins. Autodesk marks the API as a preview, so
re-check anything that matters.

Each point says how well it is established:

- **Confirmed**: seen repeatedly, or isolated by an experiment.
- **Observed**: seen, but the cause was not isolated.
- **Open**: not understood.

The working code is in [`fusion_layer/feature.py`](../fusion_layer/feature.py) and
[`fusion_layer/geometry.py`](../fusion_layer/geometry.py). The experiments are in
[`spikes/GearFeatureSpike`](../spikes/GearFeatureSpike) and described in [spikes.md](spikes.md).

## The shape that works

A custom feature groups ordinary timeline features and recomputes them through a handler.
The structure that worked, here and in the Laser Finger Joint add-in:

- A **base feature** holds the body. The body is made without timeline features.
- For Join or Cut, one **combine feature** applies that body to a target.
- The custom feature groups the base feature alone, or the base feature plus the combine
  (`setStartAndEndFeatures(base, last)`; both arguments may be the same feature).
- On recompute, build a new body and swap it in with `BaseFeature.updateBody`.

Autodesk's manual says custom compute is supported only for groups of base features, sketches
and combine features. We did not try anything else.

## Lifecycle

1. **Create features only after `run()` has returned.** (Confirmed) Features created inside
   the add-in's `run()` show "The extension that owns this feature is not running" and never
   recompute. In `run()`, register the definition and commands only. For automated tests,
   start the work from a custom event (`app.registerCustomEvent` / `fireCustomEvent`).
2. **Create the `CustomFeatureDefinition` in `run()`.** `CustomFeatureDefinition.create`
   returns the existing definition if the id is already registered in this session.
3. **The feature id is permanent.** Saved designs refer to their features by it. The same goes
   for custom parameter ids and custom named value ids.
4. **Fusion keeps Python modules loaded between Stop and Run.** (Confirmed) Sub-modules of the
   add-in are not re-imported, so edits are ignored until Fusion restarts. Delete the add-in's
   entries from `sys.modules` at the top of `run()` and import the sub-modules after that.
5. **Without the add-in, designs still open.** (Confirmed) The body stays as last computed, the
   feature gets a different icon, and changing a dependency gives a warning and no recompute.
   After the add-in starts, a recompute picks the changes up.

## Creating a feature

Do it in the create command's `execute` handler:

1. `baseFeatures.add()`, `startEdit()`, add the body, `finishEdit()`.
2. For Join: `combineFeatures.createInput(target, tools)` with `base.bodies.item(0)` as tool.
3. `customFeatures.createInput(definition)`, `addCustomParameter(...)` for each parameter,
   `setStartAndEndFeatures`, `customFeatures.add(input)`.
4. Add the dependencies (see below).

Creation is a single undo step. (Confirmed)

Fusion calls the compute handler twice while the feature is being created. (Confirmed) Ignore
compute events while your own dialog is open and rebuild the body yourself.

## Dependencies

- **Add them after the feature exists, with the timeline rolled back to before it.**
  (Observed) Pattern: remember `timeline.item(markerPosition - 1)`, call
  `feature.timelineObject.rollTo(True)`, `feature.dependencies.add(id, entity)`, then
  `rollTo(False)` on the remembered item. We switched to this at the same time as fixing
  lesson 1, so whether `CustomFeatureInput.addDependency` also works was not isolated.
- **Inside a component, pass the entity as it was selected.** (Confirmed) The native entity
  (`entity.nativeObject`) was rejected with "Invalid argument entity". The selected entity,
  a proxy through the occurrence, is accepted.
- **A dependency triggers a recompute when the entity changes.** (Confirmed) Tested with sketch
  circles and arcs, by moving and resizing them.
- **Do not make the feature depend on the body its combine modifies.** (Observed) A Join gear
  that listed its target body as a dependency did not appear at all, with no error. It worked
  after the dependency was removed, but the Join logic was reworked in the same change.
- To change a dependency later, set `dependency.entity` under the same timeline rollback.

## Parameters and other stored values

- `addCustomParameter(id, label, valueInput, units, isVisible)` creates a model parameter owned
  by the feature. It shows up in the parameters dialog under the feature, accepts expressions
  and user parameters, and the feature recomputes when it changes. (Confirmed)
- Create the parameter with `ValueInput.createByString(expression)` and read the dialog's
  `expression`, not its `value`, to keep references to user parameters.
- In the compute handler read `feature.parameters.itemById(id).value`: internal units, cm and
  radians.
- For non-numeric settings (a checkbox, an operation), use
  `feature.customNamedValues.addOrSetValue(id, text)`. They are stored with the feature but
  are not parameters and do not trigger a recompute.

## The compute handler

```python
base = next(f for f in feature.features
            if f.objectType == adsk.fusion.BaseFeature.classType())
base.startEdit()
try:
    old = base.sourceBodies[0]
    new = build_body(...)                      # may add helper bodies to the base feature
    base.updateBody(old, adsk.fusion.TemporaryBRepManager.get().copy(new))
    new.deleteMe()
finally:
    base.finishEdit()
```

- `updateBody` keeps the identity of the body, so the combine and anything downstream keep
  working. Deleting the old body and adding a new one would break those references.
- While the base feature is in edit mode its bodies are the source bodies; outside edit mode
  `base.bodies` are the result bodies.
- **Report failure with a predefined message id.** (Confirmed)
  `args.computeStatus.statusMessages.addError('DRPOINT_COMPUTE_FAILED', '')` turns the feature
  red in the timeline. Free text is not accepted, so log the details. If the handler changes
  nothing, the previous body stays, and the feature recovers on the next successful compute.

## Making a body without timeline features

`TemporaryBRepManager` creates primitives, booleans, wires and planar faces in memory. It has
**no extrude, sweep, loft or stitch**.

To extrude an arbitrary outline anyway (Confirmed, also inside the compute handler):

1. Build the outline as `Arc3D`, `Line3D` and `NurbsCurve3D` objects in model space.
2. `createWireFromCurves(curves)`, then `createFaceFromPlanarWires([outer, hole, ...])`.
   Further wires become holes.
3. With the base feature in edit mode, add the face body to it: `bRepBodies.add(face, base)`.
4. Extrude that face with `extrudeFeatures.createInput(face, NewBody)`, set
   `input.targetBaseFeature = base`, and add it. Inside a base feature this adds nothing to
   the timeline.
5. Delete the helper face body.

Notes:

- The extrude direction follows the face normal, which is not predictable. Check which side
  the new body is on and repeat with the other direction if needed.
- `ExtrudeFeatureInput.setDistanceExtent` does not exist in this API version. Use
  `setOneSideExtent(DistanceExtentDefinition.create(...), direction)`.
- A temporary sketch inside the base feature (`sketches.addToBaseOrFormFeature`) also works,
  but is about five times slower: 9 s against 1.6 s for a 200-tooth gear.
- Timing for the face route: 0.2 s for 144 curves, 1.6 s for 1200 curves, per recompute.
- A cubic spline can be passed as a degree-3 NURBS made of Bezier segments: clamped knots with
  every interior knot of multiplicity 3. Fusion accepts that.

## The edit command

- Set `definition.editCommandId` to the id of a second command definition. Fusion runs it on
  double-click or Edit Feature. The feature is `ui.activeSelections.item(0).entity`.
- **Fusion offers Edit Feature only in Hybrid and Assembly designs, not in Part designs.**
  (Confirmed, also with the Laser Finger Joint add-in.) In a Part design, double-click does
  nothing and the menu entry is missing. Parameters can still be changed in the parameters
  dialog.
- Selection inputs cannot be filled in `commandCreated`. Use `addSelection` in the `activate`
  event.

### Timeline handling during an edit

A feature can only be changed while the timeline marker is before it. Three ways were tried:

| Approach | Result |
|---|---|
| Roll back in `activate` (`rollTo(True)` then `command.beginStep()`), roll forward in `destroy`. This is what Autodesk's sample does. | Works, but the feature is hidden while the dialog is open, and Undo needs an extra step that only moves the timeline marker. |
| `command.editingFeature = feature` and let Fusion roll the timeline. | Undo is clean and the feature is hidden as above, but the setter sometimes raises. Cause unknown. (Open) |
| Leave the timeline alone while the dialog is open. In `execute` and `executePreview`, roll back, apply the change, roll forward, all inside the handler. | **Use this.** The feature stays visible, the preview updates live, Cancel restores everything, and one Undo reverts the edit. (Confirmed) |

With the third approach the user can pick an entity that was created after the feature. That
cannot be a dependency and fails when applied.

## Preview

- `executePreview` runs the same code as `execute`; Fusion undoes whatever it changed.
- **While editing, apply the change to the feature itself.** (Confirmed) Creating a second,
  temporary feature for the preview only works if the timeline is rolled back to before the
  edited feature for the whole edit. Otherwise two features show up and the gear disappears.
- **Refresh the viewport after a preview** (`app.activeViewport.refresh()`). (Observed) After
  the inputs had been invalid for a moment, the next preview stayed invisible until the mouse
  moved over it.
- `validateInputs` decides whether OK is enabled. It runs before the preview and must not
  change the design.

## Join like Fusion's own features

Fusion's features do not ask for a target body; Extrude joins whatever the new body touches.
To match that (Confirmed):

- After building the tool body, test each visible solid body of the component: union
  temporary copies of both with `TemporaryBRepManager.booleanOperation` and compare
  `lumps.count`. If the union has no more lumps than the candidate had, they touch or overlap.
  A bounding-box check first keeps this cheap.
- Use the first hit as the combine's target and add the other hits as extra tool bodies, so
  everything merges into one body.
- To disable OK before any body exists, run the same test with a simple temporary stand-in
  (we use a cylinder of the gear's tip diameter). It can be optimistic; the real test at
  creation still has to handle "nothing to join".

## Components and coordinates

- Create the features in the component that owns the selected entity
  (`native.parentSketch.parentComponent.features`). (Confirmed)
- Compute geometry in that component's model space: `sketch.sketchToModelSpace(point)`,
  `sketch.xDirection`, `sketch.yDirection`. This works for sketches on tilted planes and on
  body faces.

## How we tested

- **Offline dry runs.** Fusion ships Python stub classes for its API under
  `...\webdeploy\production\<hash>\Api\Python\packages\adsk\defs`. Putting that folder on
  `sys.path` lets the add-in be imported and driven outside Fusion. It only catches plain
  Python errors, but that saved many round trips. The same files are a searchable, exact
  reference for method names and docstrings of the installed version.
- **Logging.** `app.log(text)` writes to the Text Commands window. Logging each step of
  creation, with timeline marker positions and feature health, found most problems.
- **Self-running spike.** A queue of small test steps driven by a custom event, each step
  checking body volume and center of mass against expected values.
- **Manual checklist.** [manual-tests.md](manual-tests.md), for what needs a person.

## Still open

- Why `Command.editingFeature` is sometimes refused.
- Whether the target-body dependency was really what broke Join.
- Whether `CustomFeatureInput.addDependency` works when lesson 1 is respected.
- What happens when a dependency is deleted, or its sketch is.
- Whether a joined gear follows its curve after the curve moves (CHK-5 in the spec).
