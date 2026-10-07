# Experimental session cleanup: 0.1.3-rc2

Branch: `work/session-performance-cleanup`, based on `5c61883`.
Historical development notes for the local rc2 trial. These changes are included
in v0.1.3; current release behavior is described in release/NOTES-0.1.3.md.
The offline evidence and outstanding rendering findings below describe that trial.

## Corrections after the first trial

The repository's GitHub Issues setting was disabled, causing the bug-report
URL to return 404. Issues was enabled on 2026-10-05, and the anonymous report
URL was verified to return HTTP 200 after redirecting to GitHub sign-in.
No issue or release was submitted.

Clam ignored the first trial's `sliderthickness` configuration. The timing
control now uses an image element with a real 32-pixel thumb/trough height
at 100% scale, multiplied by the app's DPI scale. Synthetic Tk pointer events
on an unshown desktop verified dragging from 0.03 to 0.08 seconds.

The coffee button now has five pixels of left padding, west alignment and
ten pixels between image and text at 100% scale. The icon moved left within
the button, while the label keeps its position. Its artwork is unchanged.

The corrected source passed 120 GUI/window tests and all 22 layout cases.
Final light/dark previews are under `scratch/session-cleanup/rc2-final-preview`.

## Changes to try

- Header: By Blue Natto subtitle, version link, blue GitHub profile button moved
  out of About, and blue bug-report button. The report opens a GitHub draft
  prefilled with version and control mode; it sends no report automatically.
- Taller timing slider and a shared two-second upper bound for tap delays,
  including randomized samples. The ordinary default remains 0.3 seconds.
- Excel export includes the entire saved history, while the main table displays
  the latest 25 sessions. Columns include UTC start time, control mode, outcome,
  reason and counters; totals are numeric Excel formulas with cached values.
- Session recording happens once for completion, cooperative Stop or failure.
  Mouse and the matching ADB engine share interruptible pacing and stdin Stop.
  The GUI gives bounded capture/OCR cleanup up to 12 seconds before forcing exit.
- Old CSV rows retain their counters, unknown columns and extra fields. Migration
  saves the original bytes under `ShopRefreshHistory/schema-backups` before
  atomically replacing the history file. Legacy timestamps/outcomes are not invented.
- Scenery is tinted once, resizes use a cheaper filter, and repaint requests are
  throttled. Position-only window moves skip scenery redraws.
- Settings/protocol, timing, history/export and product links are separate modules.
  Attention and pause reasons remain visible in condensed layouts.

The supplied app icon and existing coffee design are retained. Coffee-button
spacing is slightly tighter; a new themed design still needs the owner's review.
Friendship purchases and red-equipment detection remain outside this experiment.

## Offline evidence

Checks used fake engines, synthetic images and temporary settings/history. The
GUI ran on an unshown Windows desktop without switching the user's desktop,
activating a game, running ADB, moving their pointer or spending game currency.

- 76 focused tests passed, with two private-image fixture checks skipped.
- 121 shared-flow and Mouse tests passed. OpenCV used one thread only in this
  test process; production thread settings are unchanged.
- 120 GUI/window tests passed and 22 ADB/Mouse layout cases had no reported
  clipping or overlap problems, spanning 1080p through 4K and DPI scales 1–3.
- Independent openpyxl loading verified a 30-session export, numeric spending,
  SUM formulas/cached totals, frozen headers and literal formula-like reason text.
- Light/dark 1500 × 940 screenshots were inspected using background PrintWindow
  captures. Earlier incomplete screenshots were a capture limitation resolved by
  the full-content capture flag; they are not the final visual evidence.
- A controlled three-render comparison against the base renderer measured a
  median 96.63 ms versus 78.69 ms for full redraws, about 19% less elapsed time.
  A position-only move caused four base redraw calls and zero candidate calls.
  This measures rendering work, not a guarantee of subjective live smoothness.

Detailed local logs, screenshots, benchmark code and generated workbook are
under ignored `scratch/session-cleanup/`. Package receipts and checksums belong
under ignored `dist/candidates/`.

## Still needs a supervised trial

Rendering follow-up is paused at the owner's request on 2026-10-05. Their video
showed black/unpainted regions and stale layout during resizing, plus delayed
theme repaint. An offline 3840 × 2020 redraw benchmark measured a median
394.66 ms, compared with 78.69 ms at 1500 × 940. The current renderer prepares
artwork and uploads per-widget crops on the UI thread. Investigate cached theme
images, background image preparation and fewer redraws during resizing when
work resumes. No further rendering implementation changes were made.

Live Mouse/ADB behavior with the new matching engine, Stop during a real session,
perceived resize/theme smoothness on the visible desktop, and a real Excel UI
opening the export are not verified by the offline checks. Existing recognition
thresholds, purchase confirmation rules and input/focus guards are preserved.

Extract the trial ZIP into a fresh folder and use its bundled runtime. Keep the
current installation as-is. Use a copy of existing history if you want to try
migration/export before running a session.
