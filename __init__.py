bl_info = {
    "name": "Head-Tracked View Assist",
    "author": "IndoorDragon (indoordragon.com | github.com/indoordragon)",
    "version": (0, 1, 7),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > View Assist",
    "description": "Webcam head-tracking driven viewport assist via UDP (bundled tracker executable).",
    "warning": "",
    "doc_url": "https://github.com/indoordragon",
    "category": "3D View",
}

import atexit
import bpy
from bpy.app.handlers import persistent

from .props import HTVA_Props
from .operators import (
    HTVA_OT_use_this_viewport,
    HTVA_OT_start,
    HTVA_OT_stop,
    HTVA_OT_toggle,
    HTVA_OT_launch_tracker,
    HTVA_OT_launch_tracker_bg,
    HTVA_OT_stop_tracker,
    htva_stop_tracker_on_exit,  # NEW: exit cleanup
)
from .ui import HTVA_PT_panel
from .prefs import (
    HTVA_AddonPreferences,
    HTVA_OT_apply_defaults_to_scene,
    HTVA_OT_save_scene_as_defaults,
)

_addon_keymaps = []
_atexit_registered = False


def _get_prefs_safe():
    """Safe preferences lookup (works even when context is restricted)."""
    try:
        prefs = bpy.context.preferences
        addon = prefs.addons.get(__package__) if prefs else None
        return addon.preferences if addon else None
    except Exception:
        return None


def apply_prefs_to_scene(scene):
    prefs = _get_prefs_safe()
    if prefs is None or scene is None or not hasattr(scene, "htva_props"):
        return

    p = scene.htva_props
    p.yaw_strength_deg = prefs.default_yaw
    p.pitch_strength_deg = prefs.default_pitch
    p.zoom_strength = prefs.default_zoom
    p.min_distance = prefs.default_min_dist
    p.max_distance = prefs.default_max_dist
    p.smoothing_alpha = prefs.default_alpha
    p.deadzone = prefs.default_deadzone


def _scene_looks_like_stock_defaults(scene) -> bool:
    if scene is None or not hasattr(scene, "htva_props"):
        return False

    p = scene.htva_props
    return (
        abs(p.yaw_strength_deg - 25.0) < 1e-6 and
        abs(p.pitch_strength_deg - 25.0) < 1e-6 and
        abs(p.zoom_strength - 2.0) < 1e-6 and
        abs(p.min_distance - 0.2) < 1e-6 and
        abs(p.max_distance - 20.0) < 1e-6 and
        abs(p.smoothing_alpha - 0.2) < 1e-6 and
        abs(p.deadzone - 0.03) < 1e-6
    )


@persistent
def _htva_apply_defaults_on_load(_dummy):
    """
    Apply saved defaults after a file loads (when Blender has a real scene context).
    Only applies if the scene is still at stock defaults.
    """
    try:
        scene = getattr(bpy.context, "scene", None)
        if scene and _scene_looks_like_stock_defaults(scene):
            apply_prefs_to_scene(scene)
    except Exception:
        pass


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')

    # Toggle View Assist (existing)
    kmi = km.keymap_items.new("htva.toggle", type='Q', value='PRESS', alt=True, shift=True)
    _addon_keymaps.append((km, kmi))

    # Launch Tracker (Background) (new)
    # Default: Alt+Shift+W
    kmi = km.keymap_items.new("htva.launch_tracker_bg", type='W', value='PRESS', alt=True, shift=True)
    _addon_keymaps.append((km, kmi))

    # Stop Tracker (new)
    # Default: Alt+Shift+S
    kmi = km.keymap_items.new("htva.stop_tracker", type='S', value='PRESS', alt=True, shift=True)
    _addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in _addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _addon_keymaps.clear()


classes = (
    HTVA_Props,
    HTVA_OT_launch_tracker,
    HTVA_OT_launch_tracker_bg,
    HTVA_OT_stop_tracker,
    HTVA_OT_use_this_viewport,
    HTVA_OT_start,
    HTVA_OT_stop,
    HTVA_OT_toggle,
    HTVA_PT_panel,
    HTVA_OT_apply_defaults_to_scene,
    HTVA_OT_save_scene_as_defaults,
    HTVA_AddonPreferences,
)


def register():
    global _atexit_registered

    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.htva_props = bpy.props.PointerProperty(type=HTVA_Props)

    register_keymaps()

    if _htva_apply_defaults_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_htva_apply_defaults_on_load)

    # NEW: Ensure tracker stops when Blender exits.
    # We guard so it doesn't get registered multiple times during reload/dev.
    if not _atexit_registered:
        try:
            atexit.register(htva_stop_tracker_on_exit)
            _atexit_registered = True
        except Exception:
            pass


def unregister():
    global _atexit_registered

    unregister_keymaps()

    if _htva_apply_defaults_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_htva_apply_defaults_on_load)

    # NEW: If user disables/uninstalls the add-on, stop the tracker immediately too.
    try:
        htva_stop_tracker_on_exit()
    except Exception:
        pass

    # NEW: Unregister exit hook (helps during add-on reloads in development).
    if _atexit_registered:
        try:
            atexit.unregister(htva_stop_tracker_on_exit)
        except Exception:
            pass
        _atexit_registered = False

    del bpy.types.Scene.htva_props

    for c in reversed(classes):
        bpy.utils.unregister_class(c)
