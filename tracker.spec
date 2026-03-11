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

# Runtime compatibility import
hiddenimports += [
    "backports",
    "backports.tarfile",
]

# Bundle runtime resources
datas += [
    ("tracker/face_landmarker.task", "."),
    ("tracker/test.mp4", "."),
]

a = Analysis(
    ["tracker/webcam_sender.py"],
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

UPX_OK = (sys.platform != "darwin")

exe_kwargs = dict(
    exclude_binaries=True,
    name="tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=UPX_OK,
    console=False,
)

# Let PyInstaller know about entitlements too on macOS
if sys.platform == "darwin":
    exe_kwargs["entitlements_file"] = "entitlements.plist"

exe = EXE(
    pyz,
    a.scripts,
    [],
    **exe_kwargs,
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

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="tracker.app",
        icon=None,
        bundle_identifier="com.indoordragon.tracker",
        info_plist={
            "CFBundleName": "tracker",
            "CFBundleDisplayName": "tracker",
            "CFBundleIdentifier": "com.indoordragon.tracker",
            "CFBundleShortVersionString": "0.1.6",
            "CFBundleVersion": "0.1.6",
            "NSCameraUsageDescription": "Head Tracked View Assist uses your camera for real-time head tracking.",
            # Only include this if you actually use microphone input:
            # "NSMicrophoneUsageDescription": "Head Tracked View Assist may use audio input when available.",
        },
    )
