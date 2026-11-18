# macOS mode — design (draft)

Status: design only. No macOS code exists in the engine or GUI yet. Branch
`work/macos`, cut from `work/linux-steam`.

Target: Epic Seven's App Store **iPad app running on Apple silicon Macs**
(probed on an M4 Mac mini, macOS 26.6.2). There is no Steam/STOVE client or
ADB on this setup.

## What the probes established

Throwaway probes (`scratch/`, ignored) on 2026-11-15 and 2026-11-17. Each
result has screenshots; clicks only touched the Arena and lobby navigation.

| Question | Result |
|---|---|
| Capture the game window (ScreenCaptureKit, desktop-independent window) | Yes: in front and 100% covered, at full Retina resolution |
| Is the covered capture live? | Yes: the lobby banner rotated between covered frames |
| Click via `CGEventPostToPid`, covered (plain or with window number) | No |
| Click via `CGEventPostToPid`, game in front | No |
| System-wide click via `CGEventPost(kCGHIDEventTap)`, game in front | Yes: 8 of 8, screen changed within 0.7–0.8 s |
| Same click while the user moves the mouse | Landed; the pointer jumps for ~0.5 s |
| Window | 1920 × 985 pt (3840 × 1970 px at 2×), including a 32 pt (64 px) title bar |
| Game area at that size | 3840 × 1906 px = **2.015 : 1**, beyond the 2.0 limit of the stretched path |
| Can the window be resized? | Yes, freely: 515 × 699 to 1920 × 985 pt seen (Phase 0 guide, 2026-11-17) |

Consequences:

- **Foreground only.** Capture works in the background, but input needs real,
  system-wide events with the game frontmost. This is the Windows *Mouse* model
  (takes over the pointer), not *Background*.
- **Layout follows the window shape.** A 2 pt height change moved the Arena tab
  column ~64 px. Nothing may assume fixed positions from one window size.
- **Menus fade in** when the game becomes active. A capture is trusted only
  after it settles (the shared flow's settled screenshots already do this).
- **`NSWorkspace.frontmostApplication()` goes stale** in a process without a
  run loop. Focus must be read from the window server's live stacking order.

## Architecture

Follow the Linux port: reuse the shared flow, add a transport.

```
e7_shop_refresh_gui.py ──launch──▶ E7ADBShopRefresh.py --macos-session …
                                        │
                              e7_macos_refresh.py   (E7MacShopRefresh, thin;
                                        │            dry run like Background)
                              e7_mouse_refresh.E7MouseShopRefresh
                                        │  transport=
                                 e7_macos.MacMouse   (new)
                       ScreenCaptureKit capture · CGEventPost input · guards
```

`MacMouse` implements the interface `WindowsMouse` and `BackgroundGame` already
share: `screenshot()`, `click()`, `move()`, `drag()`, `guard()`,
`pause_revision`, `view`, `native_stove`, `close()`. No change to
`e7_shop_flow.py` is planned. A change there would mean the design is wrong
and should be revisited first.

### Target identity

- Find the game by owner name `Epic Seven` and its bundle identifier
  (`NSRunningApplication(pid).bundleIdentifier`). Refuse when zero or more than
  one normal-layer game window exists.
- Record pid, `CGWindowID` and bounds at start. Any change (closed, moved,
  resized, relaunched) stops the session, as `WindowsMouse` does.

### Guard (before every capture and every input event)

1. Session active (Stop not requested).
2. Same window id, pid and bounds.
3. **Frontmost:** the topmost normal-layer window in
   `CGWindowListCopyWindowInfo(OnScreenOnly)` belongs to the game.
4. **Uncovered:** no window above the game in that list overlaps the game's
   interior samples or the action point. This includes higher layers
   (notification banners, floating panels), excluding the cursor and menu bar.
5. **User idle:** the pointer is where `MacMouse` last put it. If the user moved
   it, pause instead of fighting them. The Windows guard has no such check; the
   interference test showed why the Mac one needs it.

On failure: print `E7GUI_MOUSE_PAUSED`, wait up to 10 s, then resume with
`MouseRecheckRequired` (look again before acting) or stop. Never wait while a
button is held; a held drag stops immediately. Same contract and messages as
`WindowsMouse.guard`.

### Capture

- `SCScreenshotManager.captureImageWithFilter` with
  `SCContentFilter(desktopIndependentWindow:)`, `showsCursor = false`, at the
  window's `pointPixelScale`.
- Crop the title bar. It measured 32 pt (64 px) on macOS 26.6; measure it as a
  uniform band rather than hard-coding it.
- **Require a 16:9 game area** (±0.035) and hand it to `normalize_game_frame`
  unstretched, like the other 16:9 clients. At full size the game area is
  2.015 : 1, which the stretched native path (16/9…2.0) refuses. The window
  resizes freely, so the GUI tells the player the exact size to set
  (for example 1680 × 977 pt: a 1680 × 945 game area plus the title bar) and
  refuses to start otherwise. `native_stove` stays False.
- Blank or wrong-size capture: look once more, then stop (existing rule).

### Input

- Map 1920 × 1080 game space → content rect in **global display points**
  (top-left origin; correct across displays).
- Glide the pointer with `kCGEventMouseMoved` events along the existing
  `pointer_glide` path, then verify with `CGEventGetLocation`. If it isn't on
  target within 3 pt, no click.
- Click: `LeftMouseDown`, hold ~80 ms, `LeftMouseUp`, all via
  `CGEventPost(kCGHIDEventTap)`. Guard before down; after up, never retry
  (input already delivered).
- Drag: down → `LeftMouseDragged` along the glide → up, guarding each step
  with `held=True`. **Untested on the iPad app**; the shop list scroll depends on it.
- Leave the pointer where the last action put it, like Windows Mouse mode. The
  probe's put-it-back behaviour is not adopted: it fights a user who is moving.
- Forced termination: post `LeftMouseUp` at the current location (the
  `release_native_button` equivalent).

### OCR

Confirmation checks need word boxes (`read_ui_text`, `read_confirmation_text`).

- **First:** Tesseract (`brew install tesseract`), the backend Linux already
  uses with its tested thresholds. `ocr_backend()` already selects it on every
  non-Windows platform, so no change is needed. The launcher's `check` must
  report Tesseract when it's missing.
- **Later, optional:** Apple Vision (`VNRecognizeTextRequest`) needs no install,
  but its boxes are per line, not per word. It would need its own entries in
  the `test_e7_ocr_backend` checks and the frame corpus before replacing Tesseract.

### Stop key

A `MacStopKey` beside `WindowsStopKey`/`X11StopKey` in `stop_key_monitor()`:
a listen-only `CGEventTap` for key-down on its own run-loop thread. It needs
**Input Monitoring** permission. If the tap can't be created, refuse to start
(as Wayland does), because the Stop key is a safety control.

### GUI, launch, packaging

- `CONTROL_MODES` on macOS: one mode, shown as *Mouse · macOS iPad app, takes
  over your pointer*. Launch with `--macos-session`, plus `--dry-run` like
  Background.
- `e7-shop-refresh-macos.sh` (setup / run / check), modelled on the Linux
  script, plus `requirements-macos.txt`: numpy, opencv-python-headless,
  Pillow, `pyobjc-framework-{Quartz,ScreenCaptureKit,Cocoa,ApplicationServices}`.
  Use python.org or Homebrew Python with Tk 8.6. Apple's `/usr/bin/python3`
  (3.9, Tk 8.5) is not supported.
- `e7_process.launch_engine` already has a POSIX path. Forced stop must also
  release the mouse button (above).

### Permissions

| Permission | Why | Checked at start |
|---|---|---|
| Screen Recording | capture | `CGPreflightScreenCaptureAccess` |
| Accessibility | posting input events | `CGPreflightPostEventAccess` / `AXIsProcessTrusted` |
| Input Monitoring | global Stop key | event tap creation |

macOS charges these to the *responsible* app: Terminal when launched from
Terminal, or a packaged `.app` later. Any missing permission refuses the
start with exact System Settings steps. Never send partial input.

## Phases and gates

Each phase ends with evidence. Automated checks, live game checks and any
spending are separate gates (AGENTS.md).

0. **Recognition on Mac frames (no input).** The owner navigates by hand. The
   probe captures lobby (menus shown and hidden), Secret Shop pages 1 and 2,
   and the refresh and buy confirmation dialogs (cancelled by hand, nothing
   bought). Add them to the private frame corpus as client `macos-ipad`, then
   run `check_frame_corpus.py --variants`. Also try resizing the window to
   16:9 and record what the app allows. **Gate:** every label passes, or the
   aspect handling is redesigned before any code.

   *Run 1 (2026-11-17, full-size window, 2.015 : 1):* 17/30 checks passed.
   - Passed: refresh and buy dialog OCR (Tesseract 5.5.4, all tint variants),
     and lobby-hidden.
   - Failed: every shop frame, and the untinted lobby-shown frame.
   - Cause: the stretch to 16:9 compresses the frame ~12% horizontally. With
     true proportions the shop title matched at 0.981 and the lobby icon was
     found, but the Refresh label sits further right in the wider layout,
     outside its search box.
   - Next: repeat the capture with a 16:9 window.

   *Run 2 (2026-11-17, 16:9 window, 671 × 408 pt, game area 1342 × 752 px
   = 1.785 : 1):* **30/30 checks passed** with all tint variants: lobby shown
   and hidden, all four shop frames, refresh dialog, and the hero buy dialog
   rejected for every currency item. The 16:9 layout matches the PC clients
   (Refresh at bottom-left). Run 1's labels were taken out of the corpus
   because the mode refuses that window shape; its images are kept.
   **Gate passed**, with these coverage gaps:
   - No Covenant, Mystic or Friendship row was on offer, so positive purchase
     recognition and a currency confirmation dialog are untested on Mac.
   - Only one 16:9 size was tested (a small one, upscaled 1.43×).
1. **`MacMouse` + fakes.** Transport, guard and coordinate mapping with fake
   capture/input/window-list back ends, in the style of `test_e7_mouse_refresh.py`.
   Full test suite passes on macOS and still on Linux. Codex review round.

   *Status (2026-11-17):* `e7_macos.py` and `test_e7_macos.py` written; after
   a /code-review round (10 findings, 9 fixed), 39 new tests pass. The title
   bar measured 64 px on all 20 real captures. Kept Mac-only by the owner's
   choice: no shared file is changed. The fractional-point glide fix lives in
   `e7_macos.py`, not in the shared `pointer_glide`.
   Full suite on macOS: 377 tests, the same 9 pre-existing
   failures as the baseline run without these files (7 GUI modules need
   Tk, plus one Windows-only test and one `/private/var` path test). Not yet
   done: a Linux suite run, the Codex review (`codex-review` isn't installed
   on this Mac), and any live use of `QuartzBackend`.
2. **Stop key, OCR backend, GUI mode, launcher, permission checks.** Tests for
   each; GUI smoke test on the owner's desktop, coordinated with the owner.

   *Status (2026-11-17):* written; 60 macOS tests pass, including a real
   keyboard-tap start/stop.
   - New Mac-only files: `e7_macos_stop_key.py` (listen-only tap; Input
     Monitoring), `e7_macos_refresh.py` (`--macos-session`, dry run,
     Tesseract check), `e7-shop-refresh-macos.sh`, `requirements-macos.txt`,
     `test_e7_macos_stop_key.py`, `test_e7_macos_session.py`.
   - Shared files, each change only for macOS or Mac mode:
     - `E7ADBShopRefresh.py`: the `--macos-session` switch.
     - `e7_stop_key.py`: the macOS branch in `stop_key_monitor`.
     - `e7_shop_refresh_gui.py`: a "Mac" mode with its own texts and scan
       (`list_mac_games`), the launch arguments, a pointer-run treatment
       (graceful STOP, button release via `e7_macos`, no always-on-top
       tracker), and the macOS Stop-key modifier mask.
     - Shared tests that assumed "not Windows" means Linux: a
       platform-aware default mode, `e7_macos` excluded from the Windows
       package list, the Num Lock test skipped on macOS, and two "Linux
       only" X11 Stop-key tests that now also skip on macOS.
   - The game is brought forward once at start (app activation, not a
     click), as WindowsMouse does.
   - Full suite on macOS: 602 tests, only the 5 pre-existing failures (the
     `/private/var` path test and four Windows folder-default tests).
   - Tk here is 9.1 (Homebrew), not 8.6.
   - GUI smoke test (2026-11-17, owner present, `E7_DRY_RUN=1`): only Mac
     mode offered; Scan found the game; Start brought it forward, then
     refused the 1920 × 1050 window at the 16:9 check. The session log has
     no input events. It also exposed wrong size advice (1863 × 1080, taller
     than the window could go). The advice now only shrinks one side of the
     current window (here 1809 × 1050), so it always fits.
   - `E7_DRY_RUN=1` in the GUI's environment passes `--dry-run` to Mac
     sessions (navigation only).
   - Not done: a Linux run.
3. **Live dry run.** Navigation clicks only (open shop, reveal home controls).
   Scrolls run; refresh and buy are blocked and logged. Owner present.
   Checks drag on the iPad app.
4. **Live minimum run.** Budget 3 (one refresh), owner watching. Then the
   `SOAK-0.2.4.md` style: several short runs, then a full run, each recorded.

Phase 0 needs nothing built and decides whether the rest is worth doing, so it
comes first.

## Open questions

1. ~~Can the window be resized?~~ Yes, freely. Still open: how does the game
   lay out in a 16:9 window (letterboxed or filled), and does it keep that
   size across restarts?
2. Title bar: 32 pt on macOS 26.6, so it must be measured, not assumed.
   Full-screen mode (no title bar, own Space) is untested.
3. ~~Multiple displays?~~ Tested 2026-11-17 with the game on a second
   monitor (LG HDR 4K, right of the main display) and Claude active. Capture
   works. A system-wide click on the inactive game **only activated it**: it
   took focus from Claude and the game did not react. A second, identical
   click with the game active revealed the lobby menus. So a second monitor
   works, but each click from an inactive state is swallowed by activation
   and steals focus; the mode keeps requiring the game to be active. Stage
   Manager and Spaces are still untested.
4. Does the iPad app accept a mouse drag as a list scroll, and at what speed?
5. Packaging: Terminal launch first, a signed `.app` later? Permission grants
   follow the app identity, and the Claude Code helper's grants used by the
   probes are tied to its version path.
6. ~~Reuse `native_stove` for its aspect allowance?~~ Not needed with a
   16:9 window.

## Risks

- **Window shape.** At full size the game area is 2.015 : 1 and the engine
  refuses it. A 16:9 window avoids stretching. If the player changes the size
  mid-run, the existing "viewport changed" stop applies.
- **Pointer takeover.** The user can't use the Mac during a run. The idle guard
  pauses rather than fights, but a click the user makes during an action still
  reaches the game. This is the same limitation as Windows Mouse mode, and the
  GUI text must say so.
- **Silent input loss.** macOS drops posted events without an error when
  Accessibility is missing or revoked. That is why every action is followed by
  an observed screen change, as the shared flow already requires.
