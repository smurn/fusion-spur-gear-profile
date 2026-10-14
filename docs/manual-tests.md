# Manual tests

Checklist for the Fusion layer (TST-3). Run the add-in from Scripts and Add-Ins first.

Record the result of each item as pass or fail, with a note on what happened.

## Setup

New design. Sketch on the XY plane with a circle of diameter 24 mm, dimensioned so it can be
moved (two position dimensions and a diameter dimension). Finish the sketch.

## Create (FEA-1, FEA-6, UI-1 to UI-5)

1. SOLID › CREATE shows **Spur Gear**. Start it.
2. Only sketch circles and arcs can be picked for "Circle or arc" (UI-2).
3. Pick the circle. The info box shows 24 teeth and the diameters (UI-4).
4. A preview of the gear appears and follows changes to Module and Thickness (UI-3, CHK-6).
5. Set Module to 3 mm. The tooth count drops to 8, the info box reports undercut, and the
    preview shows 8 undercut teeth. Set Module to 20 mm: fewer than 3 teeth is an error and OK
    is disabled (UI-5). Set Module back to 1 mm; the preview returns.
6. OK. One body appears. The timeline shows one "Spur Gear1" node with the gear icon (FEA-1).
7. The body is 5 mm thick and sits on the +Z side of the sketch plane (GEO-12).

## Dialog layout and remembered settings (UI-7, UI-8)

8. Start Spur Gear in a fresh session. Module, Thickness, Bore diameter, Flip side, Start
    rotation, Profile shift, Backlash and Print offset are visible. Pressure angle, the
    three coefficients and Max profile deviation are in a collapsed group named Advanced.
9. Create a gear with Module 2 mm, Thickness 8 mm, Flip side ticked and Pressure angle 25 deg.
    Start Spur Gear again: those values are filled in, and Advanced is open because Pressure
    angle is not at its default. The circle is not selected.
10. Set Pressure angle back to 20 deg and create another gear. Start Spur Gear again: Advanced
    is collapsed.
11. Edit an existing gear and change its thickness. Start Spur Gear again: the dialog still
    shows the values of the last gear that was created, not of the edit.
12. Stop and start the add-in. The dialog is back to the defaults.

## Recompute (FEA-2, FEA-4, FEA-5)

13. Edit the sketch, move the circle, finish. The gear follows.
14. Change the circle diameter to 30 mm. The gear has 30 teeth.
15. Modify › Change Parameters: the feature lists its parameters. Change Thickness to 8 mm;
    the gear updates. Set Module to an expression using a user parameter; it updates.
16. Change the circle diameter to 2 mm (fewer than 3 teeth). The feature turns red or yellow
    in the timeline and keeps its previous body (FEA-8). Set it back to 30 mm; the feature
    recovers.

## Edit dialog (CHK-1, FEA-7)

Use a Hybrid design for this section. In a Part design Fusion does not offer Edit Feature for
custom features (FEA-11).

17. Double-click the feature in the timeline, or right-click › Edit Feature. The dialog opens
    with the current values and the circle selected.
18. Change Thickness and tick Flip side. The preview updates. OK. The gear is on the other
    side of the sketch plane with the new thickness, and it is still one feature.
19. Open the edit dialog again and Cancel. Nothing changes and the timeline marker is back at
    the end.
20. Open the edit dialog, pick a different circle (draw a second one first), OK. The gear
    moves to the new circle and follows it afterwards.

## Changing the operation (FEA-7)

21. Create a New Body gear on a circle that sits on a plate. Edit it and set Operation to
    Join. The preview shows it fused to the plate. OK. The body count drops by one and the
    timeline still shows one Spur Gear feature. Move the circle: the gear follows.
22. Edit that gear and set Operation back to New Body. The gear is a separate body again
    and the plate is whole.
23. Undo once after each of the two changes: the previous state returns.
24. Edit a New Body gear whose circle touches no body and choose Join: the info box says
    there is nothing to join to and OK is disabled.

## Undo and redo (CHK-2, UI-6)

25. Create a gear, then Undo once. The gear and its timeline node are gone. Redo brings it back.
26. Edit a gear's thickness in the dialog, then Undo once. The old thickness is back.

## Join (CHK-5, FEA-6)

27. Extrude a 60 x 60 mm plate, 2 mm thick, downward from the XY plane, around the circle.
28. Spur Gear. Pick the circle, then set Operation to Join. No target is selected: the
    preview shows the gear fused to the plate it sits on. OK. The body count does not
    increase.
29. Draw a circle away from every body and try Join on it. The info box says the gear does
    not touch a body, and OK is disabled (VAL-12).
30. Move the circle in its sketch. The gear moves on the plate; no gear is left behind at the
    old position.

## Other planes and components (CHK-4, FEA-10)

31. Sketch a circle on an offset plane tilted 30 degrees. Create a gear on it. It lies in that
    plane, centered on the circle.
32. Sketch a circle on a planar face of a body. Create a gear on it, as New Body and as Join.
33. Create a new component, activate it, sketch a circle in it and create a gear. The body
    belongs to that component. Move the component; the gear moves with it. Edit the circle;
    the gear follows.

## Undercut, bore and arc mode (GEO-4, GEO-10, GEO-11)

34. Create a gear on a circle of diameter 10 mm (10 teeth). The teeth are visibly undercut:
    narrower just above the root than higher up.
35. Edit it and set Bore diameter to 4 mm. A round hole goes through the gear. Set it to
    9 mm: the info box says the bore does not fit inside the root circle and OK is disabled.
36. Draw an arc of radius 12 mm covering about 120 degrees. Create a gear on it. It is a
    sector: teeth along the arc, centered on the arc's middle, closed by two straight edges
    that meet at the arc's center. The info box shows how many teeth are generated.
37. Edit it and set Bore diameter to 6 mm. The straight edges now end on a round cutout around
    the center.
38. Edit the sketch and make the arc longer. Teeth are added. Make it shorter than one tooth
    pitch: the feature fails and keeps its previous body.
39. Set Start rotation to 50 on the sector gear. The teeth shift by half a pitch and the count
    may change by one.

## Print offset (GEO-7)

40. Create a 24-tooth gear with Bore diameter 8 mm. Edit it and set Print offset to 0.2 mm.
    The teeth get fatter and the tip corners become rounded. The bore stays 8 mm. Measure the
    tip diameter: 26.4 mm.
41. Set Print offset to -0.2 mm. The teeth get thinner, the tip corners are sharp, the bore
    stays 8 mm and the tip diameter is 25.6 mm.
42. On a 10-tooth gear (undercut), try Print offset 0.1 mm and -0.1 mm. Both build.
43. On a sector gear with a bore, try Print offset 0.2 mm and -0.2 mm. The teeth and the
    root circle change; the two straight edges and the bore cutout stay exactly where they
    are, with sharp corners.
44. Set Print offset to 3 mm on any gear. The info box reports an error and OK is disabled.

## Save and reopen (CHK-3, FEA-9)

45. Save, close and reopen the design with the add-in running. Move a circle; the gear follows.
46. Stop the add-in, then open the design. The gears are shown as last computed. Note what
    Fusion reports for the features and what happens when a circle is moved.
47. Start the add-in again with the design open. Move a circle; the gear follows.

## Mesh with (IN-17, FEA-12 to FEA-14, UI-9, CHK-7)

Setup: one sketch with three circles, each center fixed by dimensions: A, diameter 20 mm at
(0, 0); B, diameter 30 mm at (25, 0); C, diameter 20 mm at (25, 25). Create a plain gear A on
the first circle.

48. Start Spur Gear, select circle B, click into "Mesh with" and click gear A **in the
    timeline** (CHK-7). Note whether it is accepted. The info box says "Meshes with Spur
    Gear1: center distance 25.000 mm, ideal 25.000 mm", Start rotation is greyed out. On OK,
    zoom in where the gears meet: a tooth of one sits centered in a gap of the other, with no
    visible overlap.
49. Undo, and repeat with A's **circle** picked for "Mesh with". Same result.
50. Create gear C on circle C, meshing with B. Zoom in: C meshes with B.
51. Change A's Start rotation in Change Parameters, to 30. B and C turn and stay meshed.
52. Edit A (double-click it) and change Start rotation: B and C follow in the preview. Cancel:
    all three return.
53. Edit the sketch and move A to (-1, 0). B turns and stays meshed on the line between the
    centers. Edit B: the info box warns that the center distance is 26.000 mm and the gears
    mesh at 25.000 mm. Cancel, and move A back.
54. Undo and redo the last few steps. B and C follow every time.
55. Edit B: "Mesh with" shows A. Clear it: Start rotation becomes available and is filled in;
    B does not move. OK. Change A's Start rotation: B no longer follows (C still follows B).
    Undo both steps.
56. Errors, each in a new Spur Gear dialog on circle B:
    - Module 1.25 with "Mesh with" A: error that the module differs; OK is disabled.
    - A circle that has no gear as "Mesh with": it cannot be picked, or the info box says to
      pick a Spur Gear.
57. Edit A and try to pick B as "Mesh with": it cannot be picked, or the info box says the gear
    must come before this one in the timeline.
58. Draw a circle of diameter 30 mm on an offset plane 10 mm above, centered at (-25, 0).
    Create a gear on it meshing with A. It meshes with A, seen from above.
59. Draw an arc of radius 15 mm around (0, -25), about 120 degrees, facing A. Create a sector
    gear on it meshing with A. Its teeth mesh with A.
60. Create B as Join onto a body it touches, meshing with A. It meshes and joins.
61. Save, close and reopen. Change A's Start rotation: B and C follow.
62. Delete A in the timeline: the gears meshing with it, directly or through the chain, are
    deleted too (FEA-13). Undo restores all of them.
