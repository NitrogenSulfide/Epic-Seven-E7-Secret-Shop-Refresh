# Release checks

The player ZIP supplies the compiled GUI with Python/Tk/Pillow, external artwork,
matching engine and source, upstream ADB tools/templates/notices, and a portable
runtime configuration. The full Source ZIP is an optional developer download.
Follow [AGENTS.md](AGENTS.md), [UPSTREAM.md](UPSTREAM.md) and [SETUP.md](release/SETUP.md).
Preserve original history, licence/credits, installed runtimes and private data.

## Build and automated checks

Build only from a clean exact commit with an explicit private Python environment
using engine-build-requirements.txt. Preserve earlier outputs:

```powershell
.\.local-state\engine-build-venv\Scripts\python.exe -m unittest test_e7_shop_refresh_gui.ProtocolTests test_e7_engine_location test_e7_live_engine test_e7_shop_navigation test_e7_setup -v
.\build_release_assets.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\candidate-directory
```

Record commit, comparison base, dependency/compiler inputs, member hashes and
final player/source SHA-256s. Component ZIPs/manifests/logs stay private. All
builders refuse existing output directories. Build instructions for an extracted
source archive are in [BUILDING.md](release/BUILDING.md) and [ENGINE.md](ENGINE.md).

## Package boundaries

Use the GUI and engine builders' explicit file lists. Include only tracked
artwork/source and tracked upstream adb-assets; never copy an installed runtime.
Generate engine-location.ini with exactly [engine] and directory = runtime.
Generate runtime/E7ADBShopRefresh.sha256 from the matching rebuilt binary.
Omit historical CMD/PowerShell/C# launchers from the player ZIP; its only player
entry point is the compiled GUI EXE. Preserve those files in source history.

Exclude personal INIs, devices, logs/history, setup-captures, gui-navigation,
private images/evidence, .git, .local-state, scratch, virtual environments and
caches. Keep GPL, upstream authorship, asset provenance, ADB notices and bundled
Python/Pillow/PyInstaller/Tcl/Tk dependency licences. Inspect all source-archive
members for private data. Never change reviewed ZIP bytes in place.

Generic English label crops under adb-assets/builtin-navigation are public assets;
their provenance/dimensions/hashes must be inspected. Full screenshots and saved
gui-navigation calibration remain private. Verify a fresh folder with no personal
references can use the built-in set, without writing calibration. Unknown or
ambiguous screens must not cause guessed navigation or spending. Recognition
failure must stop the engine and offer setup; Stop/stale output must not start
another engine or bypass an explicit Start after setup.

## Extracted and GUI checks

Verify ZIP integrity, member hashes/allowlists, required files/document links and
extraction/portable configuration in paths with spaces/non-English characters.
Run the compiled GUI --verify with a JSON verification report under a PATH
without Python/py/pyw. Require frozen=true, Pillow/artwork/Tcl support and the
included runtime path. This creates no GUI window and makes no ADB/game calls.
Run the actual engine's offline --verify and synthetic reference preparation.

Coordinate full fake-engine GUI tests and layout/visual checks on an isolated
desktop where practical. Cover Start, Stop/key capture, per-action counters,
themes/scenery, credits and first-use setup. Record partial/missing visual
evidence honestly. Fake runners must prove setup sends only screenshot commands,
never launches refreshing, preserves old calibration on failure/success and
rejects a mismatched setup-engine binary. A separate explicit Start is required
after setup. Fresh normal tests use 12 skystones, 0.3 seconds, backtick and random
offsets; alternate-input/calibration fixtures are explicit exceptions.

## Review, live game and publication

Automated tests, independent review, live-game checks and publication approval
are separate gates. Give a requested independent reviewer the exact commit/base,
every proposed package hash/member list and evidence. It reports concrete
blockers and incomplete checks; it does not edit, deploy, merge or publish.
Earlier package verdicts never clear a newly built candidate.

Real ADB/device/game checks require an explicit live-check request and agreed
budget/scenario. Bind evidence to the executable/package hashes and emulator.
Check shop entry, refreshing, live counters, Stop/key behavior and owned-process
cleanup. Do not infer game correctness from fixture tests. Insufficient-currency
live cases remain owner-deferred; do not drain the owner's account or claim a
verified automatic stop for them.

Publication requires separate approval naming the exact packages and destination.
Use NitrogenSulfide (Blue Natto) as maintainer and NitrogenSulfide as GitHub account.
Fork/origin/push/publication are later actions; never push to Solunium's upstream.
General's notes/release-catalogue.md and notes/release-workflow.md remain the local
index and reusable handoff; no extra service or CI system is needed.
