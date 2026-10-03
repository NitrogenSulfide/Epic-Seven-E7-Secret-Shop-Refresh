# Rebuild the player GUI

The player EXE is compiled from `e7_shop_refresh_gui.py` and the adjacent modules
with PyInstaller. Python, Tk and Pillow are bundled; artwork remains beside the
EXE. It is different from the preserved legacy C# Python launcher.

From an extracted player folder on Windows, use Python 3.13 with Tk to create a
new private build environment. The pins are supplied with the engine source:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r runtime\engine-build-requirements.txt
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --windowed --name "E7 Secret Shop Refresh" --icon (Resolve-Path e7_gui_assets\shopkeeper-v2.ico).Path --distpath rebuilt-gui --workpath rebuild-work --specpath rebuild-work .\e7_shop_refresh_gui.py
```

Use new output directories. Stage the rebuilt EXE in a separate copy of the
complete player folder, preserving artwork and its runtime. Check it offline:

```powershell
& ".\rebuilt-gui\E7 Secret Shop Refresh.exe" --verify --engine-dir .\runtime --verification-report .\gui-verification.json
```

The check creates no GUI window or ADB connection. It verifies bundled image/Tcl
support and required artwork/runtime paths; missing recognition is reported as
setup needed, not cleared for live use. A rebuilt EXE has a different hash and
needs its own review. Engine build instructions are in [ENGINE.md](ENGINE.md).

The full source checkout has `build_release_assets.ps1`, `build_release.ps1`,
`build_engine_release.ps1` and fixture tests. These require a clean committed
checkout and an explicit private BuildPython environment. They build matching
GUI/engine components, then assemble the player ZIP and optional source archive
with checksums and private build manifests. No installed runtime or private
screenshots/settings are packaged.
