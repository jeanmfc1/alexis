# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ALEXIS.exe (one-folder, windowed).

Build from the REPO ROOT:
    py -3.11 -m PyInstaller packaging/alexis.spec --noconfirm \
        --distpath C:/ALEXIS_build/dist --workpath C:/ALEXIS_build/work

Notes
-----
* One-folder (COLLECT), not one-file: one-file re-extracts ~70 MB on every
  launch and trips antivirus. One-folder starts fast.
* Windowed (console=False): no console window. app.main.ensure_streams()
  reattaches stdout/stderr so the --run-pipeline job children can still log.
* MeSH JSON (~120 MB) and snapshots are NOT bundled -- they live in the user's
  data folder (core.paths reads them from data_root). Keeps the exe small.
* The classifier .pkl models ARE bundled (read-only) under classifiers/.
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# SPECPATH is the folder containing this spec (…/ALEXIS/packaging); the repo
# root is its parent. All source paths below are made absolute against ROOT so
# the build works regardless of the invocation CWD.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))


def R(*parts):
    return os.path.join(ROOT, *parts)

# --- hidden imports -------------------------------------------------------
hiddenimports = []
# Heavy 3rd-party packages with dynamic submodules.
for pkg in ("sklearn", "scipy", "pandas"):
    hiddenimports += collect_submodules(pkg)
# Our own packages are imported dynamically (lazy imports + runpy dispatch),
# so PyInstaller's static scan misses them -- collect explicitly.
for pkg in ("app", "core", "analytics", "pipelines", "classifiers",
            "policy", "collectors", "utils", "storage", "config"):
    hiddenimports += collect_submodules(pkg)
# uvicorn / anyio / sse pick their implementations at runtime.
hiddenimports += [
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
    "sse_starlette",
    "webview",
]

# --- bundled data (read-only assets) --------------------------------------
datas = [
    (R("app", "web"), "app/web"),          # control-panel shell
    (R("viz"), "viz"),                      # template + jsx components + vendor libs/fonts
    (R("classifiers"), "classifiers"),      # .pkl models (+ .py, harmless)
    (R("policy"), "policy"),
    (R("tools", "verify_portability.py"), "tools"),  # used by the diagnostic jobs
]
datas += collect_data_files("pyarrow")
datas += collect_data_files("sklearn")

block_cipher = None

a = Analysis(
    [R("packaging", "run_alexis.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "jedi", "pytest", "tkinter",
              "notebook", "PyQt5", "PySide2"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ALEXIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # windowed GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # set to packaging/alexis.ico once an icon exists
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ALEXIS",
)
