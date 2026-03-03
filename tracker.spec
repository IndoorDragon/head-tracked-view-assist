# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all
import sys

block_cipher = None

# collect_all() returns a tuple: (datas, binaries, hiddenimports)
mp_datas, mp_binaries, mp_hiddenimports = collect_all("mediapipe")
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")
np_datas, np_binaries, np_hiddenimports = collect_all("numpy")

datas = []
binaries = []
hiddenimports = []

datas += mp_datas + cv2_datas + np_datas
binaries += mp_binaries + cv2_binaries + np_binaries
hiddenimports += mp_hiddenimports + cv2_hiddenimports + np_hiddenimports

# ✅ Fix Linux runtime crash: pkg_resources/jaraco expects backports.* at runtime in some builds
hiddenimports += [
    "backports",
    "backports.tarfile",
]

# Bundle the model file next to the executable (NOTE: it's inside tracker/)
datas += [("tracker/face_landmarker.task", ".")]

a = Analysis(
    ["tracker/webcam_sender.py"],  # NOTE: script is inside tracker/
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Safer defaults: avoid UPX on macOS (can complicate signing/notarization)
UPX_OK = (sys.platform != "darwin")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=UPX_OK,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=UPX_OK,
    name="tracker",
)

# ✅ On macOS, wrap the collected output into a real .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="tracker.app",
        icon=None,  # optionally set an .icns here
        bundle_identifier="com.indoordragon.tracker",  # keep stable
        info_plist={
            # Camera permission prompt (important for OpenCV capture)
            "NSCameraUsageDescription": "Used to track head pose for Blender view assist.",
        },
    )