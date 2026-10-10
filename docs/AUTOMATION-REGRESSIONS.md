# Supported automation and regression coverage

| Game client | Mouse | ADB |
| --- | --- | --- |
| Google Play Games Developer Emulator | Supported | Supported |
| Official native STOVE client | Supported | Unavailable |
| Other emulators | Unverified | Unverified |

Normal sessions share `ObservedShopFlow` in `e7_shop_flow.py` for home entry,
currency rows, purchases and refresh confirmations. `E7ADBShopRefresh.py` owns
Android capture/input and the outer inventory/budget loop. `e7_mouse_refresh.py`
overrides capture/input for Windows; `e7_native_mouse.py` owns cursor movement,
visibility, Stop and held-button cleanup. `e7_frame.py` normalizes recognition
frames and maps observed ADB targets back to Android coordinates. ADB calibration
keeps its legacy overlay path and requires a 1920 × 1080 Android display.

## Required regressions

`test_e7_shared_flow.py` exercises both fake transports with shipped recognition
templates. It covers hidden home controls, seeded capture sizes, shop entry,
both currency purchases, two consecutive refreshes, budget counts, invalid or
changed capture geometry, contradictory confirmation text and Stop before
confirmation. `test_e7_mouse_refresh.py` covers fresh recognition after a pause,
transient coverage before input, persistent coverage, fresh changed dialogs,
partial rows, randomized targets and no replay after mouse-down. Navigation and
GUI tests retain their own contracts.

The live acceptance check for each supported combination starts on idle home,
reveals controls once, opens Secret Shop, scans both pages and completes at least
two refreshes. Separately verify actual Covenant and Mystic purchases when the
items are available. Repeat at more than one actual game size and wallpaper.
Confirm Stop and persistent coverage prevent another input, and counters reflect
completed actions. Do not label screenshot resizing as live resolution testing.

Normal capture supports a landscape 16:9 game view of at least 640 × 360. Mouse
also accepts wider native STOVE clients up to a 2:1 aspect ratio, identified by
the verified `EpicSeven.exe` process. Full-capture coordinate tests and shared
hidden-home, currency and repeated-refresh tests cover 1920 × 1010, 3840 × 2019
and 1920 × 1035. This exception does not change ADB/emulator validation. Resize
before starting; changing capture geometry during a session stops input. Google
desktop window size and its Android framebuffer size are different quantities.

## Limits of offline evidence

Mock captures and inputs never contact a game or spend currency. Real OCR over
saved screenshots checks recognition, but cannot verify live focus, permissions,
input delivery or rendering timing. Synthetic dialogs verify rejection and action
sequencing; they do not replace real purchase dialogs.

Wallpaper matching is optional. Unknown artwork permits one bounded reveal
attempt only when blank captures and recognized dialog/loading controls are
absent. Home/menu and shop controls must then be recognized. Arbitrary artwork
can imitate UI or produce misleading OCR, so universal wallpaper recognition is
not guaranteed. Maintain rejection guards rather than accepting unknown screens
as confirmed home or shop.

Source tests, packaged tests, frozen offline checks and live checks are separate
results. Record exact candidate/package hashes and unresolved live checks for
each candidate. Never infer an exact-byte live pass from an earlier release.
## BlueStacks private trials · 2026-10-09

After the rc4 trial was supplied, the owner reported both ADB and Mouse working
with maximized and smaller BlueStacks windows, including hidden home controls.
The owner also reported that Stop worked only while the refresher GUI had focus.
This is owner-reported evidence; an exact package hash was not confirmed in that
report. It does not verify the new rc5 global Stop implementation.

Rc5 adds Windows system-wide hotkey registration, a fifth heart-icon Friendship
buys counter, diagnostics readiness/counters, and Excel columns for current
Friendship buys and points gained. Legacy Friendship Bookmark counts remain
separate. Native message-queue tests post only to an owned, hidden-desktop fixture;
no keyboard input is simulated. Physical global-key behavior with the emulator
still needs a supervised live check.

The owner reported rc5 still missing global Stop while working through Moonlight,
and a new session stopping on Friendship Points bought beforehand. Rc6 widens
same-row purchased status recognition to the button area and adds a pumped,
non-suppressing keyboard event listener that accepts injected presses. Tests
cover released injected events without WM_HOTKEY or held state, listener cleanup,
and pre-purchased Friendship rows across fake ADB, Google Mouse and STOVE Mouse.
These tests do not establish live Moonlight delivery or the exact purchased-row
OCR from the owner's game; the supplied screenshot contains the error text only.

The owner clarified that an apparent available-Friendship skip was caused by
leaving its optional setting disabled. No default was changed. A subsequent
pre-purchased Friendship failure with buying enabled persisted in rc6.
The supplied row crop shows 0/1 beside Buy while its price and “Only 1 available”
remain visible. Windows OCR reads the stock fraction; normal text normalization
had removed its slash, and rc6 only recognized purchased/sold-out wording.

Rc7 pairs that literal fraction with the same Buy control, independent of
wallpaper. Text fallback retains full name/category/price guards; icon matches
also check stock before returning a purchase target. Fake ADB, Google Mouse and
STOVE Mouse cases retain pre-bought icons/buttons, skip each pre-bought currency,
buy the remaining available currencies, refresh once and verify costs/counts.
Available Friendship with buying enabled/disabled, normal Covenant/Mystic,
unrelated stock, missing controls and ambiguous stock have separate checks.
The crop is private evidence, not a full shop screenshot. Reconstructed placement
and background variations are offline fixtures, not live game screenshots.
No new desktop input, ADB session or currency spending is used for these checks.
Actual rc7 input/purchases, remote Stop delivery and an independent raw shop
fixture remain separate incomplete checks.

Offline Windows OCR passed 18 reconstructed-crop combinations (three sizes,
two brightness levels and three surrounding backgrounds). The row retry uses
enlargement/contrast and original-view bounds. Conflicting stock between reads
or changed Buy bounds stops; only matching controls can retain a stock reading.
