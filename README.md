# Spur Gear

An Autodesk Fusion add-in that turns a sketch circle or arc into a solid involute spur gear.
The gear is one feature in the timeline and stays attached to its curve: move or resize the
curve, or change a parameter, and the gear is recomputed.

**Status:** in development. Full gears with 18 or more teeth work, as New Body or Join.
Undercut, print offset, bore and arc mode are not implemented yet; the dialog says so and
disables OK. The specification is in [docs/spec.md](docs/spec.md).

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

The add-in must be running for gears to recompute.

## Development

- `gearcore/` is the gear math in pure Python. Run its tests with `python -m pytest` from the
  repository root.
- `fusion_layer/` is the Fusion side. It is checked by hand with
  [docs/manual-tests.md](docs/manual-tests.md).
- `spikes/` holds the throwaway feasibility code behind [docs/spikes.md](docs/spikes.md).
