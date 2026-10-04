# E7 Secret Shop Refresh GUI

Windows GUI by **NitrogenSulfide (Blue Natto)**, based on Solunium's GPL-3.0
Epic Seven Secret Shop Refresh engine.

## Easy mode — Windows 11

**[Download the Windows app](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/releases/download/v0.1.0-rc20/E7ShopRefresh-0.1.0-rc20.zip)**

1. Extract the **whole ZIP** and open **E7 Secret Shop Refresh.exe**. No Python install needed.
2. Open Epic Seven in an emulator with **ADB enabled**.
3. Follow the app's first-use recognition setup, check your budget, then press **Start refresh**.

Initially tested with **Google Play Games on PC Developer Emulator**, English
Epic Seven and a **1920 × 1080** Android display. Other emulators are unverified.
[Easy setup guide](release/SETUP.md) · [Release page and optional source](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/releases/tag/v0.1.0-rc20)

## Project and development notes

The original upstream source and Git history are preserved, alongside the GUI,
launchers, tests, sounds and icon. The first public preview is **0.1.0-rc20**.

The local **rc39** candidate includes **Control mode → Mouse** for visible
Epic Seven windows, including Google Play Games Developer Emulator and STOVE.
Other discovered emulator windows can use the same transport but remain unverified.
**Start Refresh** brings the selected game forward, opens its recognized
Secret Shop menu, buys detected Covenant/Mystic items, scrolls and refreshes using
your actual pointer and the existing budget, delay, counters and Stop key.
Mouse movement eases into each target. With randomized tap offsets enabled,
Refresh clicks vary slightly inside the recognized button.
Scrolling uses a short eased mouse drag. Its small position and timing variations
follow the same randomization setting; vertical travel stays consistent.
The recommended randomization checkbox also enables the saved **Timing variation**
slider in both ADB and Mouse modes. Choose up to ±0.10 seconds around the base tap
delay; very short delays limit variation to half the baseline. Turn randomization
off for fixed timing. Debug/calibration is available only in ADB mode and keeps a
fixed tap delay. Budgets accept whole Skystone counts, and spending shows used/total.
Recent sessions reload automatically. **Clear** archives the exact history CSV
before clearing it and is unavailable during sessions. The compact sidebar keeps
estimates and calibration help in an expandable section, with scrolling available
when the display needs it. The blue-bean header button opens About & Credits.
Native currency detection also verifies the observed summon name, gold price and
Buy label when icon matching fails. A recognized but uncertain currency row
stops before Refresh, so it cannot silently discard that row.
Leave the PC alone while it runs. Focus or coverage changes pause input for up to
10 seconds; changed geometry or a stale prepared click stops the session.
A supervised elevated check opened the native shop from home and refreshed once
for three Skystone. The owner reports rc34 works; long runs remain unverified.
Unexpected confirmations stop the run before a confirmation click.
Mouse mode verifies the selected window and process, then requires recognized
game controls before sending input. An emulator launcher or unknown screen gets
no pointer movements or clicks. Keep the English home controls or shop visible;
plain symmetric black bars and Google's observed dark title bar can be cropped.
Restored Google windows may have a thin light frame above the dark title bar;
that frame is handled at smaller sizes too. Other emulator toolbars are not guessed.
The Google crop stays fixed for the session so confirmation dimming cannot
change its bounds; moving or resizing the window still stops input. Resize
before pressing Start. An already open Secret Shop does not require visiting home.
Google developer-emulator live refreshes and purchases in rc39 remain unverified.
ADB mode remains available. **Mouse (preview)** is an optional read-only capture
check; regular Google Play Games and STOVE preview capture remain supported.
See [Mouse instructions](release/SETUP.md#mouse-automation--experimental-native-stove).

The window selector uses readable names, keeps your selection across rescans,
and shows the selected capture size and preparation steps. The countdown starts
a readiness check; the app then waits for you to switch to the unobstructed game.
**Cancel preview** remains available. Native STOVE shop recognition succeeded
in an owner-run rc27 preview. The new Mouse session has fake/offline checks;
native purchases and long runs still need supervised checks.
Plain symmetric black letterboxing is cropped before recognition; a maximized
client area is not required to have exactly the same aspect ratio as the game.
Wider native STOVE views are preserved without cropping or stretching the
displayed preview. Hidden controls produce an unrecognized preview with guidance.
After its countdown, preview waits up to 20 seconds for the user to bring the
selected game forward and uncover it; Stop cancels the wait without capturing.

For a new user's beta setup, see [SETUP.md](release/SETUP.md). Players need only the combined player ZIP, with the GUI, matching engine,
upstream ADB tools/item templates and a portable runtime configuration. A separate
full source ZIP is available for developers; players do not need it. SHA-256s
identify both downloads. Recognition references are created locally and personal
state stays private.

The header's ⓘ button opens About & Credits, also shown on first launch for the
selected runtime's saved GUI preferences. Continue or closing that window marks
it seen. Show this on startup is off by default, and can be enabled there later.
It remembers the choice in ShopRefreshGUI.ini alongside sound/theme/device
preferences; keep this file when updating. Full credits and the software licence
are readable offline. The modeless window also remains available during sessions.
The credits header includes a small NitrogenSulfide (Blue Natto) cozy portrait.

The rc8 GUI fixes Start and live counter captions after the rc7 card redesign.
It sharpens the day/night scenes with AI restoration and uses lighter image
opacity (23% dark / 20% light), retaining the sun/moon button and currency icons.
Fresh settings and prepared offline/manual tests use a 12-skystone budget,
0.3-second tap delay, backtick stop key, and randomized tap offsets.
Existing saved settings still take precedence; calibration retains its engine
defaults and requires its existing confirmation.
The rc19 player EXE bundles Python/Tk/Pillow for this appearance. Source-only
launches still need Pillow; the legacy plain fallback remains available there. The prepared local test launcher uses the existing private
environment, without installing anything into system Python. The engine remains
paired with the GUI and retains rc9 handling of startup with hidden controls.
rc16 also fixes selecting an already connected device when several ADB devices
are listed; shop/purchase logic is unchanged.

When home controls fade away, Start waits up to 60 seconds and shows
**Waiting for game**. Click the game to reveal its controls, or open Secret Shop
manually. The session continues when the menu or shop is recognized, without
restarting. No navigation taps or spending happen while controls are unrecognized;
Stop still works. Wallpaper is never used to identify the home screen. If the
controls remain unknown, the session ends with a clear explanation.

The rc10 GUI adds an amber notice above the counters: if hidden home UI is
enabled, click once inside the game before starting. While waiting, the notice
explains that the session continues automatically after the controls return.
Both the notice and waiting status use amber in light and dark mode. The
reminder's × button dismisses the banner until the app restarts; waiting status
and session messages remain available even when the banner is hidden. The engine
is unchanged from rc9. Live insufficient-currency checks are deferred at the
owner's request; no automatic-stop guarantee has been established for that case.

## Run the imported GUI

Use a source Python environment with Tkinter and Pillow and the separately installed upstream ADB engine:

```powershell
py -3 .\e7_shop_refresh_gui.py
```

The default engine folder is `%USERPROFILE%\Downloads\E7 Secret Shop Refresh`.
To use another existing installation, choose its folder:

```powershell
py -3 .\e7_shop_refresh_gui.py --engine-dir "D:\Games\E7 Secret Shop Refresh"
```

To save the choice for double-click launches, copy `engine-location.example.ini`
to `engine-location.ini` beside the GUI and edit its `directory` value. Use the
folder containing `E7ADBShopRefresh.exe` and `adb-assets\platform-tools\adb.exe`,
without surrounding quotes. The saved file is ignored by Git. Relative paths
are resolved beside the GUI; Windows environment variables such as
`%USERPROFILE%` can be used. The GUI does not move or copy an installation.

Selection order is `--engine-dir`, the `E7_ENGINE_DIR` environment variable,
`engine-location.ini`, then the Downloads default. An invalid selection stops
startup with an error before scanning devices or writing settings. Settings and
history remain inside the selected installation; GUI artwork stays beside the
GUI. The PowerShell and CMD launchers also accept `--engine-dir`; the copied EXE
uses the saved file or environment variable.

For the Stop key setting, click its box and press Esc or another supported
single key. Tab remains navigation; unsupported keys leave the selection intact.

**Dark mode** in the top-right header switches appearance and remembers the
choice in `ShopRefreshGUI.ini`. It remains available during a session.

The separately built [live-counter engine](ENGINE.md) sleeps between
stop-key checks and emits counts after each completed buy/refresh. The GUI consumes
those reports immediately. The original engine remains supported with its older
10% milestone updates. Build candidates from recorded source; preserve the
installed binary and test a separate runtime folder first.

The rc5 engine recognizes the Secret Shop menu and checks the shop title and
Refresh button before shop actions. It requires private navigation references;
the supplied local test setup already has them. The old installed engine does
not gain these checks just by using a newer GUI.

The historical copied launcher remains as a recovery artifact and requires
external Python. The rc19 player EXE instead bundles Python/Tk/Pillow and is
built from the maintained GUI source. The existing desktop shortcut still uses
the original General/scripts copy. No shortcut or installed engine was changed.

## Checks

Non-GUI protocol and validation checks:

```powershell
py -3 -m unittest test_e7_shop_refresh_gui.ProtocolTests test_e7_engine_location -v
```

The following tests create GUI windows and should run in a suitable coordinated
desktop session. They use fixtures; passing them does not establish live-engine
or emulator correctness:

```powershell
py -3 test_e7_shop_refresh_gui.py
py -3 test_e7_shop_refresh_layout.py
py -3 test_e7_shop_refresh_icons.py
```

No dependencies were installed and the upstream engine source was not rebuilt
during project extraction. Read [UPSTREAM.md](UPSTREAM.md) for the source and
installed-engine distinction, and [the preserved upstream README](docs/UPSTREAM-README.md)
for Solunium's original setup and build instructions.

## Local release candidate

The component builder creates a GUI-only ZIP for private build evidence, with
source, assets and a launcher compiled from the same clean commit:

```powershell
.\build_release.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe
```

The output is under ignored `dist/candidates/<VERSION>/` with a build manifest.
Existing candidate directories are never overwritten. Use the combined builder
below for the player download. See [RELEASES.md](RELEASES.md) for checks and
publication gates, and [the packaged instructions](release/README.md).

To prepare the player ZIP and separate source ZIP using the existing private engine build
environment, choose a new output directory:

```powershell
.\build_release_assets.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\candidate-directory
```

This adds no installer or service and runs no ADB/game checks. rc14/rc15 improve
setup documentation and packaging; rc16 fixes the multiple-device startup loop.
rc18 combines player files in one ZIP and uses NitrogenSulfide (Blue Natto) as the
maintainer name. Component GUI/engine ZIPs remain private build outputs.

## Ownership and licensing

The new project directory is the maintained source workspace. The previous
General/scripts files and their backups are retained as recovery copies.

Software in this project is released under GPL-3.0; retain the upstream notices
and [LICENSE](LICENSE). Artwork and sounds retain their respective rights and
licences; see [CREDITS.txt](CREDITS.txt) and [asset provenance](e7_gui_assets/provenance.json).
The supplied icon is retained at the owner's request and is not asserted to be
original project artwork or covered by the software licence.

For a future GitHub fork, create the fork under NitrogenSulfide and add it as
`origin`. The existing `upstream` fetch remote points to Solunium. This checkout
has upstream ancestry, so the GUI work can be pushed to the fork without
rewriting Solunium's history. Public hosting is a separate approval step.

## rc19 fresh-install fixes

The player EXE now contains Python, Tk and Pillow. It reads artwork and portable
configuration beside the EXE, never from PyInstaller's temporary extraction path.
Fresh player installs need no system Python launcher or Pillow installation.
The preserved C# launcher and CMD/PowerShell source launchers remain historical
developer entry points; they are not included in the current player ZIP.

Missing recognition opens a read-only, user-directed home/shop capture dialog
before launching the engine. It uses the exact bundled setup engine, verified
against its package checksum, and preserves previous calibration as a backup.
Setup never sends game taps or starts a refresh. A separate explicit Start is
required after successful setup. Private captures remain in the selected runtime.

rc20 adds an amber first-use reminder to use an emulator with ADB enabled.
Dismissing it remembers that acknowledgement in local GUI preferences. The
hidden-UI click reminder still appears while waiting for visible controls.

rc21 is a local candidate adding built-in English Secret Shop recognition. Fresh
users can press Start without first capturing screens. Saved private references
remain supported, and startup recognition failure stops the engine before buys
or refreshes, then offers the screenshot helper. Completing it requires another
explicit Start. The published rc20 preview and its downloads above remain unchanged.

rc22 adds a red warning for missing ADB connections and a bounded background
connection check before engine launch. Start stays available to retry after the
emulator opens. Offline/unauthorized or unselected devices cannot satisfy this
check. The recognition timeout and guided fallback from rc21 are unchanged.

rc23 fixes rc22 accepting Google Play's connected background VM after its window
was closed. Read-only checks now require an open Google Play window and Epic Seven
as the current Android activity. A launcher/history entry does not count. Missing
game/window readiness shows the red banner and launches no refresh engine.
