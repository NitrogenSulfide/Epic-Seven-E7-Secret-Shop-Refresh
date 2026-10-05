# Experimental session cleanup: 0.1.3-rc1

Branch: `work/session-performance-cleanup`, based on `5c61883`.
This is a local trial, not a published release or an installed-runtime update.

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

Live Mouse/ADB behavior with the new matching engine, Stop during a real session,
perceived resize/theme smoothness on the visible desktop, and a real Excel UI
opening the export are not verified by the offline checks. Existing recognition
thresholds, purchase confirmation rules and input/focus guards are preserved.

Extract the trial ZIP into a fresh folder and use its bundled runtime. Keep the
current installation as-is. Use a copy of existing history if you want to try
migration/export before running a session.
