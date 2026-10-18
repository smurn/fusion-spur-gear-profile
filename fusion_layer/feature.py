"""The Spur Gear custom feature: create and edit commands, preview, recompute.

Structure follows ARC-3: the gear body lives in a base feature; the custom
feature groups that base feature and, for Join, one combine feature.
"""

import dataclasses
import math
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
NOTHING_TO_JOIN = ('The gear does not touch a body to join to. Use New Body, or move the curve '
                   'onto a body.')

#: Numeric inputs: id, label, kind (length | angle | number), default expression.
#: They are dialog inputs and feature parameters (FEA-5). Never change the ids.
PARAMS = (
    ('module', 'Module', 'length', '1 mm'),
    ('start_offset', 'Start offset', 'length', '0 mm'),
    ('thickness', 'Thickness', 'length', '5 mm'),
    ('bore', 'Bore diameter', 'length', '0 mm'),
    ('rotation', 'Start rotation (% of pitch)', 'number', '0'),
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

app = adsk.core.Application.get()
ui = app.userInterface


def log(message: str):
    app.log('Spur Gear: ' + message)


def design() -> adsk.fusion.Design:
    return adsk.fusion.Design.cast(app.activeProduct)


def find_input(inputs: adsk.core.CommandInputs, input_id: str):
    """A dialog input by id, whether it is at the top level or in the Advanced group."""
    found = inputs.itemById(input_id)
    if found is None:
        group = adsk.core.GroupCommandInput.cast(inputs.itemById('advanced'))
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
        tolerance=mm('tolerance'), thickness=mm('thickness'), bore=mm('bore'))


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
class Settings:
    """What the dialog currently says."""
    curve: typing.Any
    operation: str
    flip: bool
    expressions: dict
    values: dict
    start: str = PROFILE_PLANE   # IN-18
    start_object: typing.Any = None


@dataclasses.dataclass
class Evaluation:
    frame: typing.Optional[geometry.Frame] = None
    params: typing.Optional[gearcore.GearParams] = None
    outline: typing.Optional[gearcore.Outline] = None
    issues: list = dataclasses.field(default_factory=list)
    train: typing.Optional[layout.Train] = None
    object_distance: typing.Optional[float] = None   # cm, from the curve's plane to the start object


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


def evaluate(curve, values: dict, target, start: str = PROFILE_PLANE, start_object=None,
             known_distance: typing.Optional[float] = None) -> Evaluation:
    """Run the gear math for a curve and parameter values. target is the gear's
    component and the occurrence of it (FEA-14); start and start_object are IN-18
    and IN-20. known_distance is the start object's distance from an earlier
    evaluation, used if the object is not valid right now. Never raises for bad
    input."""
    ev = Evaluation()
    if not geometry.is_gear_curve(geometry.native(curve) if curve else None):
        ev.issues.append(gearcore.Issue('VAL-1', gearcore.ERROR, 'Select a sketch circle or arc.'))
        return ev
    try:
        ev.frame = geometry.frame_in(curve, *target)
    except geometry.AmbiguousOccurrence as e:
        ev.issues.append(gearcore.Issue('VAL-24', gearcore.ERROR, str(e)))
        return ev
    if start != PROFILE_PLANE:   # GEO-12: move to the start plane
        distance = values.get('start_offset', 0.0)
        if start == OBJECT:
            if start_object is not None and start_object.isValid:
                try:
                    ev.object_distance = geometry.start_distance(start_object, ev.frame, *target)
                except geometry.AmbiguousOccurrence as e:
                    ev.issues.append(gearcore.Issue('VAL-24', gearcore.ERROR, str(e)))
                    return ev
                except geometry.StartObjectError as e:
                    ev.issues.append(gearcore.Issue('VAL-26', gearcore.ERROR, str(e)))
                    return ev
            elif known_distance is not None:
                # While a Join preview is shown, a face of the body it joins has been
                # replaced, and the selected face is not valid until the preview goes.
                # When editing, the gear keeps its start object without it being
                # selected (_keeps_start_object).
                ev.object_distance = known_distance
            else:
                ev.issues.append(gearcore.Issue('VAL-25', gearcore.ERROR, 'Select the start object.'))
                return ev
            distance += ev.object_distance
        ev.frame = geometry.shifted(ev.frame, distance)
    ev.params = to_gear_params(ev.frame, values)
    ev.issues = gearcore.validate(ev.params)
    if not any(i.severity == gearcore.ERROR for i in ev.issues):
        # The rotation is relative to the curve's own frame, so it holds in the
        # gear's component too (ARC-8).
        ev.train = layout.train_of(curve, geometry.frame_of(curve), ev.params)   # section 7
        if ev.train.rotation is not None:
            ev.params = dataclasses.replace(ev.params, rotation=ev.train.rotation)
            # Which teeth of an arc are generated depends on the rotation (VAL-6).
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
        lines.append('Reference {:.3f} / base {:.3f} mm'.format(d.reference_diameter, d.base_diameter))
        lines.append('Tip {:.3f} / root {:.3f} mm'.format(d.tip_diameter, d.root_diameter))
        if d.tip_thickness is not None:
            lines.append('Tooth thickness {:.3f}, at the tip {:.3f} mm'.format(
                d.tooth_thickness, d.tip_thickness))
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
        self._handlers = []          # kept for the lifetime of the add-in
        self._command_handlers = []  # kept while a dialog is open
        self._command = None
        self._editing: typing.Optional[adsk.fusion.CustomFeature] = None
        #: Settings of the last gear created, to start the next one with (UI-7).
        #: Kept in memory only.
        self._last_used: dict = {}
        #: The start object's distance from the last evaluation where it was valid.
        self._object_distance: typing.Optional[float] = None
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
        self._object_distance = None
        self._start_object_changed = False
        self._logged = set()
        inputs = command.commandInputs
        feature = self._editing

        curve = inputs.addSelectionInput('curve', 'Circle or arc', 'Select a sketch circle or arc')
        curve.addSelectionFilter('SketchCurves')
        curve.setSelectionLimits(1, 1)

        operation = inputs.addDropDownCommandInput(
            'operation', 'Operation', adsk.core.DropDownStyles.TextListDropDownStyle)
        if feature:
            current = feature.customNamedValues.value('operation')
            flip = feature.customNamedValues.value('flip') == '1'
        else:
            current = self._last_used.get('operation', NEW_BODY)
            flip = self._last_used.get('flip', False)
        for name in (NEW_BODY, JOIN):
            operation.listItems.add(name, name == current)
        start = named_value(feature, 'start', PROFILE_PLANE) if feature else \
            self._last_used.get('start', PROFILE_PLANE)

        # The common inputs first, the rarely changed ones in a group that is only
        # open if one of them is not at its default (UI-8).
        advanced = []
        for pid, label, kind, default in PARAMS:
            if pid in ADVANCED:
                advanced.append((pid, label, kind, default))
                continue
            if pid == 'start_offset':   # UI-10: Start comes right before Thickness
                choice = inputs.addDropDownCommandInput(
                    'start', 'Start', adsk.core.DropDownStyles.TextListDropDownStyle)
                for name in (PROFILE_PLANE, OFFSET, OBJECT):
                    choice.listItems.add(name, name == start)
            value_input = inputs.addValueInput(pid, label, unit(kind), self._initial(pid, kind, default)[0])
            if pid == 'start_offset':
                if feature and parameter_of(feature, pid) is None:
                    value_input.isEnabled = False   # FEA-5
                    value_input.tooltip = ('This gear was made before the start offset existed. '
                                           'Create it again to use one.')
                start_object = inputs.addSelectionInput(
                    'start_object', 'Start object', 'Select a planar face, construction plane or point')
                for name in ('PlanarFaces', 'ConstructionPlanes', 'Vertices', 'SketchPoints',
                             'ConstructionPoints'):
                    start_object.addSelectionFilter(name)
                start_object.setSelectionLimits(0, 1)
            if pid == 'bore':
                inputs.addBoolValueInput('flip', 'Flip side', True, '', flip)
        group = inputs.addGroupCommandInput('advanced', 'Advanced')
        changed = False
        for pid, label, kind, default in advanced:
            value, differs = self._initial(pid, kind, default)
            group.children.addValueInput(pid, label, unit(kind), value)
            changed = changed or differs
        group.isExpanded = changed
        inputs.addTextBoxCommandInput('info', '', '', 7, True)
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
            return by_string(parameter.expression), abs(parameter.value - standard) > 1e-9
        if pid in self._last_used.get('params', {}):
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
        expressions, values = {}, {}
        for pid, _, _, _ in PARAMS:
            value_input = adsk.core.ValueCommandInput.cast(find_input(inputs, pid))
            if not value_input.isValidExpression:
                return None
            expressions[pid], values[pid] = value_input.expression, value_input.value
        curve_input = adsk.core.SelectionCommandInput.cast(inputs.itemById('curve'))
        operation = adsk.core.DropDownCommandInput.cast(inputs.itemById('operation')).selectedItem.name
        curve = curve_input.selection(0).entity if curve_input.selectionCount else None
        flip = adsk.core.BoolValueCommandInput.cast(inputs.itemById('flip')).value
        start = adsk.core.DropDownCommandInput.cast(inputs.itemById('start')).selectedItem.name
        object_input = adsk.core.SelectionCommandInput.cast(inputs.itemById('start_object'))
        start_object = object_input.selection(0).entity if object_input.selectionCount else None
        return Settings(curve, operation, flip, expressions, values, start, start_object)

    def _evaluate(self, settings: Settings) -> Evaluation:
        known = self._object_distance
        if known is None and self._keeps_start_object(settings):
            # Where the gear started when it was last created or edited; good enough
            # for the dialog's checks. The gear itself is built from the object.
            stored = named_value(self._editing, 'start_distance', '')
            known = float(stored) if stored else 0.0
        ev = evaluate(settings.curve, settings.values, self._target(), settings.start,
                      settings.start_object, known)
        if settings.start_object is not None and settings.start_object.isValid:
            self._object_distance = ev.object_distance
        return ev

    def _keeps_start_object(self, settings: Settings) -> bool:
        """Whether an edited gear keeps the start object it has. The edit dialog does
        not select it: a face of a body the gear joins exists only before the join,
        at the gear's place in the timeline, and selecting a face that a preview
        replaces disables OK (CHK-9). Picking an object replaces it."""
        if not (self._editing and settings.start == OBJECT and settings.start_object is None):
            return False
        return not self._start_object_changed and bool(self._editing.dependencies.itemById('start_object'))

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
            ev.frame, gearcore.derive(ev.params).tip_diameter / 2, ev.params.thickness, settings.flip)
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
            # UI-10: show only what the chosen start needs.
            find_input(inputs, 'start_offset').isVisible = settings.start != PROFILE_PLANE
            inputs.itemById('start_object').isVisible = settings.start == OBJECT
            if self._keeps_start_object(settings):
                text += '<br/>Start object: as before. Pick another one to change it.'
        if note:
            text += '<br/><b>Error:</b> ' + note
        adsk.core.TextBoxCommandInput.cast(inputs.itemById('info')).formattedText = text

    def _on_input_changed(self, args: adsk.core.InputChangedEventArgs):
        if args.input.id == 'start_object':
            self._object_distance = None
            self._start_object_changed = True
        if args.input.id != 'info':
            self._update_dialog(self._command.commandInputs)

    def _on_pre_select(self, args: adsk.core.SelectionEventArgs):
        if args.activeInput.id == 'curve':
            args.isSelectable = geometry.is_gear_curve(geometry.native(args.selection.entity))
        elif args.activeInput.id == 'start_object':
            args.isSelectable = geometry.is_start_object(args.selection.entity)

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
        # The start object is not selected; see _keeps_start_object.

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
            if settings.operation == JOIN and adsk.fusion.BRepFace.cast(self._start_object(settings)):
                # Joining in the preview replaces the faces of the joined body, and Fusion
                # then disables OK because the selected start face is no longer valid.
                # The preview shows the gear as its own body; OK joins it (CHK-9).
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
                    'operation': settings.operation, 'flip': settings.flip, 'start': settings.start,
                    'params': {pid: (settings.expressions[pid], settings.values[pid])
                               for pid, _, _, _ in PARAMS}}
        except NothingToJoin as e:
            ui.messageBox(str(e), NAME)

    # --------------------------------------------------------------- feature --
    def _create(self, settings: Settings) -> typing.Optional[adsk.fusion.CustomFeature]:
        component, occurrence = self._target()
        ev = evaluate(settings.curve, settings.values, (component, occurrence), settings.start,
                      settings.start_object)
        if ev.outline is None:
            return None
        features = component.features

        base = features.baseFeatures.add()
        base.startEdit()
        try:
            geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness,
                                settings.flip)
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
        feature.customNamedValues.addOrSetValue('flip', '1' if settings.flip else '0')
        feature.customNamedValues.addOrSetValue('operation', settings.operation)
        feature.customNamedValues.addOrSetValue('occurrence', occurrence.entityToken if occurrence else '')
        feature.customNamedValues.addOrSetValue('start', settings.start)
        self._store_start_distance(feature, ev)
        self._set_dependencies(feature, settings.curve, ev.train, self._start_object(settings))
        return feature

    @staticmethod
    def _store_start_distance(feature: adsk.fusion.CustomFeature, ev: Evaluation):
        """For the edit dialog (_evaluate). Written in the command, never during a
        compute, which must not write to the feature (SPIKE-6)."""
        if ev.object_distance is not None:
            feature.customNamedValues.addOrSetValue('start_distance', repr(ev.object_distance))

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
    def _start_object(settings: Settings):
        return settings.start_object if settings.start == OBJECT else None

    @staticmethod
    def _set_dependencies(feature: adsk.fusion.CustomFeature, curve,
                          train: typing.Optional[layout.Train], start_object=None,
                          keep_start_object: bool = False):
        """Point the feature at its curve and start object (FEA-2) and its layout
        sketch (FEA-12). A dependency can only refer to the design as it was before
        the feature."""
        timeline = design().timeline
        position = timeline.markerPosition
        resume_at = timeline.item(position - 1) if position > 0 else None
        feature.timelineObject.rollTo(True)
        try:
            wanted = {'curve': curve}
            if start_object is not None:
                wanted['start_object'] = start_object
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
            stale += [] if start_object is not None or keep_start_object else ['start_object']
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
            feature.customNamedValues.addOrSetValue('flip', '1' if settings.flip else '0')
            feature.customNamedValues.addOrSetValue('start', settings.start)
            keep = self._keeps_start_object(settings)
            self._set_dependencies(feature, settings.curve, self._evaluate(settings).train,
                                   None if keep else self._start_object(settings), keep)
            self._store_start_distance(feature, self._recompute(feature))
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
        start = named_value(feature, 'start', PROFILE_PLANE)
        dependency = feature.dependencies.itemById('start_object')
        start_object = dependency.entity if dependency else None
        ev = evaluate(curve, values, (feature.parentComponent, feature_occurrence(feature)), start,
                      start_object)
        if ev.outline is None:
            raise gearcore.GearError('; '.join(
                i.message for i in ev.issues if i.severity == gearcore.ERROR))
        flip = feature.customNamedValues.value('flip') == '1'
        base = base_feature(feature)
        component = feature.parentComponent
        base.startEdit()
        try:
            old = geometry.source_bodies(base)[0]
            new = geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness, flip)
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
