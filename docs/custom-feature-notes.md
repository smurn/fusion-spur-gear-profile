# Fusion custom feature API: lessons learned

What we learned about Fusion's custom feature API while building the Spur Gear add-in, written
for whoever builds the next add-in on it. Everything here was observed on Fusion 2705.1.30
(October 2026) on Windows, with Python add-ins. Autodesk marks the API as a preview, so
re-check anything that matters.

Each point says how well it is established:

- **Confirmed**: seen repeatedly, or isolated by an experiment.
- **Observed**: seen, but the cause was not isolated.
- **Open**: not understood.

The working code is in [`fusion_layer/feature.py`](../fusion_layer/feature.py),
[`fusion_layer/geometry.py`](../fusion_layer/geometry.py) and
[`fusion_layer/layout.py`](../fusion_layer/layout.py). The experiments are in `spikes/`
(GearFeatureSpike, MeshSpike, ComponentMeshSpike, LayoutSketchSpike) and described in
[spikes.md](spikes.md) as SPIKE-5 to SPIKE-8.

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
- **A face of that body works, though.** (Confirmed) A joined gear that starts on a face of
  the very body it joins follows the face when the body changes. The dependency refers to the
  face as it is at the feature's place in the timeline, before the join. That face does not
  exist at the end of the timeline, which has two consequences for the edit dialog:
  - It cannot show the face as selected. `addSelection` of the dependency's entity gives a
    selection that is not valid there.
  - Setting `dependency.entity` to a face the user selected at the end of the timeline, which
    is the joined body's new face, fails with "InternalValidationError : face" when the
    timeline is rolled back. Keep the existing dependency unless the user picks a new entity.
- To change a dependency later, set `dependency.entity` under the same timeline rollback.
- **A custom feature can depend on another custom feature.** (Confirmed, SPIKE-6) Not in
  Autodesk's list of allowed entities, but accepted. The dependent feature recomputes whenever
  the other one does, in the same recompute, and this carries on along a chain. Depending on
  the other feature's base feature works the same way. It survives save and reopen, and undo
  and redo. **Deleting the other feature in the timeline deletes the dependent ones with it**
  (Undo restores them).
- **Parameters are rejected as dependencies** with "Invalid argument entity", both a custom
  feature's own parameter and the same `ModelParameter`, although the documentation lists
  "any parameter". (Confirmed, SPIKE-6)
- **Do not depend on another custom feature's body**, nor on a body its combine modifies.
  (Confirmed, SPIKE-6) The dependent feature ends up with no body, and then nothing in the
  document recomputes after an edit.
- To find another custom feature during compute, store its `entityToken` in a named value at
  creation and look it up with `design.findEntityByToken`. (Confirmed, SPIKE-6)
- **Across components, a dependency on another component's custom feature or sketch curve
  must be a proxy through an occurrence** (`entity.createForAssemblyContext(occurrence)`).
  The native object is rejected with "Invalid argument entity". With the proxy, recomputes
  propagate across components as within one. (Confirmed, SPIKE-7) If the component has
  several occurrences, store which one (its entity token) yourself.

## Parameters and other stored values

- `addCustomParameter(id, label, valueInput, units, isVisible)` creates a model parameter owned
  by the feature. It shows up in the parameters dialog under the feature, accepts expressions
  and user parameters, and the feature recomputes when it changes. (Confirmed)
- Create the parameter with `ValueInput.createByString(expression)` and read the dialog's
  `expression`, not its `value`, to keep references to user parameters.
- In the compute handler read `feature.parameters.itemById(id).value`: internal units, cm and
  radians.
- **Parameters cannot be added to an existing feature.** (Confirmed) `CustomFeatureParameters`
  has no `add`; parameters exist only from `CustomFeatureInput.addCustomParameter` at
  creation. A parameter introduced in a later add-in version is missing on older features,
  and `parameters.itemById(id)` then **raises** "Invalid argument id" instead of returning
  None. Wrap it, and fall back to a default.
- **A selection that the preview invalidates disables OK.** (Observed) A Join preview replaced
  the faces of the joined body; with one of those faces selected in the dialog, Fusion greyed
  out OK even though `validateInputs` said the inputs were valid, and nothing was logged. Keep
  the preview from modifying selected entities: we preview such a gear as its own body and
  join it only on OK.
- **Values the dialog needs but cannot compute can be stored in the command.** A dialog runs at
  the end of the timeline, where some of the feature's inputs no longer exist (see the face
  above). We store such a derived value (where the gear starts) in a named value whenever the
  gear is created or edited, and the edit dialog uses it for its checks. The compute itself
  must not write it.
- For non-numeric settings (a checkbox, an operation), use
  `feature.customNamedValues.addOrSetValue(id, text)`. They are stored with the feature but
  are not parameters and do not trigger a recompute.
- **Do not write named values inside the compute handler.** (Confirmed, SPIKE-6) A chain
  whose compute stored a value lost its bodies after the next edit; the same chain without the
  write worked. Write them at creation or in the edit command.

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
- **One broken custom feature can stop every recompute in its document.** (Observed,
  SPIKE-6) With a feature that had lost its body in the document, no feature recomputed after
  any edit, and Compute All ran the handlers but changed no body. Test variants in separate
  documents.
- **A failed compute makes the API call that triggered it raise** "Compute Failed", when the
  change was made through the API. (Observed, SPIKE-8)
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
- **A selection input with the "Features" filter accepts a custom feature clicked in the
  timeline.** (Confirmed) It hands over the `CustomFeature` itself, as a proxy through its
  occurrence when it is in a component.
- **`timelineObject` can fail inside the dialog.** (Observed) In a hybrid design, reading
  `feature.timelineObject.index` from `validateInputs` raised "this is not a parametric
  design", for every custom feature, and `design.designType` reported a direct design. The
  same property worked in `execute` and `executePreview` (for `rollTo`). Do not rely on
  timeline positions while the dialog is checking its inputs.

### Timeline handling during an edit

A feature can only be changed while the timeline marker is before it. Three ways were tried:

| Approach | Result |
|---|---|
| Roll back in `activate` (`rollTo(True)` then `command.beginStep()`), roll forward in `destroy`. This is what Autodesk's sample does. | Works, but the feature is hidden while the dialog is open, and Undo needs an extra step that only moves the timeline marker. |
| `command.editingFeature = feature` and let Fusion roll the timeline. | Undo is clean and the feature is hidden as above, but the setter sometimes raises. Cause unknown. (Open) |
| Leave the timeline alone while the dialog is open. In `execute` and `executePreview`, roll back, apply the change, roll forward, all inside the handler. | **Use this.** The feature stays visible, the preview updates live, Cancel restores everything, and one Undo reverts the edit. (Confirmed) |

With the third approach the user can pick an entity that was created after the feature. That
cannot be a dependency and fails when applied.

## Changing which features a custom feature contains

Needed here to switch a gear between New Body and Join, which adds or removes the combine.
(Confirmed)

- The features inside a custom feature are not separate timeline items, so the marker cannot
  be placed between them. Take them out first: with the marker before the custom feature,
  call `feature.setStartAndEndFeatures(None, None)`. The custom feature stays as an empty
  item and its former contents become ordinary timeline items after it.
- Now the marker can go between them: `base.timelineObject.rollTo(False)` puts it right after
  the base feature, where a new combine is then created. Deleting a contained feature works
  the same way.
- **Roll back before regrouping.** `setStartAndEndFeatures(base, last)` fails with "Didn't roll
  editing feature back" unless the marker is before the custom feature again
  (`feature.timelineObject.rollTo(True)`).
- Regroup in a `finally` block. If the change fails halfway and the features are not put back,
  the custom feature is left empty and everything that looks for its base feature breaks.
- Done inside `execute`, the whole switch is one undo step, and it also works in the preview.

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

- **A compute sees the assembly as it is at the feature's place in the timeline.**
  (Confirmed, SPIKE-7) Occurrence transforms read in the compute handler are those at that
  point. Moving an occurrence later (with the position captured) or driving a joint does not
  trigger a recompute, and Compute All still uses the old positions.
- A proxy sketch curve's `worldGeometry` is in assembly coordinates. (Confirmed, SPIKE-7)
- **A linked projection leads back to its source** through `SketchEntity.referencedEntity`:
  native for a source in the root component, a proxy through the occurrence for a source in
  another component. (Confirmed, SPIKE-8)
- **Any change in a sketch recomputes every feature that depends on a linked projection of
  any of its curves**, not just of the curve that changed. (Confirmed, SPIKE-8)

- **Create the features in the active component**, as Fusion's own features do
  (`design.activeComponent`, and `design.activeOccurrence`, which is None for the root).
  (Confirmed) Creating them in the component that owns the selected sketch felt wrong to the
  user: a gear made from a circle in a layout sketch in the root then landed in the root.
- When the selected entity is in another component, carry its geometry into the feature's
  component: up through the entity's occurrence path into assembly coordinates, applying each
  level's `nativeObject.transform2`, then down through the target occurrence's path with each
  level's inverse (`transform2.copy()`, `invert()`), from the top level down. Transforming
  points and vectors one level at a time avoids having to know the order `Matrix3D.transformBy`
  composes in. (Confirmed)
- Store the active occurrence's entity token with the feature, so that a component with
  several occurrences keeps using the one the feature was made in.
- Compute geometry in the component's model space: `sketch.sketchToModelSpace(point)`,
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
- Whether the target-body dependency was really what broke Join. A face of the target body
  works (see Dependencies).
- Whether `CustomFeatureInput.addDependency` works when lesson 1 is respected.
- What happens when a dependency is deleted, or its sketch is. Deleting a custom feature that
  another depends on: by hand, the dependent ones are deleted too; through the API
  (`deleteMe`), they stay in health state Unknown without a recompute.
- Why `timelineObject` fails inside `validateInputs` in a hybrid design.
