# E7 Secret Shop Refresh

Windows app by **NitrogenSulfide (Blue Natto)**, based on Solunium's GPL-3.0
Epic Seven Secret Shop Refresh engine.

**[Download the Windows app — v0.1.0](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/releases/download/v0.1.0/E7ShopRefresh-0.1.0.zip)**

1. Extract the **whole ZIP** and open **E7 Secret Shop Refresh.exe**. Python is included.
2. Open English Epic Seven at home or in Secret Shop and close popups.
3. Choose Mouse and select the game window, or choose ADB and select the emulator.
4. Check the Skystone budget, delay and Stop key, then press **Start Refresh**.

| Game client | Mouse | ADB |
| --- | --- | --- |
| Google Play Games on PC **Developer Emulator** | Supported | Supported |
| Official native STOVE client | Supported | Unavailable |

First-release testing is limited to these two clients. Other emulators and methods
have not been tested. Use English game text and a readable landscape 16:9 view,
at least 640 × 360. ADB calibration requires a 1920 × 1080 Android display.

Mouse uses your actual pointer: leave the PC alone while it runs, keep the game
visible and resize before Start. If the game runs as administrator, the app needs
the same permission. The upcoming v0.1.1 offers a restart through Windows' permission
prompt when needed; v0.1.0 users can right-click the EXE → **Run as administrator**.
ADB works through the selected emulator and lets you use
your PC pointer normally. Native STOVE cannot use ADB.

The app reveals idle home controls, recognizes the Secret Shop menu, buys detected
Covenant Bookmarks/Mystic Medals, scans both pages and refreshes within your budget.
It verifies shop controls and confirmation text before continuing; unknown or
changed screens can stop the session. Start with a small supervised budget.

Features include live session counters, used/total Skystone budget, configurable
Stop key, smooth Mouse movement/dragging, bounded tap offsets and timing variation
up to ±0.10 seconds, session history, day/night themes and in-app Quickstart/release
notes. Debug/calibration is ADB-only; Friendship purchases and Mouse preview are
removed.

**[Setup guide](release/SETUP.md)** · **[Release notes](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/releases/tag/v0.1.0)**

The owner reports the ordinary live cases pass on both clients with rc51. The
release preserves rc51's automation code. Automated source, package and saved-frame
tests are recorded separately; they do not establish universal wallpaper/layout
support or long-run reliability. Insufficient-currency stopping has not been
live-tested.

Settings, CSV history and private recognition captures live under `runtime`.
Back them up when updating; there is no automatic updater or migration. Personal
data is excluded from the release ZIPs.

## Source and credits

The optional **E7Source-0.1.0.zip** contains the maintained source and rebuild
instructions. Matching GUI/engine source is also supplied with the player package.
See [build instructions](release/BUILDING.md), [engine notes](ENGINE.md) and
[regression coverage](docs/AUTOMATION-REGRESSIONS.md).

Software is GPL-3.0; see [LICENSE](LICENSE), [CREDITS.txt](CREDITS.txt) and
[upstream notices](UPSTREAM.md). Third-party artwork/audio retain their respective
rights and provenance. This is an independent community tool with no official
endorsement. Upstream source history is preserved.

Optional support: [Buy me a coffee](https://ko-fi.com/bluenatto).
