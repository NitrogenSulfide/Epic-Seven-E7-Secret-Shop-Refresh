# Upstream relationship

- Author: Solunium
- Repository: https://github.com/Solunium/Epic-Seven-E7-Secret-Shop-Refresh
- Imported source base: `49313d14b24f1b8efbeb49f9a6b2126f9bbd0849`
- Licence: GPL-3.0; full text retained in LICENSE
- Local fetch remote: upstream
- Local work branch: work/gui-release-setup
- GitHub fork/origin: not created

This checkout preserves the upstream history. Your Windows GUI is added on top;
no upstream engine source was modified during extraction. The original README
is retained in docs/UPSTREAM-README.md.

For 0.1.0-rc4, the maintained ADB engine source is modified to sleep between
stop-key checks, emit flushed per-action counters, and avoid counting interrupted
or failed ADB tap sequences. A new engine candidate is built from this checkout
and supplied with its exact source and [build instructions](ENGINE.md).
It is separate from the previously installed binary described below. Both
candidate hashes and the full source commit are recorded by their builders.

For rc5, legacy fixed shop-entry taps are replaced by template matching against
private user-prepared navigation references. Shop verification gates entry and
shop actions. The engine package includes the navigation module, offline
preparation utility and corresponding tests; game screenshots/reference crops
remain private runtime files and are not bundled.

For rc6, shop markers use brightness-normalized grayscale matching to tolerate
desktop screenshot resampling, while retaining both required markers and the
menu detector. Errors include match scores and distinguish failed verification
from a claim that the shop did not open. This does not change item detection.

The preserved original installation contains an ADB engine executable,
with SHA-256 `79ba2165937a326a3c4bdf2593c5ceee3383f7644f6f302e4266cf8584f35a6b`.
That binary was not rebuilt from the source base above, and its exact matching
source commit has not yet been established. Do not describe this source base as
the binary's corresponding source without verifying it.

The local enhanced candidates use a separately built matching engine and do not
replace that installed executable. rc16 fixes the inherited multiple-device
startup selection loop; the corresponding source/test is supplied with the
player ZIP's `runtime` folder and full Source ZIP. Every new build has its own recorded hashes.

Before distributing a bundled engine, identify/build the exact source version,
retain licence and copyright notices, record modifications and provide its
corresponding source and build instructions. A GUI-only release can require a
separately installed supported engine.

Creating an actual GitHub fork is a later publishing step. Add the owner's fork
as origin and keep upstream for fetching Solunium's updates. Upstream pushes are
disabled in this local checkout. Existing local work can then be pushed to the
fork with its original upstream ancestry intact.
