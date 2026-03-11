import bpy
import math
import mathutils
import socket
import platform
import subprocess
import time
import os
import csv
import io
import signal
import stat
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

HTVA_CTRL_PORT = 5006  # control port for QUIT message (tracker binds this)
HTVA_POSE_PORT = 5005  # pose data port (tracker -> blender; Blender binds when Status ON)


def _tracker_dir() -> Path:
    return Path(__file__).resolve().parent / "tracker"


def _tracker_internal_dir() -> Path:
    return _tracker_dir() / "_internal"


def _platform_name() -> str:
    # "Windows", "Darwin" (macOS), "Linux"
    return platform.system()


def _is_windows() -> bool:
    return _platform_name().lower().startswith("win")


def _is_macos() -> bool:
    return _platform_name().lower() == "darwin"


def _is_linux() -> bool:
    return _platform_name().lower() == "linux"


def _pid_file() -> Path:
    return _tracker_dir() / "tracker_pid.txt"


def _write_tracker_pid(pid: int) -> None:
    try:
        _pid_file().write_text(str(int(pid)), encoding="utf-8")
    except Exception:
        pass


def _clear_tracker_pid() -> None:
    try:
        p = _pid_file()
        if p.exists():
            p.unlink()
    except Exception:
        pass


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


def _port_in_use_udp(port: int) -> bool:
    """
    True if something is already bound to 127.0.0.1:port (UDP).
    We use this to detect an already-running tracker.

    NOTE:
    Blender itself binds the POSE port (5005) when Status is ON.
    So we use CONTROL port (5006) to detect tracker.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        try:
            s.close()
        except Exception:
            pass


def _is_tracker_running() -> bool:
    """Tracker should be the one binding the CONTROL port (5006)."""
    return _port_in_use_udp(HTVA_CTRL_PORT)


# =========================================================
# macOS tracker.app.zip extraction support
# =========================================================

def _macos_app_bundle_path() -> Path:
    return _tracker_dir() / "tracker.app"


def _macos_app_zip_path() -> Path:
    return _tracker_dir() / "tracker.app.zip"


def _macos_app_executable_path() -> Path:
    return _macos_app_bundle_path() / "Contents" / "MacOS" / "tracker"


def _remove_quarantine_recursively(path: Path) -> None:
    """
    Helpful on macOS if the addon zip or nested files inherit quarantine.
    Safe to ignore errors.
    """
    if not _is_macos():
        return
    try:
        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        pass


def _extract_macos_tracker_app(report_fn=None) -> bool:
    """
    Extract tracker.app.zip into tracker/ using ditto so the .app bundle
    structure/signature stays intact.
    """
    tracker_dir = _tracker_dir()
    app_zip = _macos_app_zip_path()
    app_bundle = _macos_app_bundle_path()
    app_exec = _macos_app_executable_path()

    if app_exec.exists():
        return True

    if not app_zip.exists():
        if report_fn:
            report_fn(
                {'ERROR'},
                "macOS tracker package not found.\n\n"
                f"Expected:\n{app_zip}"
            )
        return False

    try:
        if app_bundle.exists():
            import shutil
            shutil.rmtree(app_bundle, ignore_errors=True)

        tracker_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["ditto", "-x", "-k", str(app_zip), str(tracker_dir)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            if report_fn:
                msg = result.stderr.strip() or result.stdout.strip() or "Unknown extraction error."
                report_fn({'ERROR'}, f"Failed to extract tracker.app.zip:\n{msg}")
            return False

        if not app_exec.exists():
            if report_fn:
                report_fn(
                    {'ERROR'},
                    "tracker.app.zip extracted, but tracker executable was not found.\n\n"
                    f"Expected:\n{app_exec}"
                )
            return False

        _remove_quarantine_recursively(app_bundle)
        ensure_executable(app_exec)

        if report_fn:
            report_fn({'INFO'}, "Extracted macOS tracker.app.")

        return True

    except Exception as e:
        if report_fn:
            report_fn({'ERROR'}, f"Failed to prepare macOS tracker.app: {e}")
        return False


def _ensure_tracker_ready(report_fn=None) -> bool:
    """
    Prepare the tracker for launch if needed.
    On macOS, this extracts tracker.app from tracker.app.zip on first run.
    """
    if _is_macos():
        return _extract_macos_tracker_app(report_fn=report_fn)
    return True


def _tracker_exec_candidates() -> list[Path]:
    """
    Return candidate executable paths in preferred order for the current OS.

    Expected packaging:

    Windows:
      tracker/tracker.exe
      tracker/_internal/...

    Linux:
      tracker/tracker
      tracker/_internal/...

    macOS:
      tracker/tracker.app/Contents/MacOS/tracker
      tracker/tracker
    """
    td = _tracker_dir()

    if _is_windows():
        return [td / "tracker.exe"]

    if _is_macos():
        return [
            td / "tracker.app" / "Contents" / "MacOS" / "tracker",
            td / "tracker",
        ]

    return [td / "tracker"]


def _resolve_tracker_executable() -> Path:
    for p in _tracker_exec_candidates():
        if p.exists():
            return p
    cands = _tracker_exec_candidates()
    return cands[0] if cands else (_tracker_dir() / "tracker")


def ensure_executable(exe_path: Path) -> None:
    """
    Linux/macOS UX fix:
    ZIP extraction can drop executable permissions on POSIX.
    Before launching, ensure the tracker file is executable.
    """
    if _is_windows():
        return
    try:
        if not exe_path.exists():
            return
        st_mode = exe_path.stat().st_mode
        exe_path.chmod(st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def _process_name_for_pid_windows(pid: int) -> str:
    """Return the image name for a PID using tasklist (Windows)."""
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        out = (r.stdout or "").strip()
        if not out or "No tasks are running" in out:
            return ""

        reader = csv.reader(io.StringIO(out))
        row = next(reader, None)
        if not row or len(row) < 2:
            return ""
        return row[0].strip().strip('"')
    except Exception:
        return ""


def _process_comm_for_pid_posix(pid: int) -> str:
    """Return process 'comm' for PID via ps on macOS/Linux. Empty if unknown."""
    try:
        r = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _pid_looks_like_tracker(pid: int) -> bool:
    """
    Defensive check to avoid killing an unrelated process due to stale PID file.
    """
    if pid <= 0:
        return False

    if _is_windows():
        name = _process_name_for_pid_windows(pid).lower()
        return name == "tracker.exe"

    comm = _process_comm_for_pid_posix(pid).strip()
    if not comm:
        return False
    base = Path(comm).name.lower()
    return "tracker" in base


def _kill_pid_windows(pid: int) -> bool:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        return True
    except Exception:
        return False


def _kill_pid_posix(pid: int) -> bool:
    """
    Try SIGTERM then SIGKILL if needed.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return False

    for _ in range(10):
        time.sleep(0.05)
        try:
            os.kill(pid, 0)
            still_alive = True
        except Exception:
            still_alive = False
        if not still_alive:
            return True

    try:
        os.kill(pid, signal.SIGKILL)
        return True
    except Exception:
        return False


def _force_kill_pid_if_tracker(pid: int) -> bool:
    """
    Kill only if PID looks like tracker (avoid stale PID accidents).
    Returns True if we attempted to kill.
    """
    if not _pid_looks_like_tracker(pid):
        return False

    if _is_windows():
        return _kill_pid_windows(pid)
    return _kill_pid_posix(pid)


def htva_stop_tracker_on_exit():
    """
    Called during Blender shutdown via atexit (registered in __init__.py).
    Keep this very defensive: Blender data may already be partially freed.
    """
    try:
        if not _is_tracker_running():
            _clear_tracker_pid()
            return

        _send_tracker_quit()

        try:
            time.sleep(0.25)
        except Exception:
            pass

        pid = _read_tracker_pid()
        if pid > 0 and _is_tracker_running():
            _force_kill_pid_if_tracker(pid)

        _clear_tracker_pid()
    except Exception:
        pass


def _launch_tracker_macos(show_preview: bool, report_fn=None) -> bool:
    """
    Launch macOS tracker as an actual .app bundle so macOS attributes
    permissions (camera, etc.) to tracker.app instead of Blender.

    We pass args via `open ... --args` for future-proofing / tracker-side parsing.
    """
    tracker_dir = _tracker_dir()
    app_bundle = _macos_app_bundle_path()

    if not app_bundle.exists():
        if report_fn:
            report_fn(
                {'ERROR'},
                "macOS tracker.app not found.\n\n"
                f"Expected:\n{app_bundle}"
            )
        return False

    try:
        # Best effort: remove quarantine from extracted bundle
        _remove_quarantine_recursively(app_bundle)

        cmd = [
            "open",
            "-n",
            str(app_bundle),
            "--args",
            "--show-preview", "1" if show_preview else "0",
            "--udp-ip", "127.0.0.1",
            "--udp-port", str(HTVA_POSE_PORT),
            "--ctrl-port", str(HTVA_CTRL_PORT),
        ]

        proc = subprocess.Popen(
            cmd,
            cwd=str(tracker_dir),
            start_new_session=True,
        )

        # This PID is for the `open` helper, not the final app process.
        # We keep writing it for compatibility, but actual tracker shutdown
        # should primarily happen through the UDP QUIT control message.
        _write_tracker_pid(proc.pid)

        if report_fn:
            report_fn({'INFO'}, "Launching tracker (macOS app bundle)…")
        return True

    except Exception as e:
        if report_fn:
            report_fn({'ERROR'}, f"Failed to launch macOS tracker.app: {e}")
        return False


def _launch_tracker(show_preview: bool, report_fn=None) -> bool:
    """
    Shared launcher.
    show_preview=True  -> windowed preview
    show_preview=False -> background (no preview)
    Returns True if launched successfully, False otherwise.
    """
    if _is_tracker_running():
        if report_fn:
            report_fn({'INFO'}, "Tracker is already running.")
        return False

    tracker_dir = _tracker_dir()

    if not tracker_dir.exists():
        if report_fn:
            report_fn({'ERROR'}, f"Tracker folder not found:\n{tracker_dir}")
        return False

    if not _ensure_tracker_ready(report_fn=report_fn):
        return False

    # macOS: launch the .app bundle, not the inner executable
    if _is_macos():
        return _launch_tracker_macos(show_preview=show_preview, report_fn=report_fn)

    exe = _resolve_tracker_executable()

    if not exe.exists():
        if _is_windows():
            expected = tracker_dir / "tracker.exe"
        else:
            expected = tracker_dir / "tracker"

        if report_fn:
            report_fn(
                {'ERROR'},
                "Tracker executable not found.\n\n"
                f"Expected (for this OS) something like:\n{expected}\n\n"
                "Make sure you copied your platform's build output into the add-on's tracker/ folder."
            )
        return False

    try:
        env = dict(os.environ)
        env["HTVA_UDP_IP"] = env.get("HTVA_UDP_IP", "127.0.0.1")
        env["HTVA_UDP_PORT"] = env.get("HTVA_UDP_PORT", str(HTVA_POSE_PORT))
        env["HTVA_CTRL_PORT"] = env.get("HTVA_CTRL_PORT", str(HTVA_CTRL_PORT))
        env["HTVA_SHOW_PREVIEW"] = "1" if show_preview else "0"

        popen_kwargs = {
            "cwd": str(tracker_dir),
            "env": env,
        }

        if _is_windows():
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        else:
            popen_kwargs["start_new_session"] = True

        ensure_executable(exe)

        proc = subprocess.Popen([str(exe)], **popen_kwargs)

        _write_tracker_pid(proc.pid)

        if report_fn:
            report_fn({'INFO'}, f"Launching tracker ({_platform_name()})…")
        return True

    except Exception as e:
        if report_fn:
            report_fn({'ERROR'}, f"Failed to launch tracker: {e}")
        return False


class HTVA_OT_launch_tracker(bpy.types.Operator):
    bl_idname = "htva.launch_tracker"
    bl_label = "Launch Tracker (Preview)"
    bl_description = "Launch the external webcam tracker (with preview window)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        ok = _launch_tracker(show_preview=True, report_fn=self.report)
        return {'FINISHED'} if ok else {'CANCELLED'}


class HTVA_OT_launch_tracker_bg(bpy.types.Operator):
    bl_idname = "htva.launch_tracker_bg"
    bl_label = "Launch Tracker (Background)"
    bl_description = "Launch the external webcam tracker in the background (no preview window)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        ok = _launch_tracker(show_preview=False, report_fn=self.report)
        return {'FINISHED'} if ok else {'CANCELLED'}


class HTVA_OT_stop_tracker(bpy.types.Operator):
    bl_idname = "htva.stop_tracker"
    bl_label = "Stop Tracker"
    bl_description = "Gracefully stop the external webcam tracker"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _is_tracker_running():
            _clear_tracker_pid()
            self.report({'INFO'}, "Tracker is not running.")
            return {'CANCELLED'}

        _send_tracker_quit()
        time.sleep(0.25)

        pid = _read_tracker_pid()
        if pid > 0 and _is_tracker_running():
            killed = _force_kill_pid_if_tracker(pid)
            if killed:
                _clear_tracker_pid()
                self.report({'INFO'}, "Tracker stopped.")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "Sent QUIT, but PID did not match tracker (not killing).")
                return {'FINISHED'}

        _clear_tracker_pid()
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
        self._sock.bind(("127.0.0.1", HTVA_POSE_PORT))

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
