# PyInstaller spec for the Sapient engine (FastAPI + analytics), one-folder build.
#   uv run --with pyinstaller pyinstaller packaging/sapient-api.spec --noconfirm --distpath packaging/dist --workpath packaging/build
# Output: packaging/dist/sapient-api/ (sapient-api.exe on Windows), bundled by
# electron-builder as resources/engine.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("backend")
    + collect_submodules("core")
    # The official IBKR API is loaded from the user's install at runtime; recent
    # versions import protobuf, so ship it inside the engine.
    + collect_submodules("google.protobuf")
)
datas = collect_data_files("yfinance") + collect_data_files("curl_cffi")

a = Analysis(
    [ROOT + "/backend/desktop_main.py"],
    pathex=[ROOT],
    hiddenimports=hiddenimports,
    datas=datas,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "notebook", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sapient-api",
    console=True,  # stdio pipes to Electron; the window is hidden by the parent (windowsHide)
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="sapient-api", upx=False)
