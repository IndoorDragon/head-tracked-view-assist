# webcam_sender.py
import os
import sys
import json
import socket
import time
from pathlib import Path

import cv2
import mediapipe as mp


def get_app_dir() -> Path:
    """
    Returns the directory this app should treat as its "working folder":
    - When packaged (PyInstaller): folder containing tracker.exe / tracker binary
    - When running as .py: folder containing this script
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# ----------------------------
# Platform flags
# ----------------------------
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


# ----------------------------
# Networking
# ----------------------------
UDP_IP = os.environ.get("HTVA_UDP_IP", "127.0.0.1")
UDP_PORT = int(os.environ.get("HTVA_UDP_PORT", "5005"))      # pose packets
CTRL_PORT = int(os.environ.get("HTVA_CTRL_PORT", "5006"))    # control messages (QUIT)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# ----------------------------
# Paths
# ----------------------------
HERE = get_app_dir()
CONFIG_PATH = HERE / "config.json"
PID_PATH = HERE / "tracker_pid.txt"

# Model lookup order:
# 1) explicit env override
# 2) alongside tracker binary
# 3) PyInstaller one-folder internal dir (dist/tracker/_internal/...)
_env_model = os.environ.get("HTVA_MODEL_PATH", "").strip()
if _env_model:
    MODEL_PATH = Path(_env_model)
else:
    candidate_1 = HERE / "face_landmarker.task"
    candidate_2 = HERE / "_internal" / "face_landmarker.task"
    MODEL_PATH = candidate_1 if candidate_1.exists() else candidate_2


# ----------------------------
# Settings
# ----------------------------
SEND_HZ = float(os.environ.get("HTVA_SEND_HZ", "60"))
X_GAIN = float(os.environ.get("HTVA_X_GAIN", "1.2"))
Y_GAIN = float(os.environ.get("HTVA_Y_GAIN", "1.0"))
Z_GAIN = float(os.environ.get("HTVA_Z_GAIN", "1.0"))
SHOW_PREVIEW = os.environ.get("HTVA_SHOW_PREVIEW", "1") != "0"

# Preview/camera defaults:
# - Linux: aggressive defaults to prevent black frames (MJPG + set size + resize preview)
# - Windows/macOS: conservative defaults for fast startup + less CPU
_default_force_mjpg = "1" if IS_LINUX else "0"
_default_force_size = "1" if IS_LINUX else "0"

# Capture defaults per-OS
_default_capture_w = "1280" if IS_LINUX else "640"
_default_capture_h = "720"  if IS_LINUX else "480"

# Preview window defaults per-OS
_default_preview_w = "960" if IS_LINUX else "640"
_default_preview_h = "540" if IS_LINUX else "480"

FORCE_MJPG = os.environ.get("HTVA_FORCE_MJPG", _default_force_mjpg) != "0"
FORCE_PREVIEW_SIZE = os.environ.get("HTVA_FORCE_SIZE", _default_force_size) != "0"

PREVIEW_W = int(os.environ.get("HTVA_PREVIEW_W", _default_preview_w))
PREVIEW_H = int(os.environ.get("HTVA_PREVIEW_H", _default_preview_h))
CAPTURE_W = int(os.environ.get("HTVA_CAPTURE_W", _default_capture_w))
CAPTURE_H = int(os.environ.get("HTVA_CAPTURE_H", _default_capture_h))

# Windows-only: auto-fit the preview window to the first captured frame
# (prevents "stretched face" when the camera is 4:3 but the window is 16:9)
AUTO_FIT_WIN_PREVIEW = os.environ.get("HTVA_WIN_AUTOFIT", "1") != "0"

CAM_INDEX_ENV = os.environ.get("HTVA_CAM_INDEX", "").strip()
CAM_INDEX = int(CAM_INDEX_ENV) if CAM_INDEX_ENV.isdigit() else None

MAX_CAM_TRY = 6  # tries 0..5


# ----------------------------
# Camera backend selection (cross-platform)
# ----------------------------
# Allow override (useful for debugging):
#   HTVA_CAP_BACKEND=any|v4l2|dshow|msmf|avfoundation|gstreamer
_backend_override = os.environ.get("HTVA_CAP_BACKEND", "").strip().lower()

_BACKEND_MAP = {
    "any": cv2.CAP_ANY,
    "v4l2": getattr(cv2, "CAP_V4L2", cv2.CAP_ANY),
    "dshow": getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY),
    "msmf": getattr(cv2, "CAP_MSMF", cv2.CAP_ANY),
    "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY),
    "gstreamer": getattr(cv2, "CAP_GSTREAMER", cv2.CAP_ANY),
}

if _backend_override in _BACKEND_MAP:
    BACKEND = _BACKEND_MAP[_backend_override]
else:
    if IS_WIN:
        BACKEND = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)
    elif IS_MAC:
        BACKEND = getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)
    else:
        BACKEND = getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)


# ----------------------------
# Helpers: config + PID file
# ----------------------------
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def write_pid_file():
    try:
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def remove_pid_file():
    try:
        if PID_PATH.exists():
            PID_PATH.unlink()
    except Exception:
        pass


# ----------------------------
# Camera open helpers
# ----------------------------
def _configure_capture(cap: cv2.VideoCapture):
    """
    Apply camera settings.

    IMPORTANT:
    - On Linux/V4L2, forcing size + MJPG often fixes black frames.
    - On Windows, forcing MJPG/size can slow camera negotiation, so defaults are OFF there.
      (But you can still force it via env vars if needed.)
    """
    if FORCE_PREVIEW_SIZE:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(CAPTURE_W))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(CAPTURE_H))

    if FORCE_MJPG:
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        except Exception:
            pass

    # Try to reduce latency a bit where supported (safe if ignored)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass


def try_open_cam(index: int):
    """
    Try to open a camera index with:
    1) chosen platform backend
    2) CAP_ANY fallback (lets OpenCV pick)
    """
    cap = cv2.VideoCapture(index, BACKEND)
    if cap.isOpened():
        _configure_capture(cap)
        return cap
    cap.release()

    cap = cv2.VideoCapture(index, cv2.CAP_ANY)
    if cap.isOpened():
        _configure_capture(cap)
        return cap
    cap.release()
    return None


def open_camera_auto(preferred=None):
    if preferred is not None:
        cap = try_open_cam(preferred)
        if cap:
            return cap, preferred

    for idx in range(MAX_CAM_TRY):
        cap = try_open_cam(idx)
        if cap:
            return cap, idx

    # Extra Linux fallback: try opening the device path directly
    if IS_LINUX:
        cap = cv2.VideoCapture("/dev/video0", BACKEND)
        if cap.isOpened():
            _configure_capture(cap)
            return cap, 0
        cap.release()

        cap = cv2.VideoCapture("/dev/video0", cv2.CAP_ANY)
        if cap.isOpened():
            _configure_capture(cap)
            return cap, 0
        cap.release()

    # Last resort
    cap = cv2.VideoCapture(0, cv2.CAP_ANY)
    _configure_capture(cap)
    return cap, 0


def draw_hud(frame, cam_idx, msg_line):
    cv2.putText(
        frame,
        f"Camera index: {cam_idx}   (N=next, P=prev, R=recenter, Q=quit)",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (50, 255, 50),
        2,
    )
    if msg_line:
        cv2.putText(
            frame,
            msg_line,
            (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (50, 255, 50),
            2,
        )


# ----------------------------
# Control socket for graceful quit
# ----------------------------
ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ctrl_sock.setblocking(False)
ctrl_sock.bind(("127.0.0.1", CTRL_PORT))


def check_quit_signal() -> bool:
    """Returns True if a QUIT control message was received."""
    try:
        data, _addr = ctrl_sock.recvfrom(128)
        if data.strip().upper() == b"QUIT":
            return True
    except BlockingIOError:
        return False
    except Exception:
        return False
    return False


# ----------------------------
# MediaPipe setup
# ----------------------------
if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Model file not found: {MODEL_PATH}\n"
        f"Option A requires face_landmarker.task to ship with the app.\n"
        f"Tried:\n"
        f"  - {HERE / 'face_landmarker.task'}\n"
        f"  - {HERE / '_internal' / 'face_landmarker.task'}\n"
        f"Or set HTVA_MODEL_PATH to an absolute path."
    )

BaseOptions = mp.tasks.BaseOptions
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
RunningMode = mp.tasks.vision.RunningMode
FaceLandmarker = mp.tasks.vision.FaceLandmarker

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
    running_mode=RunningMode.VIDEO,
    num_faces=1,
)


# ----------------------------
# Choose preferred camera
# ----------------------------
cfg = load_config()
cfg_cam = cfg.get("camera_index", None)
cfg_cam = int(cfg_cam) if isinstance(cfg_cam, int) or (isinstance(cfg_cam, str) and str(cfg_cam).isdigit()) else None
preferred_cam = CAM_INDEX if CAM_INDEX is not None else cfg_cam

VIDEO_FILE = HERE / "test.mp4"

if VIDEO_FILE.exists():
    cap = cv2.VideoCapture(str(VIDEO_FILE))
    cam_index = -1
else:
    cap, cam_index = open_camera_auto(preferred_cam)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open any webcam and fallback video was not found: {VIDEO_FILE}"
        )

cfg["camera_index"] = cam_index
save_config(cfg)

# Write PID so Blender can fallback-kill if needed
write_pid_file()

# ----------------------------
# Preview window setup
# ----------------------------
WINDOW_NAME = "Head-Tracked View Assist — Tracker"
if SHOW_PREVIEW:
    try:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        if FORCE_PREVIEW_SIZE:
            cv2.resizeWindow(WINDOW_NAME, PREVIEW_W, PREVIEW_H)
    except Exception:
        pass

# Track whether we already auto-fit the window on Windows
_win_autofit_done = False

baseline_set = False
base_x = base_y = base_size = 0.0

last_send = 0.0
period = 1.0 / max(1.0, SEND_HZ)

info_msg = f"Using camera {cam_index} (saved to {CONFIG_PATH.name})"

try:
    with FaceLandmarker.create_from_options(options) as landmarker:
        start_time = time.time()

        while True:
            if check_quit_signal():
                break

            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            h, w = frame.shape[:2]

            # --- Windows fix: match the preview window to the camera aspect ratio ---
            # Only do this once, and only when we're NOT explicitly forcing a preview size.
            if (
                SHOW_PREVIEW
                and IS_WIN
                and AUTO_FIT_WIN_PREVIEW
                and (not FORCE_PREVIEW_SIZE)
                and (not _win_autofit_done)
            ):
                try:
                    cv2.resizeWindow(WINDOW_NAME, int(w), int(h))
                except Exception:
                    pass
                _win_autofit_done = True
            # ----------------------------------------------------------------------

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            timestamp_ms = int((time.time() - start_time) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.face_landmarks:
                lms = result.face_landmarks[0]
                xs = [p.x for p in lms]
                ys = [p.y for p in lms]

                minx, maxx = min(xs), max(xs)
                miny, maxy = min(ys), max(ys)

                cx = (minx + maxx) * 0.5
                cy = (miny + maxy) * 0.5
                face_size = max(maxx - minx, maxy - miny)

                if not baseline_set:
                    base_x, base_y, base_size = cx, cy, face_size
                    baseline_set = True

                x = (cx - base_x) * 2.0 * X_GAIN
                y = (cy - base_y) * 2.0 * Y_GAIN

                z = 0.0
                if base_size > 1e-6:
                    z = ((face_size / base_size) - 1.0) * Z_GAIN

                x = max(-1.0, min(1.0, x))
                y = max(-1.0, min(1.0, y))
                z = max(-1.0, min(1.0, z))

                now = time.time()
                if now - last_send >= period:
                    msg = f"{x:.4f} {y:.4f} {z:.4f}".encode("utf-8")
                    sock.sendto(msg, (UDP_IP, UDP_PORT))
                    last_send = now

                if SHOW_PREVIEW:
                    p1 = (int(minx * w), int(miny * h))
                    p2 = (int(maxx * w), int(maxy * h))
                    cv2.rectangle(frame, p1, p2, (0, 255, 0), 2)
                    cv2.circle(frame, (int(cx * w), int(cy * h)), 5, (0, 255, 0), -1)
                    cv2.putText(
                        frame,
                        f"x={x:+.2f} y={y:+.2f} z={z:+.2f}",
                        (10, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
            else:
                if SHOW_PREVIEW:
                    cv2.putText(
                        frame,
                        "No face detected",
                        (10, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                    )

            if SHOW_PREVIEW:
                draw_hud(frame, cam_index, info_msg)
                info_msg = ""
                cv2.imshow(WINDOW_NAME, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("r"):
                    baseline_set = False
                    info_msg = "Recentered baseline"
                elif key in (ord("n"), ord("p")):
                    step = 1 if key == ord("n") else -1
                    next_idx = (cam_index + step) % MAX_CAM_TRY

                    new_cap = try_open_cam(next_idx)
                    if new_cap:
                        cap.release()
                        cap = new_cap
                        cam_index = next_idx
                        baseline_set = False
                        _win_autofit_done = False  # re-fit window for the new camera mode

                        cfg["camera_index"] = cam_index
                        save_config(cfg)

                        info_msg = f"Switched to camera {cam_index} (saved)"
                    else:
                        info_msg = f"Camera {next_idx} unavailable"

finally:
    try:
        cap.release()
    except Exception:
        pass
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    try:
        ctrl_sock.close()
    except Exception:
        pass
    remove_pid_file()
