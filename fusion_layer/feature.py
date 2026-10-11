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
from . import geometry
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

#: Numeric inputs: id, label, kind (length | angle | number), default expression.
#: They are dialog inputs and feature parameters (FEA-5). Never change the ids.
PARAMS = (
    ('module', 'Module', 'length', '1 mm'),
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

app = adsk.core.Application.get()
ui = app.userInterface


def log(message: str):
    app.log('Spur Gear: ' + message)


def design() -> adsk.fusion.Design:
    return adsk.fusion.Design.cast(app.activeProduct)


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


@dataclasses.dataclass
class Settings:
    """What the dialog currently says."""
    curve: typing.Any
    target: typing.Any
    operation: str
    flip: bool
    expressions: dict
    values: dict


@dataclasses.dataclass
class Evaluation:
    frame: typing.Optional[geometry.Frame] = None
    params: typing.Optional[gearcore.GearParams] = None
    outline: typing.Optional[gearcore.Outline] = None
    issues: list = dataclasses.field(default_factory=list)


def evaluate(curve, values: dict) -> Evaluation:
    """Run the gear math for a curve and parameter values. Never raises for bad input."""
    ev = Evaluation()
    if not geometry.is_gear_curve(geometry.native(curve) if curve else None):
        ev.issues.append(gearcore.Issue('VAL-1', gearcore.ERROR, 'Select a sketch circle or arc.'))
        return ev
    ev.frame = geometry.frame_of(curve)
    ev.params = to_gear_params(ev.frame, values)
    ev.issues = gearcore.validate(ev.params)
    if not any(i.severity == gearcore.ERROR for i in ev.issues):
        try:
            ev.outline = gearcore.gear_outline(ev.params)
        except NotImplementedError as e:
            ev.issues.append(gearcore.Issue('TODO', gearcore.ERROR, 'Not supported yet: {}.'.format(e)))
        except gearcore.GearError as e:
            ev.issues.append(gearcore.Issue('GEO', gearcore.ERROR, str(e)))
    return ev


def info_text(ev: Evaluation) -> str:
    lines = []
    if ev.params:
        d = gearcore.derive(ev.params)
        lines.append('<b>{} teeth</b>, selected diameter {:.3f} mm'.format(d.teeth, ev.params.diameter))
        lines.append('Reference {:.3f} / base {:.3f} mm'.format(d.reference_diameter, d.base_diameter))
        lines.append('Tip {:.3f} / root {:.3f} mm'.format(d.tip_diameter, d.root_diameter))
        if d.tip_thickness is not None:
            lines.append('Tooth thickness {:.3f}, at the tip {:.3f} mm'.format(
                d.tooth_thickness, d.tip_thickness))
    for issue in ev.issues:
        lines.append('<b>{}:</b> {}'.format(issue.severity.capitalize(), issue.message))
    return '<br/>'.join(lines)


class SpurGearFeature:
    def __init__(self, resources: str):
        self._handlers = []          # kept for the lifetime of the add-in
        self._command_handlers = []  # kept while a dialog is open
        self._command = None
        self._editing: typing.Optional[adsk.fusion.CustomFeature] = None
        self._resume_at = None       # timeline object to return to after an edit
        self._fusion_rolls_timeline = False

        for cid, callback in ((CREATE_ID, self._on_create_created), (EDIT_ID, self._on_edit_created)):
            old = ui.commandDefinitions.itemById(cid)
            if old:
                old.deleteMe()
            definition = ui.commandDefinitions.addButtonDefinition(cid, NAME, TOOLTIP, resources)
            self._listen(definition.commandCreated, adsk.core.CommandCreatedEventHandler, callback,
                         self._handlers)

        self._definition = adsk.fusion.CustomFeatureDefinition.create(FEATURE_ID, NAME, resources)
        self._definition.editCommandId = EDIT_ID
        log('registered feature {!r}, edit command {!r} (exists: {})'.format(
            self._definition.id, self._definition.editCommandId,
            ui.commandDefinitions.itemById(EDIT_ID) is not None))
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
        log('edit command started, {} entities selected'.format(ui.activeSelections.count))
        feature = adsk.fusion.CustomFeature.cast(ui.activeSelections.item(0).entity)
        if feature is None:
            raise RuntimeError('Select a Spur Gear feature to edit.')
        self._editing = feature
        # Let Fusion roll the timeline to the feature while the dialog is open and
        # restore it afterwards. Rolling it ourselves (rollTo plus beginStep) worked
        # but left Undo with an extra step that only moved the timeline marker.
        self._fusion_rolls_timeline = False
        try:
            args.command.editingFeature = feature
            self._fusion_rolls_timeline = True
        except Exception:
            log('editingFeature is not available, rolling the timeline manually')
        self._build_dialog(args.command)

    def _build_dialog(self, command: adsk.core.Command):
        self._command = command
        inputs = command.commandInputs
        feature = self._editing

        curve = inputs.addSelectionInput('curve', 'Circle or arc', 'Select a sketch circle or arc')
        curve.addSelectionFilter('SketchCurves')
        curve.setSelectionLimits(1, 1)

        operation = inputs.addDropDownCommandInput(
            'operation', 'Operation', adsk.core.DropDownStyles.TextListDropDownStyle)
        current = feature.customNamedValues.value('operation') if feature else NEW_BODY
        for name in (NEW_BODY, JOIN):
            operation.listItems.add(name, name == current)
        target = inputs.addSelectionInput('target', 'Target body', 'Select the body to join to')
        target.addSelectionFilter('SolidBodies')
        if feature:
            # Not yet editable: changing them means restructuring the feature.
            operation.isEnabled = False
            target.isVisible = False
            target.setSelectionLimits(0, 1)

        flip = feature.customNamedValues.value('flip') == '1' if feature else False
        inputs.addBoolValueInput('flip', 'Flip side', True, '', flip)
        for pid, label, kind, default in PARAMS:
            expression = feature.parameters.itemById(pid).expression if feature else default
            inputs.addValueInput(pid, label, unit(kind), adsk.core.ValueInput.createByString(expression))
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

    def _read(self, inputs: adsk.core.CommandInputs) -> typing.Optional[Settings]:
        """The dialog's current settings, or None while a value cannot be evaluated."""
        expressions, values = {}, {}
        for pid, _, _, _ in PARAMS:
            value_input = adsk.core.ValueCommandInput.cast(inputs.itemById(pid))
            if not value_input.isValidExpression:
                return None
            expressions[pid], values[pid] = value_input.expression, value_input.value
        curve_input = adsk.core.SelectionCommandInput.cast(inputs.itemById('curve'))
        target_input = adsk.core.SelectionCommandInput.cast(inputs.itemById('target'))
        operation = adsk.core.DropDownCommandInput.cast(inputs.itemById('operation')).selectedItem.name
        curve = curve_input.selection(0).entity if curve_input.selectionCount else None
        target = None
        if operation == JOIN:
            if self._editing:
                target = self._stored_target(self._editing)
            elif target_input.selectionCount:
                target = target_input.selection(0).entity
        flip = adsk.core.BoolValueCommandInput.cast(inputs.itemById('flip')).value
        return Settings(curve, target, operation, flip, expressions, values)

    @staticmethod
    def _stored_target(feature: adsk.fusion.CustomFeature):
        """The body a Join gear was joined to, as it is at the current timeline position."""
        try:
            token = feature.customNamedValues.value('target')
            for entity in design().findEntityByToken(token) if token else []:
                body = adsk.fusion.BRepBody.cast(entity)
                if body and body.isValid:
                    return body
        except Exception:
            log('target body lookup failed:\n' + traceback.format_exc())
        return None

    def _update_dialog(self, inputs: adsk.core.CommandInputs):
        settings = self._read(inputs)
        if not self._editing:
            target = adsk.core.SelectionCommandInput.cast(inputs.itemById('target'))
            join = settings is not None and settings.operation == JOIN
            target.isVisible = join
            target.setSelectionLimits(1 if join else 0, 1)
            if not join:
                target.clearSelection()
        text = 'Enter valid values.'
        if settings is not None:
            text = info_text(evaluate(settings.curve, settings.values))
            if settings.operation == JOIN and settings.target is None:   # VAL-12
                text += '<br/><b>Error:</b> Select the body to join to.'
        adsk.core.TextBoxCommandInput.cast(inputs.itemById('info')).formattedText = text

    def _on_input_changed(self, args: adsk.core.InputChangedEventArgs):
        if args.input.id == 'info':
            return
        inputs = self._command.commandInputs
        self._update_dialog(inputs)
        if args.input.id == 'operation' and not self._editing:
            # Picking Join should let the user click the body right away; otherwise
            # clicks keep going to the curve selection.
            target = adsk.core.SelectionCommandInput.cast(inputs.itemById('target'))
            if target.isVisible:
                target.hasFocus = True

    def _on_pre_select(self, args: adsk.core.SelectionEventArgs):
        if args.activeInput.id == 'curve':
            args.isSelectable = geometry.is_gear_curve(geometry.native(args.selection.entity))

    def _on_validate(self, args: adsk.core.ValidateInputsEventArgs):
        settings = self._read(args.inputs)
        args.areInputsValid = (
            settings is not None
            and (settings.operation == NEW_BODY or settings.target is not None)   # VAL-12
            and evaluate(settings.curve, settings.values).outline is not None)    # UI-5

    def _on_activate(self, args: adsk.core.CommandEventArgs):
        """Edit only: show the design as it was before the feature and select its curve."""
        timeline = design().timeline
        position = timeline.markerPosition
        log('edit activated: marker at {} of {}, feature at {}, Fusion rolls the timeline: {}'.format(
            position, timeline.count, self._editing.timelineObject.index, self._fusion_rolls_timeline))
        if not self._fusion_rolls_timeline:
            self._resume_at = timeline.item(position - 1) if position > 0 else None
            self._editing.timelineObject.rollTo(True)
            args.command.beginStep()
        dependency = self._editing.dependencies.itemById('curve')
        if dependency and dependency.entity:
            selection = adsk.core.SelectionCommandInput.cast(
                args.command.commandInputs.itemById('curve'))
            if not selection.addSelection(dependency.entity):
                log('could not select the curve of ' + self._editing.name)

    def _on_destroy(self, args: adsk.core.CommandEventArgs):
        try:
            if self._resume_at is not None:
                self._resume_at.rollTo(False)
        finally:
            self._resume_at = None
            self._command = None
            self._command_handlers = []
            self._editing = None

    def _on_preview(self, args: adsk.core.CommandEventArgs):
        # A new feature in both modes: while editing, the timeline is rolled back to
        # before the edited feature, so the preview takes its place. Fusion undoes it.
        settings = self._read(args.command.commandInputs)
        if settings is not None:
            if self._editing:
                log('edit preview: marker at {}, feature at {}'.format(
                    design().timeline.markerPosition, self._editing.timelineObject.index))
            self._create(settings)
            # Without this the preview stays invisible after the inputs were
            # invalid for a moment, until the mouse moves over it.
            app.activeViewport.refresh()

    def _on_execute(self, args: adsk.core.CommandEventArgs):
        settings = self._read(args.command.commandInputs)
        if settings is None:
            raise RuntimeError('The inputs are not valid.')
        if self._editing:
            self._apply_edit(self._editing, settings)
        else:
            self._create(settings)

    # --------------------------------------------------------------- feature --
    def _create(self, settings: Settings) -> typing.Optional[adsk.fusion.CustomFeature]:
        ev = evaluate(settings.curve, settings.values)
        if ev.outline is None or (settings.operation == JOIN and settings.target is None):
            log('create skipped: outline {}, operation {}, target {}'.format(
                ev.outline is not None, settings.operation, settings.target is not None))
            return None
        component = geometry.native(settings.curve).parentSketch.parentComponent
        features = component.features
        timeline = design().timeline
        log('create {} in {!r}: design intent {}, marker {} of {}'.format(
            settings.operation, component.name, design().designIntent, timeline.markerPosition,
            timeline.count))

        base = features.baseFeatures.add()
        base.startEdit()
        try:
            geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness,
                                settings.flip)
        finally:
            base.finishEdit()
        log('  base feature has {} bodies, solid: {}'.format(
            base.bodies.count, [base.bodies.item(i).isSolid for i in range(base.bodies.count)]))
        last = base
        if settings.operation == JOIN:
            target = geometry.native(settings.target)
            tools = adsk.core.ObjectCollection.create()
            tools.add(base.bodies.item(0))
            combine = features.combineFeatures.createInput(target, tools)
            combine.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            last = features.combineFeatures.add(combine)
            log('  combine into {!r}: health {} {!r}, component has {} bodies'.format(
                target.name, last.healthState, last.errorOrWarningMessage,
                component.bRepBodies.count))

        inp = features.customFeatures.createInput(self._definition)
        for pid, label, kind, _ in PARAMS:
            inp.addCustomParameter(pid, label, adsk.core.ValueInput.createByString(
                settings.expressions[pid]), unit(kind), True)
        inp.setStartAndEndFeatures(base, last)
        feature = features.customFeatures.add(inp)
        feature.customNamedValues.addOrSetValue('flip', '1' if settings.flip else '0')
        feature.customNamedValues.addOrSetValue('operation', settings.operation)
        self._set_dependencies(feature, settings)
        log('  {} created: health {} {!r}, {} dependencies, marker {} of {}'.format(
            feature.name, feature.healthState, feature.errorOrWarningMessage,
            feature.dependencies.count, timeline.markerPosition, timeline.count))
        return feature

    @staticmethod
    def _set_dependencies(feature: adsk.fusion.CustomFeature, settings: Settings):
        """Point the feature at its curve (FEA-2) and, for Join, its target body.
        Dependencies can only refer to the design as it was before the feature."""
        timeline = design().timeline
        position = timeline.markerPosition
        resume_at = timeline.item(position - 1) if position > 0 else None
        feature.timelineObject.rollTo(True)
        try:
            # The target body is not a dependency: the combine feature already
            # refers to it, and the gear would depend on the body it modifies. Its
            # token is kept so the edit dialog can find the body as it was before
            # the gear.
            if settings.operation == JOIN and settings.target is not None:
                feature.customNamedValues.addOrSetValue(
                    'target', geometry.native(settings.target).entityToken)
            wanted = {'curve': settings.curve}
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
        finally:
            if resume_at is not None:
                resume_at.rollTo(False)

    def _apply_edit(self, feature: adsk.fusion.CustomFeature, settings: Settings):
        for pid, _, _, _ in PARAMS:
            feature.parameters.itemById(pid).expression = settings.expressions[pid]
        feature.customNamedValues.addOrSetValue('flip', '1' if settings.flip else '0')
        self._set_dependencies(feature, settings)
        self._recompute(feature)

    def _recompute(self, feature: adsk.fusion.CustomFeature):
        """Rebuild the gear body from the feature's curve and parameters (FEA-2, FEA-4)."""
        dependency = feature.dependencies.itemById('curve')
        curve = dependency.entity if dependency else None
        if curve is None or not curve.isValid:
            raise gearcore.GearError('The curve of {} no longer exists.'.format(feature.name))
        values = {pid: feature.parameters.itemById(pid).value for pid, _, _, _ in PARAMS}
        ev = evaluate(curve, values)
        if ev.outline is None:
            raise gearcore.GearError('; '.join(
                i.message for i in ev.issues if i.severity == gearcore.ERROR))
        flip = feature.customNamedValues.value('flip') == '1'
        base = next(f for f in feature.features
                    if f.objectType == adsk.fusion.BaseFeature.classType())
        component = feature.parentComponent
        base.startEdit()
        try:
            old = geometry.source_bodies(base)[0]
            new = geometry.build_body(component, base, ev.frame, ev.outline, ev.params.thickness, flip)
            base.updateBody(old, adsk.fusion.TemporaryBRepManager.get().copy(new))
            new.deleteMe()
        finally:
            base.finishEdit()

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
