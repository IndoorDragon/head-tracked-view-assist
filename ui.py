import bpy


class HTVA_PT_panel(bpy.types.Panel):
    bl_label = "Head-Tracked View Assist"
    bl_idname = "HTVA_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "View Assist"

    def draw(self, context):
        layout = self.layout
        props = context.scene.htva_props

        # ===============================
        # TRACKER CONTROLS
        # ===============================
        box = layout.box()
        box.label(text="Tracker", icon="CAMERA_DATA")

        row = box.row(align=True)
        row.operator("htva.launch_tracker", text="Launch Tracker", icon="PLAY")
        row.operator("htva.stop_tracker", text="Stop Tracker", icon="CANCEL")

        # ===============================
        # STATUS / PRIMARY CONTROLS
        # ===============================
        box = layout.box()

        row = box.row(align=True)
        icon = "PLAY" if not props.enabled else "PAUSE"
        text = "Start" if not props.enabled else "Stop"
        row.operator("htva.toggle", text=text, icon=icon)

        status = "ON" if props.enabled else "OFF"
        status_icon = "CHECKMARK" if props.enabled else "CANCEL"
        box.label(text=f"Status: {status}", icon=status_icon)

        # ===============================
        # VIEWPORT SELECTION
        # ===============================
        box = layout.box()
        box.label(text="Viewport", icon="VIEW3D")
        box.operator("htva.use_this_viewport", icon="RESTRICT_VIEW_OFF")

        # ===============================
        # SENSITIVITY
        # ===============================
        box = layout.box()
        box.label(text="Sensitivity", icon="ORIENTATION_VIEW")

        col = box.column(align=True)
        col.prop(props, "yaw_strength_deg", text="Yaw")
        col.prop(props, "pitch_strength_deg", text="Pitch")
        col.prop(props, "zoom_strength", text="Zoom")

        # ===============================
        # DISTANCE LIMITS
        # ===============================
        box = layout.box()
        box.label(text="Distance Limits", icon="EMPTY_ARROWS")

        col = box.column(align=True)
        col.prop(props, "max_distance", text="Max")
        col.prop(props, "min_distance", text="Min")

        # ===============================
        # SMOOTHING
        # ===============================
        box = layout.box()
        box.label(text="Smoothing", icon="MOD_SMOOTH")

        col = box.column(align=True)
        col.prop(props, "smoothing_alpha", text="Smooth Alpha")
        col.prop(props, "deadzone", text="Deadzone")