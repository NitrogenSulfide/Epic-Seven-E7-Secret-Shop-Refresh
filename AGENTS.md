# Purpose

This is the Windows E7 Secret Shop Refresh GUI project. It preserves Solunium's
upstream source history and adds NitrogenSulfide (Blue Natto)'s GUI and release work. It is
separate from the native OldUnreal UT2004 workspace.

# Working boundaries

- Preserve the upstream GPL-3.0 licence, notices, authorship and Git history.
  Keep the upstream README under docs/UPSTREAM-README.md.
- Maintain source here. Treat the old General/scripts copy and extraction
  backups as recovery material; compare current files before any later migration.
- Installed engine binaries, emulator state, settings and history are external
  runtime data. Never commit personal INIs, device identifiers, history or logs.
- Do not launch the real engine, ADB sessions or calibration, or spend game
  currency, without an explicit request for those live checks. Use fake engines
  and temporary files for automated tests.
- Restrict process management to processes owned by this GUI session. Do not
  terminate unrelated game, emulator, ADB or launcher processes.
- Coordinate GUI tests that require the user's desktop. Do not silently take
  mouse/keyboard focus. Inspect screenshots for any visual change; mark missing
  visual evidence incomplete.
- Retain the supplied icon as requested by the owner on 2026-10-03. Preserve its
  origin and credit record. Do not claim the owner owns third-party artwork or
  that credit establishes redistribution rights. Do not replace the icon automatically.
- Keep sound credits and asset provenance. The software GPL licence does not
  relicense third-party artwork or audio.
- Use ignored .local-state/ for local receipts and scratch/ for experiments.
  Keep generated packages under ignored dist/. Do not install software,
  retarget desktop shortcuts, change the installed engine, push, or publish as
  part of ordinary source preparation.

# Model and review

Respect the user's selected model and reasoning effort. Machine-specific Codex
configuration remains ignored. Helper agents are opt-in.

Claude is the primary agent: it plans, edits, builds and tests. Codex is a
read-only second reviewer and edits only when the user starts Codex directly
and asks it to, under the same rules. For code changes Claude runs
`codex-review` (or `codex-review SINCE`), judges each finding independently,
and reports which were accepted or rejected and why; one round per change.
Skip it for docs-only and trivial changes.

Invoke an independent reviewer when the user requests release-candidate review.
Record the comparison-base commit, candidate commit and exact package SHA-256s.
Report concrete blockers with source lines/package members, reproduction and
evidence, and list incomplete checks separately. The reviewer must not edit,
deploy, merge or publish.

Automated checks, independent review, live-engine/game verification and
publication approval are separate gates. Approval names the exact package and
destination. Never push to Solunium's upstream repository.

# Local artifact retention

Keep the current version plus five previous distinct versions as complete local
packages. Preserve compact iteration notes, source/evidence, screenshots, logs,
package receipts and SHA-256s for older versions. Follow docs/LOCAL-RETENTION.md
and the General/scripts/e7_release_retention.py preview/archive workflow after
verified releases. Review the exact payload deletion scope before pruning;
never delete source Git checkouts, generic workspace recovery snapshots, shared
fixtures, installed runtime data or held versions automatically.
