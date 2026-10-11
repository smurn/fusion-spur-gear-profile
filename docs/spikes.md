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

The spec needs a different construction method before implementation starts. The gear
math (`gearcore`, ARC-1) is not affected.

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

## Open

- Replacement construction method. Candidate: a custom feature (preview API) that takes the
  circle or arc as input and recomputes the geometry itself. Needs its own spike.
