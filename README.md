# Spur Gear Profile

An Autodesk Fusion add-in that generates involute spur gear profiles as sketches.

**Status:** scaffold only. The add-in loads and adds a button, but doesn't generate gears yet.

## Install

Fusion needs the folder to be named `SpurGearProfile`, matching the `.manifest` and `.py` files.

1. Clone into Fusion's add-ins folder:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\SpurGearProfile`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/SpurGearProfile`

   ```
   git clone https://github.com/smurn/fusion-spur-gear-profile SpurGearProfile
   ```
2. In Fusion, open **UTILITIES > ADD-INS > Scripts and Add-Ins**, select **SpurGearProfile**, and click **Run**.
3. The **Spur Gear Profile** button appears under **SOLID > CREATE**.
