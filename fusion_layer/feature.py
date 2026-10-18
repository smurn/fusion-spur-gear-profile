"""The Spur Gear custom feature: create and edit commands, preview, recompute.

Structure follows ARC-3: the gear body lives in a base feature; the custom
feature groups that base feature and, for Join, one combine feature.
"""

import dataclasses
import math
import os
import traceback
import typing

import adsk.core
import adsk.fusion

from .. import gearcore
from . import geometry, layout
from .geometry import CM

#: Never change: saved designs refer to their gear features by this id.
FEATURE_ID = 'smurn.SpurGear'
CREATE_ID = 'smurn_SpurGear_create'
EDIT_ID = 'smurn_SpurGear_edit'
NAME = 'Spur Gear'
TOOLTIP = 'Creates an involute spur gear from a sketch circle or arc.'
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'

NEW_BODY, JOIN = 'New Body', 'Join'
PROFILE_PLANE, OFFSET, OBJECT = 'Profile Plane', 'Offset', 'Object'   # IN-18
DISTANCE, TO_OBJECT = 'Distance', 'To Object'                         # IN-22, IN-25
HALF_LENGTH, WHOLE_LENGTH = 'Half Length', 'Whole Length'             # IN-27
#: Start and extent objects (IN-20, IN-23, IN-26): dialog input and dependency ids, labels.
OBJECT_INPUTS = {'start_object': 'Start object', 'extent_object': 'Extent object',
                 'extent_object2': 'Extent object (side 2)'}
#: The inputs of one side's extent, by role (UI-11). Side 1 has two sets, as in
#: Extrude: ungrouped for One Side and Symmetric, in the Side 1 group for Two Sides.
#: Fusion cannot move an input into a group, so the dialog has both and carries the
#: values across when the direction changes (_carry_side1).
SIDE_SETS = {
    'one': {'extent': 'extent', 'thickness': 'thickness', 'object': 'extent_object',
            'offset': 'extent_offset'},
    'side1': {'extent': 'side1_extent', 'thickness': 'side1_thickness',
              'object': 'side1_extent_object', 'offset': 'side1_extent_offset'},
    'side2': {'extent': 'extent2', 'thickness': 'thickness2', 'object': 'extent_object2',
              'offset': 'extent_offset2'},
}
#: The feature parameters behind each set's thickness and offset (FEA-5).
SET_PARAMS = {'one': ('thickness', 'extent_offset'), 'side1': ('thickness', 'extent_offset'),
              'side2': ('thickness2', 'extent_offset2')}
#: Selection input id: the start or extent object (dependency id) it picks.
INPUT_OBJECT = {'start_object': 'start_object', 'extent_object': 'extent_object',
                'side1_extent_object': 'extent_object', 'extent_object2': 'extent_object2'}
#: Drop-down id: the selection input its object choice activates, and that choice (UI-11).
CHOICE_OBJECT = {'start': ('start_object', OBJECT), 'extent': ('extent_object', TO_OBJECT),
                 'side1_extent': ('side1_extent_object', TO_OBJECT),
                 'extent2': ('extent_object2', TO_OBJECT)}
GROUPS = ('advanced', 'side1', 'side2')
NOTHING_TO_JOIN = ('The gear does not touch a body to join to. Use New Body, or move the curve '
                   'onto a body.')

#: Numeric inputs: id, label, kind (length | angle | number), default expression.
#: They are dialog inputs and feature parameters (FEA-5). Never change the ids.
PARAMS = (
    ('module', 'Module', 'length', '1 mm'),
    ('start_offset', 'Start offset', 'length', '0 mm'),
    ('thickness', 'Distance', 'length', '5 mm'),
    ('extent_offset', 'Extent offset', 'length', '0 mm'),
    ('thickness2', 'Distance (side 2)', 'length', '5 mm'),
    ('extent_offset2', 'Extent offset (side 2)', 'length', '0 mm'),
    ('bore', 'Bore diameter', 'length', '0 mm'),
    ('rotation', 'Start rotation (% of pitch)', 'number', '0'),
    ('extra_teeth', 'Extra teeth', 'number', '0'),
    ('pressure_angle', 'Pressure angle', 'angle', '20 deg'),
    ('addendum', 'Addendum coefficient', 'number', '1'),
    ('dedendum', 'Dedendum coefficient', 'number', '1.25'),
    ('fillet', 'Root fillet coefficient', 'number', '0.38'),
    ('profile_shift', 'Profile shift coefficient', 'number', '0'),
    ('backlash', 'Backlash', 'length', '0 mm'),
    ('print_offset', 'Print offset', 'length', '0 mm'),
    ('tolerance', 'Max profile deviation', 'length', '0.01 mm'),
)
#: Inputs that are rarely changed. The dialog shows them in a collapsed group (UI-8).
ADVANCED = ('pressure_angle', 'addendum', 'dedendum', 'fillet', 'tolerance')
#: Extrusion values that a new gear does not take over from the last one (UI-7, D-35).
#: The thickness is the gear's face width and is taken over.
NOT_REMEMBERED = ('start_offset', 'extent_offset', 'thickness2', 'extent_offset2')

app = adsk.core.Application.get()
ui = app.userInterface


def log(message: str):
    app.log('Spur Gear: ' + message)


def design() -> adsk.fusion.Design:
    return adsk.fusion.Design.cast(app.activeProduct)


def find_input(inputs: adsk.core.CommandInputs, input_id: str):
    """A dialog input by id, at the top level or in one of the groups."""
    found = inputs.itemById(input_id)
    for group_id in GROUPS:
        if found is not None:
            break
        group = adsk.core.GroupCommandInput.cast(inputs.itemById(group_id))
        found = group.children.itemById(input_id) if group else None
    return found


def unit(kind: str) -> str:
    if kind == 'length':
        return design().unitsManager.defaultLengthUnits
    return 'deg' if kind == 'angle' else ''


def to_gear_params(frame: geometry.Frame, values: dict) -> gearcore.GearParams:
    """Feature parameter values (Fusion's internal cm and radians) to gearcore's mm."""
    mm = lambda pid: values[pid] / CM
    return gearcore.GearParams(
        diameter=frame.diameter, arc_span=frame.arc_span,
        module=mm('module'), pressure_angle=values['pressure_angle'],
        addendum=values['addendum'], dedendum=values['dedendum'], fillet=values['fillet'],
        profile_shift=values['profile_shift'], backlash=mm('backlash'),
        print_offset=mm('print_offset'), rotation=values['rotation'] / 100.0,
        tolerance=mm('tolerance'), thickness=mm('thickness'), bore=mm('bore'),
        extra_teeth=values.get('extra_teeth', 0.0))


def parameter_of(feature: adsk.fusion.CustomFeature, pid: str):
    """A feature parameter, or None if the gear was created before the parameter
    existed: Fusion cannot add one to an existing feature (FEA-5). For an unknown
    id, itemById raises "Invalid argument id" rather than returning None."""
    try:
        return feature.parameters.itemById(pid)
    except RuntimeError:
        return None


def parameter_value(feature: adsk.fusion.CustomFeature, pid: str, kind: str, default: str) -> float:
    """A feature parameter's value, or its default for a gear created before the
    parameter existed (FEA-5)."""
    parameter = parameter_of(feature, pid)
    if parameter is None:
        return design().unitsManager.evaluateExpression(default, unit(kind))
    return parameter.value


def named_value(feature: adsk.fusion.CustomFeature, value_id: str, default: str) -> str:
    values = feature.customNamedValues
    return values.value(value_id) if values.isExistingValue(value_id) else default


def base_feature(feature: adsk.fusion.CustomFeature) -> adsk.fusion.BaseFeature:
    """The base feature that holds the gear body."""
    return next(f for f in feature.features
                if f.objectType == adsk.fusion.BaseFeature.classType())


class NothingToJoin(gearcore.GearError):
    """Operation is Join and the gear touches no body (VAL-12)."""


@dataclasses.dataclass
class Extent:
    """Where the gear begins and ends (GEO-12): start, direction and extents."""
    start: str = PROFILE_PLANE                # IN-18
    direction: str = gearcore.ONE_SIDE        # IN-21
    flip: bool = False                        # only on gears made before D-36
    extent: str = DISTANCE                    # IN-22
    extent2: str = DISTANCE                   # IN-25
    objects: dict = dataclasses.field(default_factory=dict)   # by OBJECT_INPUTS id
    half_length: bool = False                 # IN-27, with Symmetric

    def needed(self) -> list:
        """The ids of the objects this extent uses."""
        ids = []
        if self.start == OBJECT:
            ids.append('start_object')
        if self.direction != gearcore.SYMMETRIC and self.extent == TO_OBJECT:
            ids.append('extent_object')
        if self.direction == gearcore.TWO_SIDES and self.extent2 == TO_OBJECT:
            ids.append('extent_object2')
        return ids


def stored_extent(feature: adsk.fusion.CustomFeature) -> Extent:
    """A gear's extent, from its named values and dependencies (ARC-7)."""
    objects = {}
    for object_id in OBJECT_INPUTS:
        dependency = feature.dependencies.itemById(object_id)
        objects[object_id] = dependency.entity if dependency else None
    return Extent(named_value(feature, 'start', PROFILE_PLANE),
                  named_value(feature, 'direction', gearcore.ONE_SIDE),
                  named_value(feature, 'flip', '0') == '1',
                  named_value(feature, 'extent', DISTANCE), named_value(feature, 'extent2', DISTANCE),
                  objects, named_value(feature, 'measurement', WHOLE_LENGTH) == HALF_LENGTH)


@dataclasses.dataclass
class Settings:
    """What the dialog currently says."""
    curve: typing.Any
    operation: str
    expressions: dict
    values: dict
    extent: Extent = dataclasses.field(default_factory=Extent)
    auto_teeth: bool = True   # IN-30


@dataclasses.dataclass
class Evaluation:
    frame: typing.Optional[geometry.Frame] = None    # at the gear's lowest plane (GEO-12)
    params: typing.Optional[gearcore.GearParams] = None
    outline: typing.Optional[gearcore.Outline] = None
    issues: list = dataclasses.field(default_factory=list)
    train: typing.Optional[layout.Train] = None
    extent: typing.Optional[Extent] = None
    heights: dict = dataclasses.field(default_factory=dict)   # cm, of the objects used


def feature_occurrence(feature: adsk.fusion.CustomFeature):
    """The occurrence of the gear's component that was active when the gear was
    created (FEA-14), or its only one, or None in the root component."""
    values = feature.customNamedValues
    token = values.value('occurrence') if values.isExistingValue('occurrence') else ''
    if token:
        for entity in design().findEntityByToken(token):
            occurrence = adsk.fusion.Occurrence.cast(entity)
            if occurrence:
                return occurrence
    try:
        return geometry.component_occurrence(feature.parentComponent)
    except geometry.AmbiguousOccurrence:
        # A gear made before FEA-14 has no stored occurrence; it is in its curve's
        # component, where no occurrence is needed (frame_in).
        return None


def evaluate(curve, values: dict, target, extent: typing.Optional[Extent] = None,
             known: typing.Optional[dict] = None, auto_teeth: bool = False) -> Evaluation:
    """Run the gear math for a curve and parameter values. target is the gear's
    component and the occurrence of it (FEA-14). known holds the heights of objects
    from an earlier evaluation, used for objects that are not valid right now.
    auto_teeth is IN-30. Never raises for bad input."""
    ev = Evaluation(extent=extent or Extent())
    extent = ev.extent
    if not geometry.is_gear_curve(geometry.native(curve) if curve else None):
        ev.issues.append(gearcore.Issue('VAL-1', gearcore.ERROR, 'Select a sketch circle or arc.'))
        return ev
    try:
        ev.frame = geometry.frame_in(curve, *target)
    except geometry.AmbiguousOccurrence as e:
        ev.issues.append(gearcore.Issue('VAL-24', gearcore.ERROR, str(e)))
        return ev
    for object_id in extent.needed():
        entity = extent.objects.get(object_id)
        if entity is not None and entity.isValid:
            try:
                ev.heights[object_id] = geometry.object_height(entity, ev.frame, *target)
            except geometry.AmbiguousOccurrence as e:
                ev.issues.append(gearcore.Issue('VAL-24', gearcore.ERROR, str(e)))
                return ev
            except geometry.ObjectError as e:
                ev.issues.append(gearcore.Issue('VAL-26', gearcore.ERROR, str(e)))
                return ev
        elif known and object_id in known:
            # While a Join preview is shown, a face of the body it joins has been
            # replaced, and the selected face is not valid until the preview goes.
            # When editing, the gear keeps its objects without them being selected
            # (_keeps_object).
            ev.heights[object_id] = known[object_id]
        else:
            ev.issues.append(gearcore.Issue('VAL-25', gearcore.ERROR, 'Select the {}.'.format(
                OBJECT_INPUTS[object_id].lower())))
            return ev

    # GEO-12: from the start plane by the direction and the extents, in mm.
    start = 0.0
    if extent.start != PROFILE_PLANE:
        start = (values.get('start_offset', 0.0) + ev.heights.get('start_object', 0.0)) / CM

    def side(object_id: str, pid: str, offset_id: str, kind: str) -> gearcore.Side:
        if kind == TO_OBJECT:   # IN-28, IN-29
            return gearcore.Side(height=ev.heights[object_id] / CM,
                                 offset=values.get(offset_id, 0.0) / CM)
        # A gear made before D-36 may have a flip, which turned both sides round.
        return gearcore.Side(distance=values.get(pid, 0.0) / CM * (-1.0 if extent.flip else 1.0))

    first = side('extent_object', 'thickness', 'extent_offset',
                 DISTANCE if extent.direction == gearcore.SYMMETRIC else extent.extent)
    second = (side('extent_object2', 'thickness2', 'extent_offset2', extent.extent2)
              if extent.direction == gearcore.TWO_SIDES else None)
    ev.issues = gearcore.extent_issues(extent.direction, first, second)
    if ev.issues:
        return ev
    low, high = gearcore.span(start, extent.direction, first, second, extent.half_length)
    if high - low < 1e-6:
        ev.issues.append(gearcore.Issue('VAL-27', gearcore.ERROR, 'The gear has no thickness: its '
                                        'start and end are on the same plane.'))
        return ev
    ev.frame = geometry.shifted(ev.frame, low * CM)
    ev.params = dataclasses.replace(to_gear_params(ev.frame, values), thickness=high - low,
                                    auto_teeth=auto_teeth)
    ev.issues = gearcore.validate(ev.params)
    if not any(i.severity == gearcore.ERROR for i in ev.issues):
        # The rotation is relative to the curve's own frame, so it holds in the
        # gear's component too (ARC-8).
        ev.train = layout.train_of(curve, geometry.frame_of(curve), ev.params)   # section 7
        changes = {'mates': ev.train.mates}   # TRN-12
        if ev.train.rotation is not None:
            changes['rotation'] = ev.train.rotation
        if ev.train.mates or ev.train.rotation is not None:
            ev.params = dataclasses.replace(ev.params, **changes)
            # Which teeth of an arc are generated depends on both (VAL-6).
            ev.issues = gearcore.validate(ev.params)
        ev.issues += ev.train.issues
    if not any(i.severity == gearcore.ERROR for i in ev.issues):
        try:
            ev.outline = gearcore.gear_outline(ev.params)
        except gearcore.GearError as e:   # VAL-14: only found while building the outline
            ev.issues.append(gearcore.Issue('VAL-14', gearcore.ERROR, str(e)))
    return ev


def oriented_by_layout(ev: Evaluation) -> bool:
    """Whether the layout sketch sets the gear's orientation (TRN-10), even if it
    cannot right now because of an error in the train."""
    o = ev.train.orientation if ev.train else None
    return bool(o and (o.train_size > 1 or o.start_line))


def info_text(ev: Evaluation) -> str:
    lines = []
    if ev.params:
        d = gearcore.derive(ev.params)
        teeth = '{} teeth'.format(d.teeth)
        if ev.params.arc_span is not None:   # DER-9
            teeth = '{} of {} teeth'.format(d.generated_teeth, d.teeth)
        lines.append('<b>{}</b>, selected diameter {:.3f} mm'.format(teeth, ev.params.diameter))
        if d.motion_range is not None:   # DER-12, UI-13
            lines.append('Range of motion {:.1f} deg'.format(math.degrees(d.motion_range)))
        lines.append('Reference {:.3f} / base {:.3f} mm'.format(d.reference_diameter, d.base_diameter))
        lines.append('Tip {:.3f} / root {:.3f} mm'.format(d.tip_diameter, d.root_diameter))
        if d.tip_thickness is not None:
            lines.append('Tooth thickness {:.3f}, at the tip {:.3f} mm'.format(
                d.tooth_thickness, d.tip_thickness))
        lines.append('Face width {:.3f} mm'.format(ev.params.thickness))   # UI-11
    if oriented_by_layout(ev):   # UI-9
        o = ev.train.orientation
        by = ('oriented by its start line' if o.start_line else
              'no start line: oriented by its first circle in the sketch')
        if o.train_size > 1:
            lines.append('Gear train of {} gears, touching {}; {}'.format(o.train_size, o.touching, by))
        else:
            lines.append('Oriented by its start line')
    for issue in ev.issues:
        lines.append('<b>{}:</b> {}'.format(issue.severity.capitalize(), issue.message))
    return '<br/>'.join(lines)


class SpurGearFeature:
    def __init__(self, resources: str):
        self._resources = resources
        self._handlers = []          # kept for the lifetime of the add-in
        self._command_handlers = []  # kept while a dialog is open
        self._command = None
        self._editing: typing.Optional[adsk.fusion.CustomFeature] = None
        #: Settings of the last gear created, to start the next one with (UI-7).
        #: Kept in memory only.
        self._last_used: dict = {}
        #: Heights of the start and extent objects from the last evaluation where
        #: they were valid, by object id.
        self._known: dict = {}
        #: Object inputs the user changed in this dialog.
        self._changed: set = set()
        self._logged: set = set()   # reasons for a disabled OK, logged once per dialog

        for cid, callback in ((CREATE_ID, self._on_create_created), (EDIT_ID, self._on_edit_created)):
            old = ui.commandDefinitions.itemById(cid)
            if old:
                old.deleteMe()
            definition = ui.commandDefinitions.addButtonDefinition(cid, NAME, TOOLTIP, resources)
            self._listen(definition.commandCreated, adsk.core.CommandCreatedEventHandler, callback,
                         self._handlers)

        self._definition = adsk.fusion.CustomFeatureDefinition.create(FEATURE_ID, NAME, resources)
        self._definition.editCommandId = EDIT_ID
        self._listen(self._definition.customFeatureCompute, adsk.fusion.CustomFeatureEventHandler,
                     self._on_compute, self._handlers, quiet=True)

        panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
        old = panel.controls.itemById(CREATE_ID)
        if old:
            old.deleteMe()
        self._control = panel.controls.addCommand(ui.commandDefinitions.itemById(CREATE_ID))

    def close(self):
        self._handlers = []
        self._command_handlers = []
        for item in (self._control, ui.commandDefinitions.itemById(CREATE_ID),
                     ui.commandDefinitions.itemById(EDIT_ID)):
            if item and item.isValid:
                item.deleteMe()

    @staticmethod
    def _listen(event, base_class, callback, keep: list, quiet: bool = False):
        class Handler(base_class):
            def notify(self, args):
                try:
                    callback(args)
                except Exception:
                    log(traceback.format_exc())
                    if not quiet:
                        ui.messageBox('{} failed:\n{}'.format(NAME, traceback.format_exc()))
        handler = Handler()
        event.add(handler)
        keep.append(handler)

    # ---------------------------------------------------------------- dialog --
    def _on_create_created(self, args: adsk.core.CommandCreatedEventArgs):
        self._editing = None
        self._build_dialog(args.command)

    def _on_edit_created(self, args: adsk.core.CommandCreatedEventArgs):
        feature = adsk.fusion.CustomFeature.cast(ui.activeSelections.item(0).entity)
        if feature is None:
            raise RuntimeError('Select a Spur Gear feature to edit.')
        self._editing = feature
        self._build_dialog(args.command)

    def _build_dialog(self, command: adsk.core.Command):
        self._command = command
        self._known = {}
        self._changed = set()
        self._logged = set()
        self._syncing = False   # set while the dialog changes its own inputs
        inputs = command.commandInputs
        feature = self._editing

        curve = inputs.addSelectionInput('curve', 'Circle or arc', 'Select a sketch circle or arc')
        curve.addSelectionFilter('SketchCurves')
        curve.setSelectionLimits(1, 1)

        operation = inputs.addDropDownCommandInput(
            'operation', 'Operation', adsk.core.DropDownStyles.TextListDropDownStyle)
        if feature:
            current, extent = feature.customNamedValues.value('operation'), stored_extent(feature)
        else:
            # A new gear starts with the default extrusion settings (UI-7, D-35).
            current, extent = self._last_used.get('operation', NEW_BODY), Extent()
        for name in (NEW_BODY, JOIN):
            operation.listItems.add(name, name == current)

        # The common inputs first, the rarely changed ones in a group that is only
        # open if one of them is not at its default (UI-8). Start, direction and
        # extents are placed like Extrude's (UI-10, UI-11).
        advanced = []
        for pid, label, kind, default in PARAMS:
            if pid in ADVANCED:
                advanced.append((pid, label, kind, default))
            elif pid in ('thickness', 'extent_offset', 'thickness2', 'extent_offset2'):
                continue   # in the side inputs, below
            elif pid == 'extra_teeth':   # UI-13
                if feature:
                    auto = named_value(feature, 'auto_teeth', '0') == '1'
                else:
                    auto = self._last_used.get('auto_teeth', True)
                inputs.addBoolValueInput('auto_teeth', 'Automatic extra teeth', True, '', auto)
                self._add_value(inputs, pid, pid)
            elif pid == 'start_offset':
                self._add_choice(inputs, 'start', 'Start', 'start', (PROFILE_PLANE, OFFSET, OBJECT),
                                 extent.start)
                self._add_value(inputs, pid, pid)
                self._add_object(inputs, 'start_object', 'Start object')
                self._add_choice(inputs, 'direction', 'Direction', 'direction',
                                 (gearcore.ONE_SIDE, gearcore.TWO_SIDES, gearcore.SYMMETRIC),
                                 extent.direction)
                # IN-27, shown like Extrude's: a row of two icon buttons.
                measurement = inputs.addButtonRowCommandInput('measurement', 'Measurement', False)
                for name, folder in ((HALF_LENGTH, 'half_length'), (WHOLE_LENGTH, 'whole_length')):
                    measurement.listItems.add(name, (name == HALF_LENGTH) == extent.half_length,
                                              os.path.join(self._resources, 'measurement', folder))
                self._add_side(inputs, 'one', extent.extent)
                side1 = inputs.addGroupCommandInput('side1', 'Side 1')
                self._add_side(side1.children, 'side1', extent.extent)
                side2 = inputs.addGroupCommandInput('side2', 'Side 2')
                self._add_side(side2.children, 'side2', extent.extent2)
                self._two = extent.direction == gearcore.TWO_SIDES
            else:
                self._add_value(inputs, pid, pid)
        group = inputs.addGroupCommandInput('advanced', 'Advanced')
        changed = False
        for pid, label, kind, default in advanced:
            value, differs = self._initial(pid, kind, default)
            group.children.addValueInput(pid, label, unit(kind), value)
            changed = changed or differs
        group.isExpanded = changed
        inputs.addTextBoxCommandInput('info', '', '', 8, True)
        self._update_dialog(inputs)

        self._command_handlers = []
        events = [(command.destroy, adsk.core.CommandEventHandler, self._on_destroy),
                  (command.validateInputs, adsk.core.ValidateInputsEventHandler, self._on_validate),
                  (command.preSelect, adsk.core.SelectionEventHandler, self._on_pre_select),
                  (command.inputChanged, adsk.core.InputChangedEventHandler, self._on_input_changed),
                  (command.executePreview, adsk.core.CommandEventHandler, self._on_preview),
                  (command.execute, adsk.core.CommandEventHandler, self._on_execute)]
        if feature:
            events.append((command.activate, adsk.core.CommandEventHandler, self._on_activate))
        for event, base_class, callback in events:
            self._listen(event, base_class, callback, self._command_handlers)

    def _add_value(self, inputs: adsk.core.CommandInputs, input_id: str, pid: str, label: str = ''):
        """A value input for the feature parameter pid (FEA-5)."""
        _, own_label, kind, default = next(p for p in PARAMS if p[0] == pid)
        value_input = inputs.addValueInput(input_id, label or own_label, unit(kind),
                                           self._initial(pid, kind, default)[0])
        if self._editing and parameter_of(self._editing, pid) is None:   # FEA-5
            value_input.isEnabled = False
            value_input.tooltip = 'This gear was made before this input existed. Create it again to use it.'

    @staticmethod
    def _add_object(inputs: adsk.core.CommandInputs, input_id: str, label: str):
        """A selection for a start or extent object (IN-20, IN-23, IN-26)."""
        selection = inputs.addSelectionInput(input_id, label,
                                             'Select a planar face, construction plane or point')
        for name in ('PlanarFaces', 'ConstructionPlanes', 'Vertices', 'SketchPoints', 'ConstructionPoints'):
            selection.addSelectionFilter(name)
        selection.setSelectionLimits(0, 1)

    def _add_side(self, inputs: adsk.core.CommandInputs, set_name: str, current: str):
        """One side's extent inputs (UI-11): extent type, thickness, object, offset."""
        ids = SIDE_SETS[set_name]
        thickness, offset = SET_PARAMS[set_name]
        self._add_choice(inputs, ids['extent'], 'Extent Type', 'extent', (DISTANCE, TO_OBJECT), current)
        self._add_value(inputs, ids['thickness'], thickness, 'Distance')
        self._add_object(inputs, ids['object'], 'Extent object')
        self._add_value(inputs, ids['offset'], offset, 'Extent offset')

    def _add_choice(self, inputs: adsk.core.CommandInputs, input_id: str, label: str, icons: str,
                    names, current: str):
        """A drop-down with an icon for each choice, as in Extrude (UI-11). The icons are
        in resources/<icons>/<name in lower case, words joined by _>."""
        choice = inputs.addDropDownCommandInput(input_id, label,
                                                adsk.core.DropDownStyles.LabeledIconDropDownStyle)
        for name in names:
            folder = os.path.join(self._resources, icons, name.lower().replace(' ', '_'))
            choice.listItems.add(name, name == current, folder)

    def _initial(self, pid: str, kind: str, default: str):
        """What a numeric input starts with, and whether that differs from its default:
        the feature's value when editing, else the value used for the last gear
        (UI-7), else the default."""
        units = design().unitsManager
        standard = units.evaluateExpression(default, unit(kind))
        by_string = adsk.core.ValueInput.createByString
        if self._editing:
            parameter = parameter_of(self._editing, pid)
            if parameter is None:   # FEA-5: made before this parameter existed
                return by_string(default), False
            if pid in ('thickness', 'thickness2') and named_value(self._editing, 'flip', '0') == '1':
                # D-36: a flipped gear shows its distances negated, which keeps its shape;
                # OK then clears the flip.
                return by_string('-({})'.format(parameter.expression)), True
            return by_string(parameter.expression), abs(parameter.value - standard) > 1e-9
        if pid in self._last_used.get('params', {}) and pid not in NOT_REMEMBERED:
            expression, value = self._last_used['params'][pid]
            differs = abs(value - standard) > 1e-9
            # The expression may use a user parameter that this design does not have.
            if units.isValidExpression(expression, unit(kind)):
                return by_string(expression), differs
            return adsk.core.ValueInput.createByReal(value), differs
        return by_string(default), False

    def _target(self):
        """The gear's component and its occurrence: the edited gear's, or the active
        one for a new gear, as with Fusion's own features (FEA-14)."""
        if self._editing:
            return self._editing.parentComponent, feature_occurrence(self._editing)
        return design().activeComponent, design().activeOccurrence

    def _read(self, inputs: adsk.core.CommandInputs) -> typing.Optional[Settings]:
        """The dialog's current settings, or None while a value cannot be evaluated."""
        def choice(input_id: str) -> str:
            return adsk.core.DropDownCommandInput.cast(find_input(inputs, input_id)).selectedItem.name

        def selected(input_id: str):
            selection = adsk.core.SelectionCommandInput.cast(find_input(inputs, input_id))
            return selection.selection(0).entity if selection.selectionCount else None

        direction = choice('direction')
        side1 = SIDE_SETS['side1' if direction == gearcore.TWO_SIDES else 'one']
        input_of = {'thickness': side1['thickness'], 'extent_offset': side1['offset']}
        expressions, values = {}, {}
        for pid, _, _, _ in PARAMS:
            value_input = adsk.core.ValueCommandInput.cast(find_input(inputs, input_of.get(pid, pid)))
            if not value_input.isValidExpression:
                return None
            expressions[pid], values[pid] = value_input.expression, value_input.value
        objects = {'start_object': selected('start_object'), 'extent_object': selected(side1['object']),
                   'extent_object2': selected('extent_object2')}
        measurement = adsk.core.ButtonRowCommandInput.cast(inputs.itemById('measurement')).selectedItem
        extent = Extent(choice('start'), direction, False, choice(side1['extent']), choice('extent2'),
                        objects, bool(measurement) and measurement.name == HALF_LENGTH)
        auto = adsk.core.BoolValueCommandInput.cast(inputs.itemById('auto_teeth')).value
        return Settings(selected('curve'), choice('operation'), expressions, values, extent, auto)

    def _carry_side1(self, inputs: adsk.core.CommandInputs):
        """When the direction switches to or from Two Sides, carry side 1's values to
        the set of inputs that is shown now (SIDE_SETS)."""
        two = adsk.core.DropDownCommandInput.cast(inputs.itemById('direction')).selectedItem.name \
            == gearcore.TWO_SIDES
        if two == self._two:
            return
        source, target = SIDE_SETS['one' if two else 'side1'], SIDE_SETS['side1' if two else 'one']
        self._two = two
        self._syncing = True
        try:
            name = adsk.core.DropDownCommandInput.cast(find_input(inputs, source['extent'])).selectedItem.name
            items = adsk.core.DropDownCommandInput.cast(find_input(inputs, target['extent'])).listItems
            for i in range(items.count):
                items.item(i).isSelected = items.item(i).name == name
            for role in ('thickness', 'offset'):
                adsk.core.ValueCommandInput.cast(find_input(inputs, target[role])).expression = \
                    adsk.core.ValueCommandInput.cast(find_input(inputs, source[role])).expression
            src = adsk.core.SelectionCommandInput.cast(find_input(inputs, source['object']))
            dst = adsk.core.SelectionCommandInput.cast(find_input(inputs, target['object']))
            if src.selectionCount or dst.selectionCount:   # leave empty ones alone (_keeps_object)
                dst.clearSelection()
                if src.selectionCount:
                    dst.addSelection(src.selection(0).entity)
        finally:
            self._syncing = False

    def _evaluate(self, settings: Settings) -> Evaluation:
        known = dict(self._known)
        for object_id in OBJECT_INPUTS:
            if object_id not in known and self._keeps_object(settings, object_id):
                # Its height when the gear was last created or edited; good enough for
                # the dialog's checks. The gear itself is built from the object.
                stored = named_value(self._editing, 'height_' + object_id, '')
                known[object_id] = float(stored) if stored else 0.0
        ev = evaluate(settings.curve, settings.values, self._target(), settings.extent, known,
                      settings.auto_teeth)
        for object_id, entity in settings.extent.objects.items():
            if entity is not None and entity.isValid and object_id in ev.heights:
                self._known[object_id] = ev.heights[object_id]
        return ev

    def _keeps_object(self, settings: Settings, object_id: str) -> bool:
        """Whether an edited gear keeps a start or extent object it has. The edit
        dialog does not select it: a face of a body the gear joins exists only before
        the join, at the gear's place in the timeline, and selecting a face that a
        preview replaces disables OK (CHK-9). Picking an object replaces it."""
        extent = settings.extent
        if not (self._editing and object_id in extent.needed() and extent.objects.get(object_id) is None):
            return False
        return object_id not in self._changed and bool(self._editing.dependencies.itemById(object_id))

    def _join_problem(self, settings: Settings, ev: Evaluation) -> str:
        """VAL-12, checked without building the gear: if not even a cylinder of the
        tip diameter touches a body, there is nothing to join to. A gear that
        misses a body only between its teeth is caught when it is created."""
        if settings.operation != JOIN or ev.outline is None:
            return ''
        own_body = None
        if self._editing:
            if self._editing.customNamedValues.value('operation') == JOIN:
                return ''   # already joined; the combine keeps its bodies
            # The gear's own body must not count as something to join to. It is
            # missing here if a later feature has consumed it.
            try:
                bodies = base_feature(self._editing).bodies
                own_body = bodies.item(0) if bodies.count else None
            except (StopIteration, RuntimeError):
                own_body = None
        component = self._target()[0]
        envelope = geometry.envelope_body(
            ev.frame, gearcore.derive(ev.params).tip_diameter / 2, ev.params.thickness, False)
        if geometry.touching_bodies(component, envelope, ignore=own_body):
            return ''
        return NOTHING_TO_JOIN

    def _update_dialog(self, inputs: adsk.core.CommandInputs, note: str = ''):
        settings = self._read(inputs)
        text = 'Enter valid values.'
        if settings is not None:
            ev = self._evaluate(settings)
            text = info_text(ev)
            note = note or self._join_problem(settings, ev)
            # UI-9: the layout sketch sets the rotation; the start rotation is not used.
            find_input(inputs, 'rotation').isEnabled = not oriented_by_layout(ev)
            # UI-10, UI-11: show only what the chosen start, direction and extents use.
            e = settings.extent
            symmetric, two = e.direction == gearcore.SYMMETRIC, e.direction == gearcore.TWO_SIDES
            one = e.direction == gearcore.ONE_SIDE
            to1, to2 = e.extent == TO_OBJECT, e.extent2 == TO_OBJECT
            curve = geometry.native(settings.curve) if settings.curve else None
            arc = bool(curve) and curve.objectType == adsk.fusion.SketchArc.classType()
            shown = {'auto_teeth': arc, 'extra_teeth': arc,   # UI-13
                     'start_offset': e.start != PROFILE_PLANE, 'start_object': e.start == OBJECT,
                     'measurement': symmetric,
                     'extent': one, 'thickness': symmetric or (one and not to1),
                     'extent_object': one and to1, 'extent_offset': one and to1,
                     'side1': two, 'side2': two,
                     'side1_thickness': not to1, 'side1_extent_object': to1, 'side1_extent_offset': to1,
                     'thickness2': not to2, 'extent_object2': to2, 'extent_offset2': to2}
            for input_id, visible in shown.items():
                find_input(inputs, input_id).isVisible = visible
            kept = [OBJECT_INPUTS[i] for i in OBJECT_INPUTS if self._keeps_object(settings, i)]
            if kept:
                text += '<br/>{}: as before. Pick another one to change it.'.format(', '.join(kept))
        if note:
            text += '<br/><b>Error:</b> ' + note
        adsk.core.TextBoxCommandInput.cast(inputs.itemById('info')).formattedText = text

    def _on_input_changed(self, args: adsk.core.InputChangedEventArgs):
        if self._syncing:
            return
        input_id, inputs = args.input.id, self._command.commandInputs
        if input_id in INPUT_OBJECT:
            self._known.pop(INPUT_OBJECT[input_id], None)
            self._changed.add(INPUT_OBJECT[input_id])
        if input_id == 'direction':
            self._carry_side1(inputs)
        if input_id != 'info':
            self._update_dialog(inputs)
        if input_id in CHOICE_OBJECT:
            # UI-11: with Object or To Object chosen, the next click picks the object.
            selection_id, wanted = CHOICE_OBJECT[input_id]
            if adsk.core.DropDownCommandInput.cast(args.input).selectedItem.name == wanted:
                adsk.core.SelectionCommandInput.cast(find_input(inputs, selection_id)).hasFocus = True

    def _on_pre_select(self, args: adsk.core.SelectionEventArgs):
        if args.activeInput.id == 'curve':
            args.isSelectable = geometry.is_gear_curve(geometry.native(args.selection.entity))
        elif args.activeInput.id in INPUT_OBJECT:
            args.isSelectable = geometry.is_height_object(args.selection.entity)

    def _on_validate(self, args: adsk.core.ValidateInputsEventArgs):
        settings = self._read(args.inputs)
        valid = False
        if settings is not None:
            ev = self._evaluate(settings)
            problem = self._join_problem(settings, ev)
            valid = ev.outline is not None and not problem
            if not valid:   # the info box says the same; the log helps when it does not
                reason = '; '.join([i.message for i in ev.issues if i.severity == gearcore.ERROR]
                                   + ([problem] if problem else [])) or 'no outline'
                if reason not in self._logged:
                    self._logged.add(reason)
                    log('OK disabled: ' + reason)
        args.areInputsValid = valid   # UI-5

    def _on_activate(self, args: adsk.core.CommandEventArgs):
        """Edit only: select the feature's curve. Selections cannot be set earlier.

        The timeline stays where it is while the dialog is open. Rolling it back for
        the whole edit (rollTo plus beginStep, or Command.editingFeature, which is
        not always accepted) hid the gear and gave Undo an extra step that only
        moved the timeline marker. _apply_edit rolls it back just for the change."""
        dependency = self._editing.dependencies.itemById('curve')
        if dependency and dependency.entity:
            selection = adsk.core.SelectionCommandInput.cast(
                args.command.commandInputs.itemById('curve'))
            if not selection.addSelection(dependency.entity):
                log('could not select the curve of ' + self._editing.name)
        # Start and extent objects are not selected; see _keeps_object.

    def _on_destroy(self, args: adsk.core.CommandEventArgs):
        self._command = None
        self._command_handlers = []
        self._editing = None

    def _on_preview(self, args: adsk.core.CommandEventArgs):
        # Fusion undoes whatever the preview changes. While editing, the preview
        # applies the edit to the feature itself; creating a second feature for it
        # made the gear disappear.
        settings = self._read(args.command.commandInputs)
        if settings is not None:
            faces = [adsk.fusion.BRepFace.cast(settings.extent.objects.get(i))
                     for i in settings.extent.needed()]
            if settings.operation == JOIN and any(faces):
                # Joining in the preview replaces the faces of the joined body, and Fusion
                # then disables OK because a selected face is no longer valid. The
                # preview shows the gear as its own body; OK joins it (CHK-9).
                settings = dataclasses.replace(settings, operation=NEW_BODY)
            try:
                if self._editing:
                    self._apply_edit(self._editing, settings)
                else:
                    self._create(settings)
            except NothingToJoin as e:
                # VAL-12 can only be checked with the gear body in hand.
                self._update_dialog(args.command.commandInputs, str(e))
            # Without this the preview stays invisible after the inputs were
            # invalid for a moment, until the mouse moves over it.
            app.activeViewport.refresh()

    def _on_execute(self, args: adsk.core.CommandEventArgs):
        settings = self._read(args.command.commandInputs)
        if settings is None:
            raise RuntimeError('The inputs are not valid.')
        try:
            if self._editing:
                self._apply_edit(self._editing, settings)
            elif self._create(settings):
                self._last_used = {
                    'operation': settings.operation, 'auto_teeth': settings.auto_teeth,
                    'params': {pid: (settings.expressions[pid], settings.values[pid])
                               for pid, _, _, _ in PARAMS if pid not in NOT_REMEMBERED}}
        except NothingToJoin as e:
            ui.messageBox(str(e), NAME)

    # --------------------------------------------------------------- feature --
    def _create(self, settings: Settings) -> typing.Optional[adsk.fusion.CustomFeature]:
        component, occurrence = self._target()
        ev = evaluate(settings.curve, settings.values, (component, occurrence), settings.extent,
                      auto_teeth=settings.auto_teeth)
        if ev.outline is None:
            return None
        features = component.features

        base = features.baseFeatures.add()
        base.startEdit()
        try:
            # The frame is at the gear's lowest plane, so it always extends along the
            # normal (GEO-12).
            geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness, False)
        finally:
            base.finishEdit()
        last = base
        if settings.operation == JOIN:
            try:
                last = self._join(component, base)
            except NothingToJoin:
                base.deleteMe()
                raise

        inp = features.customFeatures.createInput(self._definition)
        for pid, label, kind, _ in PARAMS:
            inp.addCustomParameter(pid, label, adsk.core.ValueInput.createByString(
                settings.expressions[pid]), unit(kind), True)
        inp.setStartAndEndFeatures(base, last)
        feature = features.customFeatures.add(inp)
        feature.customNamedValues.addOrSetValue('operation', settings.operation)
        feature.customNamedValues.addOrSetValue('auto_teeth', '1' if settings.auto_teeth else '0')
        feature.customNamedValues.addOrSetValue('occurrence', occurrence.entityToken if occurrence else '')
        self._store_extent(feature, settings.extent)
        self._store_heights(feature, ev)
        objects = {i: settings.extent.objects.get(i) for i in settings.extent.needed()}
        self._set_dependencies(feature, settings.curve, ev.train, objects)
        return feature

    @staticmethod
    def _store_extent(feature: adsk.fusion.CustomFeature, extent: Extent):
        """Start, direction, extents and measurement as named values (ARC-7)."""
        values = feature.customNamedValues
        values.addOrSetValue('flip', '1' if extent.flip else '0')   # only old gears have one (D-36)
        values.addOrSetValue('start', extent.start)
        values.addOrSetValue('direction', extent.direction)
        values.addOrSetValue('extent', extent.extent)
        values.addOrSetValue('extent2', extent.extent2)
        values.addOrSetValue('measurement', HALF_LENGTH if extent.half_length else WHOLE_LENGTH)

    @staticmethod
    def _store_heights(feature: adsk.fusion.CustomFeature, ev: Evaluation):
        """The objects' heights, for the edit dialog (_evaluate). Written in the
        command, never during a compute, which must not write to the feature (SPIKE-6)."""
        for object_id, height in ev.heights.items():
            feature.customNamedValues.addOrSetValue('height_' + object_id, repr(height))

    @staticmethod
    def _join(component: adsk.fusion.Component, base: adsk.fusion.BaseFeature):
        """Add the combine that merges the gear into every body it touches, like
        Extrude does (FEA-6). It is created at the timeline marker."""
        gear = base.bodies.item(0)
        targets = geometry.touching_bodies(component, gear)
        if not targets:
            raise NothingToJoin(NOTHING_TO_JOIN)   # VAL-12
        tools = adsk.core.ObjectCollection.create()
        tools.add(gear)
        for other in targets[1:]:
            tools.add(other)
        combine = component.features.combineFeatures.createInput(targets[0], tools)
        combine.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        return component.features.combineFeatures.add(combine)

    def _change_operation(self, feature: adsk.fusion.CustomFeature, operation: str):
        """Switch an existing gear between New Body and Join (FEA-7). Called with
        the timeline before the feature.

        The features inside a custom feature cannot be reached in the timeline, so
        they are taken out of it, changed, and put back, as Autodesk's manual
        suggests."""
        base = base_feature(feature)
        combines = [f for f in feature.features
                    if f.objectType == adsk.fusion.CombineFeature.classType()]
        feature.setStartAndEndFeatures(None, None)
        last = base
        try:
            if operation == JOIN:
                base.timelineObject.rollTo(False)   # the combine goes right after the base feature
                last = self._join(feature.parentComponent, base)
            else:
                for combine in combines:
                    combine.deleteMe()
        except Exception:
            last = combines[-1] if combines else base   # put it back as it was
            raise
        finally:
            # Regrouping is refused ("Didn't roll editing feature back") unless the
            # marker is before the custom feature again.
            feature.timelineObject.rollTo(True)
            feature.setStartAndEndFeatures(base, last)
        feature.customNamedValues.addOrSetValue('operation', operation)

    @staticmethod
    def _set_dependencies(feature: adsk.fusion.CustomFeature, curve,
                          train: typing.Optional[layout.Train], objects: dict,
                          keep: typing.Collection[str] = ()):
        """Point the feature at its curve and its start and extent objects (FEA-2) and
        its layout sketch (FEA-12). objects are the objects to set, by id; those in
        keep stay as they are, all others are removed. A dependency can only refer to
        the design as it was before the feature."""
        timeline = design().timeline
        position = timeline.markerPosition
        resume_at = timeline.item(position - 1) if position > 0 else None
        feature.timelineObject.rollTo(True)
        try:
            wanted = {'curve': curve}
            wanted.update({i: e for i, e in objects.items() if e is not None})
            for dep_id, entity in wanted.items():
                # Inside a component, Fusion rejected the native entity ("Invalid
                # argument entity"). Try the entity as it was selected, then the
                # native one, then a proxy through an occurrence of its component.
                candidates = [entity]
                native = geometry.native(entity)
                if native is not entity:
                    candidates.append(native)
                try:
                    occurrences = design().rootComponent.allOccurrencesByComponent(
                        feature.parentComponent)
                    if occurrences.count:
                        candidates.append(native.createForAssemblyContext(occurrences.item(0)))
                except Exception:
                    pass
                error = None
                for candidate in candidates:
                    try:
                        existing = feature.dependencies.itemById(dep_id)
                        if existing:
                            existing.entity = candidate
                        else:
                            feature.dependencies.add(dep_id, candidate)
                        error = None
                        break
                    except RuntimeError as e:
                        error = e
                if error is not None:
                    raise error
            # 'mate' is left over from the unreleased Mesh with version.
            stale = ['mate'] + (['layout'] if train is None or train.own_sketch else [])
            stale += [i for i in OBJECT_INPUTS if i not in wanted and i not in keep]
            for dep_id in stale:
                existing = feature.dependencies.itemById(dep_id)
                if existing:
                    existing.deleteMe()
            if train is not None and not train.own_sketch:
                sketch = train.sketch
                if train.occurrence is not None:
                    sketch = sketch.createForAssemblyContext(train.occurrence)
                try:
                    existing = feature.dependencies.itemById('layout')
                    if existing:
                        existing.entity = sketch
                    else:
                        feature.dependencies.add('layout', sketch)
                except RuntimeError as e:
                    # Not essential: a change in the layout sketch recomputes the gear
                    # through its projected curve anyway (SPIKE-8).
                    log('layout sketch dependency of {} refused: {}'.format(feature.name, e))
        finally:
            if resume_at is not None:
                resume_at.rollTo(False)

    def _apply_edit(self, feature: adsk.fusion.CustomFeature, settings: Settings):
        """Change an existing gear. The feature can only be changed while the
        timeline is before it; the marker is put back afterwards, all within the
        command's transaction, so one Undo reverts the whole edit (UI-6)."""
        timeline = design().timeline
        position = timeline.markerPosition
        resume_at = timeline.item(position - 1) if position > 0 else None
        feature.timelineObject.rollTo(True)
        try:
            for pid, _, _, _ in PARAMS:
                parameter = parameter_of(feature, pid)
                if parameter is not None:   # FEA-5: missing on gears made before it existed
                    parameter.expression = settings.expressions[pid]
            self._store_extent(feature, settings.extent)
            feature.customNamedValues.addOrSetValue('auto_teeth', '1' if settings.auto_teeth else '0')
            needed = settings.extent.needed()
            keep = {i for i in needed if self._keeps_object(settings, i)}
            objects = {i: settings.extent.objects.get(i) for i in needed if i not in keep}
            self._set_dependencies(feature, settings.curve, self._evaluate(settings).train,
                                   objects, keep)
            self._store_heights(feature, self._recompute(feature))
            if settings.operation != feature.customNamedValues.value('operation'):
                self._change_operation(feature, settings.operation)
        finally:
            if resume_at is not None:
                resume_at.rollTo(False)

    def _recompute(self, feature: adsk.fusion.CustomFeature) -> Evaluation:
        """Rebuild the gear body from the feature's curve and parameters (FEA-2, FEA-4)."""
        dependency = feature.dependencies.itemById('curve')
        curve = dependency.entity if dependency else None
        if curve is None or not curve.isValid:
            raise gearcore.GearError('The curve of {} no longer exists.'.format(feature.name))
        values = {pid: parameter_value(feature, pid, kind, default) for pid, _, kind, default in PARAMS}
        # Gears made before IN-30 existed have no automatic extra teeth (D-37).
        ev = evaluate(curve, values, (feature.parentComponent, feature_occurrence(feature)),
                      stored_extent(feature), auto_teeth=named_value(feature, 'auto_teeth', '0') == '1')
        if ev.outline is None:
            raise gearcore.GearError('; '.join(
                i.message for i in ev.issues if i.severity == gearcore.ERROR))
        base = base_feature(feature)
        component = feature.parentComponent
        base.startEdit()
        try:
            old = geometry.source_bodies(base)[0]
            new = geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness, False)
            base.updateBody(old, adsk.fusion.TemporaryBRepManager.get().copy(new))
            new.deleteMe()
        finally:
            base.finishEdit()
        return ev

    def _on_compute(self, args: adsk.fusion.CustomFeatureEventArgs):
        if self._command is not None:
            return   # our own dialog rebuilds the gear itself
        try:
            self._recompute(args.customFeature)
        except Exception:
            # FEA-8: mark the feature as failed and keep the previous body. Only
            # predefined message ids are accepted; the details go to the log.
            log('recompute of {} failed:\n{}'.format(args.customFeature.name, traceback.format_exc()))
            args.computeStatus.statusMessages.addError('DRPOINT_COMPUTE_FAILED', '')
