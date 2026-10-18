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
   on the other side of the sketch plane.
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

### Meshing gears

**Mesh with** turns a gear so that it meshes with another one, the mate. Pick the mate in the
timeline, or click its circle or arc. A tooth of one gear then faces a gap of the other on the
line between their centers, whatever their tooth counts, profile shifts or backlash. The
start rotation is not used while a mate is set.

- The gear follows its mate: change the mate's settings or move its curve and the gear turns
  with it. This works along a chain, where C meshes with B and B with A.
- The info box shows the distance between the centers and the distance at which the gears
  mesh, and warns if they differ. Place the curves yourself; the add-in does not move them.
- The two gears must have the same module and pressure angle and lie in parallel planes.
- They can be in different components, so that each can get its own joint. The positions are
  taken where the gear is in the timeline: draw the gears with the components already in
  place (top-down). Moving a component or driving a joint later does not turn the gears; use a
  motion link to make them turn together.
- If the mate's component is used more than once, click its curve on the copy you mean.
- Deleting a gear also deletes the gears that mesh with it (Undo brings them back). To keep
  one, clear its Mesh with first; it stays where it is.

## Development

- `gearcore/` is the gear math in pure Python. Run its tests with `python -m pytest` from the
  repository root.
- `fusion_layer/` is the Fusion side. It is checked by hand with
  [docs/manual-tests.md](docs/manual-tests.md).
- `tools/make_icons.py` draws the icons in `resources/`.
- `spikes/` holds the throwaway feasibility code behind [docs/spikes.md](docs/spikes.md).
- [docs/custom-feature-notes.md](docs/custom-feature-notes.md) collects what we learned about
  Fusion's custom feature API. It is written to be useful for other add-ins too.
