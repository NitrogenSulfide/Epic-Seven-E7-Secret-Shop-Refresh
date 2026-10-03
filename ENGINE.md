# E7 live-counter engine candidate

Modified from Solunium's GPL-3.0 E7 ADB engine, maintained by NitrogenSulfide.
Source: `E7ADBShopRefresh.py`. The upstream history remains in the maintained
repository; upstream base `49313d14b24f1b8efbeb49f9a6b2126f9bbd0849`.
This local candidate has not been published or verified in the live game.

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

Use this engine with the matching GUI candidate for live counters. The GUI also
accepts the original engine, whose totals still arrive at 10% milestones.
This ZIP contains no ADB executables, game templates, device settings or history.

## Private navigation references

Keep references in the selected runtime's `adb-assets/gui-navigation` folder.
The three files are `menu-secret-shop.png`, `shop-title.png`, `refresh-label.png`.
They are private runtime assets and are excluded from release ZIPs. On this
owner's prepared rc5 test runtime, they are already derived from the supplied
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
