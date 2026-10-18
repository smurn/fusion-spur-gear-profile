# Spur Gear: Specification

Status: **Version 0.9** (2026-10-18). It describes the add-in as implemented in version
0.10.0. New since version 0.8: gear trains oriented from a layout sketch (§7), gears created
in the active component (FEA-14), and start, direction and extent options like Extrude's
(IN-18 to IN-29). Checked by hand so far: gears from a layout sketch in several components,
moving circles in the layout sketch, the active component, a joined gear starting on a face
(CHK-9), and direction and extent (manual checklist steps 75 to 83). The rest of the manual
checklist for these features is still to be done. Not implemented yet: Symmetric's half
and whole length (IN-27) and the To Object offsets (IN-28, IN-29), with D-34. Requirements have stable IDs
(`GEO-3`, `FEA-5`, …). Tests and code reference these IDs. Decisions are recorded in §12.

History: draft 0.3 replaced the sketch-constraint design of draft 0.2 with a custom feature
that produces a solid body; the reasons are in [spikes.md](spikes.md). Draft 0.4 dropped the
target body selection for Join. Draft 0.6 limited the print offset to the toothed profile.
Draft 0.9 first linked each gear to the gear it meshes with ("Mesh with", SPIKE-6 and
SPIKE-7). That tied the gears' order in the timeline to the chain, so it was replaced by a
layout sketch (SPIKE-8). The "Mesh with" version is tagged `mesh-with-live-link` in git.
Version 0.9 adds the start, direction and extent options and creating gears in the active
component.
Retired IDs: SKT-1 to SKT-12, IN-16, IN-17, VAL-9, VAL-15 to VAL-19, DER-10, DER-11, FEA-15,
D-1, D-4, D-6, D-17, D-22 to D-26, CHK-7, CHK-8, SPIKE-1 to SPIKE-4. VAL-13 was never used.
FEA-12 to FEA-14, UI-9 and ARC-8 had other meanings in the "Mesh with" draft, which was never
released.

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
- Gear trains: gears whose circles touch in a layout sketch are turned so that they mesh,
  without any link between the gears themselves (§7).

**Out of scope (v1)**
- Helical, internal and bevel gears, racks, worms.
- Tip relief and other flank modifications. The design must leave room to add them later.
- Diametral pitch input. Checking or calculating center distances: the user draws the circles
  touching (D-31).
- The relative rotation of gears fixed to each other on one shaft (compound gears). Each is in
  its own train (TRN-3).
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
| θ₀ | angle of the axis of tooth 0 (GEO-9) |
| inv(φ) | involute function, tan φ − φ |

## 3. User workflow

1. The user clicks **Spur Gear** in SOLID › CREATE.
2. The user selects one circle or arc in an existing sketch. For a gear train, that is a
   circle of the layout sketch, or a linked projection of one in the gear's own component
   (§7).
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
| IN-10 | Start rotation | 0 % | 0–100 % of one tooth pitch; 100 % wraps to 0 %. Used only by a gear whose orientation does not come from its layout sketch (TRN-10) |
| IN-11 | Max profile deviation | 0.010 mm | 0.0001–0.1 mm |
| IN-12 | Thickness | 5 mm | > 0. The distance of side 1 (One Side, Two Sides), or the whole face width (Symmetric); see GEO-12 |
| IN-13 | Flip side | off | Off: side 1 extends from the start plane along the sketch normal. On: the opposite way. Used with One Side and Two Sides when the extent is a distance; side 2 always goes the other way |
| IN-14 | Bore diameter d_B | 0 mm | ≥ 0; 0 means no bore; upper limit see VAL-11 |
| IN-15 | Operation | New Body | New Body or Join. Join needs no target selection (FEA-6) |
| IN-18 | Start | Profile Plane | Profile Plane, Offset or Object, as in Extrude (GEO-12) |
| IN-19 | Start offset | 0 mm | any; used with Offset and Object |
| IN-20 | Start object | none | With Object: a planar face or construction plane parallel to the sketch plane, or a point: a vertex, sketch point or construction point (VAL-25, VAL-26) |
| IN-21 | Direction | One Side | One Side, Two Sides or Symmetric, as in Extrude (GEO-12) |
| IN-22 | Extent Type | Distance | Distance or To Object, for side 1. Symmetric is always a distance |
| IN-23 | Extent object | none | With To Object: as IN-20 |
| IN-24 | Thickness, side 2 | 5 mm | > 0; with Two Sides and a distance for side 2 |
| IN-25 | Extent Type, side 2 | Distance | Distance or To Object, with Two Sides |
| IN-26 | Extent object, side 2 | none | With Two Sides and To Object for side 2: as IN-20 |
| IN-27 | Measurement | Whole Length | With Symmetric: Whole Length (the thickness is the face width) or Half Length (the thickness goes each way from the start) |
| IN-28 | Extent offset | 0 mm | any; with To Object for side 1. Positive moves the end past the object, away from the start |
| IN-29 | Extent offset, side 2 | 0 mm | any; as IN-28, for side 2 |

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
  with θ₀ from TRN-10 when the gear's orientation comes from its layout sketch.
  - Circle: θ_ref is the X axis of the selected curve's sketch; all z teeth are generated.
  - Arc: θ_ref is the direction from the center to the arc's midpoint. Only teeth whose full
    pitch unit (axis ± τ/2) lies within the arc are generated. With p = 0 and no orientation
    from the layout sketch the sector is symmetric about the arc midpoint.
- **GEO-10** Arc mode: the root circle continues from the outermost generated teeth to the
  arc's end angles. From there the outline is closed by two straight radial edges. They run
  to the bore circle, which closes the outline with an arc, or to the center if there is no
  bore.
- **GEO-11** Bore: a circular hole of diameter d_B, concentric with the selected curve,
  through the full thickness. In arc mode only the part of the bore circle inside the sector
  is used (GEO-10).
- **GEO-12** The solid is the outline extruded perpendicular to the plane of the selected
  curve, between two planes parallel to it. Heights are measured along the sketch normal.
  The start plane (IN-18) is at height s:
  - Profile Plane: 0, so the gear starts on the curve's plane.
  - Offset: the start offset (IN-19), positive along the sketch normal, whatever IN-13 says.
  - Object: the height of the object's plane (a face or construction plane) or point, plus the
    start offset.

  From there, by the direction (IN-21); "the way of side 1" is along the sketch normal, or
  against it with IN-13:
  - One Side: from s to the end of side 1: s plus the thickness (IN-12) the way of side 1, or,
    with To Object (IN-22), the height of the extent object (IN-23), on whichever side it is,
    moved by the extent offset (IN-28) away from s. If the object is on the start plane, away
    from s means the way of side 1.
  - Symmetric: from s − t to s + t, with t half the thickness for Whole Length (IN-27), or the
    whole thickness for Half Length.
  - Two Sides: side 1 as for One Side, and side 2 from s the other way, by its own thickness
    (IN-24) or to its own object and offset (IN-25, IN-26, IN-29). The gear spans both.

  The face width b is the distance between the lowest and the highest of these planes
  (VAL-27).

## 7. Gear trains

Gears mesh because their circles touch in one sketch, the layout sketch. Each gear works out
the orientation of its whole train from that sketch alone; the gears know nothing of each
other (D-27).

- **TRN-1** Layout sketch. A gear's layout circle is its curve, or, if the curve is a linked
  projection of a sketch circle or arc, the curve it was projected from, followed back
  through further projections. The layout sketch is the sketch holding the layout circle. It
  may be in any component.
- **TRN-2** Layout circles are all circles and arcs of the layout sketch, construction
  geometry included. Each is taken as a gear's circle with this gear's module (TRN-9).
- **TRN-3** Touching. Two layout circles touch when they touch from outside:
  |a − (r₁ + r₂)| ≤ 0.001 mm, where a is the distance between their centers. For an arc, the
  touching point must lie on the arc. Circles on a common center never touch, so gears on one
  shaft are not connected, and neither are circles touching from inside. Touching circles
  mesh.
- **TRN-4** Train. A train is a set of layout circles connected through touching. A sketch
  may hold several trains. A circle that touches nothing is a train of its own.
- **TRN-5** Start line. A sketch line of the layout sketch with one end on a layout circle's
  center and the other on that circle (both within 0.001 mm) is a start line of that circle.
  It belongs to that circle only, so circles on a common center can each have one. A train
  has at most one start line (VAL-20).
- **TRN-6** Pair rule. For two touching circles, where circle 1 has a tooth axis at θ₁:
  with β the direction from circle 1's center to circle 2's and u = frac((β − θ₁) / τ₁),
  circle 2 has a tooth axis at θ₂ = β + π − (½ − u)·τ₂. A tooth of one then faces a tooth
  space of the other on the line between their centers. This holds for any profile shift,
  backlash and print offset, because each tooth is symmetric (GEO-8).
- **TRN-7** Orientation of a train. Its first circle is the one with the start line, with a
  tooth axis on the line. Without a start line it is the train's first circle in the sketch
  (circles before arcs, each in the order Fusion lists them), with a tooth axis on the layout
  sketch's X axis; deleting and redrawing circles can then turn the whole train, which still
  meshes. From the first circle, TRN-6 gives a tooth axis of every circle of the train, along
  the fewest touchings (breadth first, neighbors in sketch order).
- **TRN-8** Loops. If touching circles form a loop, every touching pair not used by TRN-7 must
  also mesh by TRN-6: the mismatch, measured along the reference circle, must not exceed
  0.001 mm (VAL-21). Whether a loop that meshes can turn is not checked.
- **TRN-9** Tooth counts. Every layout circle's tooth count comes from DER-1 with this gear's
  module. All gears on a layout sketch are assumed to have the same module; this is not
  checked (D-28).
- **TRN-10** The gear's orientation comes from the layout sketch when its layout circle
  belongs to a train of two or more circles, or has a start line. Its tooth axis from TRN-7 is
  then converted from the layout sketch's plane into the gear's own plane, through assembly
  coordinates when they are in different components; the planes must be parallel (VAL-22).
  The start rotation (IN-10) is not used. Otherwise IN-10 applies (GEO-9).
- **TRN-11** Near miss. Two layout circles that do not touch but whose distance differs from
  touching by no more than 0.25·m are reported (VAL-23): usually a missing tangent
  constraint.

## 8. Feature behavior

- **FEA-1** The gear is one custom feature. The timeline shows a single node for it, with the
  add-in's icon and a name of the form "Spur Gear1".
- **FEA-2** The feature depends on the selected curve, and on the start and extent objects
  (IN-20, IN-23, IN-26) it uses. It recomputes when the curve's center, radius, plane or (for an
  arc) end angles change, when one of those objects moves, and when any of its parameters
  change.
- **FEA-3** The selected curve and its sketch are not modified.
- **FEA-4** After every recompute the gear is centered on the selected curve's center, lies on
  its plane, and has the tooth count of DER-1 for the curve's current diameter.
- **FEA-5** IN-2 to IN-12, IN-14, IN-19, IN-24, IN-28 and IN-29 are feature parameters. They
  appear in the parameters dialog under the feature and accept expressions and user
  parameters. Fusion cannot add a parameter to an existing feature, so a gear created before
  one of them existed lacks it: before IN-19 it has no start offset, before IN-24 no distance
  for side 2, before IN-28 and IN-29 no To Object offsets. Such a
  gear still computes, with those inputs disabled in its dialog.
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
- **FEA-14** The gear is created in the active component, as Fusion's own features are, also
  when its curve is in another component, for example in a layout sketch. The gear's
  position follows the curve through the assembly, in the positions at the gear's place in the
  timeline (FEA-13). If the active component has several occurrences, the gear keeps to the
  one that was active when it was created. Editing a gear does not move it to another
  component.
- **FEA-11** Fusion offers Edit Feature for custom features only in Hybrid and Assembly
  designs, not in Part designs. This is a limitation of Fusion, also seen with other custom
  feature add-ins. In a Part design the gear is still created, recomputed and editable
  through the parameters dialog.
- **FEA-12** The feature also depends on its layout sketch, if that is not its curve's own
  sketch. Any change in the layout sketch recomputes the gear: moving or resizing any of its
  circles, and adding, turning or removing a start line (SPIKE-8). The gears do not depend on
  each other: their order in the timeline does not matter, and deleting one leaves the others
  alone. Only the layout sketch must come before them.
- **FEA-13** Positions in assembly coordinates, needed when the gear, its curve and its layout
  sketch are not all in one component, are those at the gear's place in the timeline. Moving a component
  later, or driving a joint, does not turn the gear (SPIKE-7).

## 9. Command and user interface

- **UI-1** The command button is in the SOLID › CREATE panel.
- **UI-2** The curve selection accepts only sketch circles and sketch arcs.
- **UI-3** Live preview: on every input change the preview shows the resulting body. It must
  be geometrically identical to the committed result.
- **UI-4** Derived values (§5) and validation messages (§10) update together with the preview.
- **UI-5** OK is disabled while any VAL error is present. One case is only caught on OK, with
  a message: see VAL-12.
- **UI-6** Creating a gear is a single undo step. So is each edit.
- **UI-7** The create dialog starts with the inputs of the last gear that was created: all
  numeric inputs (as entered, so references to user parameters are kept), flip side,
  operation, start, direction and extents (IN-18, IN-21, IN-22, IN-25). The curve and the start
  and extent objects are not remembered. This lasts until the add-in is stopped; it is not
  saved. If a remembered expression is not valid in the current design, its value is used.
- **UI-8** Pressure angle, addendum, dedendum and root fillet coefficients and the max profile
  deviation are in a group named Advanced. It is collapsed unless one of them differs from
  its default.
- **UI-9** When the orientation comes from the layout sketch (TRN-10), the start rotation input
  is disabled and the info box says so: how many gears the train has, how many circles this
  one touches, and whether the train is oriented by a start line or, without one, by its
  first circle.
- **UI-10** Start (IN-18) is a drop-down right before Thickness. The start offset is shown for
  Offset and Object, the start object selection for Object only. When a gear is edited, its
  start object stays as it is unless another one is picked; the dialog does not show it
  selected, and the info box says it is kept. A face of a body the gear joins exists only
  before the join, so it cannot be selected at the end of the timeline (CHK-9).
- **UI-11** Direction (IN-21) follows the start inputs; with Symmetric, Measurement (IN-27)
  follows it as a row of two icon buttons, as in Extrude; otherwise Flip side. Then, as in
  Extrude: with One Side, Extent Type (IN-22), Thickness, or the extent object and its offset;
  with Two Sides, the same in two foldable groups, Side 1 and Side 2; with Symmetric, the
  Thickness. Switching between One Side and Two Sides keeps what was entered for side 1. Each
  input is shown only when it is used. Start, Direction and Extent Type are drop-downs with
  an icon for each choice, as in Extrude. Choosing Object as the start, or To Object as an
  extent type, makes that object's selection active, so the next click picks the object.
  Extent objects behave like the start object when a gear is edited (UI-10). The info box
  shows the face width when it differs from the thickness input.
- **UI-12** All icons have versions for Fusion's dark theme.

## 10. Validation

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
| VAL-10 | A thickness used as a distance (IN-12, IN-24) is ≤ 0 | error |
| VAL-11 | Bore does not fit inside the root circle: d_B ≥ d_f | error |
| VAL-12 | Operation is Join and the gear touches no body | error |
| VAL-14 | The outline cannot be built: the print offset removes the root circle or folds the root curve back on itself; no flank remains between root curve and tip circle; or x = h_f\* − ρ_f\* exactly, where the root curve has a cusp | error |
| VAL-20 | The gear's train has more than one start line (TRN-5) | error |
| VAL-21 | A loop in the gear's train does not mesh (TRN-8) | error |
| VAL-22 | The layout sketch's plane is not parallel to the gear's plane (TRN-10) | error |
| VAL-23 | Two circles of the gear's train nearly touch (TRN-11) | warning |
| VAL-25 | A start or extent object that is needed is not selected, or no longer exists | error |
| VAL-26 | A start or extent object is a plane that is not parallel to the curve's plane | error |
| VAL-27 | The face width comes out as 0: the gear's planes all coincide (GEO-12) | error |
| VAL-24 | The gear's curve or its layout sketch is in another component than the gear, and the curve was picked in a way that does not tell which occurrence of its component is meant (inside an activated component that has several occurrences). Pick it in the assembly instead | error |

A value outside the range given in §4 is an error and is reported with the ID of that input.

VAL-12 is checked in two steps. The dialog tests whether a cylinder of the tip diameter would
touch a body, which needs no change to the design, and disables OK if not. A gear that misses
every body only between its teeth passes that test and is rejected on OK.

VAL-20, VAL-21 and VAL-23 concern only the gear's own train, not other trains on the sketch.

## 11. Accuracy

- **ACC-1** Every curve that approximates an exact curve (involute, trochoid, including any
  offset) deviates from it by no more than the IN-11 tolerance, measured as normal distance.
- **ACC-2** `gearcore` chooses the number of interpolation points per curve to satisfy ACC-1
  and verifies it by dense sampling. This needs no Fusion.
- **ACC-3** Consecutive curves of the outline share their end points to within floating-point
  rounding, so the outline is closed. Where flank and root curve meet, the flank is ended on
  the first point of the root curve.
- **ACC-4** Tip, root and bore arcs, the corner arcs of GEO-7 and the radial edges are exact
  arcs and lines, not approximations.

## 12. Decisions

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

Resolved on 2026-10-18, after SPIKE-8:

- **D-27** Gears mesh through a layout sketch (§7), not through links between the gears.
  Gears linked to each other ("Mesh with") had to come in chain order in the timeline; gears
  that only read an early sketch can be modeled in any order and in any component, and later
  perhaps in other designs. Replaces D-22 to D-26.
- **D-28** Touching circles mesh, and all gears on one layout sketch use the same module,
  which is not checked (TRN-3, TRN-9).
- **D-29** A start line runs from a circle's center to the circle; at most one per train.
  Without one, the train's first circle in the sketch sets the orientation (TRN-5, TRN-7).
- **D-30** Circles on a common center are not connected: gears on one shaft are oriented
  independently. Loops are allowed if they mesh (TRN-3, TRN-8).
- **D-31** There is no center-distance check. With profile shift, the circles to draw are the
  working pitch circles, which touch at the working center distance.
- **D-32** Start options as in Extrude: Profile Plane, Offset and Object (IN-18 to IN-20). The
  offset is along the sketch normal, independent of the flip side, and also applies to
  Object. Only planes parallel to the sketch, and points, can be start objects: a gear on a
  tilted face makes no sense.
- **D-33** Direction and extent as in Extrude: One Side, Two Sides and Symmetric; Distance and
  To Object (IN-21 to IN-26). To Object goes to the object whichever side it is on.
- **D-34** Symmetric offers Extrude's Half Length and Whole Length, as icon buttons like
  Extrude's; Whole Length is the default, so a gear's thickness stays its face width unless
  chosen otherwise (IN-27). To Object has an offset per side, positive past the object, away
  from the start (IN-28, IN-29).

## 13. Feasibility

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
- **CHK-9** A gear that joins a body and starts on a face of that same body (IN-20): works
  (2026-10-18). It follows the face when the body gets thicker, and it can be edited. The
  preview shows such a gear as its own body: joining it in the preview replaced the selected
  face, and Fusion then disabled OK.

The gear-train design was tested in SPIKE-8: projections lead back to the layout sketch, the
dependency on it is accepted in the root component and through an occurrence, and every
change of the layout sketch reached every gear, created in any order.

## 14. Architecture and testing

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
- **ARC-7** The numeric inputs are custom feature parameters (FEA-5). Flip side, operation,
  start, direction and extents are stored with the feature as named values, the start and
  extent objects as dependencies.
- **ARC-8** The train rules (TRN-2 to TRN-9, TRN-11) are `gearcore` functions on plain data:
  the layout circles, arcs and lines in the layout sketch's coordinates in, tooth axes and
  issues out. The Fusion layer finds the layout circle (TRN-1), reads the layout sketch and
  converts the tooth axis into the gear's plane (TRN-10). The rotation is relative to the
  curve's own frame, so it holds in whatever component the gear is (FEA-14); only the outline's
  placement is carried into the gear's component. The occurrence that was active at creation
  is stored with the feature as a named value.
- **TST-1** `gearcore` has pytest tests runnable outside Fusion. Each test names the requirement
  IDs it covers.
- **TST-2** Reference checks include: DER formulas against hand-calculated values;
  undercut threshold z ≈ 17 for type A; tooth symmetry; involute points lying on the base
  circle involute; ACC-1 by sampling; s at the reference circle matching DER-6; the outline
  being closed (ACC-3); the enclosed area in arc mode and with a bore; the tooth outline
  against an independent model of the generating rack, including undercut; the offset outline
  lying at distance |δ| from the outline without offset; two gears oriented by TRN-6 at the
  center distance where they mesh touching when there is no backlash (overlap no deeper than
  the IN-11 tolerance), and with a clearance of j_bn/2 on each flank when there is; the train
  rules: touching, arcs, start lines, several trains, circles on a common center, loops that
  do and do not mesh, near misses.
- **TST-3** The Fusion layer is verified with a manual checklist in `docs/manual-tests.md`
  that covers the FEA and UI requirements and the CHK items.

## 15. References

- ISO 53:1998, cylindrical gears: standard basic rack tooth profile (types A–D).
- ISO 21771-1:2024, cylindrical involute gears: geometry.
- ISO 1328-1:2013, cylindrical gears: ISO system of flank tolerance classification.
- ISO/TR 10064-2:1996, inspection practice: backlash guidance.
