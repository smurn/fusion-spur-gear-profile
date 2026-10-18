# Spur Gear

An Autodesk Fusion add-in that turns a sketch circle or arc into a solid involute spur gear.
The gear is one feature in the timeline and stays attached to its curve: move or resize the
curve, or change a parameter, and the gear is recomputed.

It makes full gears from circles and sector gears from arcs, with undercut, profile shift,
backlash, a print offset and an optional bore, as a new body or joined to the bodies it
touches. The specification is in [docs/spec.md](docs/spec.md).

The add-in uses Fusion's custom feature API, which Autodesk marks as a preview.

## Install

Fusion needs the folder to be named `SpurGearProfile`, matching the `.manifest` and `.py` files.

1. Clone into Fusion's add-ins folder:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\SpurGearProfile`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/SpurGearProfile`

   ```
   git clone https://github.com/smurn/fusion-spur-gear-profile SpurGearProfile
   ```
2. In Fusion, open **UTILITIES > ADD-INS > Scripts and Add-Ins**, select **SpurGearProfile**, and click **Run**.
3. The **Spur Gear** button appears under **SOLID > CREATE**.

The add-in is set to run on startup. It must be running for gears to recompute. A design
opened without it shows each gear as last computed.

## Use

1. Sketch a circle of roughly the pitch diameter you want, or an arc for a sector gear, and
   finish the sketch.
2. Start **SOLID > CREATE > Spur Gear** and pick the circle or arc.
3. Set the **Module**. The tooth count is the curve's diameter divided by the module, rounded;
   the info box at the bottom shows it together with the resulting diameters. The gear's
   reference diameter is module times tooth count, so it usually differs a little from the
   curve you drew.
4. Set **Thickness**, and a **Bore diameter** if you want a hole. **Flip side** puts the gear
   on the other side of the sketch plane. **Start**, **Direction** and **Extent** work as in
   Extrude:
   - Start: from the sketch plane (Profile Plane), moved along the sketch normal by an offset
     (Offset), or from a parallel face, construction plane or point (Object), optionally with
     an offset too.
   - Direction: One Side, Two Sides (each side with its own extent) or Symmetric, centered
     on the start. For Symmetric, Measurement chooses whether the thickness is the whole face
     width or goes each way.
   - Extent: a Distance (the thickness), or To Object, up to a parallel face, construction
     plane or point, with an offset that moves the end past the object (or short of it, if
     negative).
5. Choose the **Operation**: New Body, or Join to merge the gear into every body it touches.
6. OK. The gear appears as one "Spur Gear" feature in the timeline.

Other inputs:

- **Start rotation** turns the teeth, from 0 to 100 % of one tooth pitch.
- **Profile shift** and **Backlash** are the usual gear terms; backlash is the normal backlash
  of the mesh, of which this gear takes half.
- **Print offset** moves the tooth profile outward (positive) or inward (negative), to
  compensate for a 3D printer. It does not change the bore.
- **Advanced** holds the pressure angle, the addendum, dedendum and root fillet coefficients
  of the generating rack (ISO 53 type A by default), and the largest allowed deviation of the
  fitted curves from the exact tooth shape.

To change a gear later, edit its sketch, change its values under **Modify > Change
Parameters**, or double-click the feature in the timeline to open the dialog again. Fusion
offers the dialog only in hybrid and assembly designs, not in part designs.

Gears with few teeth are undercut, as a real rack-cut gear would be; the info box says so. A
positive profile shift avoids it.

### Gear trains

Gears mesh when their circles touch in one sketch, the layout sketch. Draw the whole train
there: a circle for every gear, made tangent to the gears it meshes with. Then create each
gear on its circle, either directly in the layout sketch or on a linked projection of the
circle in the gear's own component. Like Fusion's own features, a gear is created in the
active component, so you can also activate the gear's component and click its circle in the
layout sketch directly. Each gear works out from the layout sketch how its train must be
turned so that every tooth faces a tooth space of its neighbor.

- The gears do not refer to each other. They can be created in any order and in any
  component; only the layout sketch must come before them in the timeline.
- Change the layout (move a circle, resize one) and every gear follows.
- A start line fixes where a tooth points: a line from a circle's center to a point on that
  circle. One per train at most. Without one, the train's first circle in the sketch has a
  tooth on the sketch's X axis.
- A sketch can hold several separate trains. Circles on a common center are not connected,
  so gears on one shaft are turned independently.
- All gears on a layout sketch must have the same module. With profile shift, draw the
  working pitch circles, which touch at the working center distance.
- The start rotation only applies to a gear whose circle touches nothing and has no start
  line.

## Development

- `gearcore/` is the gear math in pure Python. Run its tests with `python -m pytest` from the
  repository root.
- `fusion_layer/` is the Fusion side. It is checked by hand with
  [docs/manual-tests.md](docs/manual-tests.md).
- `tools/make_icons.py` draws the icons in `resources/`.
- `spikes/` holds the throwaway feasibility code behind [docs/spikes.md](docs/spikes.md).
- [docs/custom-feature-notes.md](docs/custom-feature-notes.md) collects what we learned about
  Fusion's custom feature API. It is written to be useful for other add-ins too.
