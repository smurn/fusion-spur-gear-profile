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

## Recompute (FEA-2, FEA-4, FEA-5)

8. Edit the sketch, move the circle, finish. The gear follows.
9. Change the circle diameter to 30 mm. The gear has 30 teeth.
10. Modify › Change Parameters: the feature lists its parameters. Change Thickness to 8 mm;
    the gear updates. Set Module to an expression using a user parameter; it updates.
11. Change the circle diameter to 2 mm (fewer than 3 teeth). The feature turns red or yellow
    in the timeline and keeps its previous body (FEA-8). Set it back to 30 mm; the feature
    recovers.

## Edit dialog (CHK-1, FEA-7)

Use a Hybrid design for this section. In a Part design Fusion does not offer Edit Feature for
custom features (FEA-11).

12. Double-click the feature in the timeline, or right-click › Edit Feature. The dialog opens
    with the current values and the circle selected.
13. Change Thickness and tick Flip side. The preview updates. OK. The gear is on the other
    side of the sketch plane with the new thickness, and it is still one feature.
14. Open the edit dialog again and Cancel. Nothing changes and the timeline marker is back at
    the end.
15. Open the edit dialog, pick a different circle (draw a second one first), OK. The gear
    moves to the new circle and follows it afterwards.

## Undo and redo (CHK-2, UI-6)

16. Create a gear, then Undo once. The gear and its timeline node are gone. Redo brings it back.
17. Edit a gear's thickness in the dialog, then Undo once. The old thickness is back.

## Join (CHK-5, FEA-6)

18. Extrude a 60 x 60 mm plate, 2 mm thick, downward from the XY plane, around the circle.
19. Spur Gear. Pick the circle, then set Operation to Join. No target is selected: the
    preview shows the gear fused to the plate it sits on. OK. The body count does not
    increase.
19a. Draw a circle away from every body and try Join on it. The info box says the gear does
    not touch a body, and OK is disabled (VAL-12).
20. Move the circle in its sketch. The gear moves on the plate; no gear is left behind at the
    old position.

## Other planes and components (CHK-4, FEA-10)

21. Sketch a circle on an offset plane tilted 30 degrees. Create a gear on it. It lies in that
    plane, centered on the circle.
22. Sketch a circle on a planar face of a body. Create a gear on it, as New Body and as Join.
23. Create a new component, activate it, sketch a circle in it and create a gear. The body
    belongs to that component. Move the component; the gear moves with it. Edit the circle;
    the gear follows.

## Undercut, bore and arc mode (GEO-4, GEO-10, GEO-11)

27. Create a gear on a circle of diameter 10 mm (10 teeth). The teeth are visibly undercut:
    narrower just above the root than higher up.
28. Edit it and set Bore diameter to 4 mm. A round hole goes through the gear. Set it to
    9 mm: the info box says the bore does not fit inside the root circle and OK is disabled.
29. Draw an arc of radius 12 mm covering about 120 degrees. Create a gear on it. It is a
    sector: teeth along the arc, centered on the arc's middle, closed by two straight edges
    that meet at the arc's center. The info box shows how many teeth are generated.
30. Edit it and set Bore diameter to 6 mm. The straight edges now end on a round cutout around
    the center.
31. Edit the sketch and make the arc longer. Teeth are added. Make it shorter than one tooth
    pitch: the feature fails and keeps its previous body.
32. Set Start rotation to 50 on the sector gear. The teeth shift by half a pitch and the count
    may change by one.

## Print offset (GEO-7)

33. Create a 24-tooth gear with Bore diameter 8 mm. Edit it and set Print offset to 0.2 mm.
    The teeth get fatter and the tip corners become rounded. The bore stays 8 mm. Measure the
    tip diameter: 26.4 mm.
34. Set Print offset to -0.2 mm. The teeth get thinner, the tip corners are sharp, the bore
    stays 8 mm and the tip diameter is 25.6 mm.
35. On a 10-tooth gear (undercut), try Print offset 0.1 mm and -0.1 mm. Both build.
36. On a sector gear with a bore, try Print offset 0.2 mm and -0.2 mm. The teeth and the
    root circle change; the two straight edges and the bore cutout stay exactly where they
    are, with sharp corners.
37. Set Print offset to 3 mm on any gear. The info box reports an error and OK is disabled.

## Save and reopen (CHK-3, FEA-9)

24. Save, close and reopen the design with the add-in running. Move a circle; the gear follows.
25. Stop the add-in, then open the design. The gears are shown as last computed. Note what
    Fusion reports for the features and what happens when a circle is moved.
26. Start the add-in again with the design open. Move a circle; the gear follows.
