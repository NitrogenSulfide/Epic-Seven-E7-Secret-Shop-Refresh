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

rc31 adds a Mouse transport around this same loop. rc37 also accepts selected
emulator windows, including Google Play Games Developer Emulator, without an
EpicSeven.exe requirement. Process access, window identity, client geometry and foreground visibility
are checked before input. Capture keeps the full native client (or clearly bounded
black-bar crop); normalized recognition points map back to desktop coordinates.
Google Play Games windows can additionally crop an observed mostly black custom
title bar when the remaining image fits the game aspect ratio. No fixed toolbar
height is assumed. Home/shop recognition is required before input, including
hover; unknown emulator screens receive none. The GUI requires window mouse v6
so an older STOVE-only engine cannot be used accidentally.
The native preflight checks process elevation: a normal app cannot control an
elevated game. It stops with a Run as administrator instruction before activation.
Mouse mode brings the game forward once after Start, does not resize it, uses
verified cursor movement and an 80 ms click hold. rc32 adds
an eased pointer glide lasting 0.12–0.38 seconds according to travel distance,
scaled to the displayed game size. Stop and visibility are checked at each step;
the configured tap delay still applies separately. rc36 accepts `--tap-jitter`
from the GUI's saved slider in both ADB and Mouse modes: 0–0.10 seconds either
side of the baseline, limited to half the base delay to keep short delays positive.
The saved baseline stays unchanged. Randomization off and ADB calibration use
the exact configured delay; loading waits and recognition deadlines stay fixed.
Direct engine calls without the option retain rc35's ±10%/0.05-second default.
rc33 replaces wheel scrolling
with an eased upward drag along the original ADB swipe's vertical distance.
Randomization translates the swipe by at most ±12 horizontal / ±6 vertical
normalized pixels, adds at most ±3 horizontal endpoint pixels, and varies the
drag time from 0.28 to 0.36 seconds. With randomization off it uses a fixed
0.32-second drag. A held drag releases immediately on Stop, focus/coverage loss,
geometry change or input failure, with no focus-resumption wait while held.
Drag endpoint delivery is checked before release; it never uses a placement
fallback while held. Parent cleanup also releases after forced termination.
Native drag scrolling has fake-input verification and still needs a live check.
Native capture samples the client
interior; each action checks its exact destination. Focus/coverage changes pause
input for up to 10 seconds; resumed capture discards stale frames and renews recognition timeouts. Changed geometry or a stale prepared click stops it.
Item detection is restricted to the shop icon column; Buy and confirmation clicks
use observed button bounds. rc34 adds native name/price recognition when a currency
icon does not match: the summon category, full Covenant Bookmark/Mystic Medal
name, expected gold price and active Buy label must align on one row. Shop OCR
is cached only for the same captured RGB image; a preceding purchase invalidates
it. Name/price buys target the observed Buy label; icon-based buys use the button's
right side. Both keep randomized clicks away from the stock-count inset.
Partial bottom rows may advance from the first to the second scan; uncertain
currency rows on the second scan stop before Refresh. Confirmations still verify
the intended item and price. Already purchased currencies are skipped before
second-page detection. The owner's saved native Mystic row reproduced the old
icon rejection; offline recognition and a fake both-currency purchase sequence
cover this fix. Live native buying remains unverified.
Refresh uses the recognized label, with small offsets
up to ±14 horizontal and ±7 vertical normalized pixels when randomization is
enabled and its green button is observed. Otherwise it retains the label point.
Confirmation text
is read locally using Windows' built-in English OCR and must match the intended
item/price or the native "Use Skystone to refresh?" prompt for the fixed three-skystone refresh. Native blue Confirm labels require an observed paired Cancel label; green confirmation buttons remain supported. Unexpected, changed or unreadable dialogs
stop before confirmation. Debug/calibration remains an ADB feature. No ADB call
is made by a Mouse session. An elevated live check opened native Secret Shop from home and completed one refresh costing three Skystone without purchases. Native purchases, long runs and frozen-GUI Start remain unverified.

Native home entry supplements menu templates with observed OCR word bounds and
home labels. The observed bright icon above the native caption is the click target; the caption itself is not clickable. A private known hidden-home reference permits one reveal click; no
home image is shipped in the public package. Native pause/stop events carry a
reason rather than claiming a Stop key was pressed. The GUI saves private native
session diagnostics under `runtime/mouse-session-logs`. Missing confirmations save only central before/after crops under `runtime/mouse-failures`. STOP on stdin cancels the native loop before forced job termination; button release runs on interrupted clicks and parent cleanup.

`--check-mouse-confirmation FILE --operation refresh` reads a saved full-client
image offline and reports a text match without input, hooks or ADB. A buy check
also needs `--item-name "Covenant bookmark"` or `"Mystic medal"`. The temporary
OCR crop stays local and is removed on exit; recognized text is not logged.

`--check-mouse-items FILE` runs the purchase detector on a saved shop-client image
offline and reports verified currency names, prices and Buy targets. It creates
no mouse session, capture, keyboard hook, ADB connection or purchase.

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

## Read-only Mouse preview

rc41 also recognizes a private known STOVE home image after modest changes to
the window's aspect ratio. Broad image-feature agreement identifies its framing;
aligned pixel differences must still reject dimmed dialogs, popups and changed
pages. This only enables the existing guarded reveal-controls and Secret Shop
entry sequence. In rc42, an unfamiliar stable artwork-only view with no full-frame OCR text
permits one center reveal probe. The fresh frame must still qualify immediately
before input. The probe is never repeated during this startup attempt; observed
home-menu recognition and shop verification are required afterward. It sends
no Refresh or purchase before the shop markers are verified.

The rc24 engine also supports `--preview-mouse-frame PATH --output REPORT.json`.
This early CLI branch analyzes an existing game-client screenshot with the same shop
references and writes normalized targets/item detections. It exits before ADB
initialization, keyboard hooks or the refresh loop. This remains an offline developer utility; Mouse preview is no longer an app mode.
Screenshots/reports are private runtime data. This preview branch sends no mouse
input. The engine builder includes `e7_mouse_analysis.py` in
both the binary and corresponding source distribution.

rc38 fixes dialog-induced crop changes in Google Play Games Mouse sessions.
The Google client crop is established by the initial screenshot and reused while
window identity and physical client bounds remain unchanged. Confirmation dimming
cannot shift that crop. Real moves/resizes still stop before input; dialog text
and button stability checks still apply.

rc39 recognizes the thin light top edge on restored Google windows before
locating the dark custom title bar. The header can occupy up to 20% of a small
client, but its remaining game area must still fit 16:9 and be at least 640 by
360. A maximum eight-pixel edge may precede it; colored toolbars are rejected.
Private known hidden-home matching additionally accepts native-home/google-hidden.png,
without replacing native-home/hidden.png. These references stay outside ZIPs.

rc43 re-recognizes the fresh home icon before clicking instead of comparing
animated wallpaper pixels. A binary native Secret Shop icon mask supplements
component detection, and joined SecretShop OCR is accepted. Menu templates
authorize the icon above the caption, not caption clicks. Home-entry failure
saves only a private left-menu crop and recognition details under mouse-failures.

rc44 accepts the observed native Shop-to-Shoo OCR descender error in the
same home context. A supervised live native hidden-home reveal and Secret Shop
entry passed without refreshing or purchasing. Capture/input APIs were unchanged.
