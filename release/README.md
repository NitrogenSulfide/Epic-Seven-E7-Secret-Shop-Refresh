# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

Version **0.2.7** reworks the settings panel (control-mode cards, a budget slider,
Buy tiles, toggle pills) and saves settings by itself. Version 0.2.6, released only
as part of 0.2.7, lets you choose which items to buy (Covenant, Mystic,
Friendship Points), calls out "Covenant!" / "Mystic!" on each purchase, moves timing
into a collapsed Advanced section (older custom timing is reset once), and waits up to 15 seconds when the game opens the refresh or buy
confirmation but leaves it blank (probably waiting on the server), instead of
stopping with "The refresh confirmation was not recognized". Version 0.2.5 reads the shop on Windows installed without English text
recognition (it uses another installed Latin-script OCR language) and says why when
Windows OCR fails, instead of a generic "could not read the confirmation". It also
recognizes the shop in maximized windows wider than 16:9 and reads shop rows more reliably when OCR splits or loses a small label. Version 0.2.4 pauses while the mouse rests on a windowed game (the game
cancels Background clicks then) and recovers when the game ignores a Buy, Refresh
or Confirm click, seen after buying from the bottom row of the scrolled shop. Version 0.2.3 waits for a refresh
dialog the game ignored to close instead of stopping with "The refresh confirmation
was not recognized". Version 0.2.2 made
Background runs recover when the pointer passes over the
game (a covered Refresh label, a swallowed menu or Confirm click) and adds a plain
next-step line to the compact tracker. Version 0.2.1 added **Background mode** for
Epic Seven on Steam and STOVE: clicks go to
the game window directly and frames are read from the window, so your pointer is
never moved and other windows may cover the game. Background and Mouse refreshes
are faster (about 5–6.5 seconds per refresh on Steam at 2560 × 1440, down from about
8.5). It also includes the 0.1.4 trial changes: the global Stop key, optional
Friendship Points purchases, remaining-time estimates, BlueStacks fixes and warm
display tint handling. See CHANGELOG.txt or About & Credits → Release notes.
Players need only **E7ShopRefresh-0.2.7.zip**; extract it into a fresh folder.
New settings start in Background mode. Your existing saved mode is preserved; the
app offers a one-click switch when another mode suits the game it finds.

Extract the whole ZIP and open **E7 Secret Shop Refresh.exe**. Python, Tk and
Pillow are included in this EXE. Artwork, the matching compiled engine, ADB tools
and templates are arranged beside it, with the runtime path configured.
Follow [START-HERE.md](START-HERE.md) or [SETUP.md](SETUP.md) for Steam/STOVE, emulators and
automatic shop recognition. A guided recognition helper is offered only when
startup recognition fails. The optional Source ZIP is for developers.

**Steam or STOVE (most players):** keep **Control mode → Background** (the
default), select the game and press **Start Refresh**. The app always opens as
administrator (the game runs as administrator too), so Windows asks for permission
each time you open it; choose Yes. You can keep
using the PC: input waits while the pointer moves over the game and resumes once it
has been still for a second. Don't minimize or resize the game during a run. Only
one Epic Seven window may be open.

**Tips for a smooth Background run**

- **Two monitors work best:** game on one, everything else on the other.
- **One monitor:** leave the game open behind your other windows. Covering it is
  fine, but **never minimize it**; a minimized game stops drawing and the run stops.
- Keep your pointer off the game window, still or moving (park it on the compact
  tracker bar, the taskbar or another monitor). Any pointer over the game pauses
  input, because the game cancels the app's clicks while it rests there.
- Start from the home screen or an open Secret Shop, with no Refresh or Buy dialog
  left open.
- Don't resize the game, switch it to or from fullscreen, or open a second Epic
  Seven window during a run.
- Keep the PC awake: don't let it sleep or lock during a run.
- Try a small budget first. The Stop key (default `` ` ``) works from any window.

**Emulators and Google Play Games:** choose **Control mode → Mouse** (STOVE also still works in Mouse), select Epic Seven and press
**Start Refresh**. The app brings that game forward and uses your actual pointer
to open its recognized shop, buy Covenant/Mystic items, scroll and refresh.
If no home controls are recognized, startup can try one center click, wait
briefly, then locate the Secret Shop icon. No saved wallpaper is required;
animation and incidental artwork lettering are accepted. Known dialog/loading
controls and blank captures block the attempt. Start from home or Secret Shop.
Your budget, delay, randomized offsets, counters and Stop key apply.
The app opens as administrator, so elevated games and emulators need no extra
restart.
Leave the PC alone until it stops. Focus or coverage changes pause input for up to 10 seconds;
a changed window or an unrecognized confirmation stops the session. The game keeps its current size. Use normal settings; Debug
remains an ADB feature. Saving settings also saves your control mode without
starting a session next time. The owner regression-tested Mouse and ADB with the rc3 candidate used for this
release. Begin with a small supervised budget on your own setup. Keep English game text readable.

**ADB (optional, emulators only):** use Google Play Games on PC Developer Emulator, English Epic Seven and a
landscape 16:9 Android game view of at least 640 × 360; other emulators are unverified. Press Start in ADB
mode to try the built-in English templates. If the helper is
needed, it only reads screenshots; press Start again after it succeeds.
Start checks the selected ADB connection first. A red banner explains missing
connections without launching the refresh engine; open the emulator, enable ADB
and press Start again. Idle scans update every 10 seconds.
An ADB connection alone is not enough: Epic Seven must be active inside the
emulator, and the Google Play Games window must be open. Its background VM can
stay connected after closing the window. Other PC apps can retain focus.

Normal fresh settings are 12 skystones, 0.3-second
delay, backtick stop key and randomized offsets; saved settings take precedence.
Live counters report engine-completed buys/refreshes, not confirmed balances.
Insufficient-currency stopping remains unverified. Keep initial runs supervised.
Settings and session history live in `%LOCALAPPDATA%\E7 Secret Shop Refresh`
(or `E7_DATA_DIR`) and carry over to new releases; the first start copies them
once from the `runtime` folder beside it and leaves that folder untouched (for
the first upgrade from 0.2.7 or older, copy your old settings and
`ShopRefreshHistory` into the new `runtime` before starting). Private
recognition captures and diagnostic logs still stay under `runtime`; back those
up before removing the extracted folder. No updater exists.

GUI source is supplied beside the EXE, and matching engine source is in `runtime`.
See [BUILDING.md](BUILDING.md), [ENGINE.md](ENGINE.md) and [UPSTREAM.md](UPSTREAM.md).
Source launches require a developer Python environment with Tk and Pillow; the
player EXE does not use the system Python launcher. Old CMD/PowerShell/C# launchers
remain in the full source history and are not player entry points.

Software is GPL-3.0; see [LICENSE](LICENSE) and [CREDITS.txt](CREDITS.txt). Solunium's
original notices and the artwork/audio credits are retained. Dependency licences
are under `runtime/third-party-licenses`, with ADB notices in its tool folder.

## Quickstart and tested clients

About & Credits contains Quickstart and bundled Release notes tabs. The main
screen’s Buy me a coffee button opens https://ko-fi.com/bluenatto only when clicked.

Testing has been limited to Epic Seven on Steam (Background mode, Windows 11 and
Linux), the official STOVE client (Background since 0.2.1, and Mouse) and Google
Play Games on PC Developer Emulator (Mouse and ADB).
Other emulators and methods have not been tested. Both modes buy Covenant
Bookmarks and Mystic Medals by default. Optionally enable **Also buy Friendship
Points** for the current heart item (50 points for 18,000 gold per buy), using
this trial's matching engine. Calibration excludes Friendship. Friendship
purchases have been verified live in Background mode on Steam.
