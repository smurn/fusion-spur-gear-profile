"""Spur Gear add-in for Autodesk Fusion.

Adds "Spur Gear" to SOLID > CREATE. It turns a sketch circle or arc into a solid
involute spur gear that stays attached to that curve. See docs/spec.md.
"""

import os
import sys
import traceback

import adsk.core

_feature = None


def run(context):
    global _feature
    try:
        # Fusion keeps modules loaded between runs. Drop ours so that edited code
        # is picked up when the add-in is stopped and started again.
        if __package__:
            for name in [n for n in sys.modules if n.startswith(__package__ + '.')]:
                del sys.modules[name]
        from .fusion_layer import feature

        # Custom features must only be created after run() has returned (ARC-4).
        # Here only the feature type and its commands are registered.
        resources = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
        _feature = feature.SpurGearFeature(resources)
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Spur Gear failed to start:\n{}'.format(traceback.format_exc()))


def stop(context):
    global _feature
    try:
        if _feature:
            _feature.close()
        _feature = None
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Spur Gear failed to stop:\n{}'.format(traceback.format_exc()))
