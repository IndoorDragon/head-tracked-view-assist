import bpy
from bpy.props import FloatProperty
from bpy.types import Operator


def get_addon_prefs(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


class HTVA_OT_apply_defaults_to_scene(Operator):
    bl_idname = "htva.apply_defaults_to_scene"
    bl_label = "Apply Defaults to Scene"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        prefs = get_addon_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, "Add-on preferences not available.")
            return {'CANCELLED'}

        p = context.scene.htva_props
        p.yaw_strength_deg = prefs.default_yaw
        p.pitch_strength_deg = prefs.default_pitch
        p.zoom_strength = prefs.default_zoom
        p.min_distance = prefs.default_min_dist
        p.max_distance = prefs.default_max_dist
        p.smoothing_alpha = prefs.default_alpha
        p.deadzone = prefs.default_deadzone

        self.report({'INFO'}, "Applied defaults to current scene.")
        return {'FINISHED'}


class HTVA_OT_save_scene_as_defaults(Operator):
    bl_idname = "htva.save_scene_as_defaults"
    bl_label = "Save Current Scene as Defaults"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        prefs = get_addon_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, "Add-on preferences not available.")
            return {'CANCELLED'}

        p = context.scene.htva_props
        prefs.default_yaw = p.yaw_strength_deg
        prefs.default_pitch = p.pitch_strength_deg
        prefs.default_zoom = p.zoom_strength
        prefs.default_min_dist = p.min_distance
        prefs.default_max_dist = p.max_distance
        prefs.default_alpha = p.smoothing_alpha
        prefs.default_deadzone = p.deadzone

        self.report({'INFO'}, "Saved. Now click 'Save Preferences' in Blender Preferences.")
        return {'FINISHED'}


class HTVA_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_yaw: FloatProperty(name="Default Yaw (deg)", default=25.0, min=0.0, max=100.0)
    default_pitch: FloatProperty(name="Default Pitch (deg)", default=25.0, min=0.0, max=100.0)
    default_zoom: FloatProperty(name="Default Zoom Strength", default=2.0, min=0.0, max=20.0)
    default_min_dist: FloatProperty(name="Default Min Distance", default=0.2, min=0.001, max=1000.0)
    default_max_dist: FloatProperty(name="Default Max Distance", default=20.0, min=0.01, max=10000.0)
    default_alpha: FloatProperty(name="Default Smooth Alpha", default=0.2, min=0.01, max=1.0)
    default_deadzone: FloatProperty(name="Default Deadzone", default=0.03, min=0.0, max=0.5)

    def draw(self, context):
        layout = self.layout

        layout.label(text="Saved Defaults (persist after restart):")
        col = layout.column(align=True)
        col.prop(self, "default_yaw")
        col.prop(self, "default_pitch")
        col.prop(self, "default_zoom")
        col.prop(self, "default_min_dist")
        col.prop(self, "default_max_dist")
        col.prop(self, "default_alpha")
        col.prop(self, "default_deadzone")

        row = layout.row(align=True)
        row.operator("htva.apply_defaults_to_scene", icon="IMPORT")
        row.operator("htva.save_scene_as_defaults", icon="EXPORT")

        layout.separator()
        layout.label(text="Hotkeys (editable):")

        try:
            import rna_keymap_ui
            wm = context.window_manager

            # Use USER keyconfig so changes persist
            kc = wm.keyconfigs.user
            km = kc.keymaps.get("3D View")
            if not km:
                layout.label(text="Keymap '3D View' not found.")
                return

            def draw_hotkey(op_idname: str, label: str):
                kmi = None
                for item in km.keymap_items:
                    if item.idname == op_idname:
                        kmi = item
                        break

                layout.label(text=label)
                if kmi:
                    rna_keymap_ui.draw_kmi([], kc, km, kmi, layout, 0)
                else:
                    layout.label(text=f"Hotkey for '{op_idname}' not registered yet. Re-enable add-on and reopen Preferences.")

                layout.separator(factor=0.5)

            draw_hotkey("htva.toggle", "Toggle View Assist")
            draw_hotkey("htva.launch_tracker_bg", "Launch Tracker (Background)")
            draw_hotkey("htva.stop_tracker", "Stop Tracker")

        except Exception:
            layout.label(text="Hotkey UI unavailable.")