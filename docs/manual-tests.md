# Manual tests

Checklist for the Fusion layer (TST-3). Run the add-in from Scripts and Add-Ins first.
Until the later phases land, use gears with at least 18 teeth, no print offset and no bore;
other inputs show "Not supported yet" and disable OK.

Record the result of each item as pass or fail, with a note on what happened.

## Setup

New design. Sketch on the XY plane with a circle of diameter 24 mm, dimensioned so it can be
moved (two position dimensions and a diameter dimension). Finish the sketch.

## Create (FEA-1, FEA-6, UI-1 to UI-5)

1. SOLID › CREATE shows **Spur Gear**. Start it.
2. Only sketch circles and arcs can be picked for "Circle or arc" (UI-2).
3. Pick the circle. The info box shows 24 teeth and the diameters (UI-4).
4. A preview of the gear appears and follows changes to Module and Thickness (UI-3, CHK-6).
5. Set Module to 3 mm. The tooth count drops to 8, the info box reports undercut as not
   supported yet, and OK is disabled (UI-5). Set Module back to 1 mm.
6. OK. One body appears. The timeline shows one "Spur Gear1" node with the gear icon (FEA-1).
7. The body is 5 mm thick and sits on the +Z side of the sketch plane (GEO-12).

## Recompute (FEA-2, FEA-4, FEA-5)

8. Edit the sketch, move the circle, finish. The gear follows.
9. Change the circle diameter to 30 mm. The gear has 30 teeth.
10. Modify › Change Parameters: the feature lists its parameters. Change Thickness to 8 mm;
    the gear updates. Set Module to an expression using a user parameter; it updates.
11. Change the circle diameter to 8 mm (undercut, not supported yet). The feature turns red or
    yellow in the timeline and keeps its previous body (FEA-8). Set it back to 30 mm; the
    feature recovers.

## Edit dialog (CHK-1, FEA-7)

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
19. Spur Gear. Pick the circle, then set Operation to Join. A "Target body" selection appears
    and takes the focus; click the plate. The preview shows the gear on the plate. OK. The
    body count does not increase and the gear is fused to the plate.
20. Move the circle in its sketch. The gear moves on the plate; no gear is left behind at the
    old position.

## Other planes and components (CHK-4, FEA-10)

21. Sketch a circle on an offset plane tilted 30 degrees. Create a gear on it. It lies in that
    plane, centered on the circle.
22. Sketch a circle on a planar face of a body. Create a gear on it, as New Body and as Join.
23. Create a new component, activate it, sketch a circle in it and create a gear. The body
    belongs to that component. Move the component; the gear moves with it. Edit the circle;
    the gear follows.

## Save and reopen (CHK-3, FEA-9)

24. Save, close and reopen the design with the add-in running. Move a circle; the gear follows.
25. Stop the add-in, then open the design. The gears are shown as last computed. Note what
    Fusion reports for the features and what happens when a circle is moved.
26. Start the add-in again with the design open. Move a circle; the gear follows.
