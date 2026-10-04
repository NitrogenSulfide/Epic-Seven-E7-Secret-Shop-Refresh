# Release checks

## rc46 STOVE purchase confirmation width

The saved Covenant Bookmarks dialog has a 455-pixel-wide green action button
at the normalized 1920×1080 size. The old 450-pixel maximum excluded it even
though local OCR correctly read the intended item and 184,000 gold price.
Allow up to 500 pixels only for purchase-confirmation buttons; keep list and
refresh limits unchanged. Verify the private failed crop at multiple sizes,
both currency confirmation flows, wrong-item rejection and oversized rejection
with mocked input. This fix does not claim a new live purchase check.

## rc45 home controls across wallpapers

Windows OCR read the bright field home's Secret Shop caption as `secietshop`.
Recognize the native Sanctuary, Secret Shop and Epic Pass symbols as a group,
using their edges, relative positions, scale and foreground brightness. The
shop point comes from its observed symbol. All three must be visible; hidden,
dimmed, missing or ambiguous groups fail. Fresh controls are recognized before
input. Preserve label/component fallback for other skins. Check actual portrait
and bright-field captures at four sizes with caption OCR disabled, negative
frames and the frozen saved-frame CLI, plus Google viewport/navigation fixtures.

## rc44 native OCR descender

The live STOVE capture at the owner's display scale read `secr.et shoo`.
Permit that specific Shop descender error only in the existing home context;
Mouse still requires the observed icon and fresh target agreement. The actual
source home-entry check succeeded from hidden controls with one reveal and one
shop icon click, no refresh/purchase/spending. Check compiled saved failing
frames, extracted fixtures and Google regression frames before owner handoff.

## rc43 Mouse home menu after reveal

Re-recognize the observed home icon on a fresh frame before clicking; compare
target positions rather than animated wallpaper pixels. A built-in native
question-mark mask can identify the icon despite neighboring bright artwork;
other skins retain the observed-component fallback. Joined SecretShop OCR is
accepted in the same guarded home context. Template menu captions must also
resolve to a visible icon. Save a private left menu crop plus OCR on failure,
excluding the account/currency header and all personal release data. Check
joined labels, bright fragments, changing artwork, disappearing controls,
source/package saved STOVE and Google frames, and compiled offline home checks.

## rc42 idle Mouse home controls

When no shop or home menu is recognized, Mouse startup may send one center
click on a stable artwork-only game view. Full-frame OCR must find no readable
controls on both captures; blank/loading images fail the texture checks.
This probe does not establish that the game is home. Require observed home
menu recognition followed by shop verification before any refresh/purchase.
Never repeat the reveal probe during the same startup attempt. Test actual
saved STOVE artwork without a private reference, visible dialogs, changed
frames, no-controls timeout and the existing saved Google navigation fixtures.

## rc41 STOVE home entry

STOVE reframes its home artwork when the client aspect ratio changes. The saved
private hidden-home reference now permits bounded affine alignment, requiring
broad feature agreement and matching brightness across most of the image.
Popups, dimmed dialogs, blank captures and changed pages must fail. References
remain private and never go into player/source ZIPs. Check real saved STOVE home
frames at several sizes, the one-reveal/one-shop-entry sequence with mocked
input, unknown-screen rejection, and the existing Google viewport fixtures.

## rc40 app cleanup

The app exposes ADB and Mouse only. Saved Mouse preview preferences load as
Mouse without starting a session; offline frame-analysis tooling remains in
source. Calibration and normal ADB inventory both contain only Covenant and
Mystic items. Legacy history and reserved protocol counters remain readable.

Quickstart, release notes and the first-release tested-client notice are local
About & Credits content. Include CHANGELOG.txt and original official black/white
GitHub icon assets in the player ZIP. GitHub and Ko-fi open only on button clicks.
Keep the settings canvas decoration outside the controls' scrollregion. Check
expanded/collapsed help, both themes, smaller displays and popup tab readability
using fake sessions. No new live game run is required for this GUI cleanup.

The player ZIP supplies the compiled GUI with Python/Tk/Pillow, external artwork,
matching engine and source, upstream ADB tools/templates/notices, and a portable
runtime configuration. The full Source ZIP is an optional developer download.
Follow [AGENTS.md](AGENTS.md), [UPSTREAM.md](UPSTREAM.md) and [SETUP.md](release/SETUP.md).
Preserve original history, licence/credits, installed runtimes and private data.

## Build and automated checks

Build only from a clean exact commit with an explicit private Python environment
using engine-build-requirements.txt. Preserve earlier outputs:

```powershell
.\.local-state\engine-build-venv\Scripts\python.exe -m unittest test_e7_window_preview test_e7_connection test_e7_shop_refresh_gui.ProtocolTests test_e7_engine_location test_e7_live_engine test_e7_shop_navigation test_e7_setup -v
.\build_release_assets.ps1 -BuildPython .local-state\engine-build-venv\Scripts\python.exe -OutputDirectory C:\absolute\new\candidate-directory
```

Record commit, comparison base, dependency/compiler inputs, member hashes and
final player/source SHA-256s. Component ZIPs/manifests/logs stay private. All
builders refuse existing output directories. Build instructions for an extracted
source archive are in [BUILDING.md](release/BUILDING.md) and [ENGINE.md](ENGINE.md).

## Package boundaries

Use the GUI and engine builders' explicit file lists. Include only tracked
artwork/source and tracked upstream adb-assets; never copy an installed runtime.
Generate engine-location.ini with exactly [engine] and directory = runtime.
Generate runtime/E7ADBShopRefresh.sha256 from the matching rebuilt binary.
Omit historical CMD/PowerShell/C# launchers from the player ZIP; its only player
entry point is the compiled GUI EXE. Preserve those files in source history.

Exclude personal INIs, devices, logs/history, setup-captures, mouse-previews, gui-navigation,
private images/evidence, .git, .local-state, scratch, virtual environments and
caches. Keep GPL, upstream authorship, asset provenance, ADB notices and bundled
Python/Pillow/PyInstaller/Tcl/Tk dependency licences. Inspect all source-archive
members for private data. Never change reviewed ZIP bytes in place.

Generic English label crops under adb-assets/builtin-navigation are public assets;
their provenance/dimensions/hashes must be inspected. Full screenshots and saved
gui-navigation calibration remain private. Verify a fresh folder with no personal
references can use the built-in set, without writing calibration. Unknown or
ambiguous screens must not cause guessed navigation or spending. Recognition
failure must stop the engine and offer setup; Stop/stale output must not start
another engine or bypass an explicit Start after setup.

## Extracted and GUI checks

Verify the selected-device preflight with fake ADB replies: no devices, offline,
unauthorized, a different device, connect/recheck success, missing ADB and timeout.
Failures must show an actionable red banner, keep Start retryable, and launch no
engine or recognition helper. Stop/close must invalidate pending start results;
stale scans must not overwrite newer results. Idle rescans must not replace an
edited address when the device list is unchanged. Never kill the ADB server.
Also test a connected Google Play background VM with its window closed, a visible
window on the Android launcher, activity history mentioning Epic Seven, and an
open window with the game resumed. Only the last is ready. Google window checks
must not impose a Google-specific title requirement on other emulator models.
Never persist the full Android activity dump, which can contain unrelated apps.

Verify ZIP integrity, member hashes/allowlists, required files/document links and
extraction/portable configuration in paths with spaces/non-English characters.
Run the compiled GUI --verify with a JSON verification report under a PATH
without Python/py/pyw. Require frozen=true, Pillow/artwork/Tcl support and the
included runtime path. This creates no GUI window and makes no ADB/game calls.
Run the actual engine's offline --verify and synthetic reference preparation.

Coordinate full fake-engine GUI tests and layout/visual checks on an isolated
desktop where practical. Cover Start, Stop/key capture, per-action counters,
themes/scenery, credits and first-use setup. Record partial/missing visual
evidence honestly. Fake runners must prove setup sends only screenshot commands,
never launches refreshing, preserves old calibration on failure/success and
rejects a mismatched setup-engine binary. A separate explicit Start is required
after setup. Fresh normal tests use 12 skystones, 0.3 seconds, backtick and random
offsets; alternate-input/calibration fixtures are explicit exceptions.

## Review, live game and publication

rc29 introduces real native STOVE Mouse input around the shared loop. Test the
selected EpicSeven.exe process, coordinate mapping, single-batch clicks, wheel
scrolling, focus/geometry loss, Stop between actions, same-item/price confirmation,
changed dialogs, insufficient-currency rejection and a 12-skystone/four-refresh
fake run. Verify Windows OCR on synthetic dialog frames and compiled offline CLI
checks. Actual confirmation layout, pointer input and spending require a separate
authorized live trial. The optional preview remains read-only.

rc30 adds interior visibility sampling and exact-target checks, bounded focus
pauses, typed native stop reasons and private session diagnostics. Test saved
English home frames with Windows OCR, native menu word bounds and constrained
OCR spelling variants. Check that a private hidden-home reference permits one
reveal click, while unrelated pages or a changed popup receive none. Verify Stop
during a focus pause and cancellation of stale prepared clicks after focus returns.

Test selected-window capture with fake Win32
metadata and a fake grabber: changed identity, focus, geometry, obstruction,
aspect ratio, blank images and negative monitor coordinates. Confirm cancellation,
stale-result handling, mode switching and the offline-only engine command.
Also check maximized STOVE dimensions with symmetric black side bars, top/bottom
bars, exact cropped screen coordinates and recognition on the resulting image;
preserve the full client view for other shapes, colored chrome or asymmetric
borders. Native wide frames and hidden home controls must yield a preview,
not an aspect-ratio error. The displayed image must keep its proportions and
map normalized annotations back to that image correctly. Original client
captures remain private runtime data.
Verify readiness waiting without activation/input, timeout, cancellation while
waiting/grabbing and stale-result handling. A delayed user focus change must
continue to the read-only preview; Stop/close must prevent a waiting capture.
Use saved frames to check annotations. Actual Google Play/STOVE capture remains
a separate user-run check. Do not claim verified live refreshing support until
window/process identity, focus-loss stops, purchase confirmation and budget/stop
behavior have been implemented and verified for the exact candidate.

Automated tests, independent review, live-game checks and publication approval
are separate gates. Give a requested independent reviewer the exact commit/base,
every proposed package hash/member list and evidence. It reports concrete
blockers and incomplete checks; it does not edit, deploy, merge or publish.
Earlier package verdicts never clear a newly built candidate.

Real ADB/device/game checks require an explicit live-check request and agreed
budget/scenario. Bind evidence to the executable/package hashes and emulator.
Check shop entry, refreshing, live counters, Stop/key behavior and owned-process
cleanup. Do not infer game correctness from fixture tests. Insufficient-currency
live cases remain owner-deferred; do not drain the owner's account or claim a
verified automatic stop for them.

Publication requires separate approval naming the exact packages and destination.
Use NitrogenSulfide (Blue Natto) as maintainer and NitrogenSulfide as GitHub account.
Fork/origin/push/publication are later actions; never push to Solunium's upstream.
General's notes/release-catalogue.md and notes/release-workflow.md remain the local
index and reusable handoff; no extra service or CI system is needed.
