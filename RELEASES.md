# E7 GUI release checks

The first practical release is a GUI-only package requiring Python with Tkinter
and a separately installed supported ADB engine. Keep the Solunium source history,
GPL-3.0 licence and credits. Follow [AGENTS.md](AGENTS.md), [UPSTREAM.md](UPSTREAM.md)
and the current [runtime instructions](README.md).

No release candidate is selected or approved by adding this checklist. General's
`notes/release-catalogue.md` is the local index; `notes/release-workflow.md` holds
the reusable candidate record and independent-review handoff.

## Source and automated checks

Prepare a clean checkout of the intended full candidate commit and record the
comparison-base commit. Do not package the old General/scripts recovery copy.
Run from this repository root on Windows:

```powershell
py -3 -m unittest test_e7_shop_refresh_gui.ProtocolTests test_e7_engine_location -v
.\launch_e7_shop_refresh_gui.ps1 --help
```

For the optional live-counter engine, use the approved private build environment:

```powershell
.\.local-state\engine-build-venv\Scripts\python.exe -m unittest test_e7_live_engine -v
.\build_engine_release.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\engine-candidate
```

See [engine candidate instructions](ENGINE.md). Record both GUI and engine
ZIP/binary hashes against the same exact clean source commit. Engine-only checks
use fake ADB calls and keyboard polling; `--verify` only verifies bundled imports.
Keep personal runtime assets/config/history outside both ZIPs. A rebuilt engine
does not establish live-game correctness or clear publication approval.

The current non-GUI tests use temporary fixtures and a fake engine. They check
prompt handling, validation, history interpretation, location precedence,
path isolation, stop-key capture mapping and startup failure behavior. They do not test a real ADB
connection, real engine compatibility, emulator state or purchasing.
Record the candidate's actual command, UTC time, exit result and evidence; the
earlier successful run does not clear a later commit/package.

These tests open GUI windows and require a coordinated Windows desktop:

```powershell
py -3 test_e7_shop_refresh_gui.py
py -3 test_e7_shop_refresh_layout.py
py -3 test_e7_shop_refresh_icons.py
```

Run the full GUI test module for every candidate that changes widgets or
callbacks, including Start through its actual button and live counter reports.
Appearance-only tests do not clear those paths. An isolated desktop can keep
these fake-engine tests from disturbing the user's active desktop. Use the
private Pillow environment when verifying artwork. Fresh normal fixtures and
manual candidates use 12 skystones, 0.3-second delay, backtick stop key, and
random offsets on. Tests of alternate inputs and calibration are explicit
exceptions and never authorize live spending.

Use their fixtures, inspect screenshots for final layout/icon/interaction
changes, and keep visual evidence incomplete when it is unavailable. Linux GUI
support is not claimed by this Windows project.

## Package scope

Use an explicit allowlist. The proposed GUI-only package contains:

- `e7_shop_refresh_gui.py`, `e7_process.py`, `e7_windows_icon.py`, `e7_appearance.py`;
- `launch_e7_shop_refresh_gui.ps1`, `E7 Secret Shop Refresh GUI.cmd`;
- `e7_gui_assets/`, including icon, sounds, credits and provenance;
- `engine-location.example.ini`, packaged `README.md` and `BUILDING.md`, `VERSION`,
  `LICENSE`, `CREDITS.txt`, `UPSTREAM.md`;
- `E7ShopLauncher.cs` and `docs/UPSTREAM-README.md` as source/documentation;
- a launcher EXE only if rebuilt from this candidate's C# source and checked.

The Python GUI and C# launcher source supply the corresponding source for this
GUI-only scope. An engine-bundled release is a different package specification:
first establish/build the exact engine source version and its corresponding
source/build instructions per UPSTREAM.md. Do not imply the previously installed
engine binary came from the cloned source base.

Exclude installed engine binaries, `adb-assets/`, upstream engine assets,
`.git/`, caches, virtual environments, `.local-state/`, scratch files, private
evidence, personal `engine-location.ini`, `ADBconfig.ini`, `ShopRefreshGUI.ini`,
device identifiers, logs, history, `.env*`, backups and shortcuts. Include the
safe example file; personal runtime settings remain with the selected engine.
Retain the supplied icon and its credit/provenance record as requested.

Freeze package copies under ignored `dist/candidates/<version>-rcN/` and record
all SHA-256s. The copied ignored EXE is recovery input, not proof of a build from
this candidate. A self-contained executable has not been implemented. The
maintained `build_release.ps1` builder requires a clean commit, compiles the
launcher and packages the allowlist with `release/README.md` and
`release/BUILDING.md` mapped to the package root. Run it from a separate clean
candidate checkout:

```powershell
.\build_release.ps1 -OutputDirectory 'C:\absolute\new\candidate-directory'
```

It refuses existing output directories and writes an adjacent build manifest
recording the commit, compiler, member hashes and final ZIP hash. The manifest
is local build evidence, not a public package member.

## Optional launcher build

For a source-built launcher, this compiler is present on the assessed Windows
host. Verify it on the actual release host; no compiler installation is implied.
Use a new ignored output directory so old binaries remain untouched:

```powershell
$launcherBuild = Join-Path $PWD 'dist\launcher-build-rc1'
if (Test-Path -LiteralPath $launcherBuild) { throw 'Choose a new launcher build directory.' }
New-Item -ItemType Directory -Path $launcherBuild | Out-Null
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" `
  /nologo /target:winexe /reference:System.Windows.Forms.dll `
  /win32icon:e7_gui_assets\shopkeeper-v2.ico `
  "/out:$launcherBuild\E7 Secret Shop Refresh.exe" .\E7ShopLauncher.cs
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
```

Record compiler and rebuilt EXE hashes. Stage the EXE beside the GUI and process
module in the candidate package before checking `--verify`:

```powershell
$verifiedLauncher = Start-Process -FilePath '.\E7 Secret Shop Refresh.exe' `
  -ArgumentList '--verify' -WindowStyle Hidden -PassThru -Wait
if ($verifiedLauncher.ExitCode -ne 0) { throw 'Launcher prerequisites failed.' }
```

Run that check **inside the extracted candidate directory**. It checks adjacent
source and the Python launcher only; it does not import the GUI, validate the
selected engine folder or prove the package works. Hash the ZIP after final
staging and do not rebuild/repack it after review without creating a new candidate.

## Extracted package and live checks

Inspect the ZIP member list against the allowlist and test extraction into a new
folder containing spaces/non-English characters. Check imports, `--help`, saved
engine-folder configuration and clear invalid-folder handling using fixtures.
Coordinate actual GUI launch/layout/icon tests, including use of the rebuilt
launcher, from that extracted package. Verify credits, licence, prerequisites,
config/history locations, missing-engine instructions and that normal operation
does not write personal data beside the source.

Real engine/ADB/device discovery, calibration and refresh/spending checks require
an explicit live-check request. Identify the selected engine executable and ADB
hashes, engine source/version if known, emulator and permitted test scenario.
Record startup/prompt compatibility, stop behavior, owned-process cleanup and
history results against this candidate. Agree any spending budget before testing;
fake-engine success cannot clear those checks.

## Independent review and publication

Provide exact comparison-base and candidate commits, every package hash, member
list and automated/visual/live evidence to a fresh reviewer using the General
workflow prompt. The reviewer reports blockers and incomplete checks; it cannot
edit, deploy or publish. Publication requires separate approval naming package
hashes and destination. Creating a GitHub fork/origin and pushing are later
authorized publication actions. Keep NitrogenSulfide attribution while the public
name remains undecided.
