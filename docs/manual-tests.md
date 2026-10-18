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
4. A preview of the gear appears and follows changes to Module and Distance (UI-3, CHK-6).
5. Set Module to 3 mm. The tooth count drops to 8, the info box reports undercut, and the
    preview shows 8 undercut teeth. Set Module to 20 mm: fewer than 3 teeth is an error and OK
    is disabled (UI-5). Set Module back to 1 mm; the preview returns.
6. OK. One body appears. The timeline shows one "Spur Gear1" node with the gear icon (FEA-1).
7. The body is 5 mm thick and sits on the +Z side of the sketch plane (GEO-12).

## Dialog layout and remembered settings (UI-7, UI-8)

8. Start Spur Gear in a fresh session. Module, Start, Direction, Extent Type, Distance, Bore
    diameter, Start rotation, Profile shift, Backlash and Print offset are visible. Pressure angle, the
    three coefficients and Max profile deviation are in a collapsed group named Advanced.
9. Create a gear with Module 2 mm, Distance 8 mm, Direction Symmetric and Pressure angle
    25 deg. Start Spur Gear again: Module, Distance and Pressure angle are filled in, and
    Advanced is open because Pressure angle is not at its default. Direction is One Side again
    (D-35). The circle is not selected.
10. Set Pressure angle back to 20 deg and create another gear. Start Spur Gear again: Advanced
    is collapsed.
11. Edit an existing gear and change its distance. Start Spur Gear again: the dialog still
    shows the values of the last gear that was created, not of the edit.
12. Stop and start the add-in. The dialog is back to the defaults.

## Recompute (FEA-2, FEA-4, FEA-5)

13. Edit the sketch, move the circle, finish. The gear follows.
14. Change the circle diameter to 30 mm. The gear has 30 teeth.
15. Modify › Change Parameters: the feature lists its parameters. Change Distance to 8 mm;
    the gear updates. Set Module to an expression using a user parameter; it updates.
16. Change the circle diameter to 2 mm (fewer than 3 teeth). The feature turns red or yellow
    in the timeline and keeps its previous body (FEA-8). Set it back to 30 mm; the feature
    recovers.

## Edit dialog (CHK-1, FEA-7)

Use a Hybrid design for this section. In a Part design Fusion does not offer Edit Feature for
custom features (FEA-11).

17. Double-click the feature in the timeline, or right-click › Edit Feature. The dialog opens
    with the current values and the circle selected.
18. Change Distance to a negative value. The preview updates. OK. The gear is on the other
    side of the sketch plane, and it is still one feature.
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
26. Edit a gear's distance in the dialog, then Undo once. The old distance is back.

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
64. Active component (FEA-14): add two more tangent circles to the root layout sketch. Create
    a component Gear S, activate it, and create a gear by clicking one of the new circles in
    the layout sketch directly, without projecting it. The gear appears in Gear S (browser
    and timeline), on the layout circle. Do the same for the other circle in a component
    Gear T: the two mesh.
65. Change the position of Gear S's circle in the layout: the gear in Gear S follows and still
    meshes with the one in Gear T. Edit the gear in Gear S: it stays in Gear S.
66. Create a gear with the root component active from a circle in the layout: it is in the
    root component, as before.

## Start (IN-18 to IN-20, GEO-12, UI-10, CHK-9)

67. In a new gear's dialog, Start is right before Direction and set to Profile Plane; there is
    no offset or object input. The gear starts on the sketch plane, as before.
68. Set Start to Offset and the offset to 3 mm: the gear moves 3 mm along the sketch normal.
    Set Distance to -5 mm: the gear now extends the other way from the same start, 3 mm up.
    Set -3 mm: it starts below the sketch plane.
69. Set Start to Object and pick a construction plane parallel to the sketch, 10 mm away: the
    gear starts on it. Set the offset to 1 mm: it starts 1 mm beyond the plane. Move the
    plane (edit its offset): the gear follows.
70. Pick a point as the object (a sketch point or a body vertex): the gear starts on the plane
    through the point, parallel to the sketch.
71. Try a planar face that is not parallel to the sketch: the info box reports an error and OK
    is disabled. Curved faces cannot be picked.
72. CHK-9: a plate body, and a gear set to Join that starts on the plate's top face (Object).
    Note whether the gear appears and joins. Then change the plate's thickness: does the gear
    follow the face?
73. Edit a gear made before this version: Start shows Profile Plane; the offset input is
    disabled with a tooltip; Object works.
74. Create a gear with Start set to Offset 2 mm; start a second one: it starts with Profile
    Plane again, and when Offset is chosen the offset is 0 mm (UI-7, D-35).

## Direction and extent (IN-21 to IN-26, GEO-12, UI-11)

75. In a new gear's dialog: after Start come Direction (One Side), Extent Type (Distance) and
    Distance. There is no Flip side. Nothing for side 2 is shown.
76. Direction Symmetric: Extent Type disappears. With Distance 6 mm (or -6 mm) the gear runs
    from 3 mm below to 3 mm above the start; the info box shows the face width.
77. Direction Two Sides: the side inputs move into two foldable groups, Side 1 and Side 2.
    Side 1 Distance 5 mm, Side 2 Distance 2 mm: the gear runs from 2 mm below to 5 mm above
    the start. Side 1 -5 mm and Side 2 -2 mm swap them.
78. One Side with Extent Type To Object: pick a construction plane 8 mm above the sketch: the gear
    ends on it; the info box shows a face width of 8 mm. Pick one 4 mm below instead: the gear
    goes down to it. Move the plane: the gear follows.
79. Two Sides with side 2 To Object, a point 3 mm below, and side 1 a distance of 5 mm: the
    gear runs from 3 mm below to 5 mm above.
80. Start Object and Extent Type To Object on the same plane: error that the gear has no thickness;
    OK is disabled.
81. A Join gear whose extent goes to a face of the body it joins: OK is available, the gear
    joins on OK, and it follows the face. Edit it: the extent object is kept ("as before").
82. Edit a gear made before this version: it opens with One Side and Distance; side 2's
    Distance is disabled.
83. Create a Symmetric gear; start a new one: it starts with One Side (UI-7, D-35).

## Measurement and To Object offset (IN-27 to IN-29, UI-11)

84. Direction Symmetric: a Measurement row with two icon buttons appears under Direction,
    Whole Length selected. Distance 6 mm gives a 6 mm gear centered on the start.
85. Click Half Length: the gear is 12 mm, 6 mm each way. Hover over the buttons: the tooltips
    say Half Length and Whole Length. The icons are clear in light and dark themes.
86. Extent Type To Object: an Extent offset input appears under the object. A plane 8 mm above with
    offset 1 mm: the gear ends 9 mm above. Offset -1 mm: 7 mm. A plane 4 mm below with
    offset 1 mm: the gear goes 5 mm down.
87. Two Sides with side 2 To Object: side 2 has its own offset, which works the same way.
88. Change an offset in Change Parameters: the gear follows (the offsets are parameters).
89. Edit a Symmetric Half Length gear: Half Length is still selected. Create a new gear: it
    starts with One Side, and Symmetric starts with Whole Length (UI-7, D-35).
90. Start, Direction and Extent Type show an icon next to each choice, in the closed drop-down
    and in its list. Two Sides and Symmetric are easy to tell apart. The icons are clear in
    light and dark themes.

## Dark theme, side groups, object selection (UI-11, UI-12)

91. Switch Fusion to its dark theme. The Spur Gear button, the timeline icon and all icons in
    the dialog (Start, Direction, Extent Type, Measurement) are drawn in lighter colors and
    are clear. Switch back: the normal icons return.
92. One Side, Extent Type To Object with an object and an offset of 1 mm. Switch Direction to
    Two Sides: Side 1 shows the same extent type, object and offset. Change Side 1's
    distance, switch back to One Side: the changed distance is kept.
93. Choose Extent Type To Object (ungrouped, in Side 1 and in Side 2) and Start Object: each
    time the matching selection is active right away, so clicking a face picks it without
    clicking into the selection first.
94. Fold and unfold Side 1 and Side 2: the inputs stay as they were.
95. Edit a Two Sides gear whose side 1 goes To Object: the dialog opens with the groups, and
    the info box says the extent object is kept.
96. Create a One Side gear with Distance 7 mm, then a Two Sides gear with Side 2 Distance
    3 mm. Start a new gear: Profile Plane, One Side, Extent Type Distance, Distance 7 mm.
    Switch to Two Sides: Side 2's distance is the default 5 mm, not 3 mm.

## Negative distances (IN-12, IN-24, D-36)

97. One Side, Distance -5 mm: the gear extends 5 mm against the sketch normal. Distance 0:
    error, OK is disabled. The info box always shows the face width.
98. Change Parameters lists the distance of a new gear as "Distance", not "Thickness".
99. A gear made with Flip side ticked, before this version: it keeps its shape after the
    add-in update. Edit it: Distance shows its old value negated (for example "-(5 mm)"). OK:
    the gear stays where it was.
