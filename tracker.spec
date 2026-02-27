# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect packages (python + data + binaries) from these libs
mp = collect_all("mediapipe")
cv2 = collect_all("cv2")
np = collect_all("numpy")

datas = []
binaries = []
hiddenimports = []

datas += mp.datas + cv2.datas + np.datas
binaries += mp.binaries + cv2.binaries + np.binaries
hiddenimports += mp.hiddenimports + cv2.hiddenimports + np.hiddenimports

# Bundle the model file next to the executable
datas += [("face_landmarker.task", ".")]

a = Analysis(
    ["webcam_sender.py"],
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

# console=False prevents a terminal window on Windows/macOS
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="tracker",
)