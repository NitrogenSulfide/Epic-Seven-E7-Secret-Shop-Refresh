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

Use this engine with the matching GUI candidate for live counters. The GUI also
accepts the original engine, whose totals still arrive at 10% milestones.
This ZIP contains no ADB executables, game templates, device settings or history.

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
.\build_engine_release.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\engine-candidate
```

Build from a clean committed checkout. The builder does not run the real engine,
copy personal state, or modify the installed engine. It records the exact commit,
Python/dependency versions and binary/package hashes beside the ZIP. Third-party
licence files are included under `third-party-licenses/`.
