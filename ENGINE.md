# E7 live-counter engine — v0.1.0

## Friendship Points source feature

The working source adds optional Friendship purchases, off by default, to the
existing Covenant/Mystic item loop in normal ADB and Mouse sessions. Every selected
item is checked on both scans and purchased at most once per generated inventory.
The current item is **Friendship Points**, shown as a green heart: 50 points for
18,000 gold. The upstream `adb-assets/fb.png` shows a retired clover bookmark and
is never loaded or matched for this feature. Friendship uses observed **Currency**
category, full name, price and Buy bounds; the fresh confirmation must say
Friendship Points and 18,000 gold. Contradictory names/prices stop confirmation.

The GUI toggle requires an engine advertising `friendship purchases v1` and
uses structured ADB settings or Mouse `--buy-friendship`. Calibration excludes
Friendship. The existing live `friendship` field now counts completed point-item
purchases; history stores these under `Friendship points`, separately from legacy
`Friendship bookmark` records. Gold totals include these purchases.

Evidence: the existing private saved `client-mystic.png` shop image confirms the
heart, current name/category and 18,000 price; offline Windows OCR identifies
Friendship and Mystic in that image. Fake-transport tests cover Friendship alone,
all item combinations, both scans and duplicate prevention. The private
0.1.4-rc7 trial candidate packages these changes and passed its packaged
fake-transport regressions; they have not been live-tested. A real Friendship
purchase dialog and live completion remain unverified. The February 19, 2026 update replaced Secret Shop
Friendship Bookmarks with 50 Friendship Points; see the
[archived update notice](https://epic7db.com/news/219-thu-update-content).

## Existing release behavior

Modified from Solunium's GPL-3.0 E7 ADB engine, maintained by
NitrogenSulfide (Blue Natto).
Source: `E7ADBShopRefresh.py`. The upstream history remains in the maintained
repository; upstream base `49313d14b24f1b8efbeb49f9a6b2126f9bbd0849`.
The first release preserves rc51's automation code. The owner reports the ordinary
live cases pass on both clients with rc51. Automated checks of these exact rebuilt
packages are recorded separately from that report. Long runs and insufficient-
currency live checks remain unverified. Older candidate notes retain their
historical verification status.

rc51 consolidates normal ADB and Mouse actions in `e7_shop_flow.py`. The
capture/input transports remain separate. Both modes use observed home controls,
one bounded idle-UI reveal attempt, verified shop markers, currency rows and
fresh confirmation checks. Wallpaper itself does not authorize a shop action.
Known modal/loading text blocks the reveal attempt; arbitrary artwork cannot
provide a universal guarantee of hidden-UI recognition.

`e7_frame.py` normalizes landscape 16:9 captures of at least 640 × 360. ADB taps
and drags map back to captured Android coordinates, including detected bars.
The initial crop stays fixed through modal dimming. Changing capture geometry
during a run stops input. Debug/calibration retains its original 1920 × 1080
requirement and separate overlay path. Native STOVE has no ADB transport.

Confirmation OCR uses word bounds and foreground brightness to exclude dimmed
shop rows. Intended summon name and gold price must agree; contradictory items
or prices reject the confirmation. Refresh requires its operation prompt and
rejects costs other than three. Shared fake-transport tests and saved-screen
replays do not constitute live validation of these exact release bytes.
The older candidate notes below describe their behavior at the time.

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
height is assumed. A bounded startup reveal attempt can precede home recognition;
shop-menu and purchase/refresh input require recognized controls. The GUI requires window mouse v9
so engines without verified render-child/input-host support are rejected.
BlueStacks players use a visible `BlueStacksApp` render child belonging to the
selected player process. Its screen bounds are used for capture, visibility
checks and mapped input. Missing, ambiguous, replaced or moved surfaces block
input; sibling emulator overlays do not count as a visible game target.
When BlueStacks disables its render child, Windows hit-testing reports its Qt
input host. Only the enabled direct parent, in the same process and with exactly
the same client bounds, is accepted. Other ancestors and siblings still block.
Home recognition requires Sanctuary, Secret Shop and either Epic Pass or Event
icons in the observed menu layout. Both transports recheck the matched shop
icon before entry and verify the shop before refresh or purchase actions.
The native preflight checks process elevation: a normal app cannot control an
elevated game. It stops with a Run as administrator instruction before activation.
An access-denied token check also blocks input and allows a non-elevated GUI to
offer a user-approved administrator retry. This does not establish that the
player is elevated. A denial after that retry remains blocked; no automatic
session or repeated elevation request is sent.
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

rc46 permits purchase-confirmation buttons up to 500 normalized pixels wide,
covering STOVE's observed 455-pixel combined gold-price/Buy button. List and
refresh-button limits stay at 450. Intended-item/price text checks and fresh
dialog agreement remain required before any confirmation click.

rc48 re-captures incomplete confirmation text within the existing five-second
wait, instead of treating the first mismatch as final. Item/cost checks remain
unchanged; a rejected text result never authorizes input. Persistent mismatch
and changing dialogs save the same private central crops as missing buttons.
Full-flow saved-screen regressions exercise actual confirmation OCR for both
Google and STOVE, including a constructed partial-prompt transition.

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

rc47 replaces the rc42 whole-artwork stability, brightness, quadrant-detail and
any-OCR-text exclusions. If no home controls are recognized, a nonblank frame
without known dialog/loading/game-action labels permits one center reveal
attempt. Incidental wallpaper lettering and animation are accepted. Fresh
shop/home controls are rechecked before that attempt so newly visible controls
do not get hidden again. Wait 0.5 seconds, then require the observed shop icon
and verified shop entry. It remains a bounded probe, not proof of the home page.

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

rc45 identifies the native home controls by the Sanctuary, Secret Shop and
Epic Pass glyph edges in their joint layout, with foreground brightness and
ambiguity checks. This path needs neither wallpaper references nor readable
caption OCR. The existing caption fallback remains for other skins. The saved
Mouse-home CLI uses the same grouped-control recognition as live startup.
Windows sessions register the selected Stop key on the engine's monitor thread
with `RegisterHotKey`/`WM_HOTKEY`, plus held-key polling via `GetAsyncKeyState`'s
high bit. 0.1.4-rc6 also installs a `WH_KEYBOARD_LL` event listener on that thread,
pumping its message queue and latching brief key-down events including injected
streaming input. The listener only tracks the Stop key and chord modifiers;
it never suppresses input or records other keys. Both registration and listener
must succeed before shop input. Completion, Stop and errors release this session's
hook and registration. Diagnostics show readiness, detection source, release or
failure. A Moonlight client must forward the key to this Windows host; keys
consumed by the client or host input restrictions cannot be observed here.
Standalone non-Windows calls
retain the upstream keyboard-hook fallback. GUI shutdown/Stop also retains its
independent stdin command and owned-process cleanup.

Purchased/sold-out currency status is accepted in the availability text or the
right-hand button area of the same recognized item row when there is no active
Buy button. These rows are skipped without adding buys or gold spending to this
session. Missing price/Buy without purchased evidence remains an error; status
on a different row does not permit skipping an available item.

0.1.4-rc7 also recognizes the literal 0/1 stock fraction beside the same Buy label:
the owner's pre-purchased row retained its green Buy button, price and “Only 1
available” text. The name/price path requires the complete currency name,
category and expected price with their existing row geometry before skipping.
The icon path requires its recognized currency icon and an observed button with
Buy and 0/1 inside it. Stock must be immediately left of Buy, aligned vertically
and at a compatible text size; unrelated zeros, other rows and conflicting
fractions cannot authorize skipping. Available 1/1 retains purchase verification.
The same guard covers Friendship, Covenant and Mystic. Whole-list OCR and any
bounded row retries are cached for each captured frame
and invalidated by the next capture. If small/dim stock or price text is missing,
row OCR enlarges the pixels and normalizes contrast. Stock from the first read
is retained only when both reads agree on Buy bounds; conflicting readings stop.
0.1.4-rc8: Windows OCR can assign a small text angle to a sparse crop such as
one enlarged row, and then reports word bounds rotated about the crop centre.
On Google Play Games a purchased Friendship row at the bottom of the list was
read at about -4 degrees, moving its Buy bounds ~22 pixels from the whole-list
read and stopping the session as ambiguous. Word bounds are now rotated back to
the level view before any pairing. An unclear row (ambiguous stock, ambiguous
names, or unverifiable price/Buy) is re-read from up to two fresh captures 0.4
seconds apart before stopping; no input is sent and every row check reapplies.
Visibility, Stop and partly offscreen rows keep their existing handling.

0.1.4-rc9: display tints reach the capture. With f.lux on native STOVE the
Secret Shop icon measured about RGB 254/186/108 and failed the near-white icon
mask, while a new Milestone of Radiance entry broke the grouped layout. The
caption path now white-balances only the small icon search area (skipped
unless a bright symbol is present) before the unchanged template match, and
the grouped check uses the brightest channel instead of luma. Uniform 50%
dimming of every visible-menu corpus frame still yields no target. Shop text
OCR starts at x=960 instead of 1010 after one client's framing clipped
"Currency". Recognition changes are gated on the private real-frame corpus
(check_frame_corpus.py, docs/RECOGNITION-TESTING.md).
Neither wallpaper art nor
a saved shop background is used to decide stock. Counters and gold totals include
only purchases completed by this session.
