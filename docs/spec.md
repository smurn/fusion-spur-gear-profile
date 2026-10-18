# Spur Gear: Specification

Status: **Draft 0.9** (2026-10-13). Version 0.8 describes the add-in as implemented in
version 0.9.0. Draft 0.9 adds meshing with another gear ("Mesh with"), which is not
implemented yet: IN-17, DER-10, DER-11, the mesh part of GEO-9, FEA-12 to FEA-15, UI-9,
VAL-15 to VAL-19, D-22 to D-26, CHK-7, CHK-8, ARC-8 and the mesh check in TST-2. Requirements have stable
IDs (`GEO-3`, `FEA-5`, …). Tests and code reference these IDs. Decisions are recorded in §11.

History: draft 0.3 replaced the sketch-constraint design of draft 0.2 with a custom feature
that produces a solid body; the reasons are in [spikes.md](spikes.md). Draft 0.4 dropped the
target body selection for Join. Draft 0.6 limited the print offset to the toothed profile.
Draft 0.9 added "Mesh with", after SPIKE-6, across components after SPIKE-7.
Retired IDs: SKT-1 to SKT-12, IN-16, VAL-9, D-1, D-4, D-6, D-17, SPIKE-1 to SPIKE-4. VAL-13
was never used.

## 1. Purpose and scope

A Fusion add-in command that turns a selected sketch circle or arc into a solid involute spur
gear. The gear is a single feature in the timeline. It stays attached to the selected curve:
when the curve moves or changes size, or a gear parameter is edited, the gear is recomputed.

**In scope (v1)**
- External involute spur gears, full (circle) or partial (arc), as a solid body with a
  thickness.
- Generation with an ISO 53 style basic rack, including the root fillet trochoid and undercut.
- Profile shift, backlash allowance and a 3D-print offset.
- An optional bore.
- Creating the gear as a new body or joining it to an existing body.
- Live preview while the dialog is open.
- Editing all inputs after creation, through the feature's edit dialog or the parameters
  dialog.
- Turning a gear so that it meshes with another gear, and checking their center distance.

**Out of scope (v1)**
- Helical, internal and bevel gears, racks, worms.
- Tip relief and other flank modifications. The design must leave room to add them later.
- Diametral pitch input. Placing gears at the right center distance: the user draws the
  curves; the add-in only reports the ideal distance (DER-10).
- Gears fixed to each other on one shaft (compound gears): their relative rotation is set
  with the start rotation.
- The gear outline as sketch geometry.
- Cutting the gear shape out of a body.
- Keyways, spokes, hubs and chamfers. The user adds them with ordinary features.

## 2. Symbols

| Symbol | Meaning |
|---|---|
| m | module |
| z | number of teeth of the full gear |
| α | pressure angle |
| h_a\* | addendum coefficient (gear tip above reference circle, in units of m) |
| h_f\* | dedendum coefficient (gear root below reference circle, in units of m) |
| ρ_f\* | root fillet radius coefficient of the basic rack, in units of m |
| x | profile shift coefficient |
| j_bn | normal backlash, per mesh |
| δ | print offset |
| p | start rotation as a fraction of one tooth pitch (0 ≤ p < 1) |
| b | thickness (face width) |
| d_B | bore diameter |
| τ | angular pitch, 2π / z |
| a, a_w | actual and ideal center distance to the mate (DER-10) |
| z₁, z₂, x₁, x₂ | tooth counts and profile shifts of this gear and its mate |
| inv(φ) | involute function, tan φ − φ |

## 3. User workflow

1. The user clicks **Spur Gear** in SOLID › CREATE.
2. The user selects one circle or arc in an existing sketch. Optionally, the user also
   selects the curve of an existing gear that this one should mesh with.
3. The dialog shows the inputs (§4) with defaults and the derived values (§5). A live preview
   of the body updates on every change.
4. On **OK** the gear feature is added to the timeline. **Cancel** leaves the design unchanged.
5. Later, the user can edit the feature (same dialog), change its parameters in the
   parameters dialog, or edit the sketch. The gear follows.

## 4. Inputs

| ID | Input | Default | Valid range / notes |
|---|---|---|---|
| IN-1 | Curve | none | Exactly one sketch circle or arc |
| IN-2 | Module m | 1 mm | > 0 |
| IN-3 | Pressure angle α | 20° | 10°–35° |
| IN-4 | Addendum coefficient h_a\* | 1.00 | > 0 |
| IN-5 | Dedendum coefficient h_f\* | 1.25 | > 0; see VAL-4 |
| IN-6 | Root fillet radius coefficient ρ_f\* | 0.38 | ≥ 0; upper limit see VAL-5 |
| IN-7 | Profile shift coefficient x | 0 | any; limited by VAL-3 and VAL-14 |
| IN-8 | Backlash j_bn | 0 mm | ≥ 0 |
| IN-9 | Print offset δ | 0 mm | any; positive adds material; moves the toothed profile only (GEO-7); limited by VAL-14 |
| IN-10 | Start rotation | 0 % | 0–100 % of one tooth pitch; 100 % wraps to 0 % |
| IN-11 | Max profile deviation | 0.010 mm | 0.0001–0.1 mm |
| IN-12 | Thickness b | 5 mm | > 0 |
| IN-13 | Flip side | off | Off: the gear extends from the sketch plane along its normal. On: the opposite side |
| IN-14 | Bore diameter d_B | 0 mm | ≥ 0; 0 means no bore; upper limit see VAL-11 |
| IN-15 | Operation | New Body | New Body or Join. Join needs no target selection (FEA-6) |
| IN-17 | Mesh with | none | Optional. Another Spur Gear, the mate, picked as its feature in the timeline or as its curve (IN-1). When set, the rotation comes from DER-11 and IN-10 is not used (FEA-12) |

Defaults for IN-3 to IN-6 are the ISO 53 type A basic rack. Length inputs use the document's
units. Start rotation is entered as a number from 0 to 100.

## 5. Derived values

The dialog shows the tooth count, the selected, reference, base, tip and root diameters, the
tooth thickness and the tip thickness. Undercut is reported through VAL-8.

- **DER-1** Tooth count: z = round(d_sel / m), where d_sel is the diameter of the selected curve.
  Exact halves round up.
- **DER-2** Reference (pitch) diameter: d = m·z. This generally differs from d_sel; the dialog
  shows both.
- **DER-3** Base diameter: d_b = d·cos α.
- **DER-4** Tip diameter: d_a = d + 2m(h_a\* + x) + 2δ.
- **DER-5** Root diameter: d_f = d − 2m(h_f\* − x) + 2δ.
- **DER-6** Tooth thickness at the reference circle (before print offset):
  s = m(π/2 + 2x·tan α) − j_bn / (2 cos α).
- **DER-7** Undercut indicator: undercut occurs when z < z_min, where
  z_min = 2(h_f\* − ρ_f\*(1 − sin α) − x) / sin²α. (For ISO 53 type A, x = 0: z_min ≈ 17.1.)
  The indicator does not take the print offset into account.
- **DER-8** Tip thickness s_a, the arc thickness on the tip circle. Without print offset:
  s_a = d_a·(s/d + inv α − inv α_a), with cos α_a = d_b / d_a. With a negative offset the
  flanks are closer together by 2δ / d_b in angle: s_a = d_a·(s/d + inv α − inv α_a + 2δ/d_b),
  with d_a and α_a of the offset tip circle. With a positive offset the tip arc keeps its
  angle and only moves out (GEO-7), so s_a is the value without offset times d_a / (d_a − 2δ).
  s_a is undefined if the tip circle lies inside the base circle (VAL-3).
- **DER-9** Number of teeth that are generated (see GEO-9). For a circle this is z. The
  dialog shows it for arcs.
- **DER-10** Center distance, with a mate (IN-17). The actual distance a is the distance
  between the two curves' centers in assembly coordinates, measured in the mate's plane. The ideal distance a_w is
  the one at which the two gears mesh without backlash:
  inv α_w = inv α + 2·tan α·(x₁ + x₂) / (z₁ + z₂), a_w = m(z₁ + z₂)/2 · cos α / cos α_w.
  Backlash and print offset are not included: with a = a_w the gears have the backlash j_bn
  of IN-8. The dialog shows a and a_w.
- **DER-11** Rotation, with a mate. Angles are measured in the mate's plane, counterclockwise
  about its normal. β is the direction from the mate's center to this gear's center. θ_M is
  the axis angle of the mate's tooth 0 (GEO-9; if the mate itself has a mate, from this
  rule). With u = frac((β − θ_M) / τ_M), this gear's tooth 0 axis is
  θ₀ = β + π − (½ − u)·τ. So a tooth of one gear on the line of centers faces a gap of the
  other. The result holds for any profile shift, backlash and print offset, because each
  tooth is symmetric (GEO-8). DER-11 works in assembly coordinates, so the two gears may be
  in different components (FEA-15). If this gear's plane normal points the other way, θ₀ is
  converted into its own plane.

## 6. Geometry

GEO-1 to GEO-11 describe the gear's outline in the plane of the selected curve. GEO-12 makes
it a solid.

- **GEO-1** The tooth outline is the envelope generated by rolling a basic rack along the
  reference circle (rack datum line offset by x·m from the reference circle). The rack has
  pressure angle α, depth h_f\*·m below the datum line on the cutting side, and a tip fillet of
  radius ρ_f\*·m.
- **GEO-2** The flank is the involute of the base circle d_b. It extends from the tip circle
  down to where it meets the root curve.
- **GEO-3** The root curve is the trochoid generated by the rack's tip fillet, joined by a
  root-circle arc where the rack tip has a flat land.
- **GEO-4** Undercut is generated, not avoided. When the trochoid crosses the involute, the
  outline follows the trochoid below the crossing point. The crossing is found numerically.
  If the undercut is too slight to resolve, the two curves are joined where the rack fillet
  ends, as without undercut.
- **GEO-5** The tooth tip is an arc of the tip circle d_a.
- **GEO-6** Backlash j_bn: each gear takes half of the mesh backlash as a reduction of tooth
  thickness, implemented by thickening the generating rack's teeth. The root diameter is
  unchanged.
- **GEO-7** Print offset δ: the toothed profile (tip, flanks, root curves and root circle) is
  offset by δ along its normal; positive δ adds material. Gaps at convex corners are filled
  with arcs of radius |δ|; overlaps are trimmed. The flank stays an exact involute (of the
  same base circle, turned by δ / r_b) and the root curve the exact parallel of the trochoid.
  The offset does not apply to the bore, to the radial edges of GEO-10, or to the two flat
  faces of the gear. In arc mode the radial edges stay on the ends of the arc and run from
  the offset root circle. Convex corners are the tip corners and, on an undercut tooth, the
  corner between flank and root curve.
- **GEO-8** Each tooth is symmetric about its own tooth axis (a ray from the gear center).
- **GEO-9** Tooth placement: tooth k's axis is at angle θ₀ + k·τ, with θ₀ = θ_ref + p·τ, or
  with θ₀ from DER-11 if the gear has a mate.
  - Circle: θ_ref is the X axis of the selected curve's sketch; all z teeth are generated.
  - Arc: θ_ref is the direction from the center to the arc's midpoint. Only teeth whose full
    pitch unit (axis ± τ/2) lies within the arc are generated. With p = 0 and no mate the
    sector is symmetric about the arc midpoint.
- **GEO-10** Arc mode: the root circle continues from the outermost generated teeth to the
  arc's end angles. From there the outline is closed by two straight radial edges. They run
  to the bore circle, which closes the outline with an arc, or to the center if there is no
  bore.
- **GEO-11** Bore: a circular hole of diameter d_B, concentric with the selected curve,
  through the full thickness. In arc mode only the part of the bore circle inside the sector
  is used (GEO-10).
- **GEO-12** The solid is the outline extruded by the thickness b, perpendicular to the plane
  of the selected curve, starting at that plane. IN-13 selects the side.

## 7. Feature behavior

- **FEA-1** The gear is one custom feature. The timeline shows a single node for it, with the
  add-in's icon and a name of the form "Spur Gear1".
- **FEA-2** The feature depends on the selected curve. It recomputes when the curve's center,
  radius, plane or (for an arc) end angles change, and when any of its parameters change.
- **FEA-3** The selected curve and its sketch are not modified.
- **FEA-4** After every recompute the gear is centered on the selected curve's center, lies on
  its plane, and has the tooth count of DER-1 for the curve's current diameter.
- **FEA-5** IN-2 to IN-12 and IN-14 are feature parameters. They appear in the parameters
  dialog under the feature and accept expressions and user parameters.
- **FEA-6** New Body creates one new solid body. Join merges the gear into every visible solid
  body of the same component that it touches or overlaps, as Extrude does, and creates no
  additional body. The user does not select a target. The bodies are chosen when the gear is
  created or switched to Join; a later recompute keeps them, also if the gear no longer
  touches them.
- **FEA-7** Editing the feature opens the dialog of §3 with the feature's current values,
  including the curve selection, flip side and operation. OK applies the changes to the same
  feature. The operation can be switched between New Body and Join. While the dialog is open
  the gear stays visible and the timeline is not rolled back, so a curve created after the
  gear can be clicked. Such a curve cannot be the gear's curve; this case has not been tested.
- **FEA-8** If a recompute cannot produce a valid gear (a VAL error, or the curve no longer
  exists), the feature is marked as failed in the timeline and keeps its previous body.
- **FEA-9** Recomputing requires the add-in to be running. The design must still open without
  it and show the last computed body.
- **FEA-10** The curve may lie in any sketch of the design: on any plane or planar face, and in
  any component.
- **FEA-11** Fusion offers Edit Feature for custom features only in Hybrid and Assembly
  designs, not in Part designs. This is a limitation of Fusion, also seen with other custom
  feature add-ins. In a Part design the gear is still created, recomputed and editable
  through the parameters dialog.
- **FEA-12** With a mate (IN-17), the feature also depends on the mate's feature, through
  the occurrence of the mate's component that was picked if the mate is in another component
  (SPIKE-7). It recomputes whenever the mate does: when the mate's curve moves or changes, or any of the
  mate's parameters change. This carries on along a chain of gears. While a mate is set, the
  start rotation (IN-10) is not used.
- **FEA-13** Deleting a gear also deletes every gear that meshes with it, directly or through
  a chain. This is Fusion's behavior for a feature others depend on; Undo restores them. To
  keep a gear, clear its "Mesh with" first.
- **FEA-14** Clearing "Mesh with" in the edit dialog keeps the gear where it is: the start
  rotation is set to the rotation the mate gave it.
- **FEA-15** The gear and its mate may be in different components. Their positions are taken
  from the occurrences of their components: for the mate, the occurrence it was picked in;
  for this gear, the one its curve was picked in. The positions used are those at this gear's
  place in the timeline. Moving an occurrence later, capturing a position later, or driving a
  joint does not change the gear and does not make it recompute. So the components must be in
  place when the meshing gears are created, as in a top-down design. VAL-18 reports a center
  distance that is off at that point.

## 8. Command and user interface

- **UI-1** The command button is in the SOLID › CREATE panel.
- **UI-2** The curve selection accepts only sketch circles and sketch arcs.
- **UI-3** Live preview: on every input change the preview shows the resulting body. It must
  be geometrically identical to the committed result.
- **UI-4** Derived values (§5) and validation messages (§9) update together with the preview.
- **UI-5** OK is disabled while any VAL error is present. One case is only caught on OK, with
  a message: see VAL-12.
- **UI-6** Creating a gear is a single undo step. So is each edit.
- **UI-7** The create dialog starts with the inputs of the last gear that was created: all
  numeric inputs (as entered, so references to user parameters are kept), flip side and
  operation. The curve is not remembered. This lasts until the add-in is stopped; it is not
  saved. If a remembered expression is not valid in the current design, its value is used.
- **UI-8** Pressure angle, addendum, dedendum and root fillet coefficients and the max profile
  deviation are in a group named Advanced. It is collapsed unless one of them differs from
  its default.
- **UI-9** "Mesh with" is an optional selection right after the curve. It accepts a feature,
  picked in the timeline, and sketch circles and arcs; VAL-15 checks that it is a Spur Gear
  or a Spur Gear's curve. While it is set, the
  start rotation input is disabled, and the info box names the mate and shows the actual and
  ideal center distance (DER-10). It is not remembered for the next gear (UI-7).

## 9. Validation

| ID | Condition | Severity |
|---|---|---|
| VAL-1 | No curve, or not a circle/arc | error |
| VAL-2 | z < 3 | error |
| VAL-3 | Tip thickness s_a ≤ 0 (pointed tooth) | error |
| VAL-4 | Root diameter d_f ≤ 0 | error |
| VAL-5 | Rack fillet radius does not fit the rack tip land: ρ_f\* > (π/4 + j_bn/(4m·cos α) − h_f\*·tan α)·cos α / (1 − sin α) (≈ 0.47 for type A without backlash) | error |
| VAL-6 | Arc mode generates no complete tooth | error |
| VAL-7 | s_a < 0.2·m (rule of thumb) | warning |
| VAL-8 | Undercut present (DER-7) | info |
| VAL-10 | Thickness b ≤ 0 | error |
| VAL-11 | Bore does not fit inside the root circle: d_B ≥ d_f | error |
| VAL-12 | Operation is Join and the gear touches no body | error |
| VAL-14 | The outline cannot be built: the print offset removes the root circle or folds the root curve back on itself; no flank remains between root curve and tip circle; or x = h_f\* − ρ_f\* exactly, where the root curve has a cusp | error |

| VAL-15 | "Mesh with" is not a Spur Gear, or the curve of one, earlier in the timeline; or it is this gear or its own curve; or it was picked in the timeline and its component has more than one occurrence, so it is not clear which one is meant (pick its curve instead). If several gears use the picked curve, the latest one before this gear is the mate | error |
| VAL-16 | Module or pressure angle differs from the mate's | error |
| VAL-17 | The planes of the two curves are not parallel, or the centers coincide in the mate's plane | error |
| VAL-18 | The center distance differs from the ideal one: \|a − a_w\| > 0.01·m | warning |
| VAL-19 | With a mate: this gear's curve was picked in a way that does not tell which occurrence of its component is meant (inside an activated component that has more than one occurrence). Pick it in the assembly instead | error |

A value outside the range given in §4 is an error and is reported with the ID of that input.

VAL-12 is checked in two steps. The dialog tests whether a cylinder of the tip diameter would
touch a body, which needs no change to the design, and disables OK if not. A gear that misses
every body only between its teeth passes that test and is rejected on OK.

## 10. Accuracy

- **ACC-1** Every curve that approximates an exact curve (involute, trochoid, including any
  offset) deviates from it by no more than the IN-11 tolerance, measured as normal distance.
- **ACC-2** `gearcore` chooses the number of interpolation points per curve to satisfy ACC-1
  and verifies it by dense sampling. This needs no Fusion.
- **ACC-3** Consecutive curves of the outline share their end points to within floating-point
  rounding, so the outline is closed. Where flank and root curve meet, the flank is ended on
  the first point of the root curve.
- **ACC-4** Tip, root and bore arcs, the corner arcs of GEO-7 and the radial edges are exact
  arcs and lines, not approximations.

## 11. Decisions

Resolved on 2026-10-10:

- **D-2** Print offset sign: positive adds material (IN-9, GEO-7).
- **D-3** Backlash: normal backlash per mesh, half per gear, root diameter unchanged (GEO-6).
- **D-5** Tooth count rounding: exact halves round up (DER-1).
- **D-7** Tip-thickness warning threshold: 0.2·m (VAL-7).

Resolved on 2026-10-11, after the spikes:

- **D-8** The gear is a custom feature producing a solid body with a thickness, not sketch
  geometry. The sketch-constraint design was too slow to drag and failed on large edits.
- **D-9** Fusion marks the custom feature API as preview. This is accepted.
- **D-10** Arc mode is closed by straight radial edges (GEO-10). Replaces D-1.
- **D-11** An optional bore is part of the feature (IN-14, GEO-11).
- **D-12** Operations are New Body and Join (IN-15).
- **D-13** The add-in is self-contained and does not share a framework with other add-ins.
- **D-14** No tooth-count limit or warning. A recompute took 1.6 s at z = 200 in the spike.
- **D-15** Default thickness is 5 mm (IN-12).
- **D-16** The side is chosen by a flip option; there is no symmetric option (IN-13).
- **D-18** The command is named "Spur Gear".
- **D-19** Join finds its bodies itself, like Fusion's own features; there is no target
  selection (FEA-6).
- **D-20** The print offset applies only to the toothed profile, not to the bore or to the
  radial edges of a sector gear (GEO-7, VAL-11). Replaces D-17.
- **D-21** The dialog remembers the last used settings in memory only, and keeps the rarely
  changed inputs in a collapsed group (UI-7, UI-8).

Resolved on 2026-10-13, after SPIKE-6:

- **D-22** Gears are aligned by picking the gear to mesh with (IN-17), not a reference line.
  A line only aligns pairs; a mate also works along a chain of gears. The mate can be picked
  in the timeline or by its curve; the curve needs its sketch to be visible.
- **D-23** A gear with a mate depends on the mate's custom feature. Depending on the mate's
  parameters is rejected by Fusion, and depending on its body breaks recomputing (SPIKE-6).
- **D-24** Deleting a gear deletes the gears meshing with it (FEA-13). Accepted.
- **D-25** A wrong center distance is a warning, not an error (VAL-18). The add-in does not
  move curves.

Resolved on 2026-10-17, after SPIKE-7:

- **D-26** Meshing gears may be in different components, as an assembly with joints needs.
  Positions come from the occurrences and are those at the gear's place in the timeline
  (FEA-15). This suits a top-down design, where the components are in place before the gears
  are made. Replaces the same-component rule of the first draft of VAL-15.

## 12. Feasibility

The spikes are done; results are in [spikes.md](spikes.md). The custom feature design was
tested in SPIKE-5. The points it left open were checked by hand on the first working version
of the add-in (2026-10-11):

- **CHK-1** The edit dialog (FEA-7): works, including switching between New Body and Join, in
  Hybrid designs only (FEA-11). The timeline is rolled back only while a change is applied,
  not for as long as the dialog is open; rolling it back for the whole edit hid the gear and
  broke Undo.
- **CHK-2** Undo and redo of create and edit (UI-6): work, one step each.
- **CHK-3** Save, close and reopen (FEA-9): works. Without the add-in the gear keeps its last
  body, the feature shows a different icon and a changed curve gives a warning. After the
  add-in starts again, a recompute picks up the changes.
- **CHK-4** A curve on a tilted offset plane, on a planar face, and inside a component
  (FEA-10): works.
- **CHK-5** Position of a joined gear after its curve moves (FEA-4, FEA-6): works.
- **CHK-6** Preview inside the dialog (UI-3): works for create and edit.

Open, for "Mesh with" (draft 0.9):

- **CHK-7** Whether a selection input with Fusion's "Features" filter accepts a custom feature
  clicked in the timeline, and which object it returns (the custom feature, or one of the
  features it contains). To be checked first when implementing IN-17. If it does not work,
  IN-17 accepts curves only.
- **CHK-8** Bottom-up assembly: whether a gear created after the joints that place the
  components meshes at the joined positions (FEA-15). Not tested in SPIKE-7.

## 13. Architecture and testing

- **ARC-1** `gearcore`: pure Python with no Fusion imports. It computes the closed outline as
  a sequence of exact arcs, straight lines and interpolated curves (GEO-\*, ACC-\*), the
  derived values (DER-\*) and validation (VAL-\*). The interpolated curves are C2 cubic
  splines, handed over as degree-3 NURBS curves. VAL-1 and VAL-12 need the design and are
  checked in the Fusion layer.
- **ARC-2** `fusion_layer`: the command, dialog, preview, custom feature and body
  construction (FEA-\*, UI-\*). It contains no gear math.
- **ARC-3** The body is built without timeline features: the outline becomes a planar face in
  memory, which is extruded inside a base feature. The custom feature groups that base
  feature and, for Join, one combine feature. A recompute replaces the body in the base
  feature.
- **ARC-4** Custom features are created only after the add-in's `run()` has returned.
- **ARC-5** The add-in has no dependencies outside Fusion's bundled Python (D-13).
- **ARC-6** An edit rolls the timeline back to before the feature only while the change is
  applied, inside the command's own transaction (UI-6).
- **ARC-7** The numeric inputs are custom feature parameters (FEA-5). Flip side and operation
  are stored with the feature as named values.
- **ARC-8** The mate is stored as a dependency on its custom feature and as its entity token
  in a named value, which is how the compute finds it. Across components the dependency is a
  proxy through the mate's occurrence; Fusion rejects the native feature there (SPIKE-7). The
  compute takes the occurrences from the proxies the dependencies hand back, and transforms
  each gear's frame up its occurrence path into assembly coordinates. The compute works out DER-11 along the
  whole chain each time and writes nothing to any feature: named values written during a
  compute broke the feature in SPIKE-6. DER-10 and DER-11 are `gearcore` functions.
- **TST-1** `gearcore` has pytest tests runnable outside Fusion. Each test names the requirement
  IDs it covers.
- **TST-2** Reference checks include: DER formulas against hand-calculated values;
  undercut threshold z ≈ 17 for type A; tooth symmetry; involute points lying on the base
  circle involute; ACC-1 by sampling; s at the reference circle matching DER-6; the outline
  being closed (ACC-3); the enclosed area in arc mode and with a bore; the tooth outline
  against an independent model of the generating rack, including undercut; the offset outline
  lying at distance |δ| from the outline without offset; two gears placed by DER-11 at the
  ideal center distance touching when there is no backlash (overlap no deeper than the IN-11
  tolerance), and with a clearance of j_bn/2 on each flank when there is.
- **TST-3** The Fusion layer is verified with a manual checklist in `docs/manual-tests.md`
  that covers the FEA and UI requirements and the CHK items.

## 14. References

- ISO 53:1998, cylindrical gears: standard basic rack tooth profile (types A–D).
- ISO 21771-1:2024, cylindrical involute gears: geometry.
- ISO 1328-1:2013, cylindrical gears: ISO system of flank tolerance classification.
- ISO/TR 10064-2:1996, inspection practice: backlash guidance.
