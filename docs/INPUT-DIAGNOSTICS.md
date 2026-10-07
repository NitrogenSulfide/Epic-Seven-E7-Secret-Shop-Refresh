# Optional click and timing diagnostics

Version `0.1.3` adds a
**Log click coordinates and timing** checkbox in Diagnostics. It defaults off,
persists in the local GUI preferences, and is locked during a session. It works
in normal Mouse and ADB sessions independently of ADB calibration. Calibration
still has its original manual pauses and fixed tap timing.

## Reading the log

Clicks report an action name, unrandomized anchor, final coordinates and applied
offset in the normalized **1920 × 1080 recognition frame**. The applied offset
is recorded after the existing action-specific scaling and button bounds.
Refresh therefore has a smaller range than Buy. Mapped screen/device pixels
show the actual rounded input destination; screen pixels may be negative on a
monitor left of the primary display. These are coordinate spaces, not a
requirement to set the user's monitor to 1920 × 1080.

`input sent` is logged after the transport call succeeds. It does not prove
that the game accepted the action; the existing fresh confirmation and shop
return checks still establish that. Failed/blocked attempts are labelled and
retain their original exception behavior. Home reveal/shop-entry clicks have
no randomized offset. Drag paths retain their existing Mouse input output;
the detailed anchor/offset events in this version describe clicks.

Tap pacing reports the baseline, sampled/requested delay and elapsed wait.
Elapsed time comes from the engine's monotonic clock, not when the GUI displays
the message. Fixed inventory/scroll settling waits are labelled separately.
The complete time between clicks also includes captures, OCR, pointer travel,
game animations and retries. The final sampled delay retains the existing
two-second cap. Logging never requests an extra random sample or changes waits.

A complete cycle is the interval between two verified refresh completions.
It includes inventory settling, both page scans, scrolling, any purchases and
the following refresh/confirmation. The first interval is labelled **Initial
scan**, and the final budget-exhausted inventory check is labelled **final
scan**. Stop/failure produces an **interrupted** interval. Confirmation and
visibility retries are counted; the count is not every OCR call. Focus-pause
time is included in the total and reported separately.

## Storage and compatibility

Mouse session logs remain in `runtime/mouse-session-logs`; ADB sessions with
tracing save under `runtime/input-session-logs`. Logs are local and excluded
from source control and release packages. Copy Diagnostics copies the currently
retained readable output; it does not automatically send a report.

Engine trace output is capped at 512 KiB per session with a visible limit
notice; each saved session log is capped at 2 MiB. The normal session/history
continues after a limit. The GUI already bounds its retained output. Earlier
logs are not deleted automatically.

Use the matching portable GUI/engine. Tracing settings are optional in the
structured ADB/session JSON, and older engines retain compatible launch inputs.
New engines acknowledge tracing at startup; the GUI shows a notice when the
engine does not acknowledge it. No private frame images are added by tracing.

## Verification

Use `test_e7_input_trace.py` and the existing session, shared-flow, Mouse and GUI
tests with fake inputs. In particular, compare seeded actions, purchase counters
and the final RNG state with tracing enabled/disabled in both transports. Check
blocked input, Stop-interrupted waits, coordinate mapping on a left monitor,
clamped offsets, delay capping, initial/final intervals, split protocol records,
preference persistence and both size limits. Inspect light/dark Diagnostics
screenshots on an unshown desktop. These checks do not replace a supervised
live session with the matching packaged engine.

### Development verification (2026-10-06)

- 147 GUI/window/connection/elevation checks passed on an unshown desktop.
- 154 action/timing/history/navigation checks completed: 152 passed and two
  private-image fixture checks were skipped.
- 22 layout cases passed. Light/dark Diagnostics screenshots were inspected;
  the checkbox uses the existing themed checkbutton style.
- Seeded normal Mouse/ADB fake runs produced identical actions, counters and
  final random-generator states with detailed logging enabled and disabled.
- Automated checks used fake inputs. Separately, the owner reports passing live
  Mouse and ADB regressions with the matching rc3 package. Saved evidence includes
  a completed 399-Skystone Mouse run and an ADB run stopped at 81 Skystones.
  Calibration and insufficient-currency stopping were not live-tested for this release.

Evidence is in ignored `scratch/input-trace/`; packaged checks are recorded with
the candidate artifacts separately.
