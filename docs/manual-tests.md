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

## Gear trains (section 7, FEA-12, FEA-13, UI-9)

Setup: a new hybrid design. In the root component, a sketch "Layout" with these circles, each
center fixed by dimensions or tangent constraints:

- Train 1: A, diameter 20 mm at (0, 0); B, 30 mm, tangent to A, its center 25 mm from A at
  about 20°; C, 20 mm, tangent to B.
- Train 2: D, 16 mm at (-40, 0); E, 24 mm, tangent to D.
- F, 12 mm, on A's center.
- A start line on A: a line from A's center to a point on A, at about 30°.

48. Create a gear on circle C, directly in the layout sketch. The info box says "Gear train of
    3 gears, touching 1; oriented by its start line". Start rotation is greyed out.
49. Create gears on A and then B. All three mesh: zoom in where they touch. A has a tooth
    centered on the start line.
50. Change the start line's angle: A, B and C turn and stay meshed.
51. Change B's position dimension so that B moves around A: B and C follow and stay meshed.
52. Create gears on D and E. The info box says "no start line: oriented by its first circle in
    the sketch". They mesh.
53. Add a start line to D: D and E turn; train 1 does not change.
54. Create a gear on F. It is not part of a train: Start rotation is available and works. Add
    a start line ending on F: only F turns to it, A does not.
55. Add a second start line to train 1, on C: A, B and C fail in the timeline, and their edit
    dialog names the error. D and E are unaffected. Delete the line: all recover.
56. Remove the tangent constraint between D and E and move E 0.1 mm away. Edit E: the info box
    warns that two circles nearly touch. Undo.
57. Delete the gear on B: A and C stay. Undo.
58. Top-down with components: add two tangent circles P (20 mm) and Q (30 mm) to the layout.
    Create components Gear P and Gear Q. In each, make a sketch and project the circle with
    linked projection. Create the gears on the projected circles, Q first: they mesh.
59. Change P's position in the layout: both gears follow.
60. Put a layout sketch in its own component "Layout" instead, with linked projections into
    gear components as in step 58. Same result.
61. Draw an arc in the layout, tangent to A, with the touching point on the arc, and make a
    sector gear on it: it meshes with A. Shorten the arc so the touching point is off the arc:
    it is no longer part of the train.
62. Four 24 mm circles on the corners of a 24 mm square, each tangent to two others: gears on
    all four mesh. Three 24 mm circles all tangent to each other: their gears fail with an
    error that the loop does not mesh.
63. Save, close and reopen. Change the start line of train 1: the gears follow.
