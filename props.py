import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty

class HTVA_Props(bpy.types.PropertyGroup):
    enabled: BoolProperty(name="Enabled", default=False)
    udp_port: IntProperty(name="UDP Port", default=5005, min=1024, max=65535)

    target_area_ptr: StringProperty(
        name="Target Viewport",
        default="0",
        description="Internal pointer identifying which 3D View this add-on controls"
    )

    yaw_strength_deg: FloatProperty(name="Yaw Strength (deg)", default=25.0, min=0.0, max=100.0)
    pitch_strength_deg: FloatProperty(name="Pitch Strength (deg)", default=25.0, min=0.0, max=100.0)

    zoom_strength: FloatProperty(name="Zoom Strength", default=2.0, min=0.0, max=20.0)
    min_distance: FloatProperty(name="Min Distance", default=0.2, min=0.001, max=1000.0)
    max_distance: FloatProperty(name="Max Distance", default=20.0, min=0.01, max=10000.0)

    smoothing_alpha: FloatProperty(name="Smoothing Alpha", default=0.2, min=0.01, max=1.0)
    deadzone: FloatProperty(name="Deadzone", default=0.03, min=0.0, max=0.5)