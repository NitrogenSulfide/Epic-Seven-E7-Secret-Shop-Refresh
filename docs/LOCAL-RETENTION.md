# Local release retention and folder layout

Keep the current version and five previous distinct versions as complete local
packages. Sort semantic versions and numeric release candidates, not folder
timestamps. Multiple build variants of a held version remain held; newer
candidates are also protected. At 0.1.2 this holds 0.1.2, 0.1.1, 0.1.0,
0.1.0-rc51, 0.1.0-rc50 and 0.1.0-rc49.

Preserve the Git history, release/change notes, provenance, screenshots,
verification logs, package receipts and exact SHA-256s of older iterations.
Older compiler output, complete runtime bundles, release ZIPs and extracted
test copies can be pruned after their compact evidence archive is verified
and deletion is approved. The evidence archive cannot restore complete binary
builds. Private screenshots, settings and recovery records stay private.

## Folder map

- Repository root: maintained application source and tests.
- `release/`: public release notes, setup and build documentation.
- `dist/candidates/`: complete held release packages and build payloads.
- `.local-state/retention/<UTC stamp>/iterations/`: readable older iteration notes and receipts.
- `.local-state/retention/<UTC stamp>/iteration-evidence.zip`: deduplicated older source, assets and evidence.
- `.local-state/retention/<UTC stamp>/manifest.json`: every archived original path, size and SHA-256, mapping preserved files to ZIP members.
- `.local-state/`: private local verification receipts, fixtures and build environment.
- `scratch/legacy/initial-recovery/`: original extraction and GUI recovery copies.
- `scratch/experiments/mouse-ux/`: Mouse test and inspection helpers.
- `scratch/experiments/maximized-hotfix/`: maximized-client hotfix experiment and publication receipts.
- `scratch/demo/`: E7 demo preparation and recordings.
- `scratch/release-tests/`: extracted engine/GUI, fresh setup and player setup tests; Japanese paths are retained for Unicode-path coverage.
- `scratch/legacy/source-checkouts/`: historical Git source snapshots, held independently from binary retention.

The old General E7 scratch locations are compatibility directory junctions
to their new homes, preserving existing scripts and references without making
second copies. Their moves are recorded in `.local-state/organization-20261005.json`.
General's `scratch/release-organization/` still contains historical helper
scripts, source bundles and workspace-wide recovery snapshots, plus directory
links to the organized E7 tests and source snapshots. Its version-labelled E7
test folders participate in retention through those links; generic workspace
recovery ZIPs, source repositories and bundles are held separately and never
automatically pruned.

## Commands

Run from this checkout after completing and verifying a new release, outside the
build itself. The helper lives in the parent workspace's `scripts` folder.
Nothing runs on a timer, and a failed build never triggers cleanup.

```powershell
# Preview only (default).
python ..\scripts\e7_release_retention.py --project . --previous 5

# Prepare and verify private history; delete nothing.
python ..\scripts\e7_release_retention.py --project . --previous 5 --archive-only

# After reviewing and approving the exact deletion scope.
python ..\scripts\e7_release_retention.py --project . --previous 5 --apply
```

The helper refuses nested Git checkouts and reparse points in cleanup targets,
checks running process paths, hashes each original file, verifies every retained
archive object and rechecks target inventories before pruning. It never stops
applications or touches installed engine, emulator or game data.

To recover an evidence file, find its original `path` in `manifest.json` and
extract its `evidence_member` from the ZIP. The member name is based on the file's
SHA-256; verify it against `sha256` and restore into a new recovery folder. A
null `evidence_member` identifies a compiled/runtime/archive payload whose bytes
were not retained. Source Git repositories and workspace recovery bundles remain
available separately.
