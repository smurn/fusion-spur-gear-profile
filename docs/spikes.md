# Feasibility spikes: results

Run on 2026-10-10 and 2026-10-11 with Fusion 2705.1.30, using `spikes/GearSpikes`
(throwaway code). Spikes are defined in [spec.md](spec.md) §12.

## Conclusion

The constraint-based design of spec §7 (seed half-tooth, symmetry, sketch circular
pattern) can be built and is geometrically correct, but it is **not usable**:

1. Dragging a full gear takes several seconds to respond (manual test).
2. Editing the position dimension by more than roughly a gear diameter silently fails to
   solve, and a large rotation change corrupts the tooth shape.
3. Solve time grows faster than the tooth count, so no practical tooth limit rescues it.

The replacement, a custom feature that produces a solid gear, was tested in SPIKE-5 and
works: the gear follows its circle, parameters are editable, and a recompute takes 0.2 s at
z = 24 and 1.6 s at z = 200. The spec needs a new draft for this design. The gear math
(`gearcore`, ARC-1) is not affected.

## SPIKE-1 API

| Question | Result |
|---|---|
| Fully constrain a fitted spline | Yes. Two dimensions per fit point; the spline stays rigid when the gear is rotated or moved (shape change about 1e-10 mm). Three dimensioning methods work. |
| Symmetry constraint on a spline | No. `addSymmetry(spline, spline, line)` is accepted but does not control the shape. |
| `Sketch.mirror()` | Not usable: the seed splines lose their fully-constrained state. |
| Symmetry per fit point | Works inside full builds (fully constrained, correct after rotate and move). An isolated check that started the mirror half 0.05 mm out of place failed; cause not found. |
| Sketch circular pattern of splines and arcs | Yes. All instances are created and fully constrained. |
| Partial pattern | `totalAngle` spans first to last instance: quantity 5 over 90° gives 22.5° steps. |
| Named rotation parameter (SKT-4) | Yes. The dimension's parameter can be renamed and can be driven by a user parameter. |
| Rotation dimension at 0° | Creating the angular dimension at 0° yields a 180° dimension. Creating it at a non-zero angle and then setting 0° works. |

API behavior worth knowing:

- A coincident constraint between two spline end points fails with
  `VCS_SKETCH_SOLVING_FAILED`. `SketchPoint.merge()` works.
- `sketchArcs.addByCenterStartSweep` and `addByCenterStartEnd` do not attach the arc to a
  sketch point passed as center. The center must be merged afterwards.
- A sketch left under-constrained with a pattern can hang Fusion for many minutes on a
  parameter edit.

## SPIKE-2 Performance

Full gears, m = 1, cheapest constraint scheme found (radius plus offset from the tooth axis
per fit point, mirror half dimensioned instead of symmetric). All were fully constrained and
within 0.0065 mm of the exact outline.

| z | Create | Rotate (one edit) | Move (x and y edit) |
|---|---|---|---|
| 25 | 0.65 s | 0.28 s | 1.0 s |
| 50 | 0.86 s | 0.63 s | 2.9 s |
| 100 | 1.5 s | 1.05 s | 9.1 s |
| 200 | not run | not run | not run (guard: z = 100 exceeded 5 s) |

Manual drag test on the open documents: "very slow to drag around, took several seconds to
respond". With only 8 teeth and the position dimensions removed, dragging was "pretty smooth".

The scheme as written in the spec (two offset dimensions per fit point, symmetry for the
mirror half) is slower still: 8.0 s per move at 16 of 24 teeth, against 0.46 s for the
cheapest scheme.

Baseline, plain unconstrained outline drawn into a sketch for every tooth: 0.43 s (z = 25),
0.70 s (50), 2.3 s (100), 6.8 s (200). Each gives one closed profile.

### Edit robustness (8 of 24 teeth, both schemes)

27 edits through the API. 8 failed in each scheme:

- Position x from 45 to 80 mm and from 10 to 31.5 mm: not applied, the gear stays in place.
  No exception is raised. Smaller steps worked. The same was seen by hand as "failed to solve".
- Rotation from 179° back to 10°: the outline is wrong by 0.8 to 1.2 mm and stays wrong for
  later edits. One scheme then reports "Failed to generate profile as, curves do not
  precisely overlap".
- All y edits and rotation steps from 10° up to 179° worked.

## SPIKE-3 Spline constraints

Fewest evenly spaced fit points for Fusion's spline to stay within tolerance:

| m | z | Tolerance | Flank | Root curve | Dimensions per half-tooth |
|---|---|---|---|---|---|
| 1 | 18 | 0.010 mm | 4 | 5 | 17 |
| 1 | 24 | 0.010 mm | 4 | 5 | 17 |
| 1 | 100 | 0.010 mm | 3 | 5 | 15 |
| 5 | 24 | 0.010 mm | 6 | 7 | 21 |
| 1 | 24 | 0.001 mm | 7 | 8 | 27 |
| 5 | 24 | 0.001 mm | 14 | 11 | 37 |

- The cheapest scheme dimensions both halves, so a tooth carries 35 to 43 dimensions.
- `Sketch.areDimensionsShown` hides them only outside sketch editing.
- Fusion's fitted splines are degree 5. A pure-Python cubic spline through the same 6 points
  differs by 0.0005 mm at best, so `gearcore` can estimate fit-point counts but cannot
  reproduce Fusion's curve exactly (affects ACC-2).

## SPIKE-4 Profile closure

Pass at z = 24 and z = 100: one closed profile with 7 curves per tooth, extrude succeeds,
area within 4e-5 of the exact value. Pattern instances join without extra constraints.

This holds only when the selected circle is construction geometry. Left as drawn it cuts
every tooth: 49 profiles at z = 24, 201 at z = 100. SKT-2 and SKT-9 conflict.

## SPIKE-5 Custom feature (added)

Throwaway add-in `spikes/GearFeatureSpike`. The gear is a solid body with a thickness, made
by a custom feature (preview API) that depends on the selected circle or arc.

Design that works:

- The body lives in a base feature. It is made by an extrude run inside the base feature
  while it is in edit mode, which adds nothing to the timeline.
- The custom feature groups the base feature alone (New Body) or the base feature plus one
  combine feature (Join).
- On recompute the add-in builds a new body the same way, swaps it in with
  `BaseFeature.updateBody` and deletes the helper body. An extrude inside the base feature
  is allowed during a recompute.

| Check | Result |
|---|---|
| Create as New Body, z = 24 | Pass. Volume within 2e-5 of the exact gear. Timeline shows only the custom feature. |
| Create as Join to a plate | Pass. Body count unchanged, the group holds the base feature and the combine. |
| Recompute when the circle moves or changes size | Pass, also by hand (drag the circle, finish the sketch). |
| Recompute when thickness, module or rotation change | Pass. |
| Arc as input | Pass as a dependency: the gear follows a radius change. Arc-mode geometry was not built. |
| Joined gear follows its circle | Recompute ran and reported success. The position check failed for a test reason (the tool body is consumed by the join), so the position is not verified. |

Two ways to make the outline that is extruded:

| Outline from | Create z = 24 | Recompute z = 24 | Create z = 200 | Recompute z = 200 |
|---|---|---|---|---|
| Planar face built in memory from NURBS curves and arcs | 0.22 s | 0.19 s | 1.7 s | 1.6 s |
| Temporary sketch inside the base feature | 0.48 s | 0.43 s | 8.9 s | 9.2 s |

The in-memory face is faster and its curves are fully under our control, which removes the
dependence on Fusion's fitted splines (ACC-2).

Requirements found the hard way:

- Features must be created after the add-in's `run()` has returned. Created inside `run()`,
  they show "The extension that owns this feature is not running" and never recompute.
- The spike adds dependencies after the feature exists, with the timeline rolled back to
  before it, following the Laser Finger Joint add-in. Whether `CustomFeatureInput.addDependency`
  also works was not isolated.
- Fusion calls the compute handler twice during creation; the spike ignores those calls.
- `ExtrudeFeatureInput.setDistanceExtent` does not exist in this API version; use
  `setOneSideExtent`.

Not tested: the edit command (the spike has none), undo and redo, save and reopen, a design
opened without the add-in, a selected curve on a non-XY plane or inside a component.

## SPIKE-6 One custom feature following another (added)

Question: for gears that mesh, can gear B depend on gear A so that B recomputes whenever A
changes, and does that carry on along a chain A → B → C? Code in `spikes/MeshSpike`, four runs
on Fusion 2705.1.30.

The spike leaves out the gear math. Each feature makes a small cylinder on its circle at an
angle. A's angle is its rotation parameter; B's angle follows from A's angle and the direction
A → B, as for meshing; C's from B's. Each feature finds its mate through an entity token stored
at creation and computes the angle recursively along the chain, so a feature is correct
whenever it recomputes. The tests check whether it does, after four edits: A's rotation, A's
circle moved, B's circle moved, and A's rotation changed inside a command.

Result of the final run, each chain in its own document:

| B depends on (besides its own circle) | Accepted | A's rotation changes | A's circle moves | B's circle moves |
|---|---|---|---|---|
| A's custom feature | Yes | B and C follow | B and C follow | C follows |
| A's base feature | Yes | B and C follow | B and C follow | C follows |
| A's custom feature, A joined to a plate | Yes | B and C follow | B and C follow | C follows |
| A's circle only (control) | Yes | B and C stay | B and C follow | C follows |
| A's rotation parameter | **No**, "Invalid argument entity" | (as the control) | | |
| A's body | Yes, but B gets no body and nothing in the document recomputes any more | | | |
| The plate A is joined to | Yes, same failure as A's body | | | |

Every follow-up recompute happened inside the same edit. Compute All was not needed.

Findings:

- **Depend on the other custom feature.** Fusion's documentation lists bodies, sketch
  entities, construction geometry and parameters as dependencies, not features, but a custom
  feature (or its base feature) is accepted and works: B recomputes whenever A does, for any
  reason, and C follows B in the same recompute.
- **Parameters are rejected** as dependencies, both the custom parameter and the same model
  parameter looked up by name, although the documentation lists them.
- **A dependency on another feature's body breaks things.** B ends up without a body, and
  from then on no feature in the document recomputes after an edit, including unrelated ones.
- **One broken custom feature can stop all recomputes in its document.** In runs 1 to 3 all
  chains shared one document. The broken body chain made every other chain look broken too:
  no recompute after any edit, and Compute All did not change any body.
- **Do not write to the feature during its own compute.** A chain that stored a value with
  `customNamedValues.addOrSetValue` inside the compute handler broke: after an edit, the
  bodies of A and B read with their center of mass at the origin. The same chain without the
  write worked. A value
  stored at creation, outside the compute, is fine and readable from other features.
- **Entity tokens find the mate reliably.** `design.findEntityByToken` on the token of the
  custom feature, stored in a named value at creation, worked in every compute.
- **Deleting A** through the API (`deleteMe`) leaves B and C in health state Unknown, with
  no recompute. **Deleting A by hand in the timeline deletes B and C too**; Undo restores all
  three.

Checked by hand, with the spike's manual mode (one chain, no automatic edits):

| Check | Result |
|---|---|
| Change A's Rotation in Change Parameters | B and C follow |
| Undo and redo that change | B and C follow both ways |
| Save, close, reopen, change A's Rotation again | B and C follow |
| Delete A in the timeline | B and C are deleted with it; Undo restores all three |

Conclusion: "Mesh with" is feasible. The new gear depends on the mate's custom feature, finds
it by token, and computes its rotation recursively from the chain's parameters and circles.

Not tested: the mate in another component, and a design opened without the add-in.
