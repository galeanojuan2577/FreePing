# -*- mode: python ; coding: utf-8 -*-
import os
import platform
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath("freeping.spec"))).parent.resolve()

block_cipher = None
is_windows = platform.system() == "Windows"
is_linux = platform.system() == "Linux"

if is_windows:
    exe_name = "FreePing.exe"
    console = False
    icon_path = str(ROOT / "build" / "freeping.ico")
else:
    exe_name = "freeping"
    console = False
    icon_path = None

datas = [
    (str(ROOT / "freeping" / "data" / "games_list.json"), "freeping/data"),
    (str(ROOT / "freeping" / "gui" / "resources" / "styles.qss"), "freeping/gui/resources"),
]

binaries = []

hiddenimports = [
    "freeping",
    "freeping.core",
    "freeping.core.config",
    "freeping.core.models",
    "freeping.core.ping",
    "freeping.core.tunnel",
    "freeping.core.watchdog",
    "freeping.gui",
    "freeping.gui.app",
    "freeping.gui.main_window",
    "freeping.gui.wizard",
    "freeping.gui.tray_icon",
    "freeping.gui.settings_dialog",
    "freeping.provisioning",
    "freeping.provisioning.oci_client",
    "freeping.provisioning.key_manager",
    "freeping.provisioning.cloud_init",
    "freeping.data",
    "freeping.data.games_list",
    "httpx",
    "yaml",
    "cryptography",
    "cryptography.hazmat.primitives.asymmetric.x25519",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
]

excludes = [
    "tkinter", "matplotlib", "scipy", "numpy",
    "PIL", "cv2", "notebook", "jupyter",
    "pytest", "IPython", "setuptools", "wheel",
]

a = Analysis(
    [str(ROOT / "freeping" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

if is_windows:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="FreePing",
    )