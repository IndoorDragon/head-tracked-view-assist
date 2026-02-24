import bpy
import math
import mathutils
import socket
import platform
import subprocess
import time
import os
from pathlib import Path

from .utils import (
    apply_deadzone,
    _ptr_to_str,
    find_any_view3d_region,
    find_view3d_region_by_area_ptr,
)

# =========================================================
# TRACKER LAUNCH / STOP
# =========================================================

HTVA_CTRL_PORT = 5006  # control port for QUIT message


def _tracker_dir() -> Path:
    return Path(__file__).resolve().parent / "tracker"


def _tracker_exe_path() -> Path:
    # Packaged tracker executable (PyInstaller output)
    return _tracker_dir() / "tracker.exe"


def _tracker_internal_dir() -> Path:
    # PyInstaller one-folder internal runtime dir (must sit next to tracker.exe)
    return _tracker_dir() / "_internal"


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _pid_file() -> Path:
    return _tracker_dir() / "tracker_pid.txt"


def _read_tracker_pid() -> int:
    try:
        p = _pid_file()
        if not p.exists():
            return 0
        txt = p.read_text(encoding="utf-8").strip()
        return int(txt) if txt.isdigit() else 0
    except Exception:
        return 0


def _send_tracker_quit():
    """Send a graceful quit message to the tracker."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"QUIT", ("127.0.0.1", HTVA_CTRL_PORT))
        s.close()
    except Exception:
        pass


class HTVA_OT_launch_tracker(bpy.types.Operator):
    bl_idname = "htva.launch_tracker"
    bl_label = "Launch Tracker"
    bl_description = "Launch the external webcam tracker (Windows only)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _is_windows():
            self.report({'ERROR'}, "Tracker launcher currently supports Windows only.")
            return {'CANCELLED'}

        tracker_dir = _tracker_dir()
        exe = _tracker_exe_path()
        internal_dir = _tracker_internal_dir()

        if not tracker_dir.exists():
            self.report({'ERROR'}, f"Tracker folder not found:\n{tracker_dir}")
            return {'CANCELLED'}

        if not exe.exists():
            self.report(
                {'ERROR'},
                "tracker.exe not found:\n"
                f"{exe}\n\n"
                "Make sure you copied the PyInstaller dist output into the add-on's tracker/ folder."
            )
            return {'CANCELLED'}

        # In one-folder mode, PyInstaller needs _internal next to the exe.
        if not internal_dir.exists():
            self.report(
                {'ERROR'},
                "_internal folder not found:\n"
                f"{internal_dir}\n\n"
                "This folder must be copied alongside tracker.exe (PyInstaller one-folder output)."
            )
            return {'CANCELLED'}

        try:
            # Optional: set defaults for tracker behavior when launched from Blender
            env = dict(**{k: v for k, v in dict(os.environ).items()})
            env["HTVA_UDP_IP"] = env.get("HTVA_UDP_IP", "127.0.0.1")
            env["HTVA_UDP_PORT"] = env.get("HTVA_UDP_PORT", "5005")
            env["HTVA_CTRL_PORT"] = env.get("HTVA_CTRL_PORT", str(HTVA_CTRL_PORT))

            # If you want it silent when launched from Blender, keep preview off:
            # (User can still run tracker.exe manually if they want the preview.)
            env["HTVA_SHOW_PREVIEW"] = "1"

            # Launch the tracker executable
            subprocess.Popen(
                [str(exe)],
                cwd=str(tracker_dir),
                env=env,
                # Windows nicety: avoid creating an extra console window in some cases
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )

            self.report({'INFO'}, "Launching tracker…")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to launch tracker: {e}")
            return {'CANCELLED'}


class HTVA_OT_stop_tracker(bpy.types.Operator):
    bl_idname = "htva.stop_tracker"
    bl_label = "Stop Tracker"
    bl_description = "Gracefully stop the external webcam tracker"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _is_windows():
            self.report({'ERROR'}, "Stop tracker supports Windows only.")
            return {'CANCELLED'}

        # 1) Try graceful quit
        _send_tracker_quit()

        # Give it a moment to exit cleanly
        time.sleep(0.2)

        # 2) If it’s still running, fallback to taskkill (safety net)
        pid = _read_tracker_pid()
        if pid > 0:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                )
                self.report({'INFO'}, "Tracker stopped.")
                return {'FINISHED'}
            except Exception as e:
                self.report({'WARNING'}, f"Sent QUIT, but fallback kill failed: {e}")
                return {'FINISHED'}

        # If no PID file, we still sent QUIT. That’s usually enough.
        self.report({'INFO'}, "Sent quit signal to tracker.")
        return {'FINISHED'}


# =========================================================
# VIEWPORT TARGET SELECTION
# =========================================================

class HTVA_OT_use_this_viewport(bpy.types.Operator):
    bl_idname = "htva.use_this_viewport"
    bl_label = "Use This Viewport"

    def execute(self, context):
        props = context.scene.htva_props
        if context.area and context.area.type == 'VIEW_3D':
            props.target_area_ptr = _ptr_to_str(context.area)
            self.report({'INFO'}, "Now targeting this 3D Viewport.")
        return {'FINISHED'}


# =========================================================
# HEAD-TRACKED VIEW ASSIST
# =========================================================

class HTVA_OT_start(bpy.types.Operator):
    bl_idname = "htva.start"
    bl_label = "Start Head-Tracked View Assist"
    bl_options = {'REGISTER'}

    _timer = None
    _sock = None

    _filtered = mathutils.Vector((0.0, 0.0, 0.0))
    _prev_filtered = mathutils.Vector((0.0, 0.0, 0.0))
    _baseline = mathutils.Vector((0.0, 0.0, 0.0))
    _calibrated = False

    def modal(self, context, event):
        props = context.scene.htva_props

        if not props.enabled:
            return self.cancel(context)

        if event.type != 'TIMER' or not self._sock:
            return {'PASS_THROUGH'}

        latest = None
        while True:
            try:
                data, _addr = self._sock.recvfrom(1024)
                latest = data
            except BlockingIOError:
                break
            except Exception:
                break

        if latest is None:
            return {'PASS_THROUGH'}

        try:
            parts = latest.decode("utf-8", errors="ignore").strip().split()
            if len(parts) < 2:
                return {'PASS_THROUGH'}

            raw = mathutils.Vector((
                float(parts[0]),
                float(parts[1]),
                float(parts[2]) if len(parts) >= 3 else 0.0
            ))

            if not self._calibrated:
                self._baseline = raw.copy()
                self._filtered = mathutils.Vector((0.0, 0.0, 0.0))
                self._prev_filtered = mathutils.Vector((0.0, 0.0, 0.0))
                self._calibrated = True

            raw -= self._baseline

            raw.x = apply_deadzone(raw.x, props.deadzone)
            raw.y = apply_deadzone(raw.y, props.deadzone)
            raw.z = apply_deadzone(raw.z, props.deadzone)

            self._filtered = self._filtered.lerp(raw, props.smoothing_alpha)

            delta = self._filtered - self._prev_filtered
            self._prev_filtered = self._filtered.copy()

            area, _region, rv3d = find_view3d_region_by_area_ptr(context, props.target_area_ptr)
            if rv3d is None:
                props.target_area_ptr = "0"
                area, _region, rv3d = find_any_view3d_region(context)
            if not rv3d:
                return {'PASS_THROUGH'}

            yaw = math.radians(-delta.x * props.yaw_strength_deg)
            pitch = math.radians(delta.y * props.pitch_strength_deg)

            current_rot = rv3d.view_rotation.copy()

            q_yaw = mathutils.Quaternion((0.0, 0.0, 1.0), yaw)
            rot_yawed = q_yaw @ current_rot

            right_axis_world = rot_yawed @ mathutils.Vector((1.0, 0.0, 0.0))
            q_pitch = mathutils.Quaternion(right_axis_world, pitch)

            rv3d.view_rotation = q_pitch @ rot_yawed

            zoom_delta = -delta.z * props.zoom_strength
            new_dist = rv3d.view_distance + zoom_delta
            rv3d.view_distance = max(props.min_distance, min(props.max_distance, new_dist))

            area.tag_redraw()

        except Exception:
            pass

        return {'PASS_THROUGH'}

    def execute(self, context):
        props = context.scene.htva_props
        if props.enabled:
            return {'CANCELLED'}

        props.enabled = True
        self._calibrated = False

        if context.area and context.area.type == 'VIEW_3D':
            props.target_area_ptr = _ptr_to_str(context.area)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.bind(("127.0.0.1", 5005))  # pose port

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.02, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        props = context.scene.htva_props
        props.enabled = False

        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        return {'CANCELLED'}


class HTVA_OT_stop(bpy.types.Operator):
    bl_idname = "htva.stop"
    bl_label = "Stop Head-Tracked View Assist"

    def execute(self, context):
        context.scene.htva_props.enabled = False
        return {'FINISHED'}


class HTVA_OT_toggle(bpy.types.Operator):
    bl_idname = "htva.toggle"
    bl_label = "Toggle Head-Tracked View Assist"

    def execute(self, context):
        props = context.scene.htva_props

        if not props.enabled and context.area and context.area.type == 'VIEW_3D':
            props.target_area_ptr = _ptr_to_str(context.area)

        if props.enabled:
            bpy.ops.htva.stop()
        else:
            bpy.ops.htva.start()

        return {'FINISHED'}