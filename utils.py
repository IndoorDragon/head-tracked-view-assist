import bpy

def apply_deadzone(v, dz):
    return 0.0 if abs(v) < dz else v

def _ptr_to_str(area):
    return str(area.as_pointer()) if area else "0"

def _str_to_ptr(s: str) -> int:
    try:
        return int(s)
    except Exception:
        return 0

def find_view3d_region_by_area_ptr(context, area_ptr_str: str):
    area_ptr = _str_to_ptr(area_ptr_str)
    if not area_ptr:
        return None, None, None

    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D' and area.as_pointer() == area_ptr:
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active.region_3d
    return None, None, None

def find_any_view3d_region(context):
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active.region_3d
    return None, None, None