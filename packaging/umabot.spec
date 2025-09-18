# pyinstaller -y packaging/Umaplay.spec
# Produces dist/Umaplay/Umaplay.exe with bundled data

import sys
import os # Import the os module
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from pathlib import Path

# Use os.getcwd() to get the current working directory.
# Assuming you run 'pyinstaller -y packaging/Umaplay.spec' from D:\GitHub\UmAutoplay,
# os.getcwd() will return 'D:\GitHub\UmAutoplay', which is your project root.
project_root = Path(os.getcwd())

datas = []
binaries = []

# Include built web UI
datas += [(str(project_root / "web" / "dist"), "web/dist")]

# Include datasets and sample config
datas += [(str(project_root / "datasets" / "in_game"), "datasets/in_game")]
datas += [(str(project_root / "config.sample.json"), ".")]

# If you want to include 'models' by default (might be large), uncomment:
# datas += [(str(project_root / "models"), "models")]

hiddenimports = []
# PaddleOCR/Ultralytics may need extras; auto-collect if necessary:
# Corrected usage of collect_submodules
hiddenimports += collect_submodules('ultralytics', lambda module: True)
hiddenimports += collect_submodules('cv2', lambda module: True)


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="Umaplay", # Changed name from Umaplay to Umaplay as per your initial prompt
    debug=False,
    strip=False,
    upx=False,
    console=True,  # console on; set False for fully silent
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="Umaplay")