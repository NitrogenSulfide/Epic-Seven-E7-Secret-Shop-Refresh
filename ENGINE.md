# E7 live-counter engine candidate

Modified from Solunium's GPL-3.0 E7 ADB engine, maintained by
NitrogenSulfide (Blue Natto).
Source: `E7ADBShopRefresh.py`. The upstream history remains in the maintained
repository; upstream base `49313d14b24f1b8efbeb49f9a6b2126f9bbd0849`.
This local candidate has not been published. Automated checks and the owner's
reports about earlier candidates are separate from verification of these exact
download bytes. Insufficient-currency live checks remain deferred.

The stop-key loop sleeps 20 ms between checks instead of continuously polling.
The engine flushes `E7GUI_STATS` JSON after a completed buy sequence and refresh.
Counts describe engine-completed actions, not an independent reading of game
balances. Purchase labels count buys, not individual bookmarks/medals awarded.
ADB tap failures abort rather than incrementing the affected counter.

In rc5, `e7_shop_navigation.py` replaces the original three fixed menu taps with
recognition of a private Secret Shop text reference. It sends at most one
navigation tap, waits up to eight seconds for the shop title and Refresh label,
and stops on unknown or ambiguous screens. Starting inside the verified shop
sends no menu tap. Shop-page scans and the beginning of buy/refresh sequences
also require shop verification. This is template matching, not a trained model.
English UI and 1920x1080 ADB screenshots are required. User interaction, popups,
other layouts/languages or stale references can cause recognition to fail;
failure stops the run rather than falling back to old menu coordinates.

In rc6, shop text uses brightness-normalized grayscale correlation with a 0.90
minimum, rather than thin binary edges. This fixes rejection of the owner's
raw ADB shop frame when references came from resized desktop screenshots.
Both title and Refresh are still required; ambiguous matches are rejected.
Menu matching retains the rc5 edge detector. Failed verification reports marker
scores and says the shop may already be open, rather than claiming entry failed.

In rc9, unknown startup frames enter a bounded 60-second wait. The engine checks
once per second for the recognized menu text or both shop markers, sending no
taps while waiting. The GUI asks the user to reveal the UI or open the shop,
and resumes without requiring another Start. Stop cancels the wait. Timeout
still aborts before purchasing or refreshing. This handles faded home controls
without relying on wallpaper, and does not weaken the existing checks after
shop entry. No automatic wake-up tap is used because an unknown frame cannot
establish which page or action is under a coordinate.

In rc16, selecting an already connected device leaves the device-selection loop
even when more than one ADB device is listed. The original loop repeated the
Device prompt indefinitely in that case. A bounded actual-entry-point test with
fake ADB output covers both selectable devices and stops before engine creation.
Shop navigation, purchase/refresh logic and polling behavior are unchanged.

Use this engine with the matching GUI candidate for live counters. The GUI also
accepts the original engine, whose totals still arrive at 10% milestones.
The combined player ZIP includes this engine under `runtime`, alongside tracked
upstream ADB tools/item templates and their notices. It contains no personal
device settings, game screenshots or history. The full Source ZIP is a separate
developer download; players do not need it. Follow `START-HERE.md` at the player
ZIP's root (or `release/SETUP.md` in the source checkout) for fresh setup.

## Private navigation references

Keep references in the selected runtime's `adb-assets/gui-navigation` folder.
The three files are `menu-secret-shop.png`, `shop-title.png`, `refresh-label.png`.
They are private runtime assets and are excluded from release ZIPs. On this
owner's prepared test runtime, they are already derived from the supplied
home/shop screenshots; the full screenshots remain private.

To prepare another runtime, use uncropped 16:9 English home/shop screenshots
showing the current left-hand menu, shop title and Refresh button. Use the
rebuilt engine's offline utility, which requires no separately installed Python:

```powershell
.\E7ADBShopRefresh.exe --prepare-navigation-references --home C:\path\home.png --shop C:\path\shop.png --output C:\path\test-engine\adb-assets\gui-navigation
```

Use a new destination; existing calibration is preserved. The utility reads
images, normalizes reference crops and checks them against those same images.
It makes no ADB/game calls. This calibration check is not independent live
verification; a human must still test the corresponding game layout.

## Safe test preparation

Stop the old session first. Prepare a separate test folder containing this
`E7ADBShopRefresh.exe` and a copy of your existing `adb-assets` folder. Point the
GUI at the test folder with `--engine-dir`. Preserve the installed engine and
your existing history. Use a small budget and confirm stop behavior and counters
in Google Play Games Developer Emulator before treating this as usable.
Other emulators remain unverified.

`E7ADBShopRefresh.exe --verify` checks bundled imports only. It does not connect
to ADB, install keyboard hooks, inspect the game, or spend currency.

## Rebuild on Windows

Use Python 3.13 with a private virtual environment; dependency installation is
an explicit setup step, not performed by the builder. The original upstream
`requirements.txt` is preserved; the minimal build pins are separate.

```powershell
py -3 -m venv .local-state\engine-build-venv
.\.local-state\engine-build-venv\Scripts\python.exe -m pip install -r engine-build-requirements.txt
.\.local-state\engine-build-venv\Scripts\python.exe -m unittest test_e7_live_engine -v
.\.local-state\engine-build-venv\Scripts\python.exe -m unittest test_e7_shop_navigation -v
.\build_engine_release.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\engine-candidate
```

Build from a clean committed checkout. The builder does not run the real engine,
copy personal state, or modify the installed engine. It records the exact commit,
Python/dependency versions and binary/package hashes beside the ZIP. Third-party
licence files are included under `third-party-licenses/`.

### Rebuild from a downloaded source archive

The Source ZIP and player ZIP do not contain Git metadata. The maintained builder
requires Git evidence, so use this direct compilation recipe from the player's
`runtime` directory or the full extracted source instead. It needs Python 3.13 and installs build tools
only into the new private environment you choose; it does not run the game.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r engine-build-requirements.txt
.\.venv\Scripts\python.exe -m unittest test_e7_live_engine test_e7_shop_navigation -v
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --console --name E7ADBShopRefresh --distpath rebuilt-engine --workpath rebuild-work --specpath rebuild-work .\E7ADBShopRefresh.py
.\rebuilt-engine\E7ADBShopRefresh.exe --verify
```

Use new environment/output directories to preserve any previous builds. `--verify`
checks bundled imports only. A locally rebuilt binary will have a different hash
and is not covered by the downloaded candidate's review or approval. GUI source
and its launcher rebuild instructions are supplied at the player ZIP's root;
the full Source ZIP also includes the maintained builders and tests.

For rc19 players, missing references open a guided home/shop screenshot dialog.
It checks the bundled engine checksum before invoking its offline preparation
utility. It performs no game taps and never starts refreshing automatically after
setup. The manual utility remains available for developers and older candidates.

rc21 adds generic English label crops under `adb-assets/builtin-navigation`.
The navigator checks saved references and built-in templates, requiring a complete
shop-marker pair from one set and agreement between recognized menu targets.
Missing/unreadable saved references can fall back to built-in templates without
overwriting personal calibration. Startup recognition failure exits with code 3
and an `E7GUI_SETUP_REQUIRED` message; the GUI offers the screenshot helper after
the engine exits. No purchase/refresh has started on this path, and another
explicit Start is required after setup. Existing mid-session shop guards remain.

`--check-navigation-frame PATH` checks a saved screenshot entirely offline from
the runtime directory. It prints JSON with `home`, `shop` or `unrecognized` and
sends no ADB commands, starts no keyboard hooks and makes no game actions.
